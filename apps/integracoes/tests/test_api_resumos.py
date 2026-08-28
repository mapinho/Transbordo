from django.test import TestCase

from apps.core.models import Cooperativa
from apps.integracoes.models import ApiKey
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica,
)


class ResumosMixin:
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
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=5000, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def _get(self, path, scenario_id):
        return self.client.get(
            f'/api/v1/cenarios/{scenario_id}/{path}',
            headers={'X-API-Key': self.key.chave},
        )

    def _outra_coop_cenario(self):
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        return Cenario.all_cooperativas.create(cooperativa=coop_b, nome='Cenário B')


class FabricasResumoEndpointTests(ResumosMixin, TestCase):
    def test_sucesso_formato_tipado(self):
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, mes='2026-01', fabrica=self.fabrica,
            rec_produtor=100, rec_transbordo=50, esmagado=120, saldo_estoque=30,
            capacidade_estatica=10000, excedente=0,
        )
        corpo = self._get('fabricas/resumo/', self.cenario.id).json()

        self.assertEqual(len(corpo), 1)
        self.assertEqual(corpo[0]['fabrica'], 'Fábrica Teste')
        self.assertEqual(corpo[0]['recebimento_produtor_ton'], 100.0)
        self.assertEqual(
            set(corpo[0].keys()),
            {'mes', 'fabrica_id', 'fabrica', 'recebimento_produtor_ton',
             'recebimento_transbordo_ton', 'esmagado_ton', 'saldo_estoque_ton',
             'capacidade_estatica_ton', 'excedente_estoque_ton'},
        )

    def test_cenario_de_outra_cooperativa_retorna_404(self):
        self.assertEqual(
            self._get('fabricas/resumo/', self._outra_coop_cenario().id).status_code, 404,
        )


class ArmazensResumoEndpointTests(ResumosMixin, TestCase):
    def test_sucesso_formato_tipado(self):
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, mes='2026-01', armazem=self.armazem,
            rec_produtor=200, envio_transbordo=150, vendas=10, saldo_estoque=40,
            capacidade_estatica=5000, excedente=0,
        )
        corpo = self._get('armazens/resumo/', self.cenario.id).json()

        self.assertEqual(len(corpo), 1)
        self.assertEqual(corpo[0]['armazem'], 'Armazém Teste')
        self.assertEqual(corpo[0]['envio_transbordo_ton'], 150.0)
        self.assertEqual(
            set(corpo[0].keys()),
            {'mes', 'armazem_id', 'armazem', 'recebimento_produtor_ton',
             'envio_transbordo_ton', 'vendas_ton', 'saldo_estoque_ton',
             'capacidade_estatica_ton', 'excedente_estoque_ton'},
        )

    def test_cenario_de_outra_cooperativa_retorna_404(self):
        self.assertEqual(
            self._get('armazens/resumo/', self._outra_coop_cenario().id).status_code, 404,
        )
