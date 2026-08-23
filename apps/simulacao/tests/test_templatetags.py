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
