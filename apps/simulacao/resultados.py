"""Motor de agregação do painel de Resultados (Fase 13). Funções puras sobre
`MovimentacaoDiaria`, via ORM escopado (`objects`), não `all_cooperativas`
(diferente de `services.py` — ver ADR 0006 e a spec 2026-09-01)."""
import datetime

from django.db.models import Sum
from django.db.models.functions import TruncMonth

from apps.simulacao.models import Armazem, Cenario, Fabrica, MovimentacaoDiaria
from apps.simulacao.services import KG_PER_SACA, KG_PER_TON

PAGE_SIZE = 100
EXPORT_MAX = 50_000

PERIODOS = ("diario", "mensal", "total")
AGRUPAMENTOS = ("fabrica_armazem", "fabrica", "armazem", "nada")

# Rótulos pt-BR dos dois combos primários (o valor cru vai no <option value>).
ROTULOS_PERIODO = (("diario", "Diário"), ("mensal", "Mensal"), ("total", "Total"))
ROTULOS_AGRUPAR = (
    ("fabrica_armazem", "Fábrica + Armazém"), ("fabrica", "Fábrica"),
    ("armazem", "Armazém"), ("nada", "Sem agrupamento"),
)


class RecorteGrandeDemais(Exception):
    """O recorte tem mais linhas do que o `limite` passado a `agregar`."""

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


def _traduzir_filtros(filtros, cenario_id):
    """Re-resolve armazem_ids/fabrica_ids (ids de um cenário) para os ids dos
    armazéns/fábricas de mesmo NOME em `cenario_id`. Necessário ao comparar
    cenários: clones têm ids novos, nomes iguais (mesma lógica de `_chave`)."""
    if not filtros.get("armazem_ids") and not filtros.get("fabrica_ids"):
        return filtros
    traduzido = dict(filtros)
    if filtros.get("armazem_ids"):
        nomes = Armazem.objects.filter(id__in=filtros["armazem_ids"]).values_list("nome", flat=True)
        traduzido["armazem_ids"] = list(
            Armazem.objects.filter(cenario_id=cenario_id, nome__in=list(nomes)).values_list("id", flat=True))
    if filtros.get("fabrica_ids"):
        nomes = Fabrica.objects.filter(id__in=filtros["fabrica_ids"]).values_list("nome", flat=True)
        traduzido["fabrica_ids"] = list(
            Fabrica.objects.filter(cenario_id=cenario_id, nome__in=list(nomes)).values_list("id", flat=True))
    return traduzido


def _com_sacas(ton):
    return (ton or 0.0) * KG_PER_TON / KG_PER_SACA


def agregar(cenario_id, periodo, agrupar, filtros, pagina=1, limite=None):
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
    if limite is not None and total_linhas > limite:
        raise RecorteGrandeDemais(total_linhas)
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
    """Anota `dados` (retorno de `agregar` do cenário atual) com Δ% contra
    `cenario_comparado_id`: `*_delta` por linha, colunas Δ%, e `totais_delta`.
    Linha crua (diario×fabrica_armazem) não recebe Δ."""
    periodo, agrupar = normalizar_visao(periodo, agrupar)
    if (periodo, agrupar) == ("diario", "fabrica_armazem"):
        dados["comparacao_ignorada"] = True
        return dados
    dados["comparacao_ignorada"] = False

    comp = agregar(cenario_comparado_id, periodo, agrupar,
                   _traduzir_filtros(filtros, cenario_comparado_id), pagina=None)
    por_chave = {linha_c["_chave"]: linha_c for linha_c in comp["linhas"]}

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


def totais_com_delta(cenario_id, cenario_comparado_id, filtros):
    """Totais do recorte do cenário + Δ% contra o comparado (filtros traduzidos
    por nome). `cenario_comparado_id` None → `delta` = None."""
    atual = totais_do_recorte(cenario_id, filtros)
    if cenario_comparado_id is None:
        atual["delta"] = None
        return atual
    comp = totais_do_recorte(
        cenario_comparado_id, _traduzir_filtros(filtros, cenario_comparado_id))
    atual["delta"] = {m: _delta(atual[m], comp[m]) for m in _METRICAS}
    return atual


def cenarios_comparaveis(cenario_id, cooperativa_id):
    """Cenários da cooperativa com ao menos uma `MovimentacaoDiaria`, exceto
    `cenario_id`, ordenados por `-is_oficial, nome`."""
    com_mov = (MovimentacaoDiaria.objects.filter(cooperativa_id=cooperativa_id)
               .values_list("cenario_id", flat=True).distinct())
    qs = (Cenario.objects.filter(cooperativa_id=cooperativa_id, id__in=list(com_mov))
          .exclude(id=cenario_id).order_by("-is_oficial", "nome"))
    return [{"id": c.id, "nome": c.nome} for c in qs]


def _serie_periodo(cenario_id, periodo, filtros):
    """Séries do período (labels, toneladas, custo) do cenário, sem agrupamento."""
    d = agregar(cenario_id, periodo, "nada", filtros, pagina=None)
    labels_fmt = "%m/%Y" if periodo == "mensal" else "%d/%m"
    return (
        [linha["dia"].strftime(labels_fmt) for linha in d["linhas"]],
        [linha["ton"] for linha in d["linhas"]],
        [linha["custo"] for linha in d["linhas"]],
    )


def dados_grafico(cenario_id, periodo, agrupar, filtros, cenario_comparado_id):
    """Payload de dataset para Chart.js nas duas visões com gráfico (barras
    mensal, linha diário-total). `None` nas demais. Usa sempre os totais do
    período, ignorando o agrupamento da tabela."""
    periodo, agrupar = normalizar_visao(periodo, agrupar)
    mostra = periodo == "mensal" or (periodo == "diario" and agrupar == "nada")
    if not mostra:
        return None
    labels, ton, custo = _serie_periodo(cenario_id, periodo, filtros)
    datasets = [
        {"label": "Toneladas", "dados": ton, "eixo": "y"},
        {"label": "Frete (R$)", "dados": custo, "eixo": "y2"},
    ]
    if cenario_comparado_id:
        _lab, ton_c, custo_c = _serie_periodo(
            cenario_comparado_id, periodo, _traduzir_filtros(filtros, cenario_comparado_id))
        # alinha pelo label do cenário atual; mês/dia ausente no comparado = 0
        mapa_ton = dict(zip(_lab, ton_c))
        mapa_custo = dict(zip(_lab, custo_c))
        datasets += [
            {"label": "Toneladas (comparado)",
             "dados": [mapa_ton.get(x, 0.0) for x in labels], "eixo": "y"},
            {"label": "Frete (comparado)",
             "dados": [mapa_custo.get(x, 0.0) for x in labels], "eixo": "y2"},
        ]
    return {"tipo": "bar" if periodo == "mensal" else "line",
            "labels": labels, "datasets": datasets}
