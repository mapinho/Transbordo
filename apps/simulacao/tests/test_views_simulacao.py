import datetime

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from procrastinate import testing
from procrastinate.contrib.django import procrastinate_app

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario, LogExecucao

User = get_user_model()


# TransactionTestCase, not TestCase: run_worker() executes the task via Django's sync_to_async
# thread-pool machinery, which opens its own DB connection — one that can't see data held in
# TestCase's uncommitted per-test transaction. TransactionTestCase really commits, so the worker
# thread can see it.
class SimulacaoViewsTests(TransactionTestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(
            cooperativa=self.cooperativa, nome='Cenário Teste',
        )
        self.url_tab = reverse('simulacao:simulacao_tab', kwargs={'cenario_id': self.cenario.id})
        self.url_executar = reverse(
            'simulacao:simulacao_executar', kwargs={'cenario_id': self.cenario.id},
        )
        self.url_status = reverse('simulacao:simulacao_status', kwargs={'cenario_id': self.cenario.id})

        self._connector = testing.InMemoryConnector()
        self._ctx = procrastinate_app.current_app.replace_connector(self._connector)
        self.app = self._ctx.__enter__()
        self.addCleanup(self._ctx.__exit__, None, None, None)

    def test_requer_login(self):
        response = self.client.get(self.url_tab)
        self.assertEqual(response.status_code, 302)

    def test_pagina_completa_sem_htmx(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url_tab)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html')

    def test_pagina_completa_expoe_validacao_e_toast_de_erro_4xx(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url_tab)

        self.assertEqual(response.status_code, 200)
        conteudo = response.content.decode()
        self.assertEqual(conteudo.count(' required'), 2)
        self.assertIn('id="htmx-error-toast"', conteudo)
        self.assertIn('id="htmx-error-toast-text"', conteudo)
        self.assertIn('htmx:responseError', conteudo)

    def test_partial_com_htmx(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url_tab, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<html')

    def test_cenario_de_outra_cooperativa_404(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        cenario_b = Cenario.all_cooperativas.create(cooperativa=outra_cooperativa, nome='Cenário B')
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('simulacao:simulacao_tab', kwargs={'cenario_id': cenario_b.id})
        )

        self.assertEqual(response.status_code, 404)

    def test_executar_dispara_a_task_e_cria_log_em_andamento(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Econômico',
        })

        self.assertEqual(response.status_code, 200)
        log = LogExecucao.all_cooperativas.get(cenario_id=self.cenario.id)
        self.assertEqual(log.status, 'em_andamento')
        self.assertEqual(len(self.app.connector.jobs), 1)

    def test_executar_bloqueia_quando_ja_em_andamento_recente(self):
        LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Econômico',
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.app.connector.jobs), 0)

    def test_executar_permite_quando_em_andamento_e_orfao(self):
        antigo = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        antigo.data_execucao = timezone.now() - datetime.timedelta(minutes=31)
        antigo.save(update_fields=['data_execucao'])
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Econômico',
        })

        self.assertEqual(response.status_code, 200)
        antigo.refresh_from_db()
        self.assertEqual(antigo.status, 'erro')
        self.assertEqual(len(self.app.connector.jobs), 1)

    def test_executar_rejeita_periodo_vazio(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {'data_inicio': '', 'data_fim': '', 'estrategia': 'Econômico'})

        self.assertEqual(response.status_code, 400)

    def test_executar_rejeita_estrategia_invalida(self):
        self.client.force_login(self.user)

        response = self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Chuta e Reza',
        })

        self.assertEqual(response.status_code, 400)

    def test_status_mostra_nenhuma_execucao_quando_log_nao_existe(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url_status)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nenhuma simulação')

    def test_status_apos_execucao_completa_mostra_sucesso_e_para_o_polling(self):
        self.client.force_login(self.user)
        self.client.post(self.url_executar, {
            'data_inicio': '2026-01-01', 'data_fim': '2026-01-05', 'estrategia': 'Econômico',
        })
        self.app.run_worker(wait=False)

        response = self.client.get(self.url_status)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Concluída')
        self.assertNotContains(response, 'hx-trigger')
