from django.template import Context, Template, engines
from django.test import TestCase
from django_cotton.compiler_regex import CottonCompiler


class CottonComponentesTests(TestCase):
    """Renderiza os componentes cotton isoladamente.

    O django-cotton 2.7 compila a sintaxe ``<c-...>`` no template *loader*
    (``django_cotton.cotton_loader.Loader``), passo que ``Template(string)``
    puro não executa. Reproduzimos aqui o mesmo passo com ``CottonCompiler``
    para exercitar os componentes sem precisar de arquivos de fixture.
    """

    def _render(self, corpo):
        compilado = CottonCompiler().process("{% load cotton %}" + corpo)
        return Template(compilado, engine=engines["django"].engine).render(Context({}))

    def test_card_aceita_class_e_id(self):
        html = self._render('<c-card class="mb-6" id="x">oi</c-card>')
        self.assertIn("mb-6", html)
        self.assertIn('id="x"', html)
        self.assertIn("bg-base-100", html)

    def test_resumo_numerico(self):
        html = self._render("<c-resumo-numerico><div>1</div></c-resumo-numerico>")
        self.assertIn("stats", html)

    def test_icon_conhecido_e_desconhecido(self):
        self.assertIn("<svg", self._render('<c-icon name="home" />'))
        self.assertNotIn("<svg", self._render('<c-icon name="inexistente" />'))
