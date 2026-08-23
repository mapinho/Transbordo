import datetime

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.core.models import Cooperativa
from apps.simulacao import services
from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria


class ListScenariosTests(TestCase):
    def test_lista_ordenada_por_oficial_depois_nome(self):
        cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Zebra', is_oficial=False)
        Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Oficial', is_oficial=True)
        Cenario.all_cooperativas.create(cooperativa=cooperativa, nome='Alfa', is_oficial=False)

        resultado = services.list_scenarios(cooperativa.id)

        self.assertEqual([r['nome'] for r in resultado], ['Oficial', 'Alfa', 'Zebra'])
        self.assertTrue(resultado[0]['is_oficial'])

    def test_nao_vaza_cenarios_de_outra_cooperativa(self):
        cooperativa_a = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        cooperativa_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        Cenario.all_cooperativas.create(cooperativa=cooperativa_a, nome='Cenário A1', is_oficial=True)
        Cenario.all_cooperativas.create(cooperativa=cooperativa_a, nome='Cenário A2', is_oficial=False)
        Cenario.all_cooperativas.create(cooperativa=cooperativa_b, nome='Cenário B1', is_oficial=True)

        resultado = services.list_scenarios(cooperativa_a.id)

        self.assertEqual(
            sorted(r['nome'] for r in resultado), ['Cenário A1', 'Cenário A2']
        )
        self.assertNotIn('Cenário B1', [r['nome'] for r in resultado])


class GetDailyMovementsTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_retorna_movimentacoes_com_nomes_e_conversao_para_sacas(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 1), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=6.0, custo_total=120.0,
        )

        resultado = services.get_daily_movements(scenario_id=self.cenario.id)

        self.assertEqual(len(resultado), 1)
        mov = resultado[0]
        self.assertEqual(mov['origem'], 'Armazém Teste')
        self.assertEqual(mov['destino'], 'Fábrica Teste')
        self.assertEqual(mov['quantidade_sc'], 100.0)  # 6 Ton * 1000 / 60

    def test_bulk_lookup_de_entidades_nao_escala_com_numero_de_linhas(self):
        for i in range(10):
            MovimentacaoDiaria.all_cooperativas.create(
                cooperativa=self.cooperativa, cenario=self.cenario,
                data=datetime.date(2026, 1, 1) + datetime.timedelta(days=i),
                armazem=self.armazem, fabrica=self.fabrica,
                quantidade_ton=10.0, custo_total=100.0,
            )

        with CaptureQueriesContext(connection) as ctx:
            resultado = services.get_daily_movements(scenario_id=self.cenario.id)

        self.assertEqual(len(resultado), 10)
        self.assertLess(
            len(ctx.captured_queries), 10,
            f'{len(ctx.captured_queries)} queries para 10 linhas -- parece N+1 (bug A3).',
        )

    def test_clamps_excessive_limit(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 1), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=10.0, custo_total=100.0,
        )

        resultado = services.get_daily_movements(scenario_id=self.cenario.id, limit=999999)

        self.assertEqual(len(resultado), 1)
        self.assertLessEqual(services.MAX_LIMIT, 1000)

    def test_raises_clear_error_on_malformed_start_date(self):
        with self.assertRaises(ValueError) as ctx:
            services.get_daily_movements(scenario_id=self.cenario.id, start_date='not-a-date')

        msg = str(ctx.exception)
        self.assertIn('not-a-date', msg)
        self.assertNotIn('does not match format', msg)
        self.assertIn('AAAA-MM-DD', msg)

    def test_nao_vaza_movimentacoes_de_outra_cooperativa(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 1), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=6.0, custo_total=120.0,
        )

        cooperativa_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        cenario_b = Cenario.all_cooperativas.create(cooperativa=cooperativa_b, nome='Cenário Coop B')
        armazem_b = Armazem.all_cooperativas.create(
            cooperativa=cooperativa_b, cenario=cenario_b, nome='Armazém Coop B',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        fabrica_b = Fabrica.all_cooperativas.create(
            cooperativa=cooperativa_b, cenario=cenario_b, nome='Fábrica Coop B',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=cooperativa_b, cenario=cenario_b,
            data=datetime.date(2026, 1, 1), armazem=armazem_b, fabrica=fabrica_b,
            quantidade_ton=999.0, custo_total=9999.0,
        )

        resultado = services.get_daily_movements(scenario_id=self.cenario.id)

        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]['origem'], 'Armazém Teste')


class GetMonthlySummaryTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )

    def test_sem_movimentacoes_retorna_listas_vazias(self):
        resultado = services.get_monthly_summary(scenario_id=self.cenario.id)

        self.assertEqual(resultado, {'meses': [], 'rotas': []})

    def test_agrega_por_mes_e_por_rota(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 5), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=10.0, custo_total=100.0,
        )
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            data=datetime.date(2026, 1, 20), armazem=self.armazem, fabrica=self.fabrica,
            quantidade_ton=5.0, custo_total=50.0,
        )

        resultado = services.get_monthly_summary(scenario_id=self.cenario.id)

        self.assertEqual(len(resultado['resumo_mensal']), 1)
        self.assertEqual(resultado['resumo_mensal'][0]['quantidade_ton'], 15.0)
        self.assertEqual(len(resultado['detalhe_rotas']), 1)

    def test_raises_clear_error_on_malformed_end_date(self):
        with self.assertRaises(ValueError) as ctx:
            services.get_monthly_summary(scenario_id=self.cenario.id, end_date='31/12/2026')

        msg = str(ctx.exception)
        self.assertIn('31/12/2026', msg)
        self.assertNotIn('does not match format', msg)
        self.assertIn('AAAA-MM-DD', msg)
