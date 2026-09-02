from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import estoque
from apps.simulacao.forms import EstoqueForm
from apps.simulacao.models import Armazem, Cenario, Fabrica


class VisoesConfigTests(TestCase):
    def test_tres_visoes_existem_com_colunas_de_metrica_comparaveis(self):
        for visao in ("sistema", "armazem", "fabrica"):
            self.assertIn(visao, estoque.VISOES, visao)
            metricas = [c for c in estoque.VISOES[visao]["colunas"] if c["tipo"] == "num"]
            self.assertGreaterEqual(len(metricas), 6, visao)
            self.assertTrue(all(c.get("comparavel") for c in metricas), visao)

    def test_sistema_nao_pagina_por_unidade_pagina(self):
        self.assertFalse(estoque.VISOES["sistema"]["pagina"])
        self.assertTrue(estoque.VISOES["armazem"]["pagina"])
        self.assertTrue(estoque.VISOES["fabrica"]["pagina"])

    def test_colunas_de_dimensao(self):
        chaves_sistema = [c["key"] for c in estoque.VISOES["sistema"]["colunas"]]
        self.assertEqual(chaves_sistema[0], "mes")
        self.assertNotIn("unidade", chaves_sistema)
        self.assertEqual([c["key"] for c in estoque.VISOES["armazem"]["colunas"]][:2], ["mes", "unidade"])

    def test_normalizar_visao(self):
        self.assertEqual(estoque.normalizar_visao("armazem"), "armazem")
        self.assertEqual(estoque.normalizar_visao(None), "sistema")
        self.assertEqual(estoque.normalizar_visao("xpto"), "sistema")

    def test_rotulos_visao_sao_pares(self):
        self.assertEqual(dict(estoque.ROTULOS_VISAO)["armazem"], "Por armazém")


class EstoqueFormTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cenario = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        self.arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cenario, nome="A1",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_form_vazio_valido_filtros_vazios(self):
        form = EstoqueForm({}, cenario=self.cenario)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.filtros_limpos(),
                         {"mes_de": "", "mes_ate": "", "armazem_ids": [], "fabrica_ids": []})

    def test_form_com_mes_e_armazem(self):
        form = EstoqueForm(
            {"mes_de": "2026-01", "mes_ate": "2026-06", "armazem_ids": [self.arm.id]},
            cenario=self.cenario)
        self.assertTrue(form.is_valid(), form.errors)
        f = form.filtros_limpos()
        self.assertEqual(f["mes_de"], "2026-01")
        self.assertEqual(f["armazem_ids"], [self.arm.id])

    def test_mes_formato_invalido_rejeitado(self):
        form = EstoqueForm({"mes_de": "janeiro"}, cenario=self.cenario)
        self.assertFalse(form.is_valid())

    def test_armazem_de_outro_cenario_invalido(self):
        outro = Cenario.objects.create(cooperativa=self.coop, nome="Outro")
        arm2 = Armazem.objects.create(
            cooperativa=self.coop, cenario=outro, nome="A2",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        form = EstoqueForm({"armazem_ids": [arm2.id]}, cenario=self.cenario)
        self.assertFalse(form.is_valid())
