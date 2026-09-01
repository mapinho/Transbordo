"""Motor de agregação do painel de Resultados (Fase 13). Funções puras sobre
`MovimentacaoDiaria`, via ORM escopado (`objects`), não `all_cooperativas`
(diferente de `services.py` — ver ADR 0006 e a spec 2026-09-01)."""
from django.db.models.functions import TruncMonth

from apps.simulacao.services import KG_PER_SACA, KG_PER_TON  # noqa: F401  (usados nas tasks seguintes)

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
