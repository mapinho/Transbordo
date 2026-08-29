from unittest.mock import patch

from django.conf import settings
from django.db.utils import OperationalError
from django.test import TestCase


class HealthzTests(TestCase):
    def test_healthz_ok_returns_version_and_db_ok(self):
        response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json(), {'version': settings.APP_VERSION, 'db': 'ok'})

    def test_healthz_needs_no_auth(self):
        self.assertEqual(self.client.get('/healthz/').status_code, 200)

    def test_healthz_503_when_db_down(self):
        with patch('apps.core.views.connection') as conn:
            conn.cursor.side_effect = OperationalError('connection refused')
            response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {'version': settings.APP_VERSION, 'db': 'erro'})
