from django.conf import settings
from django.test import TestCase


class Fase12ConfigTests(TestCase):
    def test_apps_de_ui_instalados(self):
        for app in ("django_tables2", "django_filters", "unfold"):
            self.assertIn(app, settings.INSTALLED_APPS)

    def test_unfold_antes_do_admin_contrib(self):
        apps = settings.INSTALLED_APPS
        self.assertLess(apps.index("unfold"), apps.index("django.contrib.admin"))

    def test_tables2_template_daisyui(self):
        self.assertEqual(settings.DJANGO_TABLES2_TEMPLATE, "django_tables2/tailwind.html")
