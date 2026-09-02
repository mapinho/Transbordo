from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.models import Armazem, Cenario, Fabrica, ResumoMensalArmazem

VAZIO = {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}


class ComparacaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.atual = self._cen("Atual", saldo=200)
        self.comp = self._cen("Comp", saldo=160)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def _cen(self, nome, saldo):
        cen = Cenario.objects.create(cooperativa=self.coop, nome=nome)
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=cen, nome="ARM",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=cen, armazem=arm, mes="2026-01",
            rec_produtor=100, envio_transbordo=10, vendas=0, saldo_estoque=saldo,
            capacidade_estatica=300, excedente=0)
        return cen

    def test_sistema_recebe_delta_e_colunas(self):
        d = estoque.agregar(self.atual.id, "sistema", VAZIO)
        d = estoque.aplicar_comparacao(d, self.comp.id, "sistema", VAZIO)
        self.assertAlmostEqual(d["linhas"][0]["saldo_delta"], (200 - 160) / 160 * 100, places=6)
        keys = [c["key"] for c in d["colunas"]]
        self.assertIn("saldo_delta", keys)
        self.assertEqual(keys.index("saldo_delta"), keys.index("saldo") + 1)

    def test_armazem_recebe_delta(self):
        d = estoque.agregar(self.atual.id, "armazem", VAZIO)
        d = estoque.aplicar_comparacao(d, self.comp.id, "armazem", VAZIO)
        self.assertIn("saldo_delta", d["linhas"][0])

    def test_chave_sem_par_e_novo(self):
        arm = Armazem.objects.filter(cenario=self.atual).first()
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=self.atual, armazem=arm, mes="2026-02",
            rec_produtor=5, envio_transbordo=0, vendas=0, saldo_estoque=5,
            capacidade_estatica=300, excedente=0)
        d = estoque.agregar(self.atual.id, "sistema", VAZIO)
        d = estoque.aplicar_comparacao(d, self.comp.id, "sistema", VAZIO)
        fev = [l for l in d["linhas"] if l["mes"] == "2026-02"][0]
        self.assertEqual(fev["saldo_delta"], "novo")

    def test_totais_delta(self):
        d = estoque.agregar(self.atual.id, "sistema", VAZIO)
        d = estoque.aplicar_comparacao(d, self.comp.id, "sistema", VAZIO)
        self.assertIn("saldo", d["totais_delta"])
