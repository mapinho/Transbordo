import datetime

import pytest
from sqlalchemy.orm import Session as SASession

import logistics_services
from models import (
    Armazem,
    Fabrica,
    MovimentacaoDiaria,
    ResumoMensalFabrica,
)


def _patch_init_db(monkeypatch, session):
    """Force logistics_services.init_db() (imported from data_loader) to
    return the test's in-memory session/fixtures instead of opening a real
    DB connection."""
    monkeypatch.setattr(logistics_services, "init_db", lambda: session)


# ---------------------------------------------------------------------------
# A3 - N+1 queries + unbounded limit
# ---------------------------------------------------------------------------

def test_get_daily_movements_does_not_do_one_session_get_per_row(
    session, cenario, fabrica, armazem, monkeypatch
):
    """A3: session.get() must not be called once (or twice) per result row.
    We monkeypatch Session.get at the class level to count calls, then
    assert the count is decoupled from the number of movement rows."""
    extra_fabrica = Fabrica(
        cenario_id=cenario.id,
        nome="Fábrica Extra",
        capacidade_estatica=10000,
        capacidade_esmagamento_diaria=500,
        capacidade_recebimento_diaria=600,
        limite_caminhoes=20,
        carga_media_caminhao=30,
        estoque_inicial=1000,
    )
    session.add(extra_fabrica)
    session.commit()

    n_rows = 10
    for i in range(n_rows):
        mov = MovimentacaoDiaria(
            cenario_id=cenario.id,
            data=datetime.date(2026, 1, 1) + datetime.timedelta(days=i),
            armazem_id=armazem.id,
            fabrica_id=fabrica.id if i % 2 == 0 else extra_fabrica.id,
            quantidade_ton=10.0,
            custo_total=100.0,
        )
        session.add(mov)
    session.commit()

    _patch_init_db(monkeypatch, session)

    get_calls = {"count": 0}
    original_get = SASession.get

    def counting_get(self, *args, **kwargs):
        get_calls["count"] += 1
        return original_get(self, *args, **kwargs)

    monkeypatch.setattr(SASession, "get", counting_get)

    results = logistics_services.get_daily_movements(scenario_id=cenario.id)

    assert len(results) == n_rows
    # There are only 2 distinct entities involved (1 armazem, 2 fabricas =
    # 3 distinct entity ids). A correct bulk-lookup implementation should
    # need far fewer session.get()/lookup calls than n_rows * 2 (=20).
    assert get_calls["count"] < n_rows, (
        f"Expected bulk lookups (few session.get calls), but got "
        f"{get_calls['count']} calls for {n_rows} rows -- looks like N+1 (bug A3)."
    )


def test_get_daily_movements_clamps_excessive_limit(
    session, cenario, fabrica, armazem, monkeypatch
):
    """A3: passing a huge limit must not error, and must be clamped by
    MAX_LIMIT rather than honored as-is."""
    for i in range(5):
        mov = MovimentacaoDiaria(
            cenario_id=cenario.id,
            data=datetime.date(2026, 1, 1) + datetime.timedelta(days=i),
            armazem_id=armazem.id,
            fabrica_id=fabrica.id,
            quantidade_ton=10.0,
            custo_total=100.0,
        )
        session.add(mov)
    session.commit()

    _patch_init_db(monkeypatch, session)

    # Should not raise, and MAX_LIMIT must exist as a sane cap.
    results = logistics_services.get_daily_movements(
        scenario_id=cenario.id, limit=999999
    )
    assert len(results) == 5  # only 5 rows exist, well under any sane cap
    assert hasattr(logistics_services, "MAX_LIMIT")
    assert logistics_services.MAX_LIMIT <= 1000


# ---------------------------------------------------------------------------
# A2 - stock ruptures (negative saldo_estoque) never surfaced
# ---------------------------------------------------------------------------

def test_get_stock_ruptures_report_detects_negative_saldo(
    session, cenario, fabrica, monkeypatch
):
    resumo = ResumoMensalFabrica(
        cenario_id=cenario.id,
        mes="2026-01",
        fabrica_id=fabrica.id,
        rec_produtor=100,
        rec_transbordo=0,
        esmagado=200,
        saldo_estoque=-50.0,
        capacidade_estatica=10000,
        excedente=0,
    )
    session.add(resumo)
    session.commit()

    _patch_init_db(monkeypatch, session)

    assert hasattr(logistics_services, "get_stock_ruptures_report")
    alerts = logistics_services.get_stock_ruptures_report(cenario.id)

    assert len(alerts) == 1
    alert = alerts[0]
    assert alert["entidade_nome"] == "Fábrica Teste"
    assert alert["entidade_tipo"] == "Fabrica"
    assert alert["deficit_ton"] == pytest.approx(50.0)
    assert alert["deficit_ton"] > 0


# ---------------------------------------------------------------------------
# A4 - malformed date strings should raise a clear ValueError
# ---------------------------------------------------------------------------

def test_get_daily_movements_raises_clear_error_on_malformed_start_date(
    session, cenario, monkeypatch
):
    _patch_init_db(monkeypatch, session)

    with pytest.raises(ValueError) as excinfo:
        logistics_services.get_daily_movements(
            scenario_id=cenario.id, start_date="not-a-date"
        )
    msg = str(excinfo.value)
    assert "not-a-date" in msg
    # Must be our own actionable message, not the raw Python strptime
    # wording ("time data ... does not match format ...").
    assert "does not match format" not in msg
    assert "AAAA-MM-DD" in msg


def test_get_monthly_summary_raises_clear_error_on_malformed_end_date(
    session, cenario, monkeypatch
):
    _patch_init_db(monkeypatch, session)

    with pytest.raises(ValueError) as excinfo:
        logistics_services.get_monthly_summary(
            scenario_id=cenario.id, end_date="31/12/2026"
        )
    msg = str(excinfo.value)
    assert "31/12/2026" in msg
    assert "does not match format" not in msg
    assert "AAAA-MM-DD" in msg
