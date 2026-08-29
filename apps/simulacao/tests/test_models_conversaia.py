from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao.models import Cenario, ConversaIA

User = get_user_model()


class ConversaIAModelTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='u', email='u@coop-a.test', password='x', cooperativa=self.coop,
            papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='C1')

    def test_defaults_and_adicionar(self):
        c = ConversaIA.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, usuario=self.user,
        )
        self.assertEqual(c.mensagens, [])
        self.assertTrue(c.ativa)
        c.adicionar('user', 'olá')
        c.adicionar('assistant', 'oi')
        c.save()
        c.refresh_from_db()
        self.assertEqual([m['papel'] for m in c.mensagens], ['user', 'assistant'])
        self.assertIn('ts', c.mensagens[0])

    def test_tenant_isolation(self):
        ConversaIA.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, usuario=self.user,
        )
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')

        token = definir_cooperativa_atual(coop_b.id)
        try:
            self.assertEqual(ConversaIA.objects.count(), 0)
        finally:
            resetar_cooperativa_atual(token)

        token = definir_cooperativa_atual(self.coop.id)
        try:
            self.assertEqual(ConversaIA.objects.count(), 1)
        finally:
            resetar_cooperativa_atual(token)
