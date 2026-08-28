# ADR 0008 — Face JSON com Django Ninja sobre services.py

- Status: Aceito
- Data: 2026-08-28

## Contexto

A Fase 6 do roteiro (`docs/superpowers/specs/2026-08-26-fase6-face-json-design.md`) expõe as 9 funções
de leitura de `apps/simulacao/services.py` por HTTP, para consumo futuro do MCP server e do Assistente
de IA — hoje ambos consultam o ORM em processo, sobre o stack legado.

## Decisão

- **Django Ninja**, não DRF: gera OpenAPI/Swagger automático a partir de schemas tipados (`ninja.Schema`),
  o que torna a API autodescritiva para um consumidor externo sem ler o código Python. As 9 respostas já
  têm formato conhecido (o mesmo que `mcp_server.py` expõe) — só é preciso declará-las.
- **`ApiKey` como model** (`cooperativa` FK, `chave`, `ativo`, `created_at`), não variável de ambiente:
  revogável sem redeploy e escala para múltiplas cooperativas sem crescer o `.env`.
- **Autenticação reaproveita a tenancy existente.** `ApiKeyAuth` resolve `X-API-Key` para uma `ApiKey`
  ativa e chama `apps.core.tenancy.definir_cooperativa_atual(api_key.cooperativa_id)` — a mesma função
  que `CooperativaScopeMiddleware` usa. O teardown do contextvar é feito pelo `finally` desse middleware
  (último da lista `MIDDLEWARE`, portanto o mais interno): ele define o contextvar como `None` para o
  request sem sessão e o reseta ao valor pré-request depois da resposta, descartando o valor que a auth
  colocou. Consequência: os endpoints autorizam `scenario_id` com o mesmo `get_object_or_404(Cenario,
  id=...)` tenant-scoped das views HTMX — nenhum mecanismo de autorização novo.
- **`services.py` não é modificado** (módulo compartilhado). O achado do `get_monthly_summary` (retorna
  `{"meses": [], "rotas": []}` quando vazio, `{"resumo_mensal": [...], "detalhe_rotas": [...]}` quando
  há dados — bug legado preservado no port 1:1) é normalizado no endpoint Ninja para
  `{resumo_mensal: [], detalhe_rotas: []}` antes do schema.
- **Somente leitura, prefixo `/api/v1/`.** `clone_scenario` (escrita) fora de escopo — nenhum consumidor
  atual precisa.

## Consequências

- Nova dependência de produção: `django-ninja>=1.4,<2.0` em `requirements.txt`. Resolveu para
  `django-ninja==1.6.3`, que declara suporte a Django 6 — nenhum ajuste de bound foi necessário.
- OpenAPI em `/api/v1/docs`.
- Riscos aceitos nesta fase (ver spec): chave em texto plano no banco (sem hash), sem rate limiting.
  Reavaliar antes de expor a API fora do controle direto do time / na Fase 7 (Auth).
- Migrar `mcp_server.py`/`ai_assistant.py` para consumir esta API é uma etapa seguinte, deliberadamente
  separada.
