import pytest

from app_logic import (
    build_editable_armazens_df,
    build_editable_fabricas_df,
    build_editable_previsoes_armazem_df,
    build_editable_previsoes_fabrica_df,
    build_editable_rotas_df,
    build_editable_safras_df,
    sync_rota_from_row,
)


# ---------------------------------------------------------------------------
# A5: post-upload session_state must use the SAME labeled shape as the
# reload-gate path, so save handlers never KeyError on raw DB column names.
# ---------------------------------------------------------------------------


def test_build_editable_fabricas_df_uses_labeled_columns_not_raw_db_names(session, fabrica):
    df = build_editable_fabricas_df(session, fabrica.cenario_id)

    assert "Fábrica" in df.columns
    assert "Capacidade Estática (Ton)" in df.columns
    assert "Esmagamento Diário (Ton)" in df.columns
    assert "Estoque Inicial (Ton)" in df.columns
    # Raw ORM/DB column names must NOT leak into the editable df shape.
    assert "nome" not in df.columns
    assert "capacidade_estatica" not in df.columns


def test_build_editable_armazens_df_uses_labeled_columns_not_raw_db_names(session, armazem):
    df = build_editable_armazens_df(session, armazem.cenario_id)

    assert "Armazém" in df.columns
    assert "Capacidade Estática (Ton)" in df.columns
    assert "Estoque Inicial (Ton)" in df.columns
    assert "nome" not in df.columns
    assert "capacidade_estatica" not in df.columns


def test_build_editable_fabricas_df_row_values_match_orm(session, fabrica):
    df = build_editable_fabricas_df(session, fabrica.cenario_id)

    assert len(df) == 1
    assert df.iloc[0]["Fábrica"] == fabrica.nome
    assert df.iloc[0]["Capacidade Estática (Ton)"] == fabrica.capacidade_estatica


def test_build_editable_rotas_df_uses_labeled_columns_and_derives_origem_destino(session, rota):
    df = build_editable_rotas_df(session, rota.cenario_id)

    assert "Distância (km)" in df.columns
    assert "Origem" in df.columns
    assert "Destino" in df.columns
    assert df.iloc[0]["Origem"] == rota.armazem.nome
    assert df.iloc[0]["Destino"] == rota.fabrica.nome


def test_build_editable_previsoes_and_safras_df_return_empty_frames_when_no_data(session, cenario):
    # Just verifying these helpers are safe / importable and don't blow up
    # when there is no data yet for the scenario (used by both reload gate
    # and post-save refresh).
    assert build_editable_previsoes_fabrica_df(session, cenario.id).empty
    assert build_editable_previsoes_armazem_df(session, cenario.id).empty
    assert build_editable_safras_df(session, cenario.id).empty


# ---------------------------------------------------------------------------
# A6: Rotas save-handler conversion logic must validate cleanly instead of
# crashing the page, and must not corrupt the object on a partial failure.
# ---------------------------------------------------------------------------


def test_sync_rota_from_row_writes_all_three_editable_fields(rota):
    row = {
        "Distância (km)": 123.0,
        "Custo Safra (R$/Ton)": 45.5,
        "Custo Entressafra (R$/Ton)": 30.0,
    }

    sync_rota_from_row(rota, row)

    assert rota.distancia_km == 123.0
    assert rota.custo_frete_ton == 45.5
    assert rota.custo_frete_entressafra == 30.0


def test_sync_rota_from_row_blank_distancia_raises_clean_exception(rota):
    row = {
        "Distância (km)": "",
        "Custo Safra (R$/Ton)": 999.0,
        "Custo Entressafra (R$/Ton)": 888.0,
    }

    with pytest.raises((ValueError, TypeError)):
        sync_rota_from_row(rota, row)


def test_sync_rota_from_row_does_not_partially_mutate_object_on_bad_row(rota):
    original_distancia = rota.distancia_km
    original_custo_safra = rota.custo_frete_ton
    original_custo_entressafra = rota.custo_frete_entressafra

    row = {
        "Distância (km)": "não é número",
        "Custo Safra (R$/Ton)": 999.0,
        "Custo Entressafra (R$/Ton)": 888.0,
    }

    with pytest.raises((ValueError, TypeError)):
        sync_rota_from_row(rota, row)

    # Object must remain fully untouched -- no partial writes before the
    # exception was raised.
    assert rota.distancia_km == original_distancia
    assert rota.custo_frete_ton == original_custo_safra
    assert rota.custo_frete_entressafra == original_custo_entressafra
