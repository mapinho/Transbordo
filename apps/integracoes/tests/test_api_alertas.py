from django.test import TestCase

from apps.core.models import Cooperativa
from apps.integracoes.models import ApiKey
from apps.simulacao.models import Cenario, Fabrica, ResumoMensalFabrica


class AlertasMixin:
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.key = ApiKey.objects.create(cooperativa=self.coop, nome='Serviço A')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=10000, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def _get(self, path, scenario_id):
        return self.client.get(
            f'/api/v1/cenarios/{scenario_id}/{path}', headers={'X-API-Key': self.key.chave},
        )

    def _outra_coop_cenario(self):
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        return Cenario.all_cooperativas.create(cooperativa=coop_b, nome='Cenário B')


class AlertasExcedentesEndpointTests(AlertasMixin, TestCase):
    def test_sucesso_formato_tipado(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=0, rec_transbordo=0, esmagado=0, saldo_estoque=12000,
            capacidade_estatica=10000, excedente=2000,
        )
        corpo = self._get('alertas/excedentes/', self.cenario.id).json()

        self.assertEqual(len(corpo), 1)
        self.assertEqual(corpo[0]['entidade_tipo'], 'Fabrica')
        self.assertEqual(corpo[0]['excedente_estouro_ton'], 2000.0)
        self.assertEqual(
            set(corpo[0].keys()),
            {'mes', 'entidade_tipo', 'entidade_id', 'entidade_nome',
             'estoque_final_ton', 'capacidade_estatica_ton', 'excedente_estouro_ton'},
        )

    def test_cenario_de_outra_cooperativa_retorna_404(self):
        self.assertEqual(
            self._get('alertas/excedentes/', self._outra_coop_cenario().id).status_code, 404,
        )


class AlertasRupturasEndpointTests(AlertasMixin, TestCase):
    def test_sucesso_formato_tipado(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=0, esmagado=200, saldo_estoque=-50.0,
            capacidade_estatica=10000, excedente=0,
        )
        corpo = self._get('alertas/rupturas/', self.cenario.id).json()

        self.assertEqual(len(corpo), 1)
        self.assertEqual(corpo[0]['entidade_nome'], 'Fábrica Teste')
        self.assertAlmostEqual(corpo[0]['deficit_ton'], 50.0)
        self.assertEqual(
            set(corpo[0].keys()),
            {'mes', 'entidade_tipo', 'entidade_id', 'entidade_nome',
             'estoque_final_ton', 'capacidade_estatica_ton', 'deficit_ton'},
        )

    def test_cenario_de_outra_cooperativa_retorna_404(self):
        self.assertEqual(
            self._get('alertas/rupturas/', self._outra_coop_cenario().id).status_code, 404,
        )
