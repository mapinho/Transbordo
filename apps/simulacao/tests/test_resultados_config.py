import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao import resultados
from apps.simulacao.forms import ResultadosForm
from apps.simulacao.models import Armazem, Cenario, Fabrica


class VisoesConfigTests(TestCase):
    def test_todas_as_combinacoes_validas_existem(self):
        for periodo in ("diario", "mensal"):
            for agrupar in ("fabrica_armazem", "fabrica", "armazem", "nada"):
                self.assertIn((periodo, agrupar), resultados.VISOES, (periodo, agrupar))
        self.assertIn(("total", "nada"), resultados.VISOES)

    def test_cada_visao_tem_colunas_de_metrica_comparaveis(self):
        for chave, visao in resultados.VISOES.items():
            metricas = [c for c in visao["colunas"] if c["key"] in ("ton", "sacas", "custo")]
            self.assertEqual(len(metricas), 3, chave)
            self.assertTrue(all(c.get("comparavel") for c in metricas), chave)

    def test_normalizar_visao_default_e_rejeita_invalida(self):
        self.assertEqual(resultados.normalizar_visao(None, None), ("diario", "fabrica_armazem"))
        self.assertEqual(resultados.normalizar_visao("mensal", "fabrica"), ("mensal", "fabrica"))
        self.assertEqual(resultados.normalizar_visao("xpto", "yz"), ("diario", "fabrica_armazem"))
        self.assertEqual(resultados.normalizar_visao("total", "fabrica"), ("total", "nada"))

    def test_paginacao_so_no_diario_agrupado(self):
        self.assertTrue(resultados.VISOES[("diario", "fabrica_armazem")]["pagina"])
        self.assertTrue(resultados.VISOES[("diario", "fabrica")]["pagina"])
        self.assertFalse(resultados.VISOES[("diario", "nada")]["pagina"])
        self.assertFalse(resultados.VISOES[("mensal", "fabrica_armazem")]["pagina"])


class ResultadosFormTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self._tok = definir_cooperativa_atual(self.coop.id)
        self.cenario = Cenario.objects.create(cooperativa=self.coop, nome="Cen")
        self.arm = Armazem.objects.create(
            cooperativa=self.coop, cenario=self.cenario, nome="A1",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def tearDown(self):
        resetar_cooperativa_atual(self._tok)

    def test_form_vazio_e_valido_e_devolve_filtros_none(self):
        form = ResultadosForm({}, cenario=self.cenario)
        self.assertTrue(form.is_valid())
        f = form.filtros_limpos()
        self.assertEqual(f, {"data_de": None, "data_ate": None, "armazem_ids": [], "fabrica_ids": []})

    def test_form_com_datas_e_armazem(self):
        form = ResultadosForm(
            {"data_de": "2026-01-01", "data_ate": "2026-01-31", "armazem_ids": [self.arm.id]},
            cenario=self.cenario,
        )
        self.assertTrue(form.is_valid(), form.errors)
        f = form.filtros_limpos()
        self.assertEqual(f["data_de"], datetime.date(2026, 1, 1))
        self.assertEqual(f["armazem_ids"], [self.arm.id])

    def test_armazem_de_outro_cenario_e_invalido(self):
        outro = Cenario.objects.create(cooperativa=self.coop, nome="Outro")
        arm2 = Armazem.objects.create(
            cooperativa=self.coop, cenario=outro, nome="A2",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        form = ResultadosForm({"armazem_ids": [arm2.id]}, cenario=self.cenario)
        self.assertFalse(form.is_valid())
