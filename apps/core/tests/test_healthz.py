from django.conf import settings
from django.test import TestCase


class HealthzTests(TestCase):
    def test_healthz_returns_version_json(self):
        response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json(), {'version': settings.APP_VERSION})

    def test_healthz_needs_no_auth(self):
        # no login — must still answer
        self.assertEqual(self.client.get('/healthz/').status_code, 200)
