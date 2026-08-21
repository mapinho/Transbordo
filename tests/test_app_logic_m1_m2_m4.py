"""Tests for the M1/M2/M4 lower-severity fixes.

M1 (cached scenario list query) is Streamlit-cache-specific and not
meaningfully unit-testable without a running Streamlit context -- see the
final report for a description of that fix instead. Only M2 and M4 have
tests here.
"""

import datetime

import pytest
from sqlalchemy.orm import Session as SASession

import app_logic
from models import Armazem, Fabrica, MovimentacaoDiaria, Rota


# ---------------------------------------------------------------------------
# M4 - comparison totals should be aggregated in SQL (func.sum), not by
# pulling every row and summing in Python.
# ---------------------------------------------------------------------------

def test_get_movement_totals_sums_matching_rows(session, cenario, fabrica, armazem):
    for i in range(3):
        session.add(
            MovimentacaoDiaria(
                cenario_id=cenario.id,
                data=datetime.date(2026, 1, 1) + datetime.timedelta(days=i),
                armazem_id=armazem.id,
                fabrica_id=fabrica.id,
                quantidade_ton=10.0,
                custo_total=100.0,
            )
        )
    session.commit()

    custo_total, quantidade_ton = app_logic.get_movement_totals(session, cenario.id)

    assert custo_total == pytest.approx(300.0)
    assert quantidade_ton == pytest.approx(30.0)


def test_get_movement_totals_respects_date_range(session, cenario, fabrica, armazem):
    session.add(
        MovimentacaoDiaria(
            cenario_id=cenario.id,
            data=datetime.date(2026, 1, 1),
            armazem_id=armazem.id,
            fabrica_id=fabrica.id,
            quantidade_ton=10.0,
            custo_total=100.0,
        )
    )
    session.add(
        MovimentacaoDiaria(
            cenario_id=cenario.id,
            data=datetime.date(2026, 6, 1),
            armazem_id=armazem.id,
            fabrica_id=fabrica.id,
            quantidade_ton=20.0,
            custo_total=200.0,
        )
    )
    session.commit()

    custo_total, quantidade_ton = app_logic.get_movement_totals(
        session,
        cenario.id,
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 1, 31),
    )

    assert custo_total == pytest.approx(100.0)
    assert quantidade_ton == pytest.approx(10.0)


def test_get_movement_totals_returns_zero_not_none_for_no_rows(session, cenario):
    custo_total, quantidade_ton = app_logic.get_movement_totals(session, cenario.id)

    assert custo_total == 0
    assert quantidade_ton == 0


def test_get_movement_totals_only_sums_requested_scenario(
    session, cenario, fabrica, armazem
):
    from models import Cenario

    other_cenario = Cenario(nome="Outro Cenário")
    session.add(other_cenario)
    session.commit()

    session.add(
        MovimentacaoDiaria(
            cenario_id=cenario.id,
            data=datetime.date(2026, 1, 1),
            armazem_id=armazem.id,
            fabrica_id=fabrica.id,
            quantidade_ton=10.0,
            custo_total=100.0,
        )
    )
    session.add(
        MovimentacaoDiaria(
            cenario_id=other_cenario.id,
            data=datetime.date(2026, 1, 1),
            armazem_id=armazem.id,
            fabrica_id=fabrica.id,
            quantidade_ton=999.0,
            custo_total=9999.0,
        )
    )
    session.commit()

    custo_total, quantidade_ton = app_logic.get_movement_totals(session, cenario.id)

    assert custo_total == pytest.approx(100.0)
    assert quantidade_ton == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# M2 - N+1 session.get() calls inside build_editable_rotas_df must be
# replaced with a bulk lookup, decoupling call count from row count.
# ---------------------------------------------------------------------------

def test_build_editable_rotas_df_does_not_do_one_session_get_per_row(
    session, cenario, monkeypatch
):
    fab1 = Fabrica(
        cenario_id=cenario.id,
        nome="Fábrica 1",
        capacidade_estatica=10000,
        capacidade_esmagamento_diaria=500,
        capacidade_recebimento_diaria=600,
        limite_caminhoes=20,
        carga_media_caminhao=30,
        estoque_inicial=1000,
    )
    fab2 = Fabrica(
        cenario_id=cenario.id,
        nome="Fábrica 2",
        capacidade_estatica=10000,
        capacidade_esmagamento_diaria=500,
        capacidade_recebimento_diaria=600,
        limite_caminhoes=20,
        carga_media_caminhao=30,
        estoque_inicial=1000,
    )
    arm1 = Armazem(
        cenario_id=cenario.id,
        nome="Armazém 1",
        capacidade_estatica=5000,
        capacidade_expedicao_diaria=300,
        estoque_inicial=2000,
    )
    arm2 = Armazem(
        cenario_id=cenario.id,
        nome="Armazém 2",
        capacidade_estatica=5000,
        capacidade_expedicao_diaria=300,
        estoque_inicial=2000,
    )
    session.add_all([fab1, fab2, arm1, arm2])
    session.commit()

    n_rows = 12
    for i in range(n_rows):
        session.add(
            Rota(
                cenario_id=cenario.id,
                armazem_id=arm1.id if i % 2 == 0 else arm2.id,
                fabrica_id=fab1.id if i % 3 == 0 else fab2.id,
                distancia_km=50 + i,
                custo_frete_ton=20.0,
                custo_frete_entressafra=15.0,
            )
        )
    session.commit()

    get_calls = {"count": 0}
    original_get = SASession.get

    def counting_get(self, *args, **kwargs):
        get_calls["count"] += 1
        return original_get(self, *args, **kwargs)

    monkeypatch.setattr(SASession, "get", counting_get)
    df_rots = app_logic.build_editable_rotas_df(session, cenario.id)

    assert len(df_rots) == n_rows
    # Only 4 distinct entities (2 armazéns + 2 fábricas) are involved. A
    # correct bulk-lookup implementation should need far fewer session.get()
    # calls than n_rows * 2 (=24) -- ideally zero, since bulk lookups use
    # session.query(...).filter(...in_(...)) instead of session.get().
    assert get_calls["count"] < n_rows, (
        f"Expected bulk lookups (few/no session.get calls), but got "
        f"{get_calls['count']} calls for {n_rows} rows -- looks like N+1 (bug M2)."
    )
    assert set(df_rots["Origem"]) == {"Armazém 1", "Armazém 2"}
    assert set(df_rots["Destino"]) == {"Fábrica 1", "Fábrica 2"}
