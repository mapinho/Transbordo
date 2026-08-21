import datetime
import logging

import pytest
from ortools.linear_solver import pywraplp

import calculations


def test_otimizar_dia_raises_when_no_solver_available(session, cenario, fabrica, armazem, rota, monkeypatch):
    """A1: quando nenhum solver OR-Tools (SCIP/GLOP) está disponível, otimizar_dia
    deve levantar RuntimeError em vez de silenciosamente retornar None."""
    monkeypatch.setattr(pywraplp.Solver, "CreateSolver", staticmethod(lambda *_args, **_kwargs: None))

    with pytest.raises(RuntimeError):
        calculations.otimizar_dia(
            session,
            data=datetime.date(2026, 2, 1),
            estoques_atuais={f"F_{fabrica.id}": 0, f"A_{armazem.id}": 1000},
            cenario_id=cenario.id,
        )


def test_otimizar_dia_logs_warning_when_status_not_optimal(session, cenario, fabrica, armazem, rota, monkeypatch, caplog):
    """A1: quando o status do solve não é OPTIMAL/FEASIBLE, otimizar_dia deve
    logar um warning identificando data/cenario antes de retornar None."""
    monkeypatch.setattr(pywraplp.Solver, "Solve", lambda self: pywraplp.Solver.INFEASIBLE)

    data_teste = datetime.date(2026, 2, 1)

    with caplog.at_level(logging.WARNING, logger="calculations"):
        resultado = calculations.otimizar_dia(
            session,
            data=data_teste,
            estoques_atuais={f"F_{fabrica.id}": 0, f"A_{armazem.id}": 1000},
            cenario_id=cenario.id,
        )

    assert resultado is None
    assert any(record.levelno == logging.WARNING for record in caplog.records)
    assert "WARNING" in caplog.text
