"""Motor de agregação do painel de Estoque (Fase 14). Funções puras sobre
`ResumoMensalArmazem` / `ResumoMensalFabrica`, via ORM escopado (`objects`),
não `all_cooperativas` (diferente de `services.py` — ver ADR 0006 e a spec
2026-09-02)."""
from apps.simulacao.models import (  # noqa: F401  (Cenario/Armazem/Fabrica usados nas tasks seguintes)
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
