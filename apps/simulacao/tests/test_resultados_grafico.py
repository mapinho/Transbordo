# apps/simulacao/tests/test_resultados_grafico.py
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

D = datetime.date
VAZIO = {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}


class GraficoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        for data, ton, custo in [(D(2026, 1, 5), 10, 100), (D(2026, 2, 3), 20, 250)]:
            MovimentacaoDiaria.objects.create(
                cooperativa=self.coop, cenario=self.cen, data=data,
                armazem=arm, fabrica=fab, quantidade_ton=ton, custo_total=custo)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_mensal_barras(self):
        g = resultados.dados_grafico(self.cen.id, "mensal", "fabrica", VAZIO, None)
        self.assertEqual(g["tipo"], "bar")
        self.assertEqual(len(g["labels"]), 2)
        ton = [d for d in g["datasets"] if d["label"] == "Toneladas"][0]
        self.assertEqual(ton["dados"], [10.0, 20.0])

    def test_diario_total_linha(self):
        g = resultados.dados_grafico(self.cen.id, "diario", "nada", VAZIO, None)
        self.assertEqual(g["tipo"], "line")

    def test_diario_agrupado_sem_grafico(self):
        self.assertIsNone(resultados.dados_grafico(self.cen.id, "diario", "fabrica", VAZIO, None))

    def test_total_sem_grafico(self):
        self.assertIsNone(resultados.dados_grafico(self.cen.id, "total", "nada", VAZIO, None))

    def test_comparado_adiciona_datasets(self):
        comp = Cenario.objects.create(cooperativa=self.coop, nome="Comp")
        g = resultados.dados_grafico(self.cen.id, "mensal", "nada", VAZIO, comp.id)
        rotulos = {d["label"] for d in g["datasets"]}
        self.assertIn("Toneladas (comparado)", rotulos)
