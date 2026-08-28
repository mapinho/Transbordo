"""Face JSON da Fase 6 — Django Ninja sobre apps/simulacao/services.py.

Endpoints somente-leitura espelhando 1:1 os 9 tools de `mcp_server.py`.
Autenticação e escopo de tenant: ver `apps/integracoes/auth.py` e
`docs/decisions/0008-face-json-django-ninja.md`.
"""
from ninja import NinjaAPI

api = NinjaAPI(title='Comigo — Face JSON', version='1.0.0', docs_url='/docs')
