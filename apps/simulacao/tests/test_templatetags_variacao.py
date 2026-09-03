from django.test import SimpleTestCase

from apps.simulacao.templatetags.simulacao_filters import variacao


class VariacaoTests(SimpleTestCase):
    def test_novo(self):
        html = variacao("novo")
        self.assertIn("novo", html)
        self.assertIn("badge", html)

    def test_none_e_nao_numero(self):
        self.assertIn("—", variacao(None))
        self.assertEqual(variacao(""), "")
        self.assertEqual(variacao("qualquer"), "")

    def test_quase_zero_e_neutro(self):
        for v in (0.0, 0.03, -0.04, 0.049, -0.049):
            html = variacao(v)
            self.assertIn("0,0%", html)
            self.assertIn("text-base-content/50", html)
            self.assertNotIn("↑", html)
            self.assertNotIn("↓", html)
            self.assertNotIn("text-error", html)
            self.assertNotIn("text-success", html)

    def test_positivo_acima_do_limiar(self):
        html = variacao(25.0)
        self.assertIn("↑", html)
        self.assertIn("+25,0%", html)
        self.assertIn("text-error", html)

    def test_negativo_acima_do_limiar(self):
        html = variacao(-20.0)
        self.assertIn("↓", html)
        self.assertIn("−", html)   # U+2212 MINUS SIGN
        self.assertIn("20,0%", html)
        self.assertIn("text-success", html)

    def test_bordas_do_limiar(self):
        self.assertIn("text-base-content/50", variacao(0.04))
        self.assertIn("↑", variacao(0.06))
