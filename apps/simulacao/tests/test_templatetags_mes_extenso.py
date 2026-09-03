from django.test import SimpleTestCase

from apps.simulacao.templatetags.simulacao_filters import mes_extenso


class MesExtensoTests(SimpleTestCase):
    def test_formata(self):
        self.assertEqual(mes_extenso("2026-02"), "Fevereiro 2026")
        self.assertEqual(mes_extenso("2026-12"), "Dezembro 2026")

    def test_entrada_estranha_passa_reto(self):
        self.assertEqual(mes_extenso(""), "")
        self.assertEqual(mes_extenso("xpto"), "xpto")
