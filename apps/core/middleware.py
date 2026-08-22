"""Middleware que expõe a cooperativa do usuário autenticado ao TenantManager
durante o ciclo de vida do request (ver apps.core.tenancy)."""
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual


class CooperativaScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        cooperativa_id = None
        if user is not None and user.is_authenticated:
            cooperativa_id = user.cooperativa_id
        token = definir_cooperativa_atual(cooperativa_id)
        try:
            return self.get_response(request)
        finally:
            resetar_cooperativa_atual(token)
