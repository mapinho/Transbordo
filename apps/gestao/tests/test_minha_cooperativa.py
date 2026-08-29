from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa, User


class MinhaCooperativaTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.outra = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        self.admin = User.objects.create_user(
            username='ac', email='ac@t.test', password='x',
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )

    def test_edita_apenas_a_propria(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('gestao:minha_cooperativa'), {'dias_janela_safra_padrao': 45})
        self.assertEqual(response.status_code, 302)
        self.coop.refresh_from_db()
        self.outra.refresh_from_db()
        self.assertEqual(self.coop.dias_janela_safra_padrao, 45)
        self.assertIsNone(self.outra.dias_janela_safra_padrao)

    def test_usuario_fabrica_recebe_403(self):
        u = User.objects.create_user(
            username='uf', email='uf@t.test', password='x',
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.coop,
        )
        self.client.force_login(u)
        self.assertEqual(self.client.get(reverse('gestao:minha_cooperativa')).status_code, 403)
