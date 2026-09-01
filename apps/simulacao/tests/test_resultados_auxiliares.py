# apps/simulacao/tests/test_resultados_auxiliares.py
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

VAZIO = {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}


class AuxiliaresTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Atual", is_oficial=True)
        self.arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        self.fab = Fabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=self.cen, data=datetime.date(2026, 1, 1),
            armazem=self.arm, fabrica=self.fab, quantidade_ton=6, custo_total=60)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_totais_do_recorte(self):
        t = resultados.totais_do_recorte(self.cen.id, VAZIO)
        self.assertEqual(t, {"ton": 6.0, "sacas": 6.0 * 1000 / 60, "custo": 60.0})

    def test_totais_recorte_vazio_zera(self):
        f = {**VAZIO, "data_de": datetime.date(2030, 1, 1)}
        self.assertEqual(resultados.totais_do_recorte(self.cen.id, f),
                         {"ton": 0.0, "sacas": 0.0, "custo": 0.0})

    def test_cenarios_comparaveis_so_com_movimentacao_exceto_atual(self):
        com_mov = Cenario.objects.create(cooperativa=self.coop, nome="Com Mov")
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=com_mov, data=datetime.date(2026, 1, 1),
            armazem=self.arm, fabrica=self.fab, quantidade_ton=1, custo_total=1)
        Cenario.objects.create(cooperativa=self.coop, nome="Sem Mov")
        outra_coop = Cooperativa.objects.create(nome="D", slug="d")
        Cenario.objects.create(cooperativa=outra_coop, nome="De Outra")

        lista = resultados.cenarios_comparaveis(self.cen.id, self.coop.id)
        self.assertEqual([c["nome"] for c in lista], ["Com Mov"])
