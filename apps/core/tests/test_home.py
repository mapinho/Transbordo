from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario

User = get_user_model()


class HomeRoutingTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="Coop A", slug="coop-a")
        Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Oficial", is_oficial=True)
        self.membro = User.objects.create_user(
            username="m", email="m@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )
        self.vector = User.objects.create_user(
            username="v", email="v@t.test", password="x", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def test_home_exige_login(self):
        self.assertIn("/accounts/login/", self.client.get(reverse("core:home")).url)

    def test_membro_ve_home_da_organizacao(self):
        self.client.force_login(self.membro)
        r = self.client.get(reverse("core:home"))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "core/home_organizacao.html")
        self.assertContains(r, "Coop A")

    def test_admin_vector_sem_org_ve_consolidado(self):
        self.client.force_login(self.vector)
        r = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(r, "core/home_consolidado.html")

    def test_admin_vector_com_org_ve_home_da_organizacao(self):
        self.client.force_login(self.vector)
        self.client.post(reverse("core:selecionar_organizacao"), {"org_id": self.coop.id})
        r = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(r, "core/home_organizacao.html")

    def test_login_redireciona_para_raiz(self):
        r = self.client.post(reverse("account_login"), {"login": "m", "password": "x"})
        self.assertEqual(r.url, "/")
