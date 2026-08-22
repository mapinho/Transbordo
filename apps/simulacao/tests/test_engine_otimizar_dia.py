import datetime
import logging

from django.test import TestCase
from ortools.linear_solver import pywraplp

from apps.core.models import Cooperativa
from apps.simulacao import engine
from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota, SafraUnidade


class OtimizarDiaFixtureMixin:
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém Teste',
            capacidade_estatica=5000, capacidade_expedicao_diaria=300, estoque_inicial=2000,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica Teste',
            capacidade_estatica=10000, capacidade_esmagamento_diaria=500,
            capacidade_recebimento_diaria=600, limite_caminhoes=20,
            carga_media_caminhao=30, estoque_inicial=1000,
        )
        self.rota = Rota.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            armazem=self.armazem, fabrica=self.fabrica,
            distancia_km=50, custo_frete_ton=20.0, custo_frete_entressafra=15.0,
        )


class OtimizarDiaSolverTests(OtimizarDiaFixtureMixin, TestCase):
    def test_raises_when_no_solver_available(self):
        original_create_solver = pywraplp.Solver.CreateSolver
        pywraplp.Solver.CreateSolver = staticmethod(lambda *_args, **_kwargs: None)
        try:
            with self.assertRaises(RuntimeError):
                engine.otimizar_dia(
                    data=datetime.date(2026, 2, 1),
                    estoques_atuais={f'F_{self.fabrica.id}': 0, f'A_{self.armazem.id}': 1000},
                    cenario_id=self.cenario.id,
                )
        finally:
            pywraplp.Solver.CreateSolver = original_create_solver

    def test_logs_warning_when_status_not_optimal(self):
        original_solve = pywraplp.Solver.Solve
        pywraplp.Solver.Solve = lambda self: pywraplp.Solver.INFEASIBLE
        try:
            with self.assertLogs('apps.simulacao.engine', level='WARNING') as captured:
                resultado = engine.otimizar_dia(
                    data=datetime.date(2026, 2, 1),
                    estoques_atuais={f'F_{self.fabrica.id}': 0, f'A_{self.armazem.id}': 1000},
                    cenario_id=self.cenario.id,
                )
        finally:
            pywraplp.Solver.Solve = original_solve

        self.assertIsNone(resultado)
        self.assertTrue(any(record.levelno == logging.WARNING for record in captured.records))


class OtimizarDiaSafraTests(OtimizarDiaFixtureMixin, TestCase):
    def test_usa_custo_de_safra_quando_data_esta_na_janela(self):
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, entidade_tipo='Armazém',
            entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        resultados = engine.otimizar_dia(
            data=datetime.date(2026, 2, 15),
            estoques_atuais={f'A_{self.armazem.id}': 2000, f'F_{self.fabrica.id}': 0},
            cenario_id=self.cenario.id,
        )

        self.assertTrue(resultados)
        mov = resultados[0]
        self.assertEqual(mov['armazem_id'], self.armazem.id)
        self.assertEqual(mov['fabrica_id'], self.fabrica.id)
        self.assertEqual(mov['custo_total'], mov['quantidade_ton'] * self.rota.custo_frete_ton)

    def test_usa_custo_de_entressafra_quando_data_fora_da_janela(self):
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, entidade_tipo='Armazém',
            entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 2, 1), data_fim=datetime.date(2026, 3, 1),
        )

        resultados = engine.otimizar_dia(
            data=datetime.date(2026, 3, 15),
            estoques_atuais={f'A_{self.armazem.id}': 2000, f'F_{self.fabrica.id}': 0},
            cenario_id=self.cenario.id,
        )

        self.assertTrue(resultados)
        mov = resultados[0]
        self.assertEqual(mov['custo_total'], mov['quantidade_ton'] * self.rota.custo_frete_entressafra)


class OtimizarDiaPreCarregamentoTests(OtimizarDiaFixtureMixin, TestCase):
    def test_nao_consulta_banco_quando_dados_pre_carregados(self):
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        estoques = {f'F_{self.fabrica.id}': 0, f'A_{self.armazem.id}': 5000}

        with CaptureQueriesContext(connection) as ctx:
            engine.otimizar_dia(
                data=datetime.date(2026, 2, 1), estoques_atuais=estoques, cenario_id=self.cenario.id,
                fabricas=[self.fabrica], armazens=[self.armazem], rotas=[self.rota], safra_cache={},
            )

        self.assertEqual(len(ctx.captured_queries), 0)
