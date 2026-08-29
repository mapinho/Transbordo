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
        self.assertIn('Cooperativas', html)
        self.assertNotIn('/simulacao/cenarios/', html)
