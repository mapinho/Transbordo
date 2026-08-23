from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario

User = get_user_model()


class CenariosListViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.oficial = Cenario.all_cooperativas.create(
            cooperativa=self.cooperativa, nome='Oficial', is_oficial=True,
        )

    def test_requer_login(self):
        response = self.client.get(reverse('simulacao:cenarios_list'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_pagina_completa_lista_cenarios(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('simulacao:cenarios_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html')
        self.assertContains(response, 'Oficial')

    def test_nao_mostra_cenario_de_outra_cooperativa(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        Cenario.all_cooperativas.create(cooperativa=outra_cooperativa, nome='Cenário B')
        self.client.force_login(self.user)

        response = self.client.get(reverse('simulacao:cenarios_list'))

        self.assertNotContains(response, 'Cenário B')

    def test_post_cria_cenario_por_clonagem(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('simulacao:cenarios_list'), {
            'nome': 'Simulação Nova', 'origem_id': self.oficial.id,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Cenario.all_cooperativas.filter(cooperativa=self.cooperativa, nome='Simulação Nova').exists())
