from django.test import TestCase

from apps.core.models import Cooperativa
from apps.integracoes.models import ApiKey
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica,
)


class ComparacoesMixin:
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
            f'/api/v1/cenarios/{scenario_id}/{path}', headers={'X-API-Key': self.key.chave},
        )

    def _outra_coop_cenario(self):
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        return Cenario.all_cooperativas.create(cooperativa=coop_b, nome='Cenário B')


class FabricasComparacaoEndpointTests(ComparacoesMixin, TestCase):
    def test_sucesso_agrega_pico_e_totais(self):
        for mes, saldo in (('2026-01', 200), ('2026-02', 300)):
            ResumoMensalFabrica.all_cooperativas.create(
                cooperativa=self.coop, cenario=self.cenario, mes=mes, fabrica=self.fabrica,
                rec_produtor=100, rec_transbordo=0, esmagado=50, saldo_estoque=saldo,
                capacidade_estatica=10000, excedente=0,
            )
        corpo = self._get('fabricas/comparacao/', self.cenario.id).json()

        self.assertEqual(len(corpo), 1)
        self.assertEqual(corpo[0]['recebimento_produtor_total_ton'], 200.0)
        self.assertEqual(corpo[0]['pico_estoque_mensal_ton'], 300.0)
        self.assertEqual(
            set(corpo[0].keys()),
            {'fabrica_id', 'fabrica', 'recebimento_produtor_total_ton',
             'recebimento_transbordo_total_ton', 'esmagado_total_ton',
             'pico_estoque_mensal_ton', 'excedente_total_acumulado_ton'},
        )

    def test_sem_dados_retorna_lista_vazia(self):
        self.assertEqual(self._get('fabricas/comparacao/', self.cenario.id).json(), [])

    def test_cenario_de_outra_cooperativa_retorna_404(self):
        self.assertEqual(
            self._get('fabricas/comparacao/', self._outra_coop_cenario().id).status_code, 404,
        )


class ArmazensComparacaoEndpointTests(ComparacoesMixin, TestCase):
    def test_sucesso_agrega_pico_e_totais(self):
        for mes, saldo in (('2026-01', 100), ('2026-02', 50)):
            ResumoMensalArmazem.all_cooperativas.create(
                cooperativa=self.coop, cenario=self.cenario, mes=mes, armazem=self.armazem,
                rec_produtor=100, envio_transbordo=0, vendas=0, saldo_estoque=saldo,
                capacidade_estatica=5000, excedente=0,
            )
        corpo = self._get('armazens/comparacao/', self.cenario.id).json()

        self.assertEqual(len(corpo), 1)
        self.assertEqual(corpo[0]['recebimento_produtor_total_ton'], 200.0)
        self.assertEqual(corpo[0]['pico_estoque_mensal_ton'], 100.0)
        self.assertEqual(
            set(corpo[0].keys()),
            {'armazem_id', 'armazem', 'recebimento_produtor_total_ton',
             'envio_transbordo_total_ton', 'vendas_total_ton',
             'pico_estoque_mensal_ton', 'excedente_total_acumulado_ton'},
        )

    def test_cenario_de_outra_cooperativa_retorna_404(self):
        self.assertEqual(
            self._get('armazens/comparacao/', self._outra_coop_cenario().id).status_code, 404,
        )
