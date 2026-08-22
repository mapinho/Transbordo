import datetime

import pandas as pd

from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria

# Ver ADR 0006: services.py consulta via `all_cooperativas`, não `objects`.

MAX_LIMIT = 1000
KG_PER_TON = 1000
KG_PER_SACA = 60


def _parse_date(value: str, field_name: str) -> datetime.date:
    """Porte 1:1 de `logistics_services._parse_date`."""
    try:
        return datetime.datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError(
            f"Data invalida para '{field_name}': '{value}'. Use o formato AAAA-MM-DD."
        )


def list_scenarios() -> list[dict]:
    """Porte 1:1 de `logistics_services.list_scenarios`."""
    scenarios_list = Cenario.all_cooperativas.order_by('-is_oficial', 'nome')
    return [
        {
            "id": c.id,
            "nome": c.nome,
            "is_oficial": bool(c.is_oficial),
            "data_criacao": c.data_criacao.strftime("%Y-%m-%d %H:%M:%S") if c.data_criacao else None,
        }
        for c in scenarios_list
    ]


def get_daily_movements(
    scenario_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    origin_id: int | None = None,
    destination_id: int | None = None,
    limit: int = 150,
) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_daily_movements`."""
    limit = min(limit, MAX_LIMIT)
    query = MovimentacaoDiaria.all_cooperativas.filter(cenario_id=scenario_id)

    if start_date:
        d_ini = _parse_date(start_date, "start_date")
        query = query.filter(data__gte=d_ini)
    if end_date:
        d_fim = _parse_date(end_date, "end_date")
        query = query.filter(data__lte=d_fim)
    if origin_id:
        query = query.filter(armazem_id=origin_id)
    if destination_id:
        query = query.filter(fabrica_id=destination_id)

    movements = list(query.order_by('data')[:limit])

    armazem_ids = {m.armazem_id for m in movements}
    fabrica_ids = {m.fabrica_id for m in movements}
    armazens_map = {
        a.id: a.nome for a in Armazem.all_cooperativas.filter(id__in=armazem_ids)
    } if armazem_ids else {}
    fabricas_map = {
        f.id: f.nome for f in Fabrica.all_cooperativas.filter(id__in=fabrica_ids)
    } if fabrica_ids else {}

    results = []
    for m in movements:
        results.append({
            "id": m.id,
            "data": m.data.strftime("%Y-%m-%d"),
            "origem_id": m.armazem_id,
            "origem": armazens_map.get(m.armazem_id, "N/A"),
            "destino_id": m.fabrica_id,
            "destino": fabricas_map.get(m.fabrica_id, "N/A"),
            "quantidade_ton": m.quantidade_ton,
            "quantidade_sc": m.quantidade_ton * KG_PER_TON / KG_PER_SACA,
            "custo_total_r$": m.custo_total,
        })
    return results


def get_monthly_summary(
    scenario_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Porte 1:1 de `logistics_services.get_monthly_summary`."""
    query = MovimentacaoDiaria.all_cooperativas.filter(cenario_id=scenario_id)
    if start_date:
        d_ini = _parse_date(start_date, "start_date")
        query = query.filter(data__gte=d_ini)
    if end_date:
        d_fim = _parse_date(end_date, "end_date")
        query = query.filter(data__lte=d_fim)

    movements = list(query)
    if not movements:
        return {"meses": [], "rotas": []}

    armazem_ids = {m.armazem_id for m in movements}
    fabrica_ids = {m.fabrica_id for m in movements}
    armazens_map = {
        a.id: a.nome for a in Armazem.all_cooperativas.filter(id__in=armazem_ids)
    } if armazem_ids else {}
    fabricas_map = {
        f.id: f.nome for f in Fabrica.all_cooperativas.filter(id__in=fabrica_ids)
    } if fabrica_ids else {}

    df = pd.DataFrame([{
        "data": m.data,
        "origem": armazens_map.get(m.armazem_id, "N/A"),
        "destino": fabricas_map.get(m.fabrica_id, "N/A"),
        "quantidade_ton": m.quantidade_ton,
        "quantidade_sc": m.quantidade_ton * KG_PER_TON / KG_PER_SACA,
        "custo_total": m.custo_total,
    } for m in movements])

    df["mes"] = pd.to_datetime(df["data"]).dt.strftime("%Y-%m")

    df_mes = df.groupby("mes").agg({
        "quantidade_ton": "sum",
        "quantidade_sc": "sum",
        "custo_total": "sum",
    }).reset_index()

    df_rotas = df.groupby(["mes", "origem", "destino"]).agg({
        "quantidade_ton": "sum",
        "quantidade_sc": "sum",
        "custo_total": "sum",
    }).reset_index()

    return {
        "resumo_mensal": df_mes.to_dict(orient="records"),
        "detalhe_rotas": df_rotas.to_dict(orient="records"),
    }
