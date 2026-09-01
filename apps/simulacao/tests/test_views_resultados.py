import datetime

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

User = get_user_model()


class ResultadosViewTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self.user = User.objects.create_user(
            username="u", email="u@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop)
        self.cen = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Cen", is_oficial=True)
        self.url = reverse("simulacao:resultados_tab", kwargs={"cenario_id": self.cen.id})

    def _povoar(self):
        arm = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, data=datetime.date(2026, 1, 5),
            armazem=arm, fabrica=fab, quantidade_ton=10, custo_total=100)

    def test_requer_login(self):
        self.assertIn("/accounts/login/", self.client.get(self.url).url)

    def test_admin_vector_sem_org_403(self):
        v = User.objects.create_user(username="v", email="v@t.test", password="x",
                                     papel=User.PAPEL_ADMIN_VECTOR)
        self.client.force_login(v)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_estado_vazio_sem_simulacao(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Nenhum resultado")

    def test_pagina_completa_com_dados(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, "<html")
        self.assertContains(r, "ARM".replace("ARM", "A"))  # nome do armazém na linha crua

    def test_parcial_htmx(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "<html")

    def test_troca_para_mensal_muda_colunas(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"periodo": "mensal", "agrupar": "nada"},
                            HTTP_HX_REQUEST="true")
        self.assertContains(r, "Mês")

    def test_comparacao_gera_colunas_delta(self):
        self._povoar()
        comp = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Comp")
        a = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=comp, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        f = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=comp, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=comp, data=datetime.date(2026, 1, 5),
            armazem=a, fabrica=f, quantidade_ton=8, custo_total=125)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"periodo": "mensal", "agrupar": "nada",
                                       "comparar": comp.id}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Δ%")

    def test_cenario_de_outra_coop_404(self):
        outra = Cooperativa.objects.create(nome="D", slug="d")
        cen_b = Cenario.all_cooperativas.create(cooperativa=outra, nome="B")
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:resultados_tab", kwargs={"cenario_id": cen_b.id}))
        self.assertEqual(r.status_code, 404)

    def test_paginacao_parcial_tabela(self):
        self._povoar()
        arm = Armazem.all_cooperativas.filter(cenario=self.cen).first()
        fab = Fabrica.all_cooperativas.filter(cenario=self.cen).first()
        for i in range(1, 151):
            MovimentacaoDiaria.all_cooperativas.create(
                cooperativa=self.coop, cenario=self.cen,
                data=datetime.date(2026, 3, 1) + datetime.timedelta(days=i),
                armazem=arm, fabrica=fab, quantidade_ton=1, custo_total=1)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"parcial": "tabela", "page": 2}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "resultados-area")  # só a tabela

    def test_aba_desabilitada_no_subnav_sem_resultado(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:simulacao_tab", kwargs={"cenario_id": self.cen.id}))
        self.assertContains(r, "tab-disabled")

    def test_aba_habilitada_com_resultado(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:simulacao_tab", kwargs={"cenario_id": self.cen.id}))
        self.assertNotContains(r, "tab-disabled")
