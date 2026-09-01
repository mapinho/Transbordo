from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase


class MoedaFilterTests(SimpleTestCase):
    def _render(self, valor):
        template = Template("{% load simulacao_filters %}{{ valor|moeda }}")
        return template.render(Context({"valor": valor}))

    def test_formata_com_duas_casas_e_separador_pt_br(self):
        self.assertEqual(self._render(1234.5), "R$ 1.234,50")

    def test_valor_negativo(self):
        self.assertEqual(self._render(-42.0), "R$ -42,00")

    def test_none_retorna_vazio(self):
        self.assertEqual(self._render(None), "")

    def test_aceita_decimal(self):
        self.assertEqual(self._render(Decimal("10")), "R$ 10,00")


class VolumeFilterTests(SimpleTestCase):
    def _render(self, valor):
        template = Template("{% load simulacao_filters %}{{ valor|volume }}")
        return template.render(Context({"valor": valor}))

    def test_formata_com_uma_casa_e_separador_pt_br(self):
        self.assertEqual(self._render(1234.5), "1.234,5")

    def test_milhar_grande(self):
        self.assertEqual(self._render(1234567.89), "1.234.567,9")

    def test_none_retorna_vazio(self):
        self.assertEqual(self._render(None), "")


class VariacaoFilterTests(SimpleTestCase):
    def _render(self, valor):
        return Template("{% load simulacao_filters %}{{ valor|variacao }}").render(
            Context({"valor": valor}))

    def test_positivo_vermelho_seta_cima(self):
        out = self._render(12.34)
        self.assertIn("text-error", out)
        self.assertIn("+12,3%", out)
        self.assertIn("↑", out)

    def test_negativo_verde_seta_baixo_menos_unicode(self):
        out = self._render(-4.08)
        self.assertIn("text-success", out)
        self.assertIn("−4,1%", out)   # U+2212
        self.assertIn("↓", out)

    def test_zero(self):
        self.assertIn("0,0%", self._render(0.0))

    def test_none_travessao(self):
        self.assertIn("—", self._render(None))

    def test_novo_badge(self):
        self.assertIn("badge", self._render("novo"))

    def test_vazio(self):
        self.assertEqual(self._render("").strip(), "")


class ItemFilterTests(SimpleTestCase):
    def test_lookup(self):
        out = Template("{% load simulacao_filters %}{{ d|item:'x' }}").render(
            Context({"d": {"x": 42}}))
        self.assertEqual(out, "42")

    def test_nao_dict(self):
        out = Template("{% load simulacao_filters %}{{ d|item:'x' }}").render(Context({"d": 5}))
        self.assertEqual(out, "")
