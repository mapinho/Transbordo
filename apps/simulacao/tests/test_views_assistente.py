from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario, ConversaIA

User = get_user_model()


class AssistenteViewsTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='u', email='u@coop-a.test', password='senha-forte-123', cooperativa=self.coop,
            papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='C1')
        self.url_tab = reverse('simulacao:assistente_tab', kwargs={'cenario_id': self.cenario.id})
        self.url_enviar = reverse('simulacao:assistente_enviar', kwargs={'cenario_id': self.cenario.id})
        self.url_nova = reverse('simulacao:assistente_nova', kwargs={'cenario_id': self.cenario.id})

    def test_requer_login(self):
        self.assertEqual(self.client.get(self.url_tab).status_code, 302)

    def test_tab_cria_conversa_ativa_na_primeira_visita(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url_tab)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ConversaIA.all_cooperativas.filter(
                cenario=self.cenario, usuario=self.user, ativa=True).count(),
            1,
        )

    def test_enviar_persiste_turnos(self):
        self.client.force_login(self.user)
        self.client.get(self.url_tab)  # cria a conversa ativa

        def fake_responder(conversa, mensagem):
            conversa.adicionar('user', mensagem)
            conversa.adicionar('assistant', 'resposta')
            conversa.save()
            return 'resposta'

        with patch('apps.simulacao.views.assistente.responder', side_effect=fake_responder) as spy:
            response = self.client.post(self.url_enviar, {'mensagem': 'olá'})
        self.assertEqual(response.status_code, 200)
        spy.assert_called_once()
        self.assertContains(response, 'resposta')
        conversa = ConversaIA.all_cooperativas.get(
            cenario=self.cenario, usuario=self.user, ativa=True)
        self.assertEqual([m['papel'] for m in conversa.mensagens], ['user', 'assistant'])

    def test_nova_arquiva_a_ativa(self):
        self.client.force_login(self.user)
        self.client.get(self.url_tab)
        antiga = ConversaIA.all_cooperativas.get(
            cenario=self.cenario, usuario=self.user, ativa=True)
        self.client.post(self.url_nova)
        antiga.refresh_from_db()
        self.assertFalse(antiga.ativa)
        self.assertEqual(
            ConversaIA.all_cooperativas.filter(
                cenario=self.cenario, usuario=self.user, ativa=True).count(),
            1,
        )

    def test_isolamento_cross_tenant(self):
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        user_b = User.objects.create_user(
            username='b', email='b@coop-b.test', password='senha-forte-123', cooperativa=coop_b,
            papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.client.force_login(user_b)
        self.assertEqual(self.client.get(self.url_tab).status_code, 404)

    @override_settings(GEMINI_API_KEY='')
    def test_tab_mostra_aviso_sem_chave(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url_tab)
        self.assertContains(response, 'indisponível')
