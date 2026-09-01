"""Motor de agregação do painel de Resultados (Fase 13). Funções puras sobre
`MovimentacaoDiaria`, via ORM escopado (`objects`), não `all_cooperativas`
(diferente de `services.py` — ver ADR 0006 e a spec 2026-09-01)."""
import datetime

from django.db.models import Sum
from django.db.models.functions import TruncMonth

from apps.simulacao.models import Cenario, MovimentacaoDiaria
from apps.simulacao.services import KG_PER_SACA, KG_PER_TON

PAGE_SIZE = 100
EXPORT_MAX = 50_000

PERIODOS = ("diario", "mensal", "total")
AGRUPAMENTOS = ("fabrica_armazem", "fabrica", "armazem", "nada")

_COL_DIA = {"key": "dia", "label": "Dia", "tipo": "data_dia"}
_COL_MES = {"key": "dia", "label": "Mês", "tipo": "data_mes"}
_COL_ORIGEM = {"key": "origem", "label": "Origem", "tipo": "texto"}
_COL_DESTINO = {"key": "destino", "label": "Destino", "tipo": "texto"}
_COLS_METRICA = [
    {"key": "ton", "label": "Toneladas", "tipo": "num", "comparavel": True},
    {"key": "sacas", "label": "Sacas", "tipo": "num", "comparavel": True},
    {"key": "custo", "label": "Frete (R$)", "tipo": "moeda", "comparavel": True},
]


def _visao(group_by, dimensoes, pagina):
    return {"group_by": group_by, "colunas": [*dimensoes, *_COLS_METRICA], "pagina": pagina}


VISOES = {
    ("diario", "fabrica_armazem"): _visao(
        ["data", "armazem__nome", "fabrica__nome"], [_COL_DIA, _COL_ORIGEM, _COL_DESTINO], True),
    ("diario", "fabrica"): _visao(["data", "fabrica__nome"], [_COL_DIA, _COL_DESTINO], True),
    ("diario", "armazem"): _visao(["data", "armazem__nome"], [_COL_DIA, _COL_ORIGEM], True),
    ("diario", "nada"): _visao(["data"], [_COL_DIA], False),
    ("mensal", "fabrica_armazem"): _visao(
        ["mes", "armazem__nome", "fabrica__nome"], [_COL_MES, _COL_ORIGEM, _COL_DESTINO], False),
    ("mensal", "fabrica"): _visao(["mes", "fabrica__nome"], [_COL_MES, _COL_DESTINO], False),
    ("mensal", "armazem"): _visao(["mes", "armazem__nome"], [_COL_MES, _COL_ORIGEM], False),
    ("mensal", "nada"): _visao(["mes"], [_COL_MES], False),
    ("total", "nada"): _visao([], [], False),
}

# `TruncMonth` fica pronto para as tasks de agregação usarem no annotate.
TRUNC_MES = TruncMonth("data")


def normalizar_visao(periodo, agrupar):
    if periodo == "total":
        return ("total", "nada")
    if (periodo, agrupar) in VISOES:
        return (periodo, agrupar)
    return ("diario", "fabrica_armazem")


def _queryset_filtrado(cenario_id, filtros):
    qs = MovimentacaoDiaria.objects.filter(cenario_id=cenario_id)
    if filtros.get("data_de"):
        qs = qs.filter(data__gte=filtros["data_de"])
    if filtros.get("data_ate"):
        qs = qs.filter(data__lte=filtros["data_ate"])
    if filtros.get("armazem_ids"):
        qs = qs.filter(armazem_id__in=filtros["armazem_ids"])
    if filtros.get("fabrica_ids"):
        qs = qs.filter(fabrica_id__in=filtros["fabrica_ids"])
    return qs


def _com_sacas(ton):
    return (ton or 0.0) * KG_PER_TON / KG_PER_SACA


def agregar(cenario_id, periodo, agrupar, filtros, pagina=1):
    periodo, agrupar = normalizar_visao(periodo, agrupar)
    visao = VISOES[(periodo, agrupar)]
    base = _queryset_filtrado(cenario_id, filtros)

    tot = base.aggregate(ton=Sum("quantidade_ton"), custo=Sum("custo_total"))
    totais = {
        "ton": tot["ton"] or 0.0,
        "sacas": _com_sacas(tot["ton"]),
        "custo": tot["custo"] or 0.0,
    }

    if periodo == "total":
        linha = {"ton": totais["ton"], "sacas": totais["sacas"], "custo": totais["custo"],
                 "_chave": ("total",)}
        return {"colunas": visao["colunas"], "linhas": [linha], "totais": totais, "paginacao": None}

    group_by = visao["group_by"]
    qs = base
    if "mes" in group_by:
        qs = qs.annotate(mes=TRUNC_MES)
    qs = (qs.values(*group_by)
            .annotate(ton=Sum("quantidade_ton"), custo=Sum("custo_total"))
            .order_by(*group_by))

    total_linhas = qs.count()
    paginacao = None
    if visao["pagina"] and pagina is not None:
        num_paginas = max(1, (total_linhas + PAGE_SIZE - 1) // PAGE_SIZE)
        pagina = min(max(1, pagina), num_paginas)
        ini = (pagina - 1) * PAGE_SIZE
        qs = qs[ini:ini + PAGE_SIZE]
        paginacao = {"pagina": pagina, "num_paginas": num_paginas, "total": total_linhas}

    linhas = []
    for row in qs:
        dia = row.get("mes") or row.get("data")
        if isinstance(dia, datetime.datetime):
            dia = dia.date()
        linha = {"dia": dia, "ton": row["ton"] or 0.0, "sacas": _com_sacas(row["ton"]),
                 "custo": row["custo"] or 0.0}
        if "armazem__nome" in group_by:
            linha["origem"] = row["armazem__nome"]
        if "fabrica__nome" in group_by:
            linha["destino"] = row["fabrica__nome"]
        chave = [dia.isoformat() if periodo == "diario" else dia.strftime("%Y-%m")]
        if "origem" in linha:
            chave.append(linha["origem"])
        if "destino" in linha:
            chave.append(linha["destino"])
        linha["_chave"] = tuple(chave)
        linhas.append(linha)

    return {"colunas": visao["colunas"], "linhas": linhas, "totais": totais, "paginacao": paginacao}


_METRICAS = ("ton", "sacas", "custo")


def _delta(atual, comparado):
    if comparado is None:
        return "novo"
    if comparado == 0:
        return 0.0 if atual == 0 else None
    return (atual - comparado) / comparado * 100


def aplicar_comparacao(dados, cenario_comparado_id, periodo, agrupar, filtros):
    periodo, agrupar = normalizar_visao(periodo, agrupar)
    if (periodo, agrupar) == ("diario", "fabrica_armazem"):
        dados["comparacao_ignorada"] = True
        return dados
    dados["comparacao_ignorada"] = False

    comp = agregar(cenario_comparado_id, periodo, agrupar, filtros, pagina=None)
    por_chave = {l["_chave"]: l for l in comp["linhas"]}

    for linha in dados["linhas"]:
        alvo = por_chave.get(linha["_chave"])
        for m in _METRICAS:
            linha[f"{m}_delta"] = _delta(linha[m], alvo[m] if alvo else None)

    novas_colunas = []
    for col in dados["colunas"]:
        novas_colunas.append(col)
        if col["key"] in _METRICAS:
            novas_colunas.append(
                {"key": f'{col["key"]}_delta', "label": "Δ%", "tipo": "delta"})
    dados["colunas"] = novas_colunas

    dados["totais_delta"] = {
        m: _delta(dados["totais"][m], comp["totais"][m]) for m in _METRICAS}
    return dados


def totais_do_recorte(cenario_id, filtros):
    """Totais do recorte para o card do topo — mesmos números de
    `agregar(...)["totais"]`, mas sem montar linhas."""
    agg = _queryset_filtrado(cenario_id, filtros).aggregate(
        ton=Sum("quantidade_ton"), custo=Sum("custo_total"))
    return {"ton": agg["ton"] or 0.0, "sacas": _com_sacas(agg["ton"]), "custo": agg["custo"] or 0.0}


def cenarios_comparaveis(cenario_id, cooperativa_id):
    """Cenários da cooperativa com ao menos uma `MovimentacaoDiaria`, exceto
    `cenario_id`, ordenados por `-is_oficial, nome`."""
    com_mov = (MovimentacaoDiaria.objects.filter(cooperativa_id=cooperativa_id)
               .values_list("cenario_id", flat=True).distinct())
    qs = (Cenario.objects.filter(cooperativa_id=cooperativa_id, id__in=list(com_mov))
          .exclude(id=cenario_id).order_by("-is_oficial", "nome"))
    return [{"id": c.id, "nome": c.nome} for c in qs]
