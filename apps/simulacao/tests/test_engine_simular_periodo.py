import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.core.models import Cooperativa
from apps.simulacao import engine
from apps.simulacao.models import (
    Armazem,
    Cenario,
    Fabrica,
    LogExecucao,
    MovimentacaoDiaria,
    PrevisaoArmazem,
    PrevisaoFabrica,
    ResumoMensalFabrica,
    Rota,
    SafraUnidade,
)


def _montar_cenario_zerado(cooperativa, cenario, estoque_armazem=0):
    fabrica = Fabrica.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, nome='Fábrica 1',
        capacidade_estatica=100000, capacidade_esmagamento_diaria=1000,
        capacidade_recebimento_diaria=1000, limite_caminhoes=50,
        carga_media_caminhao=30, estoque_inicial=0,
    )
    armazem = Armazem.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, nome='Armazém 1',
        capacidade_estatica=50000, capacidade_expedicao_diaria=1000,
        estoque_inicial=estoque_armazem,
    )
    rota = Rota.all_cooperativas.create(
        cooperativa=cooperativa, cenario=cenario, armazem=armazem, fabrica=fabrica,
        distancia_km=10, custo_frete_ton=5.0, custo_frete_entressafra=8.0,
    )
    return fabrica, armazem, rota


class SimularPeriodoAtomicidadeTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica, self.armazem, self.rota = _montar_cenario_zerado(self.cooperativa, self.cenario)

    def test_nao_perde_dados_em_falha_no_meio_do_loop(self):
        mov_existente = MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 20), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=123.45, custo_total=999.99,
        )
        self.assertEqual(
            MovimentacaoDiaria.all_cooperativas.filter(cenario_id=self.cenario.id).count(), 1
        )

        original_otimizar_dia = engine.otimizar_dia

        def _falha_forcada(*args, **kwargs):
            raise RuntimeError('forced failure')

        engine.otimizar_dia = _falha_forcada
        try:
            with self.assertRaisesMessage(RuntimeError, 'forced failure'):
                engine.simular_periodo(
                    data_inicio=datetime.date(2026, 1, 20),
                    data_fim_previsao=datetime.date(2026, 1, 25),
                    cenario_id=self.cenario.id,
                )
        finally:
            engine.otimizar_dia = original_otimizar_dia

        count_apos_falha = MovimentacaoDiaria.all_cooperativas.filter(cenario_id=self.cenario.id).count()
        self.assertGreaterEqual(count_apos_falha, 1, 'MovimentacaoDiaria anterior foi perdida após falha (bug C1).')

        logs = LogExecucao.all_cooperativas.filter(cenario_id=self.cenario.id).count()
        self.assertEqual(logs, 0, 'Nenhum LogExecucao de sucesso deve sobreviver a uma execução que falhou.')


class SimularPeriodoObservabilidadeTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Fase4')
        _montar_cenario_zerado(self.cooperativa, self.cenario)

    def test_sucesso_grava_log_execucao(self):
        dias = 7
        data_inicio = datetime.date(2026, 1, 1)
        data_fim = data_inicio + datetime.timedelta(days=dias - 1)

        engine.simular_periodo(data_inicio, data_fim, cenario_id=self.cenario.id)

        logs = list(LogExecucao.all_cooperativas.filter(cenario_id=self.cenario.id))
        self.assertEqual(len(logs), 1)

        log = logs[0]
        self.assertEqual(log.status, 'sucesso')
        self.assertEqual(log.cenario_id, self.cenario.id)
        self.assertIsNotNone(log.duracao_segundos)
        self.assertGreaterEqual(log.duracao_segundos, 0)
        self.assertEqual(log.dias_simulados, dias)


class SimularPeriodoPerformanceTests(TestCase):
    def _run(self, dias, sufixo):
        cooperativa = Cooperativa.objects.create(nome=f'Coop {sufixo}', slug=f'coop-{sufixo}')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome=f'C{sufixo}')
        # estoque_armazem folgado o bastante para nunca esvaziar dentro do
        # período simulado (capacidade_expedicao_diaria/capacidade_esmagamento_diaria
        # = 1000 ton/dia): garante que otimizar_dia produza uma MovimentacaoDiaria
        # real em todos os `dias` dias, exercitando de fato o caminho de escrita
        # em lote que este teste precisa proteger (bug/finding: bulk_create).
        fabrica, armazem, rota = _montar_cenario_zerado(
            cooperativa, cenario, estoque_armazem=dias * 2000
        )
        # Janela de safra cobrindo todo o período simulado -- sem isso, o
        # padrão (15/jan a 15/abr) bloquearia movimentação nos primeiros dias
        # de janeiro e o teste não provaria nada sobre o caminho de escrita.
        SafraUnidade.all_cooperativas.create(
            cooperativa=cooperativa, cenario=cenario, entidade_tipo='Armazém',
            entidade_id=armazem.id,
            data_inicio=datetime.date(2026, 1, 1), data_fim=datetime.date(2027, 1, 1),
        )

        data_inicio = datetime.date(2026, 1, 1)
        data_fim = data_inicio + datetime.timedelta(days=dias - 1)

        with CaptureQueriesContext(connection) as ctx:
            engine.simular_periodo(data_inicio, data_fim, cenario_id=cenario.id)

        movimentacoes_criadas = MovimentacaoDiaria.all_cooperativas.filter(cenario_id=cenario.id).count()
        self.assertGreaterEqual(
            movimentacoes_criadas, dias,
            'nenhuma (ou poucas) MovimentacaoDiaria criada -- o teste de performance '
            'não estaria exercitando o caminho de escrita.',
        )
        return len(ctx.captured_queries)

    def test_contagem_de_queries_nao_escala_com_dias(self):
        queries_10_dias = self._run(10, '10d')
        queries_40_dias = self._run(40, '40d')

        delta = queries_40_dias - queries_10_dias
        self.assertLess(
            delta, 10,
            f'contagem de queries cresceu {delta} entre 10 e 40 dias simulados '
            '(esperado: crescimento praticamente nulo)',
        )

    def test_usa_previsoes_pre_carregadas_e_mantem_resultado(self):
        cooperativa = Cooperativa.objects.create(nome='Coop Prev', slug='coop-prev')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='C Prev')
        fabrica, armazem, rota = _montar_cenario_zerado(cooperativa, cenario)

        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=cooperativa, fabrica=fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=3100, vendas=0,
        )
        PrevisaoArmazem.all_cooperativas.create(
            cooperativa=cooperativa, armazem=armazem,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=0, vendas=0,
        )

        data_inicio = datetime.date(2026, 1, 1)
        data_fim = data_inicio + datetime.timedelta(days=14)
        engine.simular_periodo(data_inicio, data_fim, cenario_id=cenario.id)

        resumo = ResumoMensalFabrica.all_cooperativas.filter(
            cenario_id=cenario.id, fabrica_id=fabrica.id
        ).first()
        self.assertIsNotNone(resumo)
        self.assertAlmostEqual(resumo.rec_produtor, 3100 / 31 * 15, places=2)


class ObterRangePrevisoesTests(TestCase):
    def test_sem_previsoes_retorna_none_none(self):
        cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Cenário Teste')

        start, end = engine.obter_range_previsoes(cenario_id=cenario.id)

        self.assertIsNone(start)
        self.assertIsNone(end)

    def test_com_previsoes_retorna_range_correto(self):
        cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        cenario = Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Cenário Teste')
        fabrica, armazem, _rota = _montar_cenario_zerado(cooperativa, cenario)

        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=cooperativa, fabrica=fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=100, vendas=0,
        )
        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=cooperativa, fabrica=fabrica,
            mes_referencia=datetime.date(2026, 3, 1), recebimento_produtor=100, vendas=0,
        )

        start, end = engine.obter_range_previsoes(cenario_id=cenario.id)

        self.assertEqual(start, datetime.date(2026, 1, 1))
        self.assertEqual(end, datetime.date(2026, 3, 31))
