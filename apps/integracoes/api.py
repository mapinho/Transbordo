"""Face JSON da Fase 6 — Django Ninja sobre apps/simulacao/services.py.

Endpoints somente-leitura espelhando 1:1 os 9 tools de `mcp_server.py`.
Autenticação e escopo de tenant: ver `apps/integracoes/auth.py` e
`docs/decisions/0008-face-json-django-ninja.md`.
"""
from django.shortcuts import get_object_or_404
from ninja import Field, NinjaAPI, Schema
from pydantic import ConfigDict

from apps.integracoes.auth import ApiKeyAuth
from apps.simulacao import services
from apps.simulacao.models import Cenario

api = NinjaAPI(
    title='Comigo — Face JSON',
    version='1.0.0',
    docs_url='/docs',
    auth=ApiKeyAuth(),
)


@api.exception_handler(ValueError)
def on_value_error(request, exc):
    """`services._parse_date` levanta ValueError em datas malformadas —
    devolve 400 com a mensagem, em vez de vazar um 500."""
    return api.create_response(request, {'detail': str(exc)}, status=400)


def _get_cenario(scenario_id: int) -> Cenario:
    """Autoriza o cenário contra a cooperativa da API key (contextvar
    definido pela auth). Cenário de outra cooperativa -> Http404 -> 404."""
    return get_object_or_404(Cenario, id=scenario_id)


def _nativos(registros: list[dict]) -> list[dict]:
    """Converte escalares numpy (vindos de `DataFrame.to_dict`) para tipos
    nativos, que o Pydantic v2 valida sem tropeçar."""
    return [
        {k: (v.item() if hasattr(v, 'item') else v) for k, v in registro.items()}
        for registro in registros
    ]


class CenarioSchema(Schema):
    id: int
    nome: str
    is_oficial: bool
    data_criacao: str | None = None


@api.get('/cenarios/', response=list[CenarioSchema])
def listar_cenarios(request):
    return services.list_scenarios(request.auth.cooperativa_id)


class MovimentacaoSchema(Schema):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    data: str
    origem_id: int
    origem: str
    destino_id: int
    destino: str
    quantidade_ton: float
    quantidade_sc: float
    custo_total_rs: float = Field(alias='custo_total_r$')


@api.get(
    '/cenarios/{scenario_id}/movimentacoes/',
    response=list[MovimentacaoSchema],
    by_alias=True,
)
def listar_movimentacoes(
    request,
    scenario_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    origin_id: int | None = None,
    destination_id: int | None = None,
    limit: int = 150,
):
    _get_cenario(scenario_id)
    return services.get_daily_movements(
        scenario_id=scenario_id,
        start_date=start_date,
        end_date=end_date,
        origin_id=origin_id,
        destination_id=destination_id,
        limit=limit,
    )


class MesResumoSchema(Schema):
    mes: str
    quantidade_ton: float
    quantidade_sc: float
    custo_total: float


class RotaResumoSchema(Schema):
    mes: str
    origem: str
    destino: str
    quantidade_ton: float
    quantidade_sc: float
    custo_total: float


class ResumoMensalSchema(Schema):
    resumo_mensal: list[MesResumoSchema]
    detalhe_rotas: list[RotaResumoSchema]


@api.get('/cenarios/{scenario_id}/resumo-mensal/', response=ResumoMensalSchema)
def resumo_mensal(request, scenario_id: int, start_date: str | None = None, end_date: str | None = None):
    _get_cenario(scenario_id)
    resultado = services.get_monthly_summary(
        scenario_id=scenario_id, start_date=start_date, end_date=end_date,
    )
    # Achado da spec: `get_monthly_summary` devolve {"meses": [], "rotas": []}
    # quando não há movimentações. Normaliza para o contrato tipado.
    if 'resumo_mensal' not in resultado:
        return {'resumo_mensal': [], 'detalhe_rotas': []}
    return {
        'resumo_mensal': _nativos(resultado['resumo_mensal']),
        'detalhe_rotas': _nativos(resultado['detalhe_rotas']),
    }


class FabricaResumoSchema(Schema):
    mes: str
    fabrica_id: int
    fabrica: str
    recebimento_produtor_ton: float
    recebimento_transbordo_ton: float
    esmagado_ton: float
    saldo_estoque_ton: float
    capacidade_estatica_ton: float
    excedente_estoque_ton: float


class ArmazemResumoSchema(Schema):
    mes: str
    armazem_id: int
    armazem: str
    recebimento_produtor_ton: float
    envio_transbordo_ton: float
    vendas_ton: float
    saldo_estoque_ton: float
    capacidade_estatica_ton: float
    excedente_estoque_ton: float


@api.get('/cenarios/{scenario_id}/fabricas/resumo/', response=list[FabricaResumoSchema])
def fabricas_resumo(request, scenario_id: int):
    _get_cenario(scenario_id)
    return services.get_factories_summary(scenario_id=scenario_id)


@api.get('/cenarios/{scenario_id}/armazens/resumo/', response=list[ArmazemResumoSchema])
def armazens_resumo(request, scenario_id: int):
    _get_cenario(scenario_id)
    return services.get_warehouses_summary(scenario_id=scenario_id)


class FabricaComparacaoSchema(Schema):
    fabrica_id: int
    fabrica: str
    recebimento_produtor_total_ton: float
    recebimento_transbordo_total_ton: float
    esmagado_total_ton: float
    pico_estoque_mensal_ton: float
    excedente_total_acumulado_ton: float


class ArmazemComparacaoSchema(Schema):
    armazem_id: int
    armazem: str
    recebimento_produtor_total_ton: float
    envio_transbordo_total_ton: float
    vendas_total_ton: float
    pico_estoque_mensal_ton: float
    excedente_total_acumulado_ton: float


@api.get('/cenarios/{scenario_id}/fabricas/comparacao/', response=list[FabricaComparacaoSchema])
def fabricas_comparacao(request, scenario_id: int):
    _get_cenario(scenario_id)
    return _nativos(services.compare_factories(scenario_id=scenario_id))


@api.get('/cenarios/{scenario_id}/armazens/comparacao/', response=list[ArmazemComparacaoSchema])
def armazens_comparacao(request, scenario_id: int):
    _get_cenario(scenario_id)
    return _nativos(services.compare_warehouses(scenario_id=scenario_id))


class AlertaExcedenteSchema(Schema):
    mes: str
    entidade_tipo: str
    entidade_id: int
    entidade_nome: str
    estoque_final_ton: float
    capacidade_estatica_ton: float
    excedente_estouro_ton: float


class AlertaRupturaSchema(Schema):
    mes: str
    entidade_tipo: str
    entidade_id: int
    entidade_nome: str
    estoque_final_ton: float
    capacidade_estatica_ton: float
    deficit_ton: float


@api.get('/cenarios/{scenario_id}/alertas/excedentes/', response=list[AlertaExcedenteSchema])
def alertas_excedentes(request, scenario_id: int):
    _get_cenario(scenario_id)
    return services.get_stock_excesses_report(scenario_id=scenario_id)


@api.get('/cenarios/{scenario_id}/alertas/rupturas/', response=list[AlertaRupturaSchema])
def alertas_rupturas(request, scenario_id: int):
    _get_cenario(scenario_id)
    return services.get_stock_ruptures_report(scenario_id=scenario_id)
