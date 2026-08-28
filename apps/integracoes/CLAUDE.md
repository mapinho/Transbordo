# apps/integracoes — file map

Face JSON da Fase 6: Django Ninja somente-leitura sobre `apps/simulacao/services.py`. Ver a spec
`docs/superpowers/specs/2026-08-26-fase6-face-json-design.md` e a
`docs/decisions/0008-face-json-django-ninja.md`.

- `apps/integracoes/models.py` — `ApiKey` (`cooperativa` FK `on_delete=PROTECT`, `nome`, `chave` opaca
  auto-gerada e `unique`, `ativo`, `created_at`). Credencial processo-a-processo, uma ou mais por
  cooperativa. **Não** é `CooperativaScopedModel` — é o que *define* a cooperativa corrente, e a busca
  da chave acontece antes de qualquer escopo de tenant existir. `gerar_chave()` é função de módulo
  (referenciada por nome nas migrations, não pode ser lambda).
- `apps/integracoes/auth.py` — `ApiKeyAuth(APIKeyHeader)`, `param_name = 'X-API-Key'`. Resolve a chave
  para uma `ApiKey` ativa (`select_related('cooperativa')`) e chama
  `apps.core.tenancy.definir_cooperativa_atual(...)`. O reset do contextvar é feito pelo `finally` do
  `CooperativaScopeMiddleware` (o último de `MIDDLEWARE`, portanto o mais interno). Chave ausente,
  desconhecida ou inativa → retorna `None` → Ninja responde 401.
- `apps/integracoes/api.py` — uma instância `NinjaAPI` (`auth=ApiKeyAuth()`, `docs_url='/docs'`), 9
  endpoints GET espelhando 1:1 os 9 `@mcp.tool()` de `mcp_server.py`, um `ninja.Schema` por formato de
  resposta. `@api.exception_handler(ValueError)` → 400 (datas malformadas de `services._parse_date`).
  Helpers: `_get_cenario(scenario_id)` — autorização tenant-scoped via `get_object_or_404` (cenário de
  outra cooperativa → 404); `_nativos(registros)` — escalares numpy → nativos, para os 3 endpoints que
  passam por pandas (resumo-mensal, fabricas/comparacao, armazens/comparacao). O endpoint
  `movimentacoes/` usa `Field(alias='custo_total_r$')` + `by_alias=True`. `resumo-mensal/` normaliza o
  formato vazio legado de `get_monthly_summary` (`{"meses": [], "rotas": []}`) para
  `{resumo_mensal: [], detalhe_rotas: []}`.
- `apps/integracoes/admin.py` — admin mínimo de `ApiKey` (criar/revogar chave sem shell); `chave` e
  `created_at` são `readonly_fields`.
- `apps/integracoes/migrations/0001_initial.py` — cria a tabela `ApiKey`.

Montado em `config/urls.py` sob `api/v1/`. OpenAPI/Swagger em `/api/v1/docs`, schema em
`/api/v1/openapi.json`.

**Fora de escopo desta fase:** migrar `mcp_server.py`/`ai_assistant.py` para consumir esta API (etapa
seguinte, deliberadamente separada — ainda consultam o ORM legado em processo); escrita
(`clone_scenario`); auth de usuário final (Fase 7). Riscos aceitos: chave em texto plano no banco, sem
rate limiting — ver "Decisões em aberto" da spec.

Os 9 endpoints: `GET /api/v1/cenarios/` e, sob `/api/v1/cenarios/{scenario_id}/`: `movimentacoes/`,
`resumo-mensal/`, `fabricas/resumo/`, `armazens/resumo/`, `fabricas/comparacao/`,
`armazens/comparacao/`, `alertas/excedentes/`, `alertas/rupturas/`.
