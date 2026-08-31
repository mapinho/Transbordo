from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa

User = get_user_model()


class LoginTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', email='usuaria@coop-a.test', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )

    def test_pagina_de_login_renderiza_form_local_e_botoes_sso(self):
        response = self.client.get(reverse('account_login'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<form')
        self.assertContains(response, 'Entrar com Google')
        self.assertContains(response, 'Entrar com Microsoft')

    def test_login_valido_redireciona(self):
        response = self.client.post(reverse('account_login'), {
            'login': 'usuaria', 'password': 'senha-forte-123',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')

    def test_login_invalido_nao_autentica(self):
        response = self.client.post(reverse('account_login'), {
            'login': 'usuaria', 'password': 'senha-errada',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_clique_no_sso_vai_direto_ao_provedor(self):
        # SOCIALACCOUNT_LOGIN_ON_GET=True: o GET no link do provedor redireciona
        # direto para o OAuth, sem a tela intermediária de confirmação do allauth.
        for provider in ('google', 'microsoft'):
            response = self.client.get(f'/accounts/{provider}/login/')
            self.assertEqual(response.status_code, 302, provider)
            self.assertNotIn('/accounts/login/', response.url, provider)

    def test_signup_fechado(self):
        response = self.client.get(reverse('account_signup'))
        self.assertIn(response.status_code, (403, 302, 200))
        if response.status_code == 200:
            self.assertContains(response, 'fechad')
