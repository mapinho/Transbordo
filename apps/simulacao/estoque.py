"""Motor de agregação do painel de Estoque (Fase 14). Funções puras sobre
`ResumoMensalArmazem` / `ResumoMensalFabrica`, via ORM escopado (`objects`),
não `all_cooperativas` (diferente de `services.py` — ver ADR 0006 e a spec
2026-09-02)."""
from django.db.models import Sum

from apps.simulacao.models import (
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
            {"key": "unidade", "label": "Armazém", "tipo": "texto"},
            _m("rec_produtor", "Rec. Produtor"), _m("envio_transbordo", "Envio Transbordo"),
            _m("vendas", "Vendas"), _m("saldo", "Saldo"),
            _m("capacidade", "Cap. Estática"), _m("excedente", "Excedente"),
        ],
        "pagina": True,
    },
    "fabrica": {
        "fonte": "fabrica",
        "colunas": [
            {"key": "unidade", "label": "Fábrica", "tipo": "texto"},
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


_FONTE_UNIDADE = {
    "armazem": (ResumoMensalArmazem, "armazem__nome", ("envio_transbordo", "vendas")),
    "fabrica": (ResumoMensalFabrica, "fabrica__nome", ("rec_transbordo", "esmagado")),
}


def _linhas_por_unidade(cenario_id, fonte, filtros):
    modelo, campo, extras = _FONTE_UNIDADE[fonte]
    campos = ["mes", campo, "rec_produtor", *extras, "saldo_estoque", "capacidade_estatica", "excedente"]
    qs = _queryset_unidade(modelo, cenario_id, fonte, filtros).values(*campos).order_by("mes", campo)
    return qs, campo, extras


def _totais_unidade(cenario_id, fonte, filtros, extras):
    """Totais do recorte INTEIRO (independem de paginação — ver `resultados.py`,
    que também agrega antes de fatiar): fluxos (`rec_produtor` + `extras`) = Σ;
    `saldo`/`excedente` = pico (max da Σ mensal); `capacidade` = Σ do 1º mês
    (Ruling T2-a)."""
    base = _queryset_unidade(_FONTE_UNIDADE[fonte][0], cenario_id, fonte, filtros)
    somas = {"rec_produtor": Sum("rec_produtor")}
    for e in extras:
        somas[e] = Sum(e)
    agg = base.aggregate(**somas)
    tot = {k: (agg[k] or 0.0) for k in somas}
    por_mes = sorted(
        base.values("mes").annotate(
            sl=Sum("saldo_estoque"), ex=Sum("excedente"), cp=Sum("capacidade_estatica")),
        key=lambda r: r["mes"])
    # pico = max da Σ mensal, semeado pelas próprias linhas (0.0 só quando não há
    # nenhuma) — um recorte todo-negativo devolve o mês menos negativo, não 0.0.
    tot["saldo"] = max((r["sl"] or 0.0 for r in por_mes), default=0.0)
    tot["excedente"] = max((r["ex"] or 0.0 for r in por_mes), default=0.0)
    tot["capacidade"] = (por_mes[0]["cp"] or 0.0) if por_mes else 0.0
    return tot


def _totais(linhas, metricas):
    """Fluxos = Σ; `saldo`/`excedente` = pico (max das linhas, `0.0` só quando
    não há linhas — um recorte todo-negativo devolve o mês menos negativo, igual
    ao `card_de_pico`); `capacidade` = valor do 1º mês (constante no sistema —
    ver Ruling T2-a)."""
    tot = {m: 0.0 for m in metricas}
    for m in metricas:
        if m in ("saldo", "excedente"):
            tot[m] = max((linha.get(m, 0.0) for linha in linhas), default=0.0)
        elif m == "capacidade":
            continue
        else:
            tot[m] = sum(linha.get(m, 0.0) for linha in linhas)
    if linhas and "capacidade" in tot:
        tot["capacidade"] = linhas[0].get("capacidade", 0.0)
    return tot


_METRICAS_CARD = ("recebimento", "transbordo", "esmagamento", "vendas",
                  "saldo", "capacidade", "excedente")


def _delta(atual, comparado):
    """Δ% de `atual` sobre `comparado` (mesma regra da Fase 13):
    `comparado is None` -> `"novo"`; `comparado == 0` -> `0.0` se `atual == 0`,
    senão `None`; senão `(atual - comparado) / comparado * 100`."""
    if comparado is None:
        return "novo"
    if comparado == 0:
        return 0.0 if atual == 0 else None
    return (atual - comparado) / comparado * 100


def _traduzir_filtros(filtros, cenario_id):
    """Re-resolve `armazem_ids`/`fabrica_ids` (ids de um cenário) para os ids
    dos armazéns/fábricas de mesmo NOME em `cenario_id` (clones têm ids novos,
    nomes iguais). Sem unidade de mesmo nome no cenário comparado, a lista fica
    vazia = "sem filtro" (limitação conhecida — Fase 13 Ruling 8)."""
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


def card_de_pico(cenario_id, filtros):
    """Card-resumo do recorte na visão "sistema": fluxos (`recebimento`,
    `transbordo`, `esmagamento`, `vendas`) = Σ de todos os meses; `saldo` e
    `excedente` = pico (máx mensal); `capacidade` = valor do 1º mês; `saldo_min`
    = mín mensal; `mes_ruptura` = `_mes_ptbr` do mês do mín se `< 0`, senão
    `None`. `mes_pico` = `_mes_ptbr` do mês de maior saldo (`""` se vazio);
    `ocupacao_pct` = `min(saldo, cap)/cap*100` e `excedente_pct` =
    `excedente/cap*100` (ambos `0.0` se `cap <= 0`). Recorte vazio -> tudo zero,
    `mes_ruptura` None."""
    linhas = _agregar_sistema(cenario_id, filtros)
    card = {m: 0.0 for m in _METRICAS_CARD}
    card["saldo_min"] = 0.0
    card["mes_ruptura"] = None
    card["mes_pico"] = ""
    card["ocupacao_pct"] = 0.0
    card["excedente_pct"] = 0.0
    if not linhas:
        return card
    for linha in linhas:
        for m in ("recebimento", "transbordo", "esmagamento", "vendas"):
            card[m] += linha[m]
    card["saldo"] = max(linha["saldo"] for linha in linhas)
    card["excedente"] = max(linha["excedente"] for linha in linhas)
    card["capacidade"] = linhas[0]["capacidade"]
    pior = min(linhas, key=lambda linha: linha["saldo"])
    card["saldo_min"] = pior["saldo"]
    if pior["saldo"] < 0:
        card["mes_ruptura"] = _mes_ptbr(pior["mes"])
    pico = max(linhas, key=lambda linha: linha["saldo"])
    card["mes_pico"] = _mes_ptbr(pico["mes"])
    cap = card["capacidade"]
    if cap > 0:
        card["ocupacao_pct"] = round(min(card["saldo"], cap) / cap * 100, 1)
        card["excedente_pct"] = round(card["excedente"] / cap * 100, 1)
    return card


def card_com_delta(cenario_id, cenario_comparado_id, filtros):
    """`card_de_pico(cenario_id, filtros)` + `"delta"`: dict `{métrica: Δ%}`
    contra `cenario_comparado_id` (filtros traduzidos por nome), ou `None` se
    `cenario_comparado_id is None`."""
    atual = card_de_pico(cenario_id, filtros)
    if cenario_comparado_id is None:
        atual["delta"] = None
        return atual
    comp = card_de_pico(cenario_comparado_id, _traduzir_filtros(filtros, cenario_comparado_id))
    atual["delta"] = {m: _delta(atual[m], comp[m]) for m in _METRICAS_CARD}
    return atual


def cenarios_comparaveis(cenario_id, cooperativa_id):
    """Cenários da cooperativa com ao menos um `ResumoMensalArmazem` OU
    `ResumoMensalFabrica`, exceto `cenario_id`, ordenados por `-is_oficial,
    nome`."""
    com_estoque = set(
        ResumoMensalArmazem.objects.filter(cooperativa_id=cooperativa_id)
        .values_list("cenario_id", flat=True)) | set(
        ResumoMensalFabrica.objects.filter(cooperativa_id=cooperativa_id)
        .values_list("cenario_id", flat=True))
    qs = (Cenario.objects.filter(cooperativa_id=cooperativa_id, id__in=list(com_estoque))
          .exclude(id=cenario_id).order_by("-is_oficial", "nome"))
    return [{"id": c.id, "nome": c.nome} for c in qs]


def agregar(cenario_id, visao, filtros, pagina=1, limite=None):
    """`{"colunas", "linhas", "totais", "paginacao", "faixas"}` para uma das três
    visões.

    `pagina=None` -> sem paginação. `limite` não-nulo e nº de linhas do recorte
    > `limite` -> `raise RecorteGrandeDemais(total)` ANTES de materializar as
    linhas por unidade (na "sistema" o check é depois — são ≤12 linhas).

    `faixas`: `None` na visão "sistema"; nas visões por unidade, `dict`
    `{mes: <linha do sistema desse mês>}` só para os meses presentes em `linhas`
    (a UI mostra os totais do sistema numa faixa por mês; a coluna "Mês" some)."""
    visao = normalizar_visao(visao)
    cfg = VISOES[visao]

    if visao == "sistema":
        linhas = _agregar_sistema(cenario_id, filtros)
        if limite is not None and len(linhas) > limite:
            raise RecorteGrandeDemais(len(linhas))
        totais = _totais(linhas, _METRICAS_SISTEMA)
        return {"colunas": cfg["colunas"], "linhas": linhas, "totais": totais,
                "paginacao": None, "faixas": None}

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
    totais = _totais_unidade(cenario_id, cfg["fonte"], filtros, extras)
    faixas = {}
    if linhas:
        meses = {linha["mes"] for linha in linhas}
        for sis in _agregar_sistema(cenario_id, filtros):
            if sis["mes"] in meses:
                faixas[sis["mes"]] = sis
    return {"colunas": cfg["colunas"], "linhas": linhas,
            "totais": totais, "paginacao": paginacao, "faixas": faixas}


def aplicar_comparacao(dados, cenario_comparado_id, visao, filtros):
    """Anota `dados` (retorno de `agregar` do cenário atual) com Δ% contra
    `cenario_comparado_id`: grava `linha["<m>_delta"]` para cada métrica
    `comparavel` e `dados["totais_delta"]`. **NÃO altera `dados["colunas"]`** — o
    template renderiza o Δ embutido na célula da métrica. Vale para as 3 visões."""
    visao = normalizar_visao(visao)
    comparaveis = [c["key"] for c in dados["colunas"] if c.get("comparavel")]

    comp = agregar(cenario_comparado_id, visao,
                   _traduzir_filtros(filtros, cenario_comparado_id), pagina=None)
    por_chave = {linha_c["_chave"]: linha_c for linha_c in comp["linhas"]}

    for linha in dados["linhas"]:
        alvo = por_chave.get(linha["_chave"])
        for m in comparaveis:
            linha[f"{m}_delta"] = _delta(linha[m], alvo[m] if alvo else None)

    dados["totais_delta"] = {
        m: _delta(dados["totais"][m], comp["totais"][m]) for m in comparaveis}
    return dados


def dados_grafico(cenario_id, filtros, cenario_comparado_id):
    """SEMPRE um gráfico de linha dos totais da visão "Sistema" ("Saldo total"
    + "Excedente total" por mês), independente da visão corrente. Com
    `cenario_comparado_id`, acrescenta os dois datasets "(comparado)" alinhados
    pelos meses do cenário atual (mês ausente no comparado -> 0.0)."""
    linhas = _agregar_sistema(cenario_id, filtros)
    labels = [_mes_ptbr(linha["mes"]) for linha in linhas]
    datasets = [
        {"label": "Saldo total", "dados": [linha["saldo"] for linha in linhas], "eixo": "y"},
        {"label": "Excedente total", "dados": [linha["excedente"] for linha in linhas], "eixo": "y"},
    ]
    if cenario_comparado_id:
        comp = _agregar_sistema(
            cenario_comparado_id, _traduzir_filtros(filtros, cenario_comparado_id))
        m_saldo = {_mes_ptbr(linha["mes"]): linha["saldo"] for linha in comp}
        m_exc = {_mes_ptbr(linha["mes"]): linha["excedente"] for linha in comp}
        datasets += [
            {"label": "Saldo total (comparado)",
             "dados": [m_saldo.get(x, 0.0) for x in labels], "eixo": "y"},
            {"label": "Excedente total (comparado)",
             "dados": [m_exc.get(x, 0.0) for x in labels], "eixo": "y"},
        ]
    return {"tipo": "line", "labels": labels, "datasets": datasets}
