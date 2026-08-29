from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.core.models import Cooperativa
from apps.simulacao import assistente, services
from apps.simulacao.models import Cenario, ConversaIA

User = get_user_model()


class FerramentasTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='C1')

    def test_closures_bind_cenario_and_delegate_to_services(self):
        ferramentas = {f.__name__: f for f in assistente._fazer_ferramentas(self.cenario)}
        self.assertEqual(
            set(ferramentas),
            {'list_scenarios', 'get_daily_movements', 'get_monthly_summary',
             'get_factories_summary', 'get_warehouses_summary', 'compare_factories',
             'compare_warehouses', 'get_stock_excesses_report', 'get_stock_ruptures_report'},
        )
        with patch.object(services, 'get_stock_excesses_report', return_value=[]) as spy:
            ferramentas['get_stock_excesses_report']()
        spy.assert_called_once_with(scenario_id=self.cenario.id)

        with patch.object(services, 'list_scenarios', return_value=[]) as spy:
            ferramentas['list_scenarios']()
        spy.assert_called_once_with(cooperativa_id=self.coop.id)


@override_settings(GEMINI_API_KEY='')
class AssistenteIndisponivelTests(TestCase):
    def test_get_client_raises_without_key(self):
        with self.assertRaises(assistente.AssistenteIndisponivel):
            assistente._get_client()


@override_settings(GEMINI_API_KEY='fake-key')
class ResponderTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='u', email='u@coop-a.test', password='x', cooperativa=self.coop,
            papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='C1')
        self.conversa = ConversaIA.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, usuario=self.user,
        )

    def _fake_client(self, texto='Resposta do assistente.'):
        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text=texto)
        client = MagicMock()
        client.chats.create.return_value = chat
        return client

    def test_persists_both_turns_and_sets_title(self):
        with patch.object(assistente, '_get_client', return_value=self._fake_client()):
            out = assistente.responder(self.conversa, 'Quais fábricas têm excedente?')
        self.assertEqual(out, 'Resposta do assistente.')
        self.conversa.refresh_from_db()
        papeis = [m['papel'] for m in self.conversa.mensagens]
        self.assertEqual(papeis, ['user', 'assistant'])
        self.assertEqual(self.conversa.mensagens[0]['conteudo'], 'Quais fábricas têm excedente?')
        self.assertTrue(self.conversa.titulo)

    def test_gemini_error_becomes_assistant_message_not_exception(self):
        chat = MagicMock()
        chat.send_message.side_effect = RuntimeError('boom')
        client = MagicMock()
        client.chats.create.return_value = chat
        with patch.object(assistente, '_get_client', return_value=client):
            out = assistente.responder(self.conversa, 'oi')
        self.assertIn('erro', out.lower())
        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.mensagens[-1]['papel'], 'assistant')
