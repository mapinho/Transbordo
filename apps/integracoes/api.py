"""Face JSON da Fase 6 — Django Ninja sobre apps/simulacao/services.py.

Endpoints somente-leitura espelhando 1:1 os 9 tools de `mcp_server.py`.
Autenticação e escopo de tenant: ver `apps/integracoes/auth.py` e
`docs/decisions/0008-face-json-django-ninja.md`.
"""
from ninja import NinjaAPI, Schema

from apps.integracoes.auth import ApiKeyAuth
from apps.simulacao import services

api = NinjaAPI(
    title='Comigo — Face JSON',
    version='1.0.0',
    docs_url='/docs',
    auth=ApiKeyAuth(),
)


class CenarioSchema(Schema):
    id: int
    nome: str
    is_oficial: bool
    data_criacao: str | None = None


@api.get('/cenarios/', response=list[CenarioSchema])
def listar_cenarios(request):
    return services.list_scenarios(request.auth.cooperativa_id)
