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
# Abas do cenário abertas a qualquer papel de membro (@requer_membro_organizacao).
ABAS_CENARIO_MEMBRO = [
    "simulacao:rotas_grid", "simulacao:previsoes_grid", "simulacao:safras_grid",
    "simulacao:simulacao_tab", "simulacao:assistente_tab",
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
        cls.usuario_armazem = User.objects.create_user(
            username="ua", email="ua@t.test", password="x",
            papel=User.PAPEL_USUARIO_ARMAZEM, cooperativa=cls.coop,
        )

    @property
    def _papeis_de_membro(self):
        return (self.admin_coop, self.usuario_fabrica, self.usuario_armazem)

    def test_telas_de_membro(self):
        for user in self._papeis_de_membro:
            self.client.force_login(user)
            for nome, kw in ROTAS_MEMBRO:
                r = self.client.get(reverse(nome, kwargs=kw))
                self.assertEqual(r.status_code, 200, f"{nome} ({user.papel})")

    def test_abas_comuns_do_cenario(self):
        for user in self._papeis_de_membro:
            self.client.force_login(user)
            for nome in ABAS_CENARIO_MEMBRO:
                r = self.client.get(reverse(nome, kwargs={"cenario_id": self.cenario.id}))
                self.assertEqual(r.status_code, 200, f"{nome} ({user.papel})")

    def test_abas_editaveis_do_cenario_por_papel(self):
        matriz = (
            ("simulacao:fabricas_grid", (
                (self.admin_coop, 200), (self.usuario_fabrica, 200), (self.usuario_armazem, 403),
            )),
            ("simulacao:armazens_grid", (
                (self.admin_coop, 200), (self.usuario_armazem, 200), (self.usuario_fabrica, 403),
            )),
        )
        for nome, casos in matriz:
            for user, esperado in casos:
                self.client.force_login(user)
                r = self.client.get(reverse(nome, kwargs={"cenario_id": self.cenario.id}))
                self.assertEqual(r.status_code, esperado, f"{nome} ({user.papel})")

    def test_403_template(self):
        self.client.force_login(self.usuario_armazem)
        r = self.client.get(
            reverse("simulacao:fabricas_grid", kwargs={"cenario_id": self.cenario.id})
        )
        self.assertEqual(r.status_code, 403)
        self.assertTemplateUsed(r, "403.html")

    # socialaccount/authentication_error.html não é coberto aqui: a rota
    # `socialaccount_login_error` responde 401 sem o estado de sessão do fluxo
    # OAuth (não é cheaply reachable a partir de um GET nu).

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
