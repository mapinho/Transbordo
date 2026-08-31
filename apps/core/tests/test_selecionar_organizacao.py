from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa

User = get_user_model()


class SelecionarOrganizacaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="A", slug="a")
        self.inativa = Cooperativa.objects.create(nome="Z", slug="z", ativo=False)
        self.vector = User.objects.create_user(
            username="v", email="v@t.test", password="x", papel=User.PAPEL_ADMIN_VECTOR,
        )
        self.membro = User.objects.create_user(
            username="m", email="m@t.test", password="x",
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.coop,
        )

    def test_grava_e_limpa_sessao(self):
        self.client.force_login(self.vector)
        self.client.post(reverse("core:selecionar_organizacao"), {"org_id": self.coop.id})
        self.assertEqual(self.client.session["org_corrente_id"], self.coop.id)
        self.client.post(reverse("core:selecionar_organizacao"), {"org_id": ""})
        self.assertNotIn("org_corrente_id", self.client.session)

    def test_ignora_id_inativo(self):
        self.client.force_login(self.vector)
        self.client.post(reverse("core:selecionar_organizacao"), {"org_id": self.inativa.id})
        self.assertNotIn("org_corrente_id", self.client.session)

    def test_membro_recebe_403(self):
        self.client.force_login(self.membro)
        self.assertEqual(
            self.client.post(reverse("core:selecionar_organizacao"), {"org_id": self.coop.id}).status_code,
            403,
        )

    def test_get_nao_permitido(self):
        self.client.force_login(self.vector)
        self.assertEqual(self.client.get(reverse("core:selecionar_organizacao")).status_code, 405)
