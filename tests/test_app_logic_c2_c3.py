import pytest

from app_logic import db_session_scope, sync_armazem_from_row, sync_fabrica_from_row


def test_sync_fabrica_from_row_writes_all_six_editable_fields(fabrica):
    """C2: all six editable Fabrica columns exposed by get_model_column_config
    must be persisted onto the ORM object, not just the first three."""
    row = {
        "Fábrica": fabrica.nome,
        "Capacidade Estática (Ton)": 12345.0,
        "Esmagamento Diário (Ton)": 999.0,
        "Recebimento Diário (Ton)": 888.0,
        "Limite de Caminhões": 42,
        "Carga Média (Ton)": 33.5,
        "Estoque Inicial (Ton)": 7777.0,
    }

    sync_fabrica_from_row(fabrica, row)

    assert fabrica.capacidade_estatica == 12345.0
    assert fabrica.capacidade_esmagamento_diaria == 999.0
    assert fabrica.capacidade_recebimento_diaria == 888.0
    assert fabrica.limite_caminhoes == 42
    assert fabrica.carga_media_caminhao == 33.5
    assert fabrica.estoque_inicial == 7777.0


def test_sync_armazem_from_row_writes_estoque_inicial_for_existing_row(armazem):
    """C2: an existing Armazem row's estoque_inicial edit must not be
    silently dropped."""
    assert armazem.estoque_inicial == 2000
    row = {
        "Armazém": armazem.nome,
        "Capacidade Estática (Ton)": 5000.0,
        "Expedição Diária (Ton)": 300.0,
        "Estoque Inicial (Ton)": 9999.0,
    }

    sync_armazem_from_row(armazem, row)

    assert armazem.estoque_inicial == 9999.0


def test_db_session_scope_closes_session_even_on_exception(session):
    """C3: the session must be closed in a finally block even when the
    wrapped code raises, and the original exception must propagate
    unchanged."""
    close_calls = []
    original_close = session.close

    def spy_close():
        close_calls.append(True)
        original_close()

    session.close = spy_close

    with pytest.raises(ValueError, match="boom"):
        with db_session_scope(session):
            raise ValueError("boom")

    assert len(close_calls) == 1
