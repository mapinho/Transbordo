from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa, User


class MenuTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')

    def _login(self, papel, coop=True):
        u = User.objects.create_user(
            username=papel, email=f'{papel}@t.test', password='x', papel=papel,
            cooperativa=self.coop if coop else None,
        )
        self.client.force_login(u)

    def test_admin_vector_ve_cooperativas_nao_ve_simulacao(self):
        self._login(User.PAPEL_ADMIN_VECTOR, coop=False)
        html = self.client.get(reverse('gestao:cooperativas')).content.decode()
        self.assertIn('Organizações', html)
        self.assertNotIn('/simulacao/cenarios/', html)

    def test_admin_cooperativa_ve_todos_os_seus_links(self):
        self._login(User.PAPEL_ADMIN_COOPERATIVA)
        from apps.simulacao.models import Cenario
        Cenario.all_cooperativas.create(cooperativa=self.coop, nome='C')
        html = self.client.get(reverse('simulacao:cenarios_list')).content.decode()
        self.assertIn(reverse('gestao:usuarios'), html)
        self.assertIn(reverse('gestao:minha_cooperativa'), html)
        self.assertIn(reverse('gestao:conta'), html)

    def test_contexto_menu_admin_vector_tem_organizacoes(self):
        self._login(User.PAPEL_ADMIN_VECTOR, coop=False)
        resp = self.client.get(reverse("core:home"))
        self.assertIn("organizacoes_disponiveis", resp.context)
        self.assertIsNotNone(resp.context["organizacoes_disponiveis"])
        self.assertIsNone(resp.context["org"])

    def test_contexto_menu_membro_tem_org(self):
        self._login(User.PAPEL_ADMIN_COOPERATIVA)
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.context["org"], self.coop)
        self.assertIsNone(resp.context["organizacoes_disponiveis"])
