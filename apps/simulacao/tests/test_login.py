from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa

User = get_user_model()


class LoginTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )

    def test_pagina_de_login_renderiza(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<form')

    def test_login_valido_redireciona(self):
        response = self.client.post(reverse('login'), {
            'username': 'usuaria', 'password': 'senha-forte-123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/simulacao/cenarios/')

    def test_login_invalido_nao_autentica(self):
        response = self.client.post(reverse('login'), {
            'username': 'usuaria', 'password': 'senha-errada',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
