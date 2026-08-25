import datetime
import io

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoFabrica, Rota, SafraUnidade,
)
from apps.simulacao.planilha import ABA_FABRICAS, analisar, aplicar
from apps.simulacao.tests.planilha_fixtures import montar_pasta
from apps.simulacao.tests.test_planilha_analisar import ARMAZEM_OK, FABRICA_OK, ROTA_OK

PREVISAO_OK = {
    'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 3, 1),
    'recebimento_produtor': 4500.5, 'vendas': 1200.25,
}
SAFRA_OK = {
    'unidade': 'ARMAZÉM A', 'data_inicio': datetime.date(2026, 2, 1),
    'data_fim': datetime.date(2026, 5, 31),
}


def pasta_completa():
    return montar_pasta(
        fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], rotas=[ROTA_OK],
        previsoes=[PREVISAO_OK], safras=[SAFRA_OK],
    )


class AplicarTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')

    def test_bootstrap_cria_o_cenario_e_o_marca_oficial(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial 2026')

        self.assertEqual(cenario.nome, 'Oficial 2026')
        self.assertTrue(cenario.is_oficial)
        self.assertEqual(cenario.cooperativa_id, self.coop.id)

    def test_segundo_cenario_da_cooperativa_nao_e_oficial(self):
        aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Primeiro')

        _, segundo = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Segundo')

        self.assertFalse(segundo.is_oficial)

    def test_grava_as_cinco_abas(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(Armazem.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(Rota.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(
            PrevisaoFabrica.all_cooperativas.filter(fabrica__cenario=cenario).count(), 1
        )
        self.assertEqual(SafraUnidade.all_cooperativas.filter(cenario=cenario).count(), 1)

    def test_rota_aponta_para_as_unidades_criadas_na_mesma_pasta(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        rota = Rota.all_cooperativas.get(cenario=cenario)
        self.assertEqual(rota.armazem.nome, 'ARMAZÉM A')
        self.assertEqual(rota.fabrica.nome, 'FÁBRICA TESTE')

    def test_safra_deriva_o_tipo_e_aponta_para_a_unidade(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        safra = SafraUnidade.all_cooperativas.get(cenario=cenario)
        armazem = Armazem.all_cooperativas.get(cenario=cenario)
        self.assertEqual(safra.entidade_tipo, 'Armazém')
        self.assertEqual(safra.entidade_id, armazem.id)

    def test_reimportar_atualiza_em_vez_de_duplicar(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')
        alterada = montar_pasta(
            fabricas=[dict(FABRICA_OK, estoque_inicial=9999)],
            armazens=[ARMAZEM_OK], rotas=[ROTA_OK],
        )

        aplicar(alterada, cenario=cenario)

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(Fabrica.all_cooperativas.get(cenario=cenario).estoque_inicial, 9999)

    def test_upsert_nao_apaga_o_que_a_pasta_nao_menciona(self):
        _, cenario = aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        aplicar(montar_pasta(fabricas=[dict(FABRICA_OK, nome='OUTRA')]), cenario=cenario)

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 2)

    def test_linhas_rejeitadas_nao_sao_gravadas_e_as_validas_sim(self):
        pasta = montar_pasta(
            fabricas=[FABRICA_OK, dict(FABRICA_OK, nome='RUIM', estoque_inicial=None)],
        )

        relatorio, cenario = aplicar(pasta, cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(len(relatorio.resumo(ABA_FABRICAS).rejeitadas), 1)

    def test_erro_estrutural_nao_cria_cenario_nem_grava(self):
        relatorio, cenario = aplicar(
            io.BytesIO(b'lixo'), cooperativa=self.coop, nome_novo='Nao Deve Existir',
        )

        self.assertTrue(relatorio.tem_erro_estrutural)
        self.assertIsNone(cenario)
        self.assertFalse(Cenario.all_cooperativas.filter(nome='Nao Deve Existir').exists())

    def test_relatorio_de_aplicar_bate_com_o_de_analisar(self):
        pasta = pasta_completa()
        previsto = analisar(pasta, None)
        pasta.seek(0)

        aplicado, _ = aplicar(pasta, cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(aplicado.total_criar, previsto.total_criar)
        self.assertEqual(aplicado.total_rejeitadas, previsto.total_rejeitadas)

    def test_nao_toca_em_cenario_de_outra_cooperativa(self):
        outra = Cooperativa.objects.create(nome='Outra', slug='outra')
        alheio = Cenario.all_cooperativas.create(
            cooperativa=outra, nome='Alheio', is_oficial=True,
        )
        Fabrica.all_cooperativas.create(
            cooperativa=outra, cenario=alheio, nome='NÃO MEXER',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )

        aplicar(pasta_completa(), cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=alheio).count(), 1)

    # -- Correções (a), (b), (c): aplicar precisa escrever exatamente o que
    # analisar prometeu -- ver as três correções descritas no brief da tarefa.

    def test_nome_duplicado_na_planilha_nao_sobrescreve_a_primeira_ocorrencia(self):
        """(a) Fábricas/Armazéns: analisar rejeita a segunda ocorrência de um
        nome repetido na mesma aba -- aplicar não pode gravá-la por cima."""
        pasta = montar_pasta(
            fabricas=[FABRICA_OK, dict(FABRICA_OK, estoque_inicial=9999)],
        )

        _, cenario = aplicar(pasta, cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(Fabrica.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(
            Fabrica.all_cooperativas.get(cenario=cenario).estoque_inicial, 8000,
        )

    def test_rota_duplicada_na_planilha_grava_so_a_primeira(self):
        """(b) Rotas: chave (origem, destino)."""
        pasta = montar_pasta(
            fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK],
            rotas=[ROTA_OK, dict(ROTA_OK, distancia_km=999)],
        )

        _, cenario = aplicar(pasta, cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(Rota.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(
            Rota.all_cooperativas.get(cenario=cenario).distancia_km, ROTA_OK['distancia_km'],
        )

    def test_previsao_duplicada_na_planilha_grava_so_a_primeira(self):
        """(b) Previsões: chave (nome, mes) com mes normalizado ao dia 1."""
        linha = dict(PREVISAO_OK, mes_referencia=datetime.date(2026, 3, 15))
        repetida = dict(linha, mes_referencia=datetime.date(2026, 3, 1), vendas=99999)
        pasta = montar_pasta(fabricas=[FABRICA_OK], previsoes=[linha, repetida])

        _, cenario = aplicar(pasta, cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(
            PrevisaoFabrica.all_cooperativas.filter(fabrica__cenario=cenario).count(), 1,
        )
        previsao = PrevisaoFabrica.all_cooperativas.get(fabrica__cenario=cenario)
        self.assertEqual(previsao.vendas, PREVISAO_OK['vendas'])

    def test_safra_duplicada_na_planilha_grava_so_a_primeira(self):
        """(b) Safras: chave (nome, data_inicio)."""
        pasta = montar_pasta(
            armazens=[ARMAZEM_OK],
            safras=[SAFRA_OK, dict(SAFRA_OK, data_fim=datetime.date(2026, 12, 31))],
        )

        _, cenario = aplicar(pasta, cooperativa=self.coop, nome_novo='Oficial')

        self.assertEqual(SafraUnidade.all_cooperativas.filter(cenario=cenario).count(), 1)
        self.assertEqual(
            SafraUnidade.all_cooperativas.get(cenario=cenario).data_fim, SAFRA_OK['data_fim'],
        )

    def test_safra_reimportada_atualiza_registro_com_entidade_tipo_nao_canonico(self):
        """(c) Uma SafraUnidade persistida com entidade_tipo não canônico
        (ex.: 'fabrica' minúsculo, como em tests/test_models_a11.py e nos
        cenários clonados/legados -- ver services.clone_scenario e
        apps/simulacao/legado.py) deve ser ATUALIZADA, não duplicada, e a
        reimportação deve convergir o valor para o canônico 'Fábrica'."""
        _, cenario = aplicar(
            montar_pasta(fabricas=[FABRICA_OK]), cooperativa=self.coop, nome_novo='Oficial',
        )
        fabrica = Fabrica.all_cooperativas.get(cenario=cenario)
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, entidade_tipo='fabrica',
            entidade_id=fabrica.id, data_inicio=datetime.date(2026, 2, 15),
            data_fim=datetime.date(2026, 6, 15),
        )
        safra_nova = {
            'unidade': 'FÁBRICA TESTE', 'data_inicio': datetime.date(2026, 2, 15),
            'data_fim': datetime.date(2026, 9, 30),
        }

        aplicar(montar_pasta(safras=[safra_nova]), cenario=cenario)

        self.assertEqual(
            SafraUnidade.all_cooperativas.filter(
                cenario=cenario, entidade_id=fabrica.id,
            ).count(),
            1,
        )
        safra = SafraUnidade.all_cooperativas.get(cenario=cenario, entidade_id=fabrica.id)
        self.assertEqual(safra.entidade_tipo, 'Fábrica')
        self.assertEqual(safra.data_fim, datetime.date(2026, 9, 30))

    def test_safra_nao_confunde_ids_iguais_de_tipos_diferentes(self):
        """(c) entidade_id sozinho não identifica a unidade -- fábricas e
        armazéns vêm de sequências independentes e os ids podem colidir.
        Simula a colisão explicitamente: uma safra de armazém gravada com o
        mesmo entidade_id que a fábrica do teste tem (entidade_id não é FK,
        então isto é uma linha legítima do ponto de vista do modelo)."""
        _, cenario = aplicar(
            montar_pasta(fabricas=[FABRICA_OK]), cooperativa=self.coop, nome_novo='Oficial',
        )
        fabrica = Fabrica.all_cooperativas.get(cenario=cenario)
        inicio = datetime.date(2026, 2, 15)
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, entidade_tipo='Armazém',
            entidade_id=fabrica.id, data_inicio=inicio, data_fim=datetime.date(2026, 6, 15),
        )

        aplicar(
            montar_pasta(safras=[{
                'unidade': 'FÁBRICA TESTE', 'data_inicio': inicio,
                'data_fim': datetime.date(2026, 9, 30),
            }]),
            cenario=cenario,
        )

        # Duas linhas devem existir: a "colisão" do armazém intocada, e uma
        # nova para a fábrica -- não uma atualização por cima da do armazém.
        self.assertEqual(
            SafraUnidade.all_cooperativas.filter(cenario=cenario, entidade_id=fabrica.id).count(),
            2,
        )
        safra_fabrica = SafraUnidade.all_cooperativas.get(
            cenario=cenario, entidade_id=fabrica.id, entidade_tipo='Fábrica',
        )
        self.assertEqual(safra_fabrica.data_fim, datetime.date(2026, 9, 30))
        safra_armazem = SafraUnidade.all_cooperativas.get(
            cenario=cenario, entidade_id=fabrica.id, entidade_tipo='Armazém',
        )
        self.assertEqual(safra_armazem.data_fim, datetime.date(2026, 6, 15))
