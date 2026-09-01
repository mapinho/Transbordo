# apps/simulacao/tests/test_resultados_agregar.py
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

D = datetime.date
VAZIO = {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}


class AgregarTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        self.a1 = self._arm("ARM1"); self.a2 = self._arm("ARM2")
        self.f1 = self._fab("FAB1"); self.f2 = self._fab("FAB2")
        # jan: a1->f1 10t/100, a2->f1 5t/50 ; fev: a1->f2 20t/400
        self._mov(D(2026, 1, 5), self.a1, self.f1, 10, 100)
        self._mov(D(2026, 1, 5), self.a2, self.f1, 5, 50)
        self._mov(D(2026, 1, 6), self.a1, self.f1, 3, 30)
        self._mov(D(2026, 2, 10), self.a1, self.f2, 20, 400)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def _arm(self, nome):
        return Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome=nome,
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)

    def _fab(self, nome):
        return Fabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen, nome=nome,
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)

    def _mov(self, data, arm, fab, ton, custo):
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=self.cen, data=data,
            armazem=arm, fabrica=fab, quantidade_ton=ton, custo_total=custo)

    def test_diario_linha_crua(self):
        d = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", VAZIO)
        self.assertEqual(len(d["linhas"]), 4)
        l0 = d["linhas"][0]
        self.assertEqual(l0["dia"], D(2026, 1, 5))
        self.assertEqual({l["origem"] for l in d["linhas"]}, {"ARM1", "ARM2"})
        self.assertEqual(l0["sacas"], l0["ton"] * 1000 / 60)
        self.assertEqual(d["totais"], {"ton": 38.0, "sacas": 38.0 * 1000 / 60, "custo": 580.0})

    def test_diario_por_fabrica_soma_armazens(self):
        d = resultados.agregar(self.cen.id, "diario", "fabrica", VAZIO)
        jan5 = [l for l in d["linhas"] if l["dia"] == D(2026, 1, 5)]
        self.assertEqual(len(jan5), 1)
        self.assertEqual(jan5[0]["ton"], 15.0)
        self.assertEqual(jan5[0]["custo"], 150.0)
        self.assertNotIn("origem", d["linhas"][0])

    def test_mensal_total(self):
        d = resultados.agregar(self.cen.id, "mensal", "nada", VAZIO)
        self.assertEqual([l["dia"] for l in d["linhas"]], [D(2026, 1, 1), D(2026, 2, 1)])
        self.assertEqual(d["linhas"][0]["ton"], 18.0)
        self.assertEqual(d["linhas"][1]["custo"], 400.0)
        self.assertEqual(d["colunas"][0]["tipo"], "data_mes")

    def test_total_do_cenario_uma_linha(self):
        d = resultados.agregar(self.cen.id, "total", "nada", VAZIO)
        self.assertEqual(len(d["linhas"]), 1)
        self.assertEqual(d["linhas"][0]["custo"], 580.0)
        self.assertEqual(d["linhas"][0]["_chave"], ("total",))

    def test_filtro_data_estreita(self):
        f = {**VAZIO, "data_de": D(2026, 2, 1), "data_ate": D(2026, 2, 28)}
        d = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", f)
        self.assertEqual(len(d["linhas"]), 1)
        self.assertEqual(d["totais"]["ton"], 20.0)

    def test_filtro_armazem(self):
        f = {**VAZIO, "armazem_ids": [self.a2.id]}
        d = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", f)
        self.assertEqual(len(d["linhas"]), 1)
        self.assertEqual(d["linhas"][0]["origem"], "ARM2")

    def test_filtro_que_zera(self):
        f = {**VAZIO, "data_de": D(2030, 1, 1)}
        d = resultados.agregar(self.cen.id, "diario", "nada", f)
        self.assertEqual(d["linhas"], [])
        self.assertEqual(d["totais"], {"ton": 0.0, "sacas": 0.0, "custo": 0.0})

    def test_paginacao(self):
        for i in range(1, 151):
            self._mov(D(2026, 3, 1) + datetime.timedelta(days=i), self.a1, self.f1, 1, 1)
        d1 = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", VAZIO, pagina=1)
        self.assertEqual(len(d1["linhas"]), 100)
        self.assertEqual(d1["paginacao"]["total"], 154)
        self.assertEqual(d1["paginacao"]["num_paginas"], 2)
        d2 = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", VAZIO, pagina=2)
        self.assertEqual(len(d2["linhas"]), 54)

    def test_sem_paginacao_quando_pagina_none(self):
        for i in range(1, 151):
            self._mov(D(2026, 3, 1) + datetime.timedelta(days=i), self.a1, self.f1, 1, 1)
        d = resultados.agregar(self.cen.id, "diario", "fabrica_armazem", VAZIO, pagina=None)
        self.assertEqual(len(d["linhas"]), 154)
        self.assertIsNone(d["paginacao"])

    def test_nao_vaza_outro_cenario(self):
        outro = Cenario.objects.create(cooperativa=self.coop, nome="Outro")
        a = Armazem.objects.create(
            cooperativa=self.coop, cenario=outro, nome="X",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        f = Fabrica.objects.create(
            cooperativa=self.coop, cenario=outro, nome="Y",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=outro, data=D(2026, 1, 5),
            armazem=a, fabrica=f, quantidade_ton=999, custo_total=999)
        d = resultados.agregar(self.cen.id, "total", "nada", VAZIO)
        self.assertEqual(d["linhas"][0]["ton"], 38.0)
