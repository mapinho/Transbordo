from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.models import Armazem, Cenario, ResumoMensalArmazem

VAZIO = {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}


class GraficoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        for mes, saldo, exc in [("2026-01", 50, 0), ("2026-02", 250, 50)]:
            ResumoMensalArmazem.objects.create(
                cooperativa=self.coop, cenario=self.cen, armazem=arm, mes=mes,
                rec_produtor=1, envio_transbordo=0, vendas=0, saldo_estoque=saldo,
                capacidade_estatica=200, excedente=exc)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_linha_saldo_excedente(self):
        g = estoque.dados_grafico(self.cen.id, VAZIO, None)
        self.assertEqual(g["tipo"], "line")
        self.assertEqual(g["labels"], ["01/2026", "02/2026"])
        saldo = [d for d in g["datasets"] if d["label"] == "Saldo total"][0]
        self.assertEqual(saldo["dados"], [50.0, 250.0])

    def test_comparado_adiciona_datasets(self):
        comp = Cenario.objects.create(cooperativa=self.coop, nome="Comp")
        g = estoque.dados_grafico(self.cen.id, VAZIO, comp.id)
        self.assertIn("Excedente total (comparado)", {d["label"] for d in g["datasets"]})
