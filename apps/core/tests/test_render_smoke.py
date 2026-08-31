from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario

User = get_user_model()

ROTAS_MEMBRO = [
    ("core:home", {}),
    ("simulacao:cenarios_list", {}),
    ("simulacao:carga", {}),
    ("gestao:conta", {}),
]
ROTAS_CENARIO = [
    "simulacao:fabricas_grid", "simulacao:armazens_grid", "simulacao:rotas_grid",
    "simulacao:previsoes_grid", "simulacao:safras_grid", "simulacao:simulacao_tab",
    "simulacao:assistente_tab",
]


class RenderSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coop = Cooperativa.objects.create(nome="Coop A", slug="coop-a")
        cls.cenario = Cenario.all_cooperativas.create(
            cooperativa=cls.coop, nome="Oficial", is_oficial=True,
        )
        cls.admin_coop = User.objects.create_user(
            username="ac", email="ac@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=cls.coop,
        )
        cls.vector = User.objects.create_user(
            username="v", email="v@t.test", password="x", papel=User.PAPEL_ADMIN_VECTOR,
        )
        cls.usuario_fabrica = User.objects.create_user(
            username="uf", email="uf@t.test", password="x",
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=cls.coop,
        )

    def test_telas_de_membro(self):
        self.client.force_login(self.admin_coop)
        for nome, kw in ROTAS_MEMBRO:
            r = self.client.get(reverse(nome, kwargs=kw))
            self.assertEqual(r.status_code, 200, nome)

    def test_abas_do_cenario(self):
        self.client.force_login(self.admin_coop)
        for nome in ROTAS_CENARIO:
            r = self.client.get(reverse(nome, kwargs={"cenario_id": self.cenario.id}))
            self.assertEqual(r.status_code, 200, nome)

    def test_gestao_forms(self):
        self.client.force_login(self.vector)
        for nome, kw in (
            ("gestao:cooperativa_nova", {}),
            ("gestao:cooperativa_editar", {"cooperativa_id": self.coop.id}),
            ("gestao:usuario_novo", {}),
            ("gestao:usuario_editar", {"usuario_id": self.usuario_fabrica.id}),
        ):
            r = self.client.get(reverse(nome, kwargs=kw))
            self.assertEqual(r.status_code, 200, nome)
        # minha_cooperativa é gated por e_admin_cooperativa (admin_vector recebe 403 lá)
        self.client.force_login(self.admin_coop)
        r = self.client.get(reverse("gestao:minha_cooperativa"))
        self.assertEqual(r.status_code, 200, "gestao:minha_cooperativa")

    def test_home_consolidado_admin_vector(self):
        self.client.force_login(self.vector)
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)

    def test_gestao_admin_vector(self):
        self.client.force_login(self.vector)
        for nome in ("gestao:cooperativas", "gestao:usuarios", "gestao:conta"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200, nome)

    def test_auth_screens_anonimo(self):
        for nome in ("account_login", "account_reset_password"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200, nome)
