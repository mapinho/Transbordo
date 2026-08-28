import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.integracoes.models import ApiKey
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria


class ResumoMensalEndpointTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.key = ApiKey.objects.create(cooperativa=self.coop, nome='Serviço A')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def _get(self, scenario_id, **params):
        return self.client.get(
            f'/api/v1/cenarios/{scenario_id}/resumo-mensal/',
            data=params, headers={'X-API-Key': self.key.chave},
        )

    def test_sucesso_agrega_por_mes_e_rota(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, data=datetime.date(2026, 1, 10),
            armazem=self.armazem, fabrica=self.fabrica, quantidade_ton=6.0, custo_total=100.0,
        )
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, data=datetime.date(2026, 1, 20),
            armazem=self.armazem, fabrica=self.fabrica, quantidade_ton=4.0, custo_total=50.0,
        )

        corpo = self._get(self.cenario.id).json()

        self.assertEqual(list(corpo.keys()), ['resumo_mensal', 'detalhe_rotas'])
        self.assertEqual(len(corpo['resumo_mensal']), 1)
        self.assertEqual(corpo['resumo_mensal'][0]['mes'], '2026-01')
        self.assertEqual(corpo['resumo_mensal'][0]['quantidade_ton'], 10.0)
        self.assertEqual(corpo['detalhe_rotas'][0]['origem'], 'Armazém Teste')

    def test_sem_movimentacoes_normaliza_para_o_formato_tipado(self):
        corpo = self._get(self.cenario.id).json()
        self.assertEqual(corpo, {'resumo_mensal': [], 'detalhe_rotas': []})

    def test_data_malformada_retorna_400(self):
        response = self._get(self.cenario.id, end_date='31/12/2026')
        self.assertEqual(response.status_code, 400)
        self.assertIn('AAAA-MM-DD', response.json()['detail'])

    def test_cenario_de_outra_cooperativa_retorna_404(self):
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        cenario_b = Cenario.all_cooperativas.create(cooperativa=coop_b, nome='Cenário B')
        self.assertEqual(self._get(cenario_b.id).status_code, 404)
