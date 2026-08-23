import datetime

import pandas as pd
from django.db import transaction

from apps.simulacao.models import (
    Armazem,
    Cenario,
    Fabrica,
    MovimentacaoDiaria,
    PrevisaoArmazem,
    PrevisaoFabrica,
    ResumoMensalArmazem,
    ResumoMensalFabrica,
    Rota,
    SafraUnidade,
)

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


def list_scenarios(cooperativa_id: int) -> list[dict]:
    """Porte de `logistics_services.list_scenarios`, com o limite de tenant
    explícito via `cooperativa_id` (ver ADR 0006) -- o original SQLAlchemy
    não tinha noção de multi-tenancy, então esse parâmetro não tem
    equivalente 1:1 na assinatura de origem."""
    scenarios_list = Cenario.all_cooperativas.filter(
        cooperativa_id=cooperativa_id
    ).order_by('-is_oficial', 'nome')
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


def get_factories_summary(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_factories_summary`."""
    resumos = list(ResumoMensalFabrica.all_cooperativas.filter(cenario_id=scenario_id))
    fabrica_ids = {r.fabrica_id for r in resumos}
    fabricas_map = {
        f.id: f.nome for f in Fabrica.all_cooperativas.filter(id__in=fabrica_ids)
    } if fabrica_ids else {}
    results = []
    for r in resumos:
        results.append({
            "mes": r.mes,
            "fabrica_id": r.fabrica_id,
            "fabrica": fabricas_map.get(r.fabrica_id, "N/A"),
            "recebimento_produtor_ton": r.rec_produtor,
            "recebimento_transbordo_ton": r.rec_transbordo,
            "esmagado_ton": r.esmagado,
            "saldo_estoque_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "excedente_estoque_ton": r.excedente,
        })
    return sorted(results, key=lambda x: (x["mes"], x["fabrica"]))


def get_warehouses_summary(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_warehouses_summary`."""
    resumos = list(ResumoMensalArmazem.all_cooperativas.filter(cenario_id=scenario_id))
    armazem_ids = {r.armazem_id for r in resumos}
    armazens_map = {
        a.id: a.nome for a in Armazem.all_cooperativas.filter(id__in=armazem_ids)
    } if armazem_ids else {}
    results = []
    for r in resumos:
        results.append({
            "mes": r.mes,
            "armazem_id": r.armazem_id,
            "armazem": armazens_map.get(r.armazem_id, "N/A"),
            "recebimento_produtor_ton": r.rec_produtor,
            "envio_transbordo_ton": r.envio_transbordo,
            "vendas_ton": r.vendas,
            "saldo_estoque_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "excedente_estoque_ton": r.excedente,
        })
    return sorted(results, key=lambda x: (x["mes"], x["armazem"]))


def compare_factories(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.compare_factories`."""
    resumos = list(ResumoMensalFabrica.all_cooperativas.filter(cenario_id=scenario_id))
    if not resumos:
        return []

    fabrica_ids = {r.fabrica_id for r in resumos}
    fabricas_map = {
        f.id: f.nome for f in Fabrica.all_cooperativas.filter(id__in=fabrica_ids)
    }

    df = pd.DataFrame([{
        "fabrica_id": r.fabrica_id,
        "fabrica": fabricas_map.get(r.fabrica_id, "N/A"),
        "rec_produtor": r.rec_produtor,
        "rec_transbordo": r.rec_transbordo,
        "esmagado": r.esmagado,
        "saldo_estoque": r.saldo_estoque,
        "excedente": r.excedente,
    } for r in resumos])

    comp = df.groupby(["fabrica_id", "fabrica"]).agg({
        "rec_produtor": "sum",
        "rec_transbordo": "sum",
        "esmagado": "sum",
        "saldo_estoque": "max",
        "excedente": "sum",
    }).reset_index()

    comp.rename(columns={
        "rec_produtor": "recebimento_produtor_total_ton",
        "rec_transbordo": "recebimento_transbordo_total_ton",
        "esmagado": "esmagado_total_ton",
        "saldo_estoque": "pico_estoque_mensal_ton",
        "excedente": "excedente_total_acumulado_ton",
    }, inplace=True)

    return comp.to_dict(orient="records")


def compare_warehouses(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.compare_warehouses`."""
    resumos = list(ResumoMensalArmazem.all_cooperativas.filter(cenario_id=scenario_id))
    if not resumos:
        return []

    armazem_ids = {r.armazem_id for r in resumos}
    armazens_map = {
        a.id: a.nome for a in Armazem.all_cooperativas.filter(id__in=armazem_ids)
    }

    df = pd.DataFrame([{
        "armazem_id": r.armazem_id,
        "armazem": armazens_map.get(r.armazem_id, "N/A"),
        "rec_produtor": r.rec_produtor,
        "envio_transbordo": r.envio_transbordo,
        "vendas": r.vendas,
        "saldo_estoque": r.saldo_estoque,
        "excedente": r.excedente,
    } for r in resumos])

    comp = df.groupby(["armazem_id", "armazem"]).agg({
        "rec_produtor": "sum",
        "envio_transbordo": "sum",
        "vendas": "sum",
        "saldo_estoque": "max",
        "excedente": "sum",
    }).reset_index()

    comp.rename(columns={
        "rec_produtor": "recebimento_produtor_total_ton",
        "envio_transbordo": "envio_transbordo_total_ton",
        "vendas": "vendas_total_ton",
        "saldo_estoque": "pico_estoque_mensal_ton",
        "excedente": "excedente_total_acumulado_ton",
    }, inplace=True)

    return comp.to_dict(orient="records")


def get_stock_excesses_report(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_stock_excesses_report`."""
    alertas = []

    res_fab = list(ResumoMensalFabrica.all_cooperativas.filter(cenario_id=scenario_id, excedente__gt=0))
    fabrica_ids = {r.fabrica_id for r in res_fab}
    fabricas_map = {
        f.id: f.nome for f in Fabrica.all_cooperativas.filter(id__in=fabrica_ids)
    } if fabrica_ids else {}
    for r in res_fab:
        alertas.append({
            "mes": r.mes,
            "entidade_tipo": "Fabrica",
            "entidade_id": r.fabrica_id,
            "entidade_nome": fabricas_map.get(r.fabrica_id, "N/A"),
            "estoque_final_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "excedente_estouro_ton": r.excedente,
        })

    res_arm = list(ResumoMensalArmazem.all_cooperativas.filter(cenario_id=scenario_id, excedente__gt=0))
    armazem_ids = {r.armazem_id for r in res_arm}
    armazens_map = {
        a.id: a.nome for a in Armazem.all_cooperativas.filter(id__in=armazem_ids)
    } if armazem_ids else {}
    for r in res_arm:
        alertas.append({
            "mes": r.mes,
            "entidade_tipo": "Armazem",
            "entidade_id": r.armazem_id,
            "entidade_nome": armazens_map.get(r.armazem_id, "N/A"),
            "estoque_final_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "excedente_estouro_ton": r.excedente,
        })

    return sorted(alertas, key=lambda x: (x["mes"], x["entidade_tipo"], x["entidade_nome"]))


def clone_scenario(cooperativa_id: int, scenario_name: str, source_scenario_id: int) -> int:
    """Porte 1:1 de `scenarios.clone_scenario` (SQLAlchemy). Diferente das
    demais funções deste módulo, recebe um ID de origem potencialmente
    vindo de fora (o cenário a clonar) -- valida explicitamente que
    pertence a `cooperativa_id` antes de tocar em qualquer dado (ver ADR
    0006 e spec 2026-08-23, §5)."""
    try:
        origem = Cenario.all_cooperativas.get(id=source_scenario_id, cooperativa_id=cooperativa_id)
    except Cenario.DoesNotExist:
        raise ValueError(
            f"Cenário de origem {source_scenario_id} não encontrado para esta cooperativa."
        )

    with transaction.atomic():
        novo = Cenario.all_cooperativas.create(
            cooperativa_id=cooperativa_id, nome=scenario_name, is_oficial=False,
        )

        fabrica_map = {}
        for f in Fabrica.all_cooperativas.filter(cenario_id=origem.id):
            nova = Fabrica.all_cooperativas.create(
                cooperativa_id=cooperativa_id, cenario_id=novo.id, nome=f.nome,
                capacidade_estatica=f.capacidade_estatica,
                capacidade_esmagamento_diaria=f.capacidade_esmagamento_diaria,
                capacidade_recebimento_diaria=f.capacidade_recebimento_diaria,
                limite_caminhoes=f.limite_caminhoes,
                carga_media_caminhao=f.carga_media_caminhao,
                estoque_inicial=f.estoque_inicial,
            )
            fabrica_map[f.id] = nova.id

        armazem_map = {}
        for a in Armazem.all_cooperativas.filter(cenario_id=origem.id):
            nova = Armazem.all_cooperativas.create(
                cooperativa_id=cooperativa_id, cenario_id=novo.id, nome=a.nome,
                capacidade_estatica=a.capacidade_estatica,
                capacidade_expedicao_diaria=a.capacidade_expedicao_diaria,
                estoque_inicial=a.estoque_inicial,
            )
            armazem_map[a.id] = nova.id

        for r in Rota.all_cooperativas.filter(cenario_id=origem.id):
            if r.armazem_id in armazem_map and r.fabrica_id in fabrica_map:
                Rota.all_cooperativas.create(
                    cooperativa_id=cooperativa_id, cenario_id=novo.id,
                    armazem_id=armazem_map[r.armazem_id], fabrica_id=fabrica_map[r.fabrica_id],
                    distancia_km=r.distancia_km, custo_frete_ton=r.custo_frete_ton,
                    custo_frete_entressafra=r.custo_frete_entressafra,
                )

        if fabrica_map:
            for p in PrevisaoFabrica.all_cooperativas.filter(fabrica_id__in=fabrica_map.keys()):
                PrevisaoFabrica.all_cooperativas.create(
                    cooperativa_id=cooperativa_id, fabrica_id=fabrica_map[p.fabrica_id],
                    mes_referencia=p.mes_referencia,
                    recebimento_produtor=p.recebimento_produtor, vendas=p.vendas,
                )

        if armazem_map:
            for p in PrevisaoArmazem.all_cooperativas.filter(armazem_id__in=armazem_map.keys()):
                PrevisaoArmazem.all_cooperativas.create(
                    cooperativa_id=cooperativa_id, armazem_id=armazem_map[p.armazem_id],
                    mes_referencia=p.mes_referencia,
                    recebimento_produtor=p.recebimento_produtor, vendas=p.vendas,
                )

        for s in SafraUnidade.all_cooperativas.filter(cenario_id=origem.id):
            if s.entidade_tipo == 'Armazém':
                novo_entidade_id = armazem_map.get(s.entidade_id)
            else:
                novo_entidade_id = fabrica_map.get(s.entidade_id)
            if novo_entidade_id:
                SafraUnidade.all_cooperativas.create(
                    cooperativa_id=cooperativa_id, cenario_id=novo.id,
                    entidade_tipo=s.entidade_tipo, entidade_id=novo_entidade_id,
                    data_inicio=s.data_inicio, data_fim=s.data_fim,
                )

    return novo.id


def get_stock_ruptures_report(scenario_id: int) -> list[dict]:
    """Porte 1:1 de `logistics_services.get_stock_ruptures_report`."""
    alertas = []

    res_fab = list(ResumoMensalFabrica.all_cooperativas.filter(cenario_id=scenario_id, saldo_estoque__lt=0))
    fabrica_ids = {r.fabrica_id for r in res_fab}
    fabricas_map = {
        f.id: f.nome for f in Fabrica.all_cooperativas.filter(id__in=fabrica_ids)
    } if fabrica_ids else {}
    for r in res_fab:
        alertas.append({
            "mes": r.mes,
            "entidade_tipo": "Fabrica",
            "entidade_id": r.fabrica_id,
            "entidade_nome": fabricas_map.get(r.fabrica_id, "N/A"),
            "estoque_final_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "deficit_ton": abs(r.saldo_estoque),
        })

    res_arm = list(ResumoMensalArmazem.all_cooperativas.filter(cenario_id=scenario_id, saldo_estoque__lt=0))
    armazem_ids = {r.armazem_id for r in res_arm}
    armazens_map = {
        a.id: a.nome for a in Armazem.all_cooperativas.filter(id__in=armazem_ids)
    } if armazem_ids else {}
    for r in res_arm:
        alertas.append({
            "mes": r.mes,
            "entidade_tipo": "Armazem",
            "entidade_id": r.armazem_id,
            "entidade_nome": armazens_map.get(r.armazem_id, "N/A"),
            "estoque_final_ton": r.saldo_estoque,
            "capacidade_estatica_ton": r.capacidade_estatica,
            "deficit_ton": abs(r.saldo_estoque),
        })

    return sorted(alertas, key=lambda x: (x["mes"], x["entidade_tipo"], x["entidade_nome"]))
