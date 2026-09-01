import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

D = datetime.date
VAZIO = {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []}


class ComparacaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.atual = self._cenario_com_mov("Atual", ton=10, custo=100)
        self.comp = self._cenario_com_mov("Comp", ton=8, custo=125)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def _cenario_com_mov(self, nome, ton, custo):
        cen = Cenario.objects.create(cooperativa=self.coop, nome=nome)
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=cen, nome="ARM",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.objects.create(
            cooperativa=self.coop, cenario=cen, nome="FAB",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=cen, data=D(2026, 1, 5),
            armazem=arm, fabrica=fab, quantidade_ton=ton, custo_total=custo)
        return cen

    def test_linha_crua_nao_recebe_delta(self):
        d = resultados.agregar(self.atual.id, "diario", "fabrica_armazem", VAZIO)
        d = resultados.aplicar_comparacao(d, self.comp.id, "diario", "fabrica_armazem", VAZIO)
        self.assertTrue(d["comparacao_ignorada"])
        self.assertNotIn("ton_delta", d["linhas"][0])

    def test_mensal_recebe_delta_e_colunas(self):
        d = resultados.agregar(self.atual.id, "mensal", "nada", VAZIO)
        d = resultados.aplicar_comparacao(d, self.comp.id, "mensal", "nada", VAZIO)
        # assertAlmostEqual: sacas = ton*1000/60, so Δ%(sacas) differs from Δ%(ton)
        # by a floating-point ULP (24.999999999999982 != 25.0). Spec forbids
        # special-casing sacas in the implementation — see task-5 brief fix 2.
        self.assertAlmostEqual(d["linhas"][0]["ton_delta"], (10 - 8) / 8 * 100, places=9)  # +25%
        self.assertEqual(d["linhas"][0]["custo_delta"], (100 - 125) / 125 * 100)  # -20%
        self.assertAlmostEqual(d["linhas"][0]["sacas_delta"], d["linhas"][0]["ton_delta"], places=9)
        keys = [c["key"] for c in d["colunas"]]
        self.assertEqual(keys, ["dia", "ton", "ton_delta", "sacas", "sacas_delta",
                                "custo", "custo_delta"])

    def test_chave_sem_par_e_novo(self):
        # comparado não tem fevereiro
        MovimentacaoDiaria.objects.create(
            cooperativa=self.coop, cenario=self.atual,
            data=D(2026, 2, 2), armazem=Armazem.objects.filter(cenario=self.atual).first(),
            fabrica=Fabrica.objects.filter(cenario=self.atual).first(),
            quantidade_ton=3, custo_total=9)
        d = resultados.agregar(self.atual.id, "mensal", "nada", VAZIO)
        d = resultados.aplicar_comparacao(d, self.comp.id, "mensal", "nada", VAZIO)
        fev = [l for l in d["linhas"] if l["dia"] == D(2026, 2, 1)][0]
        self.assertEqual(fev["ton_delta"], "novo")

    def test_totais_delta(self):
        d = resultados.agregar(self.atual.id, "total", "nada", VAZIO)
        d = resultados.aplicar_comparacao(d, self.comp.id, "total", "nada", VAZIO)
        self.assertEqual(d["totais_delta"]["custo"], (100 - 125) / 125 * 100)

    def test_filtro_armazem_traduzido_para_cenario_comparado(self):
        # F1: ids de armazém são do cenário atual; o clone comparado tem o mesmo
        # NOME com id diferente. A comparação deve traduzir por nome, não sumir.
        arm_atual = Armazem.objects.filter(cenario=self.atual).first()
        filtros = {**VAZIO, "armazem_ids": [arm_atual.id]}
        d = resultados.agregar(self.atual.id, "mensal", "nada", filtros)
        d = resultados.aplicar_comparacao(d, self.comp.id, "mensal", "nada", filtros)
        self.assertIsInstance(d["linhas"][0]["ton_delta"], float)

    def test_totais_com_delta_traduz_filtro(self):
        arm_atual = Armazem.objects.filter(cenario=self.atual).first()
        filtros = {**VAZIO, "armazem_ids": [arm_atual.id]}
        card = resultados.totais_com_delta(self.atual.id, self.comp.id, filtros)
        self.assertIsInstance(card["delta"]["ton"], float)

    def test_totais_com_delta_sem_comparado(self):
        card = resultados.totais_com_delta(self.atual.id, None, VAZIO)
        self.assertIsNone(card["delta"])
        self.assertEqual(card["ton"], 10.0)
