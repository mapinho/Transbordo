from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa, User


class ContaTests(TestCase):
    def test_qualquer_autenticado_ve_a_conta(self):
        coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        u = User.objects.create_user(
            username='uf', email='uf@t.test', password='x',
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=coop,
        )
        self.client.force_login(u)
        response = self.client.get(reverse('gestao:conta'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'uf@t.test')

    def test_anonimo_redireciona(self):
        response = self.client.get(reverse('gestao:conta'))
        self.assertEqual(response.status_code, 302)
