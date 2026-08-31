from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from apps.core.models import Cooperativa


class AdminUnfoldTests(TestCase):
    def test_cooperativa_admin_e_unfold(self):
        self.assertIsInstance(admin.site._registry[Cooperativa], UnfoldModelAdmin)

    def test_user_admin_e_unfold(self):
        self.assertIsInstance(admin.site._registry[get_user_model()], UnfoldModelAdmin)

    def test_admin_index_renderiza(self):
        u = get_user_model().objects.create_superuser(
            username="s", email="s@t.test", password="x", papel="admin_vector",
        )
        self.client.force_login(u)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_user_change_form_renderiza(self):
        u = get_user_model().objects.create_superuser(
            username="s", email="s@t.test", password="x", papel="admin_vector",
        )
        self.client.force_login(u)
        self.assertEqual(
            self.client.get(f"/admin/core/user/{u.pk}/change/").status_code, 200
        )

    def test_user_add_form_renderiza(self):
        u = get_user_model().objects.create_superuser(
            username="s", email="s@t.test", password="x", papel="admin_vector",
        )
        self.client.force_login(u)
        self.assertEqual(self.client.get("/admin/core/user/add/").status_code, 200)
