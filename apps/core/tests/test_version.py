from pathlib import Path

from django.conf import settings
from django.test import TestCase


class AppVersionTests(TestCase):
    def test_app_version_matches_version_file(self):
        version_file = Path(settings.BASE_DIR) / 'VERSION'
        self.assertTrue(version_file.exists(), 'VERSION file must exist at repo root')
        self.assertEqual(settings.APP_VERSION, version_file.read_text().strip())

    def test_app_version_is_semver_shaped(self):
        parts = settings.APP_VERSION.split('.')
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(p.isdigit() for p in parts), settings.APP_VERSION)
