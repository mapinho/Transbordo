from django.test import TestCase
from procrastinate import testing
from procrastinate.contrib.django import procrastinate_app

from apps.core.models import Cooperativa
from apps.simulacao import tasks
from apps.simulacao.models import Armazem, Cenario, Fabrica, LogExecucao, Rota


def _montar_cenario_zerado(cooperativa, cenario):
    fabrica = Fabrica.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, nome='Fábrica 1',
        capacidade_estatica=100000, capacidade_esmagamento_diaria=1000,
        capacidade_recebimento_diaria=1000, limite_caminhoes=50,
        carga_media_caminhao=30, estoque_inicial=0,
    )
    armazem = Armazem.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, nome='Armazém 1',
        capacidade_estatica=50000, capacidade_expedicao_diaria=1000,
        estoque_inicial=500,
    )
    rota = Rota.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, armazem=armazem, fabrica=fabrica,
        distancia_km=10, custo_frete_ton=5.0, custo_frete_entressafra=8.0,
    )
    return fabrica, armazem, rota


class ExecutarSimulacaoTaskTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(
            cooperativa=self.cooperativa, nome='Cenário Teste',
        )
        _montar_cenario_zerado(self.cooperativa, self.cenario)

        self._connector = testing.InMemoryConnector()
        self._ctx = procrastinate_app.current_app.replace_connector(self._connector)
        self.app = self._ctx.__enter__()
        self.addCleanup(self._ctx.__exit__, None, None, None)

    def test_sucesso_apaga_o_marcador_e_engine_ja_criou_o_log_de_sucesso(self):
        log = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )

        tasks.executar_simulacao.defer(
            log_id=log.id, cenario_id=self.cenario.id,
            data_inicio='2026-01-01', data_fim='2026-01-05', estrategia='Econômico',
        )
        self.app.run_worker(wait=False)

        self.assertFalse(LogExecucao.all_cooperativas.filter(id=log.id).exists())
        log_sucesso = LogExecucao.all_cooperativas.filter(
            cenario_id=self.cenario.id, status='sucesso',
        ).latest('id')
        self.assertIsNotNone(log_sucesso.dias_simulados)

    def test_falha_atualiza_o_marcador_para_erro_com_mensagem_truncada(self):
        log = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        cenario_inexistente_id = self.cenario.id + 999999

        tasks.executar_simulacao.defer(
            log_id=log.id, cenario_id=cenario_inexistente_id,
            data_inicio='2026-01-01', data_fim='2026-01-05', estrategia='Econômico',
        )
        self.app.run_worker(wait=False)

        log.refresh_from_db()
        self.assertEqual(log.status, 'erro')
        self.assertIn('Cenario matching query does not exist', log.mensagem)

    def test_queueing_lock_impede_dois_disparos_para_o_mesmo_cenario(self):
        log_a = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        log_b = LogExecucao.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, status='em_andamento',
        )
        lock = f'simulacao-cenario-{self.cenario.id}'

        tasks.executar_simulacao.configure(lock=lock, queueing_lock=lock).defer(
            log_id=log_a.id, cenario_id=self.cenario.id,
            data_inicio='2026-01-01', data_fim='2026-01-05', estrategia='Econômico',
        )

        from procrastinate.exceptions import AlreadyEnqueued
        with self.assertRaises(AlreadyEnqueued):
            tasks.executar_simulacao.configure(lock=lock, queueing_lock=lock).defer(
                log_id=log_b.id, cenario_id=self.cenario.id,
                data_inicio='2026-01-01', data_fim='2026-01-05', estrategia='Econômico',
            )
