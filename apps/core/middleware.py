"""Middleware que expõe a organização corrente do request ao TenantManager
durante o ciclo de vida do request (ver apps.core.tenancy).

Para membros de organização é a própria cooperativa; para Admin Vector é a
seleção guardada na sessão (obter_organizacao_corrente)."""
from apps.core.tenancy import (
    definir_cooperativa_atual,
    obter_organizacao_corrente,
    resetar_cooperativa_atual,
)


class CooperativaScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cooperativa_id = obter_organizacao_corrente(request)
        token = definir_cooperativa_atual(cooperativa_id)
        try:
            return self.get_response(request)
        finally:
            resetar_cooperativa_atual(token)
