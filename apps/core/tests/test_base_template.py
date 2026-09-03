from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Cooperativa

User = get_user_model()


class BaseTemplateTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="Coop A", slug="coop-a")
        self.membro = User.objects.create_user(
            username="m", email="m@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )
        self.vector = User.objects.create_user(
            username="v", email="v@t.test", password="x", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def test_membro_ve_faixa_de_modulos_e_nao_ve_seletor(self):
        self.client.force_login(self.membro)
        html = self.client.get("/").content.decode()
        self.assertIn("Carga de Dados", html)
        self.assertIn("Coop A", html)
        self.assertNotIn('name="org_id"', html)
        self.assertNotIn("grao-e-aco", html)
        self.assertIn('data-theme="vector"', html)

    def test_toggle_de_tema_dispara_evento(self):
        self.client.force_login(self.membro)
        html = self.client.get("/").content.decode()
        # a função de tema notifica quem desenha gráfico
        self.assertIn("vector:themechange", html)
        self.assertIn("function vectorApplyTheme", html)

    def test_token_chart_frete_tem_par_claro_escuro(self):
        self.client.force_login(self.membro)
        html = self.client.get("/").content.decode()
        # série "Frete" do gráfico: âmbar-700 no claro, âmbar-400 no escuro
        # (navy `primary` fica ilegível sobre o base-100 escuro)
        self.assertIn("--color-chart-frete: #b45309", html)
        self.assertIn("--color-chart-frete: #fbbf24", html)

    def test_admin_vector_sem_org_ve_seletor_e_so_o_modulo_inicio(self):
        self.client.force_login(self.vector)
        html = self.client.get("/").content.decode()
        self.assertIn('name="org_id"', html)
        self.assertIn("— Consolidado —", html)
        self.assertNotIn("Carga de Dados", html)
