import io

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoFabrica, Rota, SafraUnidade,
)
from apps.simulacao.planilha import ABA_ARMAZENS, ABA_FABRICAS, analisar
from apps.simulacao.tests.planilha_fixtures import montar_pasta, montar_pasta_bruta

FABRICA_OK = {
    'nome': 'FÁBRICA TESTE',
    'capacidade_estatica': 50000,
    'capacidade_esmagamento_diaria': 1200,
    'capacidade_recebimento_diaria': 2000,
    'limite_caminhoes': 60,
    'carga_media_caminhao': 36,
    'estoque_inicial': 8000,
}

ARMAZEM_OK = {
    'nome': 'ARMAZÉM A',
    'capacidade_estatica': 30000,
    'capacidade_expedicao_diaria': 900,
    'estoque_inicial': 12000,
}


class AnalisarEstruturaTests(TestCase):
    def test_arquivo_ilegivel_e_erro_estrutural(self):
        relatorio = analisar(io.BytesIO(b'isto nao e um xlsx'), None)

        self.assertTrue(relatorio.tem_erro_estrutural)
        self.assertIn('xlsx', relatorio.erro_estrutural.lower())

    def test_pasta_sem_nenhuma_aba_reconhecida_e_erro_estrutural(self):
        pasta = montar_pasta_bruta({'Planilha1': [['a', 'b'], [1, 2]]})

        relatorio = analisar(pasta, None)

        self.assertTrue(relatorio.tem_erro_estrutural)

    def test_aba_com_cabecalho_irreconhecivel_e_erro_estrutural(self):
        pasta = montar_pasta_bruta({ABA_FABRICAS: [['coluna_inventada'], ['x']]})

        relatorio = analisar(pasta, None)

        self.assertTrue(relatorio.tem_erro_estrutural)
        self.assertIn(ABA_FABRICAS, relatorio.erro_estrutural)

    def test_aba_ausente_nao_e_erro(self):
        """Uma pasta só com Fábricas é válida -- as demais abas ficam vazias."""
        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK]), None)

        self.assertFalse(relatorio.tem_erro_estrutural)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).criar, 0)

    def test_cabecalho_e_normalizado(self):
        linha = {k.upper() + '  ': v for k, v in FABRICA_OK.items()}

        relatorio = analisar(montar_pasta(fabricas=[linha]), None)

        self.assertFalse(relatorio.tem_erro_estrutural)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)


class AnalisarFabricasArmazensTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')
        self.cenario = Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome='Oficial', is_oficial=True,
        )

    def test_cenario_none_conta_tudo_como_criacao(self):
        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK]), None)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).atualizar, 0)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).criar, 1)

    def test_nome_ja_existente_no_cenario_conta_como_atualizacao(self):
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='FÁBRICA TESTE',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK]), self.cenario)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 0)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).atualizar, 1)

    def test_campo_numerico_em_branco_rejeita_a_linha_e_nomeia_a_coluna(self):
        ruim = dict(FABRICA_OK, nome='SEM CAPACIDADE', capacidade_estatica=None)

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, ruim]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 1)
        self.assertEqual(len(resumo.rejeitadas), 1)
        rejeitada = resumo.rejeitadas[0]
        self.assertIn('capacidade_estatica', rejeitada.motivo)
        self.assertEqual(rejeitada.valores['nome'], 'SEM CAPACIDADE')

    def test_numero_da_linha_e_o_do_excel(self):
        """Cabeçalho é a linha 1, então a segunda linha de dados é a 3."""
        ruim = dict(FABRICA_OK, nome='RUIM', estoque_inicial=None)

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, ruim]), None)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).rejeitadas[0].linha, 3)

    def test_valor_nao_numerico_rejeita_a_linha(self):
        ruim = dict(FABRICA_OK, nome='TEXTO NO NUMERO', limite_caminhoes='muitos')

        relatorio = analisar(montar_pasta(fabricas=[ruim]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 0)
        self.assertIn('limite_caminhoes', resumo.rejeitadas[0].motivo)

    def test_nome_em_branco_rejeita_a_linha(self):
        relatorio = analisar(montar_pasta(fabricas=[dict(FABRICA_OK, nome=None)]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 0)
        self.assertIn('nome', resumo.rejeitadas[0].motivo)

    def test_linha_ruim_nao_aborta_a_aba(self):
        outra = dict(FABRICA_OK, nome='OUTRA FÁBRICA')
        ruim = dict(FABRICA_OK, nome='RUIM', carga_media_caminhao=None)

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, ruim, outra]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 2)
        self.assertEqual(len(resumo.rejeitadas), 1)

    def test_analisar_nao_escreve_nada(self):
        """A garantia que sustenta a pré-visualização."""
        antes = (Fabrica.all_cooperativas.count(), Armazem.all_cooperativas.count())

        analisar(montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK]), self.cenario)

        depois = (Fabrica.all_cooperativas.count(), Armazem.all_cooperativas.count())
        self.assertEqual(antes, depois)

    def test_nome_duplicado_na_mesma_aba_rejeita_segunda_ocorrencia(self):
        """Duas linhas com o mesmo nome na mesma aba: primeira é criação, segunda é rejeitada."""
        duplicada = dict(FABRICA_OK, nome='FÁBRICA TESTE')  # mesmo nome de FABRICA_OK
        outra = dict(FABRICA_OK, nome='OUTRA FÁBRICA')

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK, duplicada, outra]), None)

        resumo = relatorio.resumo(ABA_FABRICAS)
        self.assertEqual(resumo.criar, 2)  # FÁBRICA TESTE e OUTRA FÁBRICA
        self.assertEqual(len(resumo.rejeitadas), 1)
        rejeitada = resumo.rejeitadas[0]
        self.assertIn('duplicado', rejeitada.motivo)
        self.assertEqual(rejeitada.linha, 3)  # segunda linha de dados = Excel row 3

    def test_mesmo_nome_em_abas_diferentes_nao_e_duplicado(self):
        """Mesmo nome em Fábricas e Armazéns é válido -- são entidades diferentes."""
        fabrica = dict(FABRICA_OK, nome='ENTIDADE COMPARTILHADA')
        armazem = dict(ARMAZEM_OK, nome='ENTIDADE COMPARTILHADA')

        relatorio = analisar(montar_pasta(fabricas=[fabrica], armazens=[armazem]), None)

        self.assertEqual(relatorio.resumo(ABA_FABRICAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_FABRICAS).atualizar, 0)
        self.assertEqual(len(relatorio.resumo(ABA_FABRICAS).rejeitadas), 0)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_ARMAZENS).atualizar, 0)
        self.assertEqual(len(relatorio.resumo(ABA_ARMAZENS).rejeitadas), 0)


import datetime

from apps.simulacao.planilha import ABA_PREVISOES, ABA_ROTAS, ABA_SAFRAS

ROTA_OK = {
    'origem': 'ARMAZÉM A',
    'destino': 'FÁBRICA TESTE',
    'distancia_km': 118.5,
    'custo_frete_ton': 42.75,
    'custo_frete_entressafra': 38.0,
}


class AnalisarResolucaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')
        self.cenario = Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome='Oficial', is_oficial=True,
        )

    def test_rota_resolve_contra_unidades_criadas_na_mesma_pasta(self):
        """O caso do bootstrap: cenário vazio, tudo vem da própria pasta."""
        pasta = montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], rotas=[ROTA_OK])

        relatorio = analisar(pasta, None)

        self.assertEqual(relatorio.resumo(ABA_ROTAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_ROTAS).rejeitadas, [])

    def test_rota_resolve_contra_unidades_ja_no_banco(self):
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='FÁBRICA TESTE',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )
        Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='ARMAZÉM A',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=1,
        )

        relatorio = analisar(montar_pasta(rotas=[ROTA_OK]), self.cenario)

        self.assertEqual(relatorio.resumo(ABA_ROTAS).criar, 1)

    def test_rota_com_origem_inexistente_e_rejeitada_com_motivo(self):
        ruim = dict(ROTA_OK, origem='ARMAZÉM FANTASMA')

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], rotas=[ruim]), None)

        rejeitadas = relatorio.resumo(ABA_ROTAS).rejeitadas
        self.assertEqual(len(rejeitadas), 1)
        self.assertIn('ARMAZÉM FANTASMA', rejeitadas[0].motivo)

    def test_custo_entressafra_em_branco_assume_o_de_safra(self):
        """Comportamento do legado (data_loader.py:386-387), preservado."""
        sem = dict(ROTA_OK, custo_frete_entressafra=None)
        pasta = montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], rotas=[sem])

        relatorio = analisar(pasta, None)

        self.assertEqual(relatorio.resumo(ABA_ROTAS).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_ROTAS).rejeitadas, [])

    def test_previsao_resolve_fabrica_ou_armazem_pelo_nome(self):
        previsoes = [
            {'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 3, 15),
             'recebimento_produtor': 4500.5, 'vendas': 1200.25},
            {'entidade': 'ARMAZÉM A', 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 7800.0, 'vendas': 300.0},
        ]
        pasta = montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], previsoes=previsoes)

        relatorio = analisar(pasta, None)

        self.assertEqual(relatorio.resumo(ABA_PREVISOES).criar, 2)

    def test_previsao_com_entidade_desconhecida_e_rejeitada_nao_pulada(self):
        """O legado só incrementava `skipped`, sem registro nenhum."""
        previsoes = [{'entidade': 'NINGUÉM', 'mes_referencia': datetime.date(2026, 3, 1),
                      'recebimento_produtor': 1, 'vendas': 1}]

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], previsoes=previsoes), None)

        rejeitadas = relatorio.resumo(ABA_PREVISOES).rejeitadas
        self.assertEqual(len(rejeitadas), 1)
        self.assertIn('NINGUÉM', rejeitadas[0].motivo)

    def test_nome_ambiguo_e_rejeitado_nomeando_o_conflito(self):
        """O legado escolhe a fábrica em silêncio (data_loader.py:439-453)."""
        pasta = montar_pasta(
            fabricas=[dict(FABRICA_OK, nome='DUPLICADO')],
            armazens=[dict(ARMAZEM_OK, nome='DUPLICADO')],
            previsoes=[{'entidade': 'DUPLICADO', 'mes_referencia': datetime.date(2026, 3, 1),
                        'recebimento_produtor': 1, 'vendas': 1}],
        )

        relatorio = analisar(pasta, None)

        rejeitadas = relatorio.resumo(ABA_PREVISOES).rejeitadas
        self.assertEqual(len(rejeitadas), 1)
        self.assertIn('ambígu', rejeitadas[0].motivo.lower())

    def test_mes_referencia_nao_parseavel_rejeita_sem_abortar_a_aba(self):
        previsoes = [
            {'entidade': 'FÁBRICA TESTE', 'mes_referencia': 'mês que vem',
             'recebimento_produtor': 1, 'vendas': 1},
            {'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 4, 1),
             'recebimento_produtor': 2, 'vendas': 2},
        ]

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], previsoes=previsoes), None)

        resumo = relatorio.resumo(ABA_PREVISOES)
        self.assertEqual(resumo.criar, 1)
        self.assertEqual(len(resumo.rejeitadas), 1)
        self.assertIn('mes_referencia', resumo.rejeitadas[0].motivo)

    def test_previsao_com_valores_em_branco_vale_zero(self):
        previsoes = [{'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 3, 1),
                      'recebimento_produtor': None, 'vendas': None}]

        relatorio = analisar(montar_pasta(fabricas=[FABRICA_OK], previsoes=previsoes), None)

        self.assertEqual(relatorio.resumo(ABA_PREVISOES).criar, 1)
        self.assertEqual(relatorio.resumo(ABA_PREVISOES).rejeitadas, [])

    def test_safra_resolve_unidade_e_deriva_o_tipo(self):
        safras = [
            {'unidade': 'ARMAZÉM A', 'data_inicio': datetime.date(2026, 2, 1),
             'data_fim': datetime.date(2026, 5, 31)},
            {'unidade': 'FÁBRICA TESTE', 'data_inicio': datetime.date(2026, 2, 15),
             'data_fim': datetime.date(2026, 6, 15)},
        ]
        pasta = montar_pasta(fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], safras=safras)

        relatorio = analisar(pasta, None)

        self.assertEqual(relatorio.resumo(ABA_SAFRAS).criar, 2)

    def test_safra_com_data_fim_antes_do_inicio_e_rejeitada(self):
        safras = [{'unidade': 'ARMAZÉM A', 'data_inicio': datetime.date(2026, 5, 1),
                   'data_fim': datetime.date(2026, 2, 1)}]

        relatorio = analisar(montar_pasta(armazens=[ARMAZEM_OK], safras=safras), None)

        rejeitadas = relatorio.resumo(ABA_SAFRAS).rejeitadas
        self.assertEqual(len(rejeitadas), 1)
        self.assertIn('data_fim', rejeitadas[0].motivo)

    # -- Fix round (review findings 1-3) --------------------------------

    def test_rota_duplicada_na_planilha_e_rejeitada(self):
        """Mesma (origem, destino) duas vezes: primeira é criação, segunda é rejeitada."""
        pasta = montar_pasta(
            fabricas=[FABRICA_OK], armazens=[ARMAZEM_OK], rotas=[ROTA_OK, dict(ROTA_OK)],
        )

        relatorio = analisar(pasta, None)

        resumo = relatorio.resumo(ABA_ROTAS)
        self.assertEqual(resumo.criar, 1)
        self.assertEqual(len(resumo.rejeitadas), 1)
        self.assertIn('rota duplicada na planilha', resumo.rejeitadas[0].motivo)

    def test_previsao_duplicada_na_planilha_e_rejeitada(self):
        """Mesma (entidade, mês) duas vezes: primeira é criação, segunda é rejeitada."""
        linha = {'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 3, 1),
                  'recebimento_produtor': 1, 'vendas': 1}
        pasta = montar_pasta(fabricas=[FABRICA_OK], previsoes=[linha, dict(linha)])

        relatorio = analisar(pasta, None)

        resumo = relatorio.resumo(ABA_PREVISOES)
        self.assertEqual(resumo.criar, 1)
        self.assertEqual(len(resumo.rejeitadas), 1)
        self.assertIn('previsão duplicada na planilha', resumo.rejeitadas[0].motivo)

    def test_safra_duplicada_na_planilha_e_rejeitada(self):
        """Mesma (unidade, data_inicio) duas vezes: primeira é criação, segunda é rejeitada."""
        linha = {'unidade': 'ARMAZÉM A', 'data_inicio': datetime.date(2026, 2, 1),
                  'data_fim': datetime.date(2026, 5, 31)}
        pasta = montar_pasta(armazens=[ARMAZEM_OK], safras=[linha, dict(linha)])

        relatorio = analisar(pasta, None)

        resumo = relatorio.resumo(ABA_SAFRAS)
        self.assertEqual(resumo.criar, 1)
        self.assertEqual(len(resumo.rejeitadas), 1)
        self.assertIn('safra duplicada na planilha', resumo.rejeitadas[0].motivo)

    def test_rota_ja_no_banco_conta_como_atualizacao(self):
        fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='FÁBRICA TESTE',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )
        armazem = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='ARMAZÉM A',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=1,
        )
        Rota.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, armazem=armazem, fabrica=fabrica,
            distancia_km=100, custo_frete_ton=40, custo_frete_entressafra=35,
        )

        relatorio = analisar(montar_pasta(rotas=[ROTA_OK]), self.cenario)

        resumo = relatorio.resumo(ABA_ROTAS)
        self.assertEqual(resumo.criar, 0)
        self.assertEqual(resumo.atualizar, 1)

    def test_previsao_ja_no_banco_conta_como_atualizacao(self):
        fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='FÁBRICA TESTE',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )
        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=self.coop, fabrica=fabrica, mes_referencia=datetime.date(2026, 3, 1),
            recebimento_produtor=1, vendas=1,
        )
        previsao = {'entidade': 'FÁBRICA TESTE', 'mes_referencia': datetime.date(2026, 3, 15),
                    'recebimento_produtor': 2, 'vendas': 2}

        relatorio = analisar(montar_pasta(previsoes=[previsao]), self.cenario)

        resumo = relatorio.resumo(ABA_PREVISOES)
        self.assertEqual(resumo.criar, 0)
        self.assertEqual(resumo.atualizar, 1)

    def test_safra_ja_no_banco_com_entidade_tipo_nao_canonico_conta_como_atualizacao(self):
        """Mirrors tests/test_scenarios_c4_c5.py: entidade_tipo persistido para uma
        fábrica nem sempre é o literal 'Fábrica' -- a convenção é checar
        `== 'Armazém'` primeiro e assumir Fábrica em qualquer outro caso."""
        fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='FÁBRICA TESTE',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, entidade_tipo='fabrica',
            entidade_id=fabrica.id, data_inicio=datetime.date(2026, 2, 15),
            data_fim=datetime.date(2026, 6, 15),
        )
        safra = {'unidade': 'FÁBRICA TESTE', 'data_inicio': datetime.date(2026, 2, 15),
                 'data_fim': datetime.date(2026, 6, 15)}

        relatorio = analisar(montar_pasta(safras=[safra]), self.cenario)

        resumo = relatorio.resumo(ABA_SAFRAS)
        self.assertEqual(resumo.criar, 0)
        self.assertEqual(resumo.atualizar, 1)
