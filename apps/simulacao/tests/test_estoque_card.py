from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica,
)

VAZIO = {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}


class CardTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = self._cenario_com_estoque("Atual", saldo_fev=250, exc_fev=50)
        self.comp = self._cenario_com_estoque("Comp", saldo_fev=100, exc_fev=0)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def _cenario_com_estoque(self, nome, saldo_fev, exc_fev):
        cen = Cenario.objects.create(cooperativa=self.coop, nome=nome)
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=cen, nome="ARM",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.objects.create(
            cooperativa=self.coop, cenario=cen, nome="FAB",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=cen, armazem=arm, mes="2026-01",
            rec_produtor=100, envio_transbordo=30, vendas=10, saldo_estoque=50,
            capacidade_estatica=200, excedente=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=cen, armazem=arm, mes="2026-02",
            rec_produtor=200, envio_transbordo=0, vendas=0, saldo_estoque=saldo_fev,
            capacidade_estatica=200, excedente=exc_fev)
        ResumoMensalFabrica.objects.create(
            cooperativa=self.coop, cenario=cen, fabrica=fab, mes="2026-01",
            rec_produtor=0, rec_transbordo=30, esmagado=20, saldo_estoque=10,
            capacidade_estatica=300, excedente=0)
        return cen

    def test_card_de_pico(self):
        c = estoque.card_de_pico(self.cen.id, VAZIO)
        self.assertEqual(c["recebimento"], 300.0)   # 100 + 200 + 0
        self.assertEqual(c["transbordo"], 30.0)
        self.assertEqual(c["esmagamento"], 20.0)
        self.assertEqual(c["saldo"], 250.0)         # pico = fev (250 + 0)
        self.assertEqual(c["excedente"], 50.0)
        # Ruling T3-a: capacidade do card = Σ capacidade_estatica de TODAS as
        # unidades do 1º mês (jan). Jan = ARM 200 + FAB 300 = 500.
        self.assertEqual(c["capacidade"], 500.0)
        self.assertIsNone(c["mes_ruptura"])

    def test_card_saldo_min_recorte_saudavel(self):
        # Ruling T3-b: saldo_min é o mín mensal INCONDICIONAL; o clause `< 0`
        # governa só mes_ruptura. Jan saldo 60, fev 250 -> mín = 60.
        c = estoque.card_de_pico(self.cen.id, VAZIO)
        self.assertEqual(c["saldo_min"], 60.0)
        self.assertIsNone(c["mes_ruptura"])

    def test_card_ruptura(self):
        ResumoMensalFabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen,
            fabrica=Fabrica.objects.filter(cenario=self.cen).first(), mes="2026-03",
            rec_produtor=0, rec_transbordo=0, esmagado=500, saldo_estoque=-40,
            capacidade_estatica=300, excedente=0)
        c = estoque.card_de_pico(self.cen.id, VAZIO)
        self.assertEqual(c["saldo_min"], -40.0)
        self.assertEqual(c["mes_ruptura"], "03/2026")

    def test_card_com_delta(self):
        c = estoque.card_com_delta(self.cen.id, self.comp.id, VAZIO)
        # saldo pico atual 250 vs comp 100 → +150%
        self.assertAlmostEqual(c["delta"]["saldo"], (250 - 100) / 100 * 100, places=6)
        self.assertEqual(c["delta"]["excedente"], None)   # comp excedente pico = 0, atual > 0

    def test_card_com_delta_sem_comparado(self):
        c = estoque.card_com_delta(self.cen.id, None, VAZIO)
        self.assertIsNone(c["delta"])

    def test_card_mes_pico_e_percentuais(self):
        c = estoque.card_de_pico(self.cen.id, VAZIO)
        self.assertEqual(c["mes_pico"], "02/2026")   # fev tem o maior saldo (250)
        self.assertEqual(c["ocupacao_pct"], 50.0)    # min(250, 500) / 500 * 100
        self.assertEqual(c["excedente_pct"], 10.0)   # 50 / 500 * 100

    def test_card_ocupacao_pct_nunca_negativa(self):
        # Recorte todo negativo: o pico mensal de saldo é < 0; a barra de
        # ocupação não pode receber `width` negativa.
        cen = Cenario.objects.create(cooperativa=self.coop, nome="TodoNegativo")
        fab = Fabrica.objects.create(
            cooperativa=self.coop, cenario=cen, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        ResumoMensalFabrica.objects.create(
            cooperativa=self.coop, cenario=cen, fabrica=fab, mes="2026-01",
            rec_produtor=0, rec_transbordo=0, esmagado=100, saldo_estoque=-50,
            capacidade_estatica=300, excedente=0)
        c = estoque.card_de_pico(cen.id, VAZIO)
        self.assertEqual(c["ocupacao_pct"], 0.0)

    def test_card_com_delta_repassa_barra_de_ocupacao(self):
        # SPEC §6: card_com_delta só repassa mes_pico / ocupacao_pct / excedente_pct.
        base = estoque.card_de_pico(self.cen.id, VAZIO)
        c = estoque.card_com_delta(self.cen.id, self.comp.id, VAZIO)
        self.assertEqual(c["mes_pico"], base["mes_pico"])
        self.assertEqual(c["ocupacao_pct"], base["ocupacao_pct"])
        self.assertEqual(c["excedente_pct"], base["excedente_pct"])

    def test_card_percentuais_sem_capacidade(self):
        cen = Cenario.objects.create(cooperativa=self.coop, nome="SemCap")
        arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=cen, armazem=arm, mes="2026-01",
            rec_produtor=10, envio_transbordo=0, vendas=0, saldo_estoque=5,
            capacidade_estatica=0, excedente=0)
        c = estoque.card_de_pico(cen.id, VAZIO)
        self.assertEqual(c["ocupacao_pct"], 0.0)
        self.assertEqual(c["excedente_pct"], 0.0)

    def test_card_vazio_tem_as_chaves_novas(self):
        cen = Cenario.objects.create(cooperativa=self.coop, nome="Vazio")
        c = estoque.card_de_pico(cen.id, VAZIO)
        self.assertEqual(c["mes_pico"], "")
        self.assertEqual(c["ocupacao_pct"], 0.0)
        self.assertEqual(c["excedente_pct"], 0.0)

    def test_cenarios_comparaveis(self):
        Cenario.objects.create(cooperativa=self.coop, nome="Sem Estoque")
        lista = estoque.cenarios_comparaveis(self.cen.id, self.coop.id)
        self.assertEqual(sorted(c["nome"] for c in lista), ["Comp"])
