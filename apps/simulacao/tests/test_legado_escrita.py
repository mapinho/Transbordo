import datetime

from django.test import TestCase
from django.utils import timezone

from apps.core.models import Cooperativa
from apps.simulacao.legado import DadosLegado, escrever
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoArmazem, PrevisaoFabrica, Rota, SafraUnidade,
)


def dados_de_exemplo():
    """Dois cenários, cada um com 1 fábrica + 1 armazém + 1 rota + previsões
    + 1 safra. Os IDs legados são deliberadamente altos e esparsos para que
    um remapeamento faltante fique evidente."""
    return DadosLegado(
        cenarios=[
            {'id': 6, 'nome': 'Oficial (Planejado)', 'is_oficial': True,
             'data_criacao': datetime.datetime(2026, 6, 1, 14, 19, 30)},
            {'id': 7, 'nome': 'Replanejado com Vendas', 'is_oficial': False,
             'data_criacao': datetime.datetime(2026, 6, 3, 13, 32, 48)},
        ],
        fabricas=[
            {'id': 101, 'cenario_id': 6, 'nome': 'FÁBRICA RIO VERDE',
             'capacidade_estatica': 50000, 'capacidade_esmagamento_diaria': 1200,
             'capacidade_recebimento_diaria': 2000, 'limite_caminhoes': 60,
             'carga_media_caminhao': 36, 'estoque_inicial': 8000},
            {'id': 102, 'cenario_id': 7, 'nome': 'FÁBRICA RIO VERDE',
             'capacidade_estatica': 50000, 'capacidade_esmagamento_diaria': 1200,
             'capacidade_recebimento_diaria': 2000, 'limite_caminhoes': 60,
             'carga_media_caminhao': 36, 'estoque_inicial': 8000},
        ],
        armazens=[
            {'id': 201, 'cenario_id': 6, 'nome': 'JATAÍ', 'capacidade_estatica': 30000,
             'capacidade_expedicao_diaria': 900, 'estoque_inicial': 12000},
            {'id': 202, 'cenario_id': 7, 'nome': 'JATAÍ', 'capacidade_estatica': 30000,
             'capacidade_expedicao_diaria': 900, 'estoque_inicial': 12000},
        ],
        rotas=[
            {'cenario_id': 6, 'armazem_id': 201, 'fabrica_id': 101,
             'distancia_km': 118.5, 'custo_frete_ton': 42.75, 'custo_frete_entressafra': 38.0},
            {'cenario_id': 7, 'armazem_id': 202, 'fabrica_id': 102,
             'distancia_km': 118.5, 'custo_frete_ton': 44.0, 'custo_frete_entressafra': 38.0},
        ],
        previsoes_fabrica=[
            {'fabrica_id': 101, 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 4500.5, 'vendas': 1200.25},
            {'fabrica_id': 102, 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 4500.5, 'vendas': 1800.0},
        ],
        previsoes_armazem=[
            {'armazem_id': 201, 'mes_referencia': datetime.date(2026, 3, 1),
             'recebimento_produtor': 7800.0, 'vendas': 300.0},
        ],
        safras=[
            {'cenario_id': 6, 'entidade_tipo': 'Armazém', 'entidade_id': 201,
             'data_inicio': datetime.date(2026, 2, 1), 'data_fim': datetime.date(2026, 5, 31)},
            {'cenario_id': 6, 'entidade_tipo': 'Fábrica', 'entidade_id': 101,
             'data_inicio': datetime.date(2026, 2, 15), 'data_fim': datetime.date(2026, 6, 15)},
        ],
    )


class EscreverTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Comigo', slug='comigo')

    def test_contagens_retornadas_batem_com_a_entrada(self):
        contagens = escrever(dados_de_exemplo(), self.coop)

        self.assertEqual(contagens, {
            'cenarios': 2, 'fabricas': 2, 'armazens': 2, 'rotas': 2,
            'previsoes_fabrica': 2, 'previsoes_armazem': 1, 'safras': 2,
        })

    def test_toda_linha_escrita_pertence_ao_tenant(self):
        escrever(dados_de_exemplo(), self.coop)

        for modelo in (Cenario, Fabrica, Armazem, Rota,
                       PrevisaoFabrica, PrevisaoArmazem, SafraUnidade):
            linhas = list(modelo.all_cooperativas.all())
            self.assertTrue(linhas, f'{modelo.__name__} não escreveu nada')
            for linha in linhas:
                self.assertEqual(
                    linha.cooperativa_id, self.coop.id,
                    f'{modelo.__name__} {linha.id} caiu no tenant errado',
                )

    def test_ids_sao_remapeados_e_nao_reaproveitam_os_do_legado(self):
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=oficial.id)
        self.assertNotEqual(fabrica.id, 101)
        self.assertEqual(fabrica.nome, 'FÁBRICA RIO VERDE')

    def test_rota_aponta_para_fabrica_e_armazem_do_mesmo_cenario(self):
        escrever(dados_de_exemplo(), self.coop)

        for rota in Rota.all_cooperativas.all():
            self.assertEqual(rota.armazem.cenario_id, rota.cenario_id)
            self.assertEqual(rota.fabrica.cenario_id, rota.cenario_id)

    def test_safra_de_armazem_remapeia_entidade_id_para_o_armazem_django(self):
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        armazem = Armazem.all_cooperativas.get(cenario_id=oficial.id)
        safra = SafraUnidade.all_cooperativas.get(entidade_tipo='Armazém')

        self.assertEqual(safra.entidade_id, armazem.id)
        self.assertNotEqual(safra.entidade_id, 201)

    def test_safra_de_fabrica_remapeia_entidade_id_para_a_fabrica_django(self):
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=oficial.id)
        safra = SafraUnidade.all_cooperativas.get(entidade_tipo='Fábrica')

        self.assertEqual(safra.entidade_id, fabrica.id)
        self.assertNotEqual(safra.entidade_id, 101)

    def test_previsao_segue_a_fabrica_do_cenario_correspondente(self):
        escrever(dados_de_exemplo(), self.coop)

        replanejado = Cenario.all_cooperativas.get(nome='Replanejado com Vendas')
        fabrica = Fabrica.all_cooperativas.get(cenario_id=replanejado.id)
        previsao = PrevisaoFabrica.all_cooperativas.get(fabrica_id=fabrica.id)

        self.assertEqual(previsao.vendas, 1800.0)

    def test_data_criacao_vira_aware_sem_deslocar_o_horario(self):
        """USE_TZ=True: escrever o datetime naive do legado sem converter faria
        o Django interpretá-lo como UTC, deslocando tudo em 3 horas."""
        escrever(dados_de_exemplo(), self.coop)

        oficial = Cenario.all_cooperativas.get(nome='Oficial (Planejado)')
        local = timezone.localtime(oficial.data_criacao)

        self.assertIsNotNone(oficial.data_criacao.tzinfo)
        self.assertEqual(
            (local.year, local.month, local.day, local.hour, local.minute),
            (2026, 6, 1, 14, 19),
        )

    def test_e_idempotente_entre_execucoes(self):
        primeira = escrever(dados_de_exemplo(), self.coop)
        segunda = escrever(dados_de_exemplo(), self.coop)

        self.assertEqual(primeira, segunda)
        self.assertEqual(Cenario.all_cooperativas.count(), 2)
        self.assertEqual(Fabrica.all_cooperativas.count(), 2)
        self.assertEqual(Rota.all_cooperativas.count(), 2)
        self.assertEqual(SafraUnidade.all_cooperativas.count(), 2)

    def test_nao_toca_nas_linhas_de_um_tenant_vizinho(self):
        vizinha = Cooperativa.objects.create(nome='Outra', slug='outra')
        cenario_vizinho = Cenario.all_cooperativas.create(
            cooperativa=vizinha, nome='Intocado', is_oficial=True,
        )
        Fabrica.all_cooperativas.create(
            cooperativa=vizinha, cenario=cenario_vizinho, nome='NÃO MEXER',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=1,
        )

        escrever(dados_de_exemplo(), self.coop)
        escrever(dados_de_exemplo(), self.coop)

        self.assertEqual(Cenario.all_cooperativas.filter(cooperativa=vizinha).count(), 1)
        self.assertEqual(Fabrica.all_cooperativas.filter(cooperativa=vizinha).count(), 1)
        self.assertTrue(
            Fabrica.all_cooperativas.filter(cooperativa=vizinha, nome='NÃO MEXER').exists()
        )
