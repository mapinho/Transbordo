"""Autenticação da face JSON: header `X-API-Key` → `ApiKey` ativa →
cooperativa corrente do request.

O contextvar de tenant é *definido* aqui e *resetado* pelo
`CooperativaScopeMiddleware` (último de `MIDDLEWARE`, portanto o mais
interno): o `finally` dele reseta ao valor pré-request. Ver ADR 0008.
"""
from ninja.security import APIKeyHeader

from apps.core.tenancy import definir_cooperativa_atual
from apps.integracoes.models import ApiKey


class ApiKeyAuth(APIKeyHeader):
    param_name = 'X-API-Key'

    def authenticate(self, request, key):
        if not key:
            return None
        try:
            api_key = ApiKey.objects.select_related('cooperativa').get(chave=key, ativo=True)
        except ApiKey.DoesNotExist:
            return None
        definir_cooperativa_atual(api_key.cooperativa_id)
        return api_key
