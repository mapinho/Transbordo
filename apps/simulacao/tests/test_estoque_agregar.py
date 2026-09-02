from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica,
)

VAZIO = {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []}


class AgregarTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cen = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        self.a1 = self._arm("ARM1"); self.a2 = self._arm("ARM2")
        self.f1 = self._fab("FAB1")
        # jan
        self._ra(self.a1, "2026-01", rec_produtor=100, envio_transbordo=40, vendas=10,
                 saldo=50, cap=200, excedente=0)
        self._ra(self.a2, "2026-01", rec_produtor=60, envio_transbordo=20, vendas=5,
                 saldo=35, cap=100, excedente=0)
        self._rf(self.f1, "2026-01", rec_produtor=0, rec_transbordo=60, esmagado=50,
                 saldo=10, cap=300, excedente=0)
        # fev — a1 estoura, f1 rompe
        self._ra(self.a1, "2026-02", rec_produtor=300, envio_transbordo=0, vendas=0,
                 saldo=250, cap=200, excedente=50)
        self._rf(self.f1, "2026-02", rec_produtor=0, rec_transbordo=0, esmagado=400,
                 saldo=-30, cap=300, excedente=0)

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

    def _ra(self, arm, mes, **kw):
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=self.cen, armazem=arm, mes=mes,
            rec_produtor=kw["rec_produtor"], envio_transbordo=kw["envio_transbordo"],
            vendas=kw["vendas"], saldo_estoque=kw["saldo"],
            capacidade_estatica=kw["cap"], excedente=kw["excedente"])

    def _rf(self, fab, mes, **kw):
        ResumoMensalFabrica.objects.create(
            cooperativa=self.coop, cenario=self.cen, fabrica=fab, mes=mes,
            rec_produtor=kw["rec_produtor"], rec_transbordo=kw["rec_transbordo"],
            esmagado=kw["esmagado"], saldo_estoque=kw["saldo"],
            capacidade_estatica=kw["cap"], excedente=kw["excedente"])

    def test_sistema_soma_as_duas_tabelas_por_mes(self):
        d = estoque.agregar(self.cen.id, "sistema", VAZIO)
        self.assertEqual([l["mes"] for l in d["linhas"]], ["2026-01", "2026-02"])
        jan = d["linhas"][0]
        self.assertEqual(jan["recebimento"], 160.0)   # 100 + 60 + 0
        self.assertEqual(jan["transbordo"], 60.0)     # 40 + 20 (envio dos armazéns)
        self.assertEqual(jan["esmagamento"], 50.0)
        self.assertEqual(jan["vendas"], 15.0)
        self.assertEqual(jan["saldo"], 95.0)          # 50 + 35 + 10
        self.assertEqual(jan["capacidade"], 600.0)    # 200 + 100 + 300
        self.assertIsNone(jan["_alerta"])
        self.assertEqual(jan["_chave"], ("2026-01",))
        self.assertNotIn("unidade", jan)

    def test_sistema_totais_pico(self):
        d = estoque.agregar(self.cen.id, "sistema", VAZIO)
        self.assertEqual(d["totais"]["recebimento"], 460.0)   # 160 + 300
        self.assertEqual(d["totais"]["saldo"], 220.0)         # pico = fev (250 + -30)
        self.assertEqual(d["totais"]["excedente"], 50.0)      # pico = fev
        self.assertEqual(d["totais"]["capacidade"], 600.0)

    def test_sistema_alerta_ruptura_tem_prioridade(self):
        d = estoque.agregar(self.cen.id, "sistema", VAZIO)
        fev = d["linhas"][1]
        self.assertEqual(fev["saldo"], 220.0)      # 250 + (-30)
        # nenhuma linha "sistema" fica negativa aqui; testa a prioridade na visão fábrica
        df = estoque.agregar(self.cen.id, "fabrica", VAZIO)
        fev_f = [l for l in df["linhas"] if l["mes"] == "2026-02"][0]
        self.assertEqual(fev_f["_alerta"], "ruptura")

    def test_armazem_uma_linha_por_unidade_mes(self):
        d = estoque.agregar(self.cen.id, "armazem", VAZIO)
        self.assertEqual(len(d["linhas"]), 3)   # a1 jan, a2 jan, a1 fev
        l0 = d["linhas"][0]
        self.assertEqual((l0["mes"], l0["unidade"]), ("2026-01", "ARM1"))
        self.assertEqual(l0["envio_transbordo"], 40.0)
        self.assertEqual(l0["_chave"], ("2026-01", "ARM1"))
        fev_a1 = [l for l in d["linhas"] if l["mes"] == "2026-02"][0]
        self.assertEqual(fev_a1["_alerta"], "excedente")

    def test_fabrica_colunas_proprias(self):
        d = estoque.agregar(self.cen.id, "fabrica", VAZIO)
        self.assertIn("rec_transbordo", d["linhas"][0])
        self.assertIn("esmagado", d["linhas"][0])
        self.assertNotIn("envio_transbordo", d["linhas"][0])

    def test_filtro_mes(self):
        f = {**VAZIO, "mes_de": "2026-02"}
        d = estoque.agregar(self.cen.id, "sistema", f)
        self.assertEqual([l["mes"] for l in d["linhas"]], ["2026-02"])

    def test_filtro_armazem(self):
        f = {**VAZIO, "armazem_ids": [self.a2.id]}
        d = estoque.agregar(self.cen.id, "armazem", f)
        self.assertEqual({l["unidade"] for l in d["linhas"]}, {"ARM2"})

    def test_filtro_que_zera(self):
        f = {**VAZIO, "mes_de": "2030-01"}
        d = estoque.agregar(self.cen.id, "sistema", f)
        self.assertEqual(d["linhas"], [])
        self.assertEqual(d["totais"]["recebimento"], 0.0)

    def test_paginacao_por_unidade(self):
        for i in range(3, 160):
            self._ra(self.a1, f"2027-{i:02d}"[:7] if i < 13 else f"20{27 + i // 12}-{i % 12 + 1:02d}",
                     rec_produtor=1, envio_transbordo=0, vendas=0, saldo=1, cap=1, excedente=0)
        d1 = estoque.agregar(self.cen.id, "armazem", VAZIO, pagina=1)
        self.assertEqual(len(d1["linhas"]), 100)
        self.assertEqual(d1["paginacao"]["num_paginas"], 2)
        d2 = estoque.agregar(self.cen.id, "armazem", VAZIO, pagina=2)
        self.assertEqual(len(d2["linhas"]), d1["paginacao"]["total"] - 100)

    def test_limite_excedido_levanta(self):
        with self.assertRaises(estoque.RecorteGrandeDemais):
            estoque.agregar(self.cen.id, "armazem", VAZIO, pagina=None, limite=2)

    def test_sem_paginacao_quando_pagina_none(self):
        d = estoque.agregar(self.cen.id, "armazem", VAZIO, pagina=None)
        self.assertIsNone(d["paginacao"])

    def test_nao_vaza_outro_cenario(self):
        outro = Cenario.objects.create(cooperativa=self.coop, nome="Outro")
        a = Armazem.objects.create(
            cooperativa=self.coop, cenario=outro, nome="X",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        ResumoMensalArmazem.objects.create(
            cooperativa=self.coop, cenario=outro, armazem=a, mes="2026-01",
            rec_produtor=999, envio_transbordo=0, vendas=0, saldo_estoque=0,
            capacidade_estatica=0, excedente=0)
        d = estoque.agregar(self.cen.id, "sistema", VAZIO)
        self.assertEqual(d["totais"]["recebimento"], 460.0)
