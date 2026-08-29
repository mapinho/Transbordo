from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa, User


class CooperativasCrudTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.vector = User.objects.create_user(
            username='vector', email='vector@t.test', password='x',
            papel=User.PAPEL_ADMIN_VECTOR,
        )
        self.admin_coop = User.objects.create_user(
            username='ac', email='ac@t.test', password='x',
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )

    def test_admin_vector_lista(self):
        self.client.force_login(self.vector)
        response = self.client.get(reverse('gestao:cooperativas'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Coop A')

    def test_admin_cooperativa_recebe_403(self):
        self.client.force_login(self.admin_coop)
        self.assertEqual(self.client.get(reverse('gestao:cooperativas')).status_code, 403)

    def test_admin_vector_cria_cooperativa(self):
        self.client.force_login(self.vector)
        response = self.client.post(reverse('gestao:cooperativa_nova'), {
            'nome': 'Coop B', 'slug': 'coop-b', 'ativo': 'on',
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Cooperativa.objects.filter(slug='coop-b').exists())

    def test_desativar_nao_apaga(self):
        self.client.force_login(self.vector)
        self.client.post(reverse('gestao:cooperativa_editar', args=[self.coop.id]), {
            'nome': 'Coop A', 'slug': 'coop-a',  # 'ativo' omitido = desmarca
        })
        self.coop.refresh_from_db()
        self.assertFalse(self.coop.ativo)
        self.assertTrue(Cooperativa.objects.filter(id=self.coop.id).exists())
