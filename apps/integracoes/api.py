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
