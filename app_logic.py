"""Pure, Streamlit-free helper logic extracted from app.py so it can be
unit tested without importing the Streamlit script directly.

This module intentionally has no direct `streamlit` import (it does reuse
`utils.build_df_from_model`, which is Streamlit-free itself even though the
`utils` module also exposes some Streamlit-dependent helpers).
"""

from contextlib import contextmanager
from typing import Union

import pandas as pd
from sqlalchemy import func

from models import (
    Armazem,
    Fabrica,
    MovimentacaoDiaria,
    PrevisaoArmazem,
    PrevisaoFabrica,
    Rota,
    SafraUnidade,
)
from utils import build_df_from_model

# The `row` argument in the sync_* functions below is populated from two
# different call sites: a plain dict in unit tests, and a pandas Series
# (from `DataFrame.iterrows()`) in the real Streamlit save handlers. Both
# support `row["Label"]` item access, so either is accepted.
RowLike = Union[dict, "pd.Series"]


def sync_fabrica_from_row(fabrica, row: RowLike) -> None:
    """Writes all six editable Fabrica fields from a data-editor row dict
    onto the ORM object. Keys match the labels used by
    utils.get_model_column_config(Fabrica) / utils.build_df_from_model.

    (C2 fix: previously only capacidade_estatica,
    capacidade_esmagamento_diaria and capacidade_recebimento_diaria were
    written, silently dropping edits to limite_caminhoes,
    carga_media_caminhao and estoque_inicial.)
    """
    fabrica.capacidade_estatica = float(row["Capacidade Estática (Ton)"])
    fabrica.capacidade_esmagamento_diaria = float(row["Esmagamento Diário (Ton)"])
    fabrica.capacidade_recebimento_diaria = float(row["Recebimento Diário (Ton)"])
    fabrica.limite_caminhoes = int(row["Limite de Caminhões"])
    fabrica.carga_media_caminhao = float(row["Carga Média (Ton)"])
    fabrica.estoque_inicial = float(row["Estoque Inicial (Ton)"])


def sync_armazem_from_row(armazem, row: RowLike) -> None:
    """Writes all editable Armazem fields from a data-editor row dict onto
    the ORM object. Keys match the labels used by
    utils.get_model_column_config(Armazem) / utils.build_df_from_model.

    (C2 fix: previously, for an already-existing row, estoque_inicial was
    never updated -- it was only set when creating a brand-new row.)
    """
    armazem.nome = row["Armazém"]
    armazem.capacidade_estatica = float(row["Capacidade Estática (Ton)"])
    armazem.capacidade_expedicao_diaria = float(row["Expedição Diária (Ton)"])
    armazem.estoque_inicial = float(row["Estoque Inicial (Ton)"])


def sync_rota_from_row(rota, row: RowLike) -> None:
    """Writes the three editable Rota fields from a data-editor row dict
    onto the ORM object. Keys match the labels used by
    utils.get_model_column_config(Rota) / utils.build_df_from_model.

    (A6 fix: the previous inline handler in app.py used dict-style item
    assignment -- e.g. ``r['distancia_km'] = ...`` -- on a plain SQLAlchemy
    declarative object, which always raises ``TypeError`` since ORM
    instances don't support ``__setitem__``. It also had no validation, so
    a blank/invalid numeric cell raised an uncaught ``ValueError``.

    All conversions are performed into local variables first and only
    assigned to the object afterwards, so a malformed cell raises a clean,
    catchable exception without partially mutating ``rota``.)
    """
    distancia_km = float(row["Distância (km)"])
    custo_frete_ton = float(row["Custo Safra (R$/Ton)"])
    custo_frete_entressafra = float(row["Custo Entressafra (R$/Ton)"])

    rota.distancia_km = distancia_km
    rota.custo_frete_ton = custo_frete_ton
    rota.custo_frete_entressafra = custo_frete_entressafra


def _bulk_names_by_id(session, model_class, ids):
    """M2 fix: one bulk `SELECT ... WHERE id IN (...)` instead of one
    `session.get()` call per row. Returns a ``{id: nome}`` dict for the
    given distinct ids (empty dict if `ids` is empty, without issuing a
    query)."""
    if not ids:
        return {}
    rows = session.query(model_class).filter(model_class.id.in_(ids)).all()
    return {row.id: row.nome for row in rows}


def build_editable_fabricas_df(session, cenario_id):
    """Returns the Fabrica editable DataFrame in the same human-labeled
    shape used throughout the app (columns such as 'Fábrica', 'Capacidade
    Estática (Ton)', ...), by wrapping `utils.build_df_from_model`.

    (A5 fix: used by both the "Dados & Cenários" reload gate and the
    post-upload refresh in "Carga de Dados", so the two code paths can no
    longer diverge in shape and crash the save handler with a KeyError.)

    (L1 fix: `build_df_from_model` already emits a 'Fábrica' column sourced
    from `Fabrica.nome` -- an id-for-id, same-order re-assignment of that
    same column was redundant and has been removed.)
    """
    fabs_list = session.query(Fabrica).filter_by(cenario_id=cenario_id).all()
    return build_df_from_model(fabs_list, Fabrica)


def build_editable_armazens_df(session, cenario_id):
    """Returns the Armazem editable DataFrame in the same human-labeled
    shape used throughout the app. See `build_editable_fabricas_df` (A5, L1).
    """
    arms_list = session.query(Armazem).filter_by(cenario_id=cenario_id).all()
    return build_df_from_model(arms_list, Armazem)


def build_editable_rotas_df(session, cenario_id):
    """Returns the Rota editable DataFrame in the same human-labeled shape
    used throughout the app, including the derived 'Origem'/'Destino'
    columns.

    (M2 fix: previously called `session.get(Armazem, ...)` and
    `session.get(Fabrica, ...)` once per row -- an N+1 query pattern.
    Replaced with two bulk lookups keyed by distinct ids.)
    """
    rots_list = session.query(Rota).filter_by(cenario_id=cenario_id).all()
    df_rots = build_df_from_model(rots_list, Rota)
    if not df_rots.empty:
        armazens_by_id = _bulk_names_by_id(
            session, Armazem, {r.armazem_id for r in rots_list}
        )
        fabricas_by_id = _bulk_names_by_id(
            session, Fabrica, {r.fabrica_id for r in rots_list}
        )
        df_rots["Origem"] = [
            str(armazens_by_id.get(r.armazem_id, "")) for r in rots_list
        ]
        df_rots["Destino"] = [
            str(fabricas_by_id.get(r.fabrica_id, "")) for r in rots_list
        ]
    return df_rots


def build_editable_previsoes_fabrica_df(session, cenario_id):
    """Returns the PrevisaoFabrica editable DataFrame in the same
    human-labeled shape used throughout the app, including the derived
    'Fábrica' column.

    (M2 fix: bulk lookup instead of one `session.get()` per row.)
    """
    pf_list = (
        session.query(PrevisaoFabrica)
        .join(Fabrica)
        .filter(Fabrica.cenario_id == cenario_id)
        .all()
    )
    df_pf = build_df_from_model(pf_list, PrevisaoFabrica)
    if not df_pf.empty:
        fabricas_by_id = _bulk_names_by_id(
            session, Fabrica, {p.fabrica_id for p in pf_list}
        )
        df_pf["Fábrica"] = [
            str(fabricas_by_id.get(p.fabrica_id, "")) for p in pf_list
        ]
    return df_pf


def build_editable_previsoes_armazem_df(session, cenario_id):
    """Returns the PrevisaoArmazem editable DataFrame in the same
    human-labeled shape used throughout the app, including the derived
    'Armazém' column.

    (M2 fix: bulk lookup instead of one `session.get()` per row.)
    """
    pa_list = (
        session.query(PrevisaoArmazem)
        .join(Armazem)
        .filter(Armazem.cenario_id == cenario_id)
        .all()
    )
    df_pa = build_df_from_model(pa_list, PrevisaoArmazem)
    if not df_pa.empty:
        armazens_by_id = _bulk_names_by_id(
            session, Armazem, {p.armazem_id for p in pa_list}
        )
        df_pa["Armazém"] = [
            str(armazens_by_id.get(p.armazem_id, "")) for p in pa_list
        ]
    return df_pa


def build_editable_safras_df(session, cenario_id):
    """Returns the SafraUnidade editable DataFrame in the same
    human-labeled shape used throughout the app, including the derived
    'Unidade' column.

    (M2 fix: SafraUnidade rows reference either an Armazem or a Fabrica via
    a polymorphic `entidade_id`/`entidade_tipo` pair. Previously each row
    did its own `session.get()`; now ids are grouped by entity type and
    resolved with two bulk lookups total.)
    """
    safras_list = session.query(SafraUnidade).filter_by(cenario_id=cenario_id).all()
    df_saf = build_df_from_model(safras_list, SafraUnidade)
    if not df_saf.empty:
        armazem_ids = {
            s.entidade_id for s in safras_list
            if getattr(s, "entidade_tipo", None) == "Armazém"
        }
        fabrica_ids = {
            s.entidade_id for s in safras_list
            if getattr(s, "entidade_tipo", None) != "Armazém"
        }
        armazens_by_id = _bulk_names_by_id(session, Armazem, armazem_ids)
        fabricas_by_id = _bulk_names_by_id(session, Fabrica, fabrica_ids)

        unidades = []
        for s_obj in safras_list:
            if getattr(s_obj, "entidade_tipo", None) == "Armazém":
                unidades.append(str(armazens_by_id.get(s_obj.entidade_id, "")))
            else:
                unidades.append(str(fabricas_by_id.get(s_obj.entidade_id, "")))
        df_saf["Unidade"] = unidades
    return df_saf


def get_movement_totals(session, cenario_id, start_date=None, end_date=None):
    """Returns ``(custo_total, quantidade_ton)`` totals for
    `MovimentacaoDiaria` rows matching `cenario_id` (and, optionally, a
    `[start_date, end_date]` date range), aggregated in SQL via
    `func.sum(...)` rather than pulling every row over the wire and summing
    in Python.

    (M4 fix: replaces the previous `session.query(MovimentacaoDiaria)...all()`
    + `sum(m.custo_total for m in ...)` pattern used by app.py's Dashboard
    comparison view.)

    Returns ``(0, 0)`` -- not ``(None, None)`` -- when no rows match, so
    callers can use the result directly in arithmetic without a None check.
    """
    query = session.query(
        func.sum(MovimentacaoDiaria.custo_total),
        func.sum(MovimentacaoDiaria.quantidade_ton),
    ).filter(MovimentacaoDiaria.cenario_id == cenario_id)

    if start_date is not None and end_date is not None:
        query = query.filter(MovimentacaoDiaria.data.between(start_date, end_date))

    custo_total, quantidade_ton = query.first()
    return (custo_total or 0, quantidade_ton or 0)


@contextmanager
def db_session_scope(session):
    """Guarantees `session.close()` runs even if the wrapped code raises.

    (C3 fix: main() previously did `session = init_db()` ... `session.close()`
    as the very last statement with no try/finally, so any uncaught
    exception anywhere in main() leaked a connection from the shared,
    st.cache_resource-cached engine pool.)

    Any exception raised inside the `with` block is re-raised unchanged
    after the session has been closed.
    """
    try:
        yield session
    finally:
        session.close()
