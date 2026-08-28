import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.integracoes.models import ApiKey
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria


class MovimentacoesEndpointTests(TestCase):
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
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, data=datetime.date(2026, 1, 15),
            armazem=self.armazem, fabrica=self.fabrica, quantidade_ton=6.0, custo_total=120.0,
        )

    def _url(self, scenario_id):
        return f'/api/v1/cenarios/{scenario_id}/movimentacoes/'

    def _get(self, scenario_id, **params):
        return self.client.get(
            self._url(scenario_id), data=params, headers={'X-API-Key': self.key.chave},
        )

    def test_sucesso_formato_tipado(self):
        response = self._get(self.cenario.id)

        self.assertEqual(response.status_code, 200)
        linha = response.json()[0]
        self.assertEqual(linha['data'], '2026-01-15')
        self.assertEqual(linha['origem'], 'Armazém Teste')
        self.assertEqual(linha['destino'], 'Fábrica Teste')
        self.assertEqual(linha['quantidade_sc'], 100.0)
        self.assertEqual(linha['custo_total_r$'], 120.0)   # chave literal preservada

    def test_filtro_por_data(self):
        response = self._get(self.cenario.id, start_date='2026-02-01')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_data_malformada_retorna_400(self):
        response = self._get(self.cenario.id, start_date='15/01/2026')
        self.assertEqual(response.status_code, 400)
        self.assertIn('AAAA-MM-DD', response.json()['detail'])

    def test_limit_nao_numerico_retorna_422(self):
        response = self._get(self.cenario.id, limit='abc')
        self.assertEqual(response.status_code, 422)

    def test_limit_negativo_retorna_422(self):
        response = self._get(self.cenario.id, limit=-1)
        self.assertEqual(response.status_code, 422)

    def test_cenario_de_outra_cooperativa_retorna_404(self):
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        cenario_b = Cenario.all_cooperativas.create(cooperativa=coop_b, nome='Cenário B')

        response = self._get(cenario_b.id)
        self.assertEqual(response.status_code, 404)

    def test_cenario_inexistente_retorna_404(self):
        response = self._get(999999)
        self.assertEqual(response.status_code, 404)
