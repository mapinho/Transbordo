"""Motor de agregação do painel de Estoque (Fase 14). Funções puras sobre
`ResumoMensalArmazem` / `ResumoMensalFabrica`, via ORM escopado (`objects`),
não `all_cooperativas` (diferente de `services.py` — ver ADR 0006 e a spec
2026-09-02)."""
from django.db.models import Sum

from apps.simulacao.models import (  # noqa: F401  (Armazem/Cenario/Fabrica usados nas tasks seguintes)
    Armazem,
    Cenario,
    Fabrica,
    ResumoMensalArmazem,
    ResumoMensalFabrica,
)

PAGE_SIZE = 100
EXPORT_MAX = 50_000

ROTULOS_VISAO = (("sistema", "Sistema"), ("armazem", "Por armazém"), ("fabrica", "Por fábrica"))


class RecorteGrandeDemais(Exception):
    """O recorte tem mais linhas do que o `limite` passado a `agregar`."""


_COL_MES = {"key": "mes", "label": "Mês", "tipo": "mes"}


def _m(key, label):
    return {"key": key, "label": label, "tipo": "num", "comparavel": True}


VISOES = {
    "sistema": {
        "fonte": "sistema",
        "colunas": [
            _COL_MES,
            _m("recebimento", "Recebimento"), _m("transbordo", "Transbordo"),
            _m("esmagamento", "Esmagamento"), _m("vendas", "Vendas"),
            _m("saldo", "Saldo"), _m("capacidade", "Cap. Estática"),
            _m("excedente", "Excedente"),
        ],
        "pagina": False,
    },
    "armazem": {
        "fonte": "armazem",
        "colunas": [
            _COL_MES, {"key": "unidade", "label": "Armazém", "tipo": "texto"},
            _m("rec_produtor", "Rec. Produtor"), _m("envio_transbordo", "Envio Transbordo"),
            _m("vendas", "Vendas"), _m("saldo", "Saldo"),
            _m("capacidade", "Cap. Estática"), _m("excedente", "Excedente"),
        ],
        "pagina": True,
    },
    "fabrica": {
        "fonte": "fabrica",
        "colunas": [
            _COL_MES, {"key": "unidade", "label": "Fábrica", "tipo": "texto"},
            _m("rec_produtor", "Rec. Produtor"), _m("rec_transbordo", "Rec. Transbordo"),
            _m("esmagado", "Esmagado"), _m("saldo", "Saldo"),
            _m("capacidade", "Cap. Estática"), _m("excedente", "Excedente"),
        ],
        "pagina": True,
    },
}


def normalizar_visao(visao):
    return visao if visao in VISOES else "sistema"


def _queryset_unidade(modelo, cenario_id, fonte, filtros):
    """QuerySet de `modelo` (`ResumoMensal*`) filtrado por cenário + mês + unidade.
    `fonte` ∈ {"armazem","fabrica"} decide qual filtro de id aplicar."""
    qs = modelo.objects.filter(cenario_id=cenario_id)
    if filtros.get("mes_de"):
        qs = qs.filter(mes__gte=filtros["mes_de"])
    if filtros.get("mes_ate"):
        qs = qs.filter(mes__lte=filtros["mes_ate"])
    if fonte == "armazem" and filtros.get("armazem_ids"):
        qs = qs.filter(armazem_id__in=filtros["armazem_ids"])
    if fonte == "fabrica" and filtros.get("fabrica_ids"):
        qs = qs.filter(fabrica_id__in=filtros["fabrica_ids"])
    return qs


# --- helpers de agregação -------------------------------------------------


def _mes_ptbr(mes):
    """`"2026-01"` -> `"01/2026"`."""
    return f"{mes[5:7]}/{mes[0:4]}"


def _alerta_da_linha(linha):
    """`"ruptura"` se saldo < 0 (prioridade); senão `"excedente"` se
    excedente > 0; senão `None`."""
    if linha.get("saldo", 0.0) < 0:
        return "ruptura"
    if linha.get("excedente", 0.0) > 0:
        return "excedente"
    return None


_METRICAS_SISTEMA = ("recebimento", "transbordo", "esmagamento", "vendas",
                     "saldo", "capacidade", "excedente")


def _mes_zerado(mes):
    d = {"mes": mes}
    for k in _METRICAS_SISTEMA:
        d[k] = 0.0
    return d


def _agregar_sistema(cenario_id, filtros):
    """Uma linha por mês, ordenada por `mes`, com o merge das duas tabelas.
    `recebimento` soma `rec_produtor` das DUAS tabelas; `transbordo` é só o
    `envio_transbordo` dos armazéns (NÃO soma `rec_transbordo`)."""
    arm = (_queryset_unidade(ResumoMensalArmazem, cenario_id, "armazem", filtros)
           .values("mes")
           .annotate(rp=Sum("rec_produtor"), tb=Sum("envio_transbordo"), vd=Sum("vendas"),
                     sl=Sum("saldo_estoque"), cp=Sum("capacidade_estatica"), ex=Sum("excedente")))
    fab = (_queryset_unidade(ResumoMensalFabrica, cenario_id, "fabrica", filtros)
           .values("mes")
           .annotate(rp=Sum("rec_produtor"), esm=Sum("esmagado"),
                     sl=Sum("saldo_estoque"), cp=Sum("capacidade_estatica"), ex=Sum("excedente")))
    por_mes = {}
    for r in arm:
        m = por_mes.setdefault(r["mes"], _mes_zerado(r["mes"]))
        m["recebimento"] += r["rp"] or 0.0
        m["transbordo"] += r["tb"] or 0.0
        m["vendas"] += r["vd"] or 0.0
        m["saldo"] += r["sl"] or 0.0
        m["capacidade"] += r["cp"] or 0.0
        m["excedente"] += r["ex"] or 0.0
    for r in fab:
        m = por_mes.setdefault(r["mes"], _mes_zerado(r["mes"]))
        m["recebimento"] += r["rp"] or 0.0
        m["esmagamento"] += r["esm"] or 0.0
        m["saldo"] += r["sl"] or 0.0
        m["capacidade"] += r["cp"] or 0.0
        m["excedente"] += r["ex"] or 0.0
    linhas = []
    for mes in sorted(por_mes):
        linha = por_mes[mes]
        linha["_chave"] = (mes,)
        linha["_alerta"] = _alerta_da_linha(linha)
        linhas.append(linha)
    return linhas


def _linhas_por_unidade(cenario_id, fonte, filtros):
    if fonte == "armazem":
        modelo, campo, extras = ResumoMensalArmazem, "armazem__nome", ("envio_transbordo", "vendas")
    else:
        modelo, campo, extras = ResumoMensalFabrica, "fabrica__nome", ("rec_transbordo", "esmagado")
    campos = ["mes", campo, "rec_produtor", *extras, "saldo_estoque", "capacidade_estatica", "excedente"]
    qs = _queryset_unidade(modelo, cenario_id, fonte, filtros).values(*campos).order_by("mes", campo)
    return qs, campo, extras


def _totais(linhas, metricas):
    """Fluxos = Σ; `saldo`/`excedente` = pico (max); `capacidade` = valor do
    1º mês (constante no sistema — ver Ruling T2-a)."""
    tot = {m: 0.0 for m in metricas}
    for linha in linhas:
        for m in metricas:
            if m in ("saldo", "excedente"):
                tot[m] = max(tot[m], linha.get(m, 0.0))
            elif m == "capacidade":
                continue
            else:
                tot[m] += linha.get(m, 0.0)
    if linhas and "capacidade" in tot:
        tot["capacidade"] = linhas[0].get("capacidade", 0.0)
    return tot


def agregar(cenario_id, visao, filtros, pagina=1, limite=None):
    """`{"colunas", "linhas", "totais", "paginacao"}` para uma das três visões.

    `pagina=None` -> sem paginação. `limite` não-nulo e nº de linhas do recorte
    > `limite` -> `raise RecorteGrandeDemais(total)` ANTES de materializar as
    linhas por unidade (na "sistema" o check é depois — são ≤12 linhas)."""
    visao = normalizar_visao(visao)
    cfg = VISOES[visao]

    if visao == "sistema":
        linhas = _agregar_sistema(cenario_id, filtros)
        if limite is not None and len(linhas) > limite:
            raise RecorteGrandeDemais(len(linhas))
        totais = _totais(linhas, _METRICAS_SISTEMA)
        return {"colunas": cfg["colunas"], "linhas": linhas, "totais": totais, "paginacao": None}

    qs, campo, extras = _linhas_por_unidade(cenario_id, cfg["fonte"], filtros)
    total = qs.count()
    if limite is not None and total > limite:
        raise RecorteGrandeDemais(total)
    paginacao = None
    if cfg["pagina"] and pagina is not None:
        num_paginas = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        pagina = min(max(1, pagina), num_paginas)
        ini = (pagina - 1) * PAGE_SIZE
        qs = qs[ini:ini + PAGE_SIZE]
        paginacao = {"pagina": pagina, "num_paginas": num_paginas, "total": total}

    metricas = ("rec_produtor", *extras, "saldo", "capacidade", "excedente")
    linhas = []
    for row in qs:
        linha = {"mes": row["mes"], "unidade": row[campo],
                 "rec_produtor": row["rec_produtor"] or 0.0,
                 "saldo": row["saldo_estoque"] or 0.0,
                 "capacidade": row["capacidade_estatica"] or 0.0,
                 "excedente": row["excedente"] or 0.0}
        for e in extras:
            linha[e] = row[e] or 0.0
        linha["_chave"] = (row["mes"], row[campo])
        linha["_alerta"] = _alerta_da_linha(linha)
        linhas.append(linha)
    return {"colunas": cfg["colunas"], "linhas": linhas,
            "totais": _totais(linhas, metricas), "paginacao": paginacao}
