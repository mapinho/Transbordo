from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Cooperativa

User = get_user_model()


class VersionFooterTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='u', email='u@coop-a.test', password='senha-forte-123',
            cooperativa=self.coop, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )

    def test_footer_shows_version(self):
        self.client.force_login(self.user)
        response = self.client.get('/simulacao/cenarios/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'v{settings.APP_VERSION}')
