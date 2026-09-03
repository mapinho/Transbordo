# apps/simulacao/tests/test_views_estoque.py
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, ResumoMensalArmazem, ResumoMensalFabrica,
)

User = get_user_model()


class EstoqueViewTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="C", slug="c")
        self.user = User.objects.create_user(
            username="u", email="u@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop)
        self.cen = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Cen", is_oficial=True)
        self.url = reverse("simulacao:estoque_tab", kwargs={"cenario_id": self.cen.id})

    def _povoar(self, cenario=None, saldo=50, excedente=0):
        cenario = cenario or self.cen
        arm = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, nome="A",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0)
        fab = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, nome="F",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0)
        ResumoMensalArmazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, armazem=arm, mes="2026-01",
            rec_produtor=100, envio_transbordo=20, vendas=5, saldo_estoque=saldo,
            capacidade_estatica=200, excedente=excedente)
        ResumoMensalFabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=cenario, fabrica=fab, mes="2026-01",
            rec_produtor=0, rec_transbordo=20, esmagado=10, saldo_estoque=10,
            capacidade_estatica=300, excedente=0)
        return arm, fab

    def test_requer_login(self):
        self.assertIn("/accounts/login/", self.client.get(self.url).url)

    def test_admin_vector_sem_org_403(self):
        v = User.objects.create_user(username="v", email="v@t.test", password="x",
                                     papel=User.PAPEL_ADMIN_VECTOR)
        self.client.force_login(v)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_estado_vazio(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Nenhum resultado de estoque")

    def test_pagina_completa(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, "<html")
        self.assertContains(r, "Recebimento")   # coluna da visão Sistema (default)

    def test_parcial_htmx(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertNotContains(r, "<html")

    def test_hx_target_tabela_renderiza_so_a_tabela(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="estoque-tabela")
        self.assertContains(r, "<table")
        self.assertNotContains(r, "form-estoque")
        self.assertNotContains(r, "stat-title")

    def test_hx_target_area_renderiza_so_a_area(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="estoque-area")
        self.assertContains(r, "stat-title")
        self.assertContains(r, "Recebimento")
        self.assertNotContains(r, "form-estoque")

    def test_parcial_tabela_por_querystring(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"parcial": "tabela", "page": 2},
                            HTTP_HX_REQUEST="true")
        self.assertContains(r, "<table")
        self.assertNotContains(r, "form-estoque")

    def test_troca_para_armazem_muda_colunas(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "armazem"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Envio Transbordo")

    def test_comparacao_gera_delta_embutido(self):
        self._povoar()
        comp = Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Comp")
        self._povoar(cenario=comp, saldo=30)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "sistema", "comparar": comp.id},
                            HTTP_HX_REQUEST="true")
        self.assertNotContains(r, "Δ%")          # não é mais cabeçalho de coluna
        self.assertContains(r, "↑")              # Δ renderizado inline (saldo 50 vs 30 → +66,7%)
        self.assertContains(r, "leading-tight")  # o span do Δ embutido

    def test_faixa_de_mes_na_visao_por_unidade(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "armazem"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "sistema — saldo")
        self.assertNotContains(r, ">Mês<")   # coluna Mês saiu

    def test_ruptura_mostra_simbolo_na_1a_coluna_visao_sistema(self):
        # SPEC §5: `⚠` no início da 1ª coluna em QUALQUER visão quando ruptura.
        # A visão Sistema tem `mes` como 1ª coluna (sem coluna de texto).
        self._povoar(saldo=-100)   # armazém -100 + fábrica 10 = sistema -90 < 0
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "sistema"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "⚠")

    def test_sinalizacao_excedente(self):
        self._povoar(excedente=40)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"visao": "armazem"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "bg-error/10")
        self.assertContains(r, "border-l-4 border-error")

    def test_card_de_pico_no_html(self):
        self._povoar(excedente=40)
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Pico do sistema")
        self.assertContains(r, "Esmagamento")   # agora no card
        self.assertContains(r, "bg-accent")     # a barra de ocupação
        # A largura da barra vai no atributo `style` — precisa sair NÃO-localizada
        # (ponto decimal), senão o pt-BR gera `width: 12,0%` (CSS inválido, some).
        self.assertContains(r, "width: 12.0%")
        self.assertNotContains(r, "width: 12,0%")

    def test_badge_de_filtros_oob_no_swap_da_area(self):
        # SPEC §4 / achado: o <summary> não é re-renderizado no swap da área;
        # a área emite um fragmento OOB que atualiza o contador.
        arm, _ = self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"armazem_ids": [arm.id]},
                            HTTP_HX_REQUEST="true", HTTP_HX_TARGET="estoque-area")
        self.assertContains(r, 'id="estoque-filtros-badge"')
        self.assertContains(r, 'hx-swap-oob="true"')
        self.assertContains(r, '<span class="badge badge-sm badge-neutral">1</span>')

    def test_badge_conta_filtros_avancados_ativos(self):
        arm, _ = self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"mes_de": "2026-01", "armazem_ids": [arm.id]},
                            HTTP_HX_REQUEST="true")
        self.assertContains(r, '<span class="badge badge-sm badge-neutral">2</span>')

    def test_grafico_escondido_no_mobile(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(r, "hidden sm:block")
        # defaults do Chart.js tematizados (cobre o eixo x / gridlines verticais)
        self.assertContains(r, "Chart.defaults.color")

    def test_legenda_de_unidade(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Valores em toneladas")

    def test_thead_fixo_so_na_visao_por_unidade(self):
        self._povoar()
        self.client.force_login(self.user)
        sis = self.client.get(self.url, {"visao": "sistema"}, HTTP_HX_REQUEST="true")
        arm = self.client.get(self.url, {"visao": "armazem"}, HTTP_HX_REQUEST="true")
        self.assertNotContains(sis, "sticky top-0")
        self.assertContains(arm, "sticky top-0")
        self.assertContains(arm, "sticky left-0")

    def test_cenario_de_outra_coop_404(self):
        outra = Cooperativa.objects.create(nome="D", slug="d")
        cen_b = Cenario.all_cooperativas.create(cooperativa=outra, nome="B")
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:estoque_tab", kwargs={"cenario_id": cen_b.id}))
        self.assertEqual(r.status_code, 404)

    def test_comparar_nao_numerico_nao_quebra(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"comparar": "xyz"}, HTTP_HX_REQUEST="true")
        self.assertEqual(r.status_code, 200)

    def test_barra_de_filtros_recolhida_por_default(self):
        self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_HX_REQUEST="true")
        self.assertContains(r, "<details")
        self.assertContains(r, 'id="estoque-visao"')
        self.assertNotContains(r, "<details open")

    def test_barra_de_filtros_abre_com_filtro_ativo(self):
        arm, _ = self._povoar()
        self.client.force_login(self.user)
        r = self.client.get(self.url, {"armazem_ids": [arm.id]}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "<details open")
        self.assertContains(r, "badge badge-sm")   # contador

    def test_aba_desabilitada_sem_simulacao(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:simulacao_tab", kwargs={"cenario_id": self.cen.id}))
        self.assertContains(r, "tab-disabled")

    def test_aba_habilitada_com_movimentacao(self):
        from apps.simulacao.models import MovimentacaoDiaria
        import datetime
        arm, fab = self._povoar()
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cen, data=datetime.date(2026, 1, 5),
            armazem=arm, fabrica=fab, quantidade_ton=1, custo_total=1)
        self.client.force_login(self.user)
        r = self.client.get(reverse("simulacao:simulacao_tab", kwargs={"cenario_id": self.cen.id}))
        # a aba Estoque só habilita quando há MovimentacaoDiaria (cenario_tem_simulacao)
        self.assertNotContains(r, 'title="Rode uma simulação"')
