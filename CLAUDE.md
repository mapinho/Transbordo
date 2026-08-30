# CLAUDE.md

Project memory for Claude Code. Keep this file accurate as the codebase changes — it is the fastest path to context for any future session.

## Project Overview

**Transbordo** is a multi-cooperative SaaS for planning & optimizing soy "transbordo" (transshipment):
daily movement of soy between Armazéns (warehouses, origins) and Fábricas (crushing plants,
destinations) to minimize freight cost while guaranteeing plants never run out of raw material. It
supports "what-if" scenario simulation (deep-cloned from the official baseline) and exposes the same
data through an MCP server and an in-app Gemini-powered chat assistant.

It began as a single-cooperative Streamlit app (**Comigo**, still in production at
`comigo.vectorconsulting.com.br` from the separate `Comigo.git` repo, development frozen) and was
rebuilt on Django 6 + HTMX across Fases 5–11. See ADR 0011.

## Tech Stack

- Python 3.10+ (developed against 3.13)
- Django 6 + HTMX + django-cotton — server-rendered UI
- PostgreSQL — production and test database (tests use a real local PostgreSQL via `DJANGO_DB_*`)
- Google OR-Tools — MILP solver (SCIP/GLOP) for the daily transbordo optimization
- pandas — usado pelo engine de otimização e pela camada de services
- FastMCP — MCP server exposing read-only logistics reports to LLM clients
- Django Ninja — Face JSON (Fase 6): read-only REST API over `apps/simulacao/services.py`, mounted at `/api/v1/`
- google-genai (Gemini) — native in-app AI assistant via function calling, over the same report layer as the MCP server

## Commands

```bash
# Install
pip install -r requirements.txt
pip install -r requirements-dev.txt   # adds pytest, for local dev only

# Run the app (dev)
python manage.py runserver
python manage.py procrastinate worker   # em outro terminal — a aba Simulação depende dele (ADR 0007)

# Run the MCP server standalone (stdio) — cliente HTTP de /api/v1/ (Fase 9)
TRANSBORDO_API_URL=http://localhost:8000/api/v1 TRANSBORDO_API_KEY=<ApiKey> python mcp_server.py

# Tests (precisa de um PostgreSQL local alcançável via DJANGO_DB_*)
pytest

# Django sanity checks
python manage.py check
python manage.py makemigrations --check --dry-run
```

## Fase 5 — Fundação Django (concluída)

Migração para Django 6 + HTMX (ver `docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md`).

- `python manage.py check` — sanity check do projeto.
- `pytest` — roda os testes de `apps/*/tests/`; precisa de um PostgreSQL local alcançável via
  `DJANGO_DB_*` (crie o banco/role antes de rodar pela primeira vez — ver `docs/decisions/0002-...`).
- O `.env` usa `DJANGO_DB_*` / `DJANGO_*` — ver `.env.example`.
- ADRs em `docs/decisions/`, de `0001` a `0011`.
- `python manage.py procrastinate worker` — worker assíncrono; precisa estar rodando junto com o
  `runserver` para a aba "Simulação" executar (ADR 0007).

## Fase 6 — Face JSON (concluída)

`apps/integracoes/` expõe `apps/simulacao/services.py` como 9 endpoints GET Django Ninja sob `/api/v1/`,
espelhando 1:1 os 9 tools de `mcp_server.py`. Autenticação por header `X-API-Key` → `ApiKey` model (uma
ou mais por cooperativa, revogável via admin), que também define a cooperativa corrente do request
(mesmo mecanismo de tenancy das views HTMX — contextvar de `apps.core.tenancy`). OpenAPI/Swagger em
`/api/v1/docs`. Ver `docs/superpowers/specs/2026-08-26-fase6-face-json-design.md` e
`docs/decisions/0008-face-json-django-ninja.md`, mais `apps/integracoes/CLAUDE.md` para o file map.

## Fase 7 — Auth (concluída)

`django-allauth` sob `/accounts/` (Google + Microsoft/Azure AD multi-tenant + usuário/senha local),
configurado via `SOCIALACCOUNT_PROVIDERS[...]['APPS']` em settings. **Sem auto-cadastro**:
`apps/core/adapters.py` bloqueia signup e só autentica conta social casada por e-mail a um `User`
pré-criado. `core.User.email` é obrigatório e único.

Autorização por papel em `apps/core/permissions.py` (funções puras + decorators
`@papel_required` / `@requer_edicao_fabricas` / `@requer_edicao_armazens` / `@requer_admin_vector`),
aplicada em todas as views de `apps/simulacao/`. `apps/gestao/` (sem models) tem as telas de
Cooperativas (Admin Vector), Usuários (Admin Vector cross-tenant; Admin Cooperativa na própria coop),
"Minha cooperativa" e "Conta". Ver `docs/superpowers/specs/2026-08-29-fase7-auth-design.md`,
`docs/decisions/0009-autenticacao-allauth-papeis.md` e `apps/gestao/CLAUDE.md`.

Bootstrap do primeiro Admin Vector: `python manage.py criar_admin_vector <username> --email <email>`.

## Fase 9 — Migração MCP / IA (concluída)

Na Fase 9, os dois consumidores da antiga camada de relatórios deixaram de tocar o ORM legado (ADR 0010):

- **`mcp_server.py`** virou **cliente HTTP puro** de `/api/v1/`. Sem acesso a banco: config por
  `TRANSBORDO_API_URL` + `TRANSBORDO_API_KEY` (fail-loud no import). As 9 tools são
  wrappers finos de `_get(path, **params)`. Setup na seção `## MCP` do `README.md`.
- **`ai_assistant.py`** foi portado para o app Django como a aba **"Assistente de IA"** por cenário:
  `apps/simulacao/assistente.py` roda o loop Gemini em processo (`responder(conversa, mensagem)`),
  chamando `apps/simulacao/services.py` com a cooperativa do usuário logado. Histórico persistido no
  model `ConversaIA` (`CooperativaScopedModel`, uma conversa ativa por cenário+usuário). Sem
  `GEMINI_API_KEY` (`settings.GEMINI_API_KEY`), a aba mostra aviso e desabilita o input.

Na Fase 11 o stack Streamlit deixou de viver neste repositório; o loop Gemini existe só em
`apps/simulacao/assistente.py`. Ver
`docs/superpowers/specs/2026-08-28-fase9-migracao-mcp-ia-design.md` e ADR 0010.

## Fase 10 — Deploy (concluída)

Transbordo em produção em `transbordo.vectorconsulting.com.br`. Imagem `python:3.13-slim` + gunicorn +
WhiteNoise (`Dockerfile`); serviços do `docker-compose.yml`: `web` (gunicorn, publicado em
`127.0.0.1:8060`), `worker` (Procrastinate) e `migrate` (one-shot). Apache é o único ingress externo
(`transbordo.conf` / `transbordo-le-ssl.conf`). PostgreSQL é externo/bare-metal no host. `/healthz/`
faz `SELECT 1` e é o healthcheck do container. `deploy.sh` é o runbook recorrente (git pull condicional
→ build → migrate → check --deploy → up → poll `/healthz/`); `docs/DEPLOY.md` cobre primeira vez,
rollback e a migração de dados dev→prod. Ver `docs/superpowers/specs/2026-08-29-fase10-deploy-design.md`.

O `docker-compose.yml` serve **só** este produto. O produto separado Comigo
(`comigo.vectorconsulting.com.br`, repo **Comigo.git**) roda com infra própria e independente,
desenvolvimento congelado — ver ADR 0011.

## Environment

A `.env` file at the project root is **required** (ver `.env.example`):

```env
DJANGO_SECRET_KEY=...
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_DB_NAME=transbordo
DJANGO_DB_USER=transbordo
DJANGO_DB_PASSWORD=...
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5432
GEMINI_API_KEY=...   # opcional — só para a aba "Assistente de IA"
```

Fase 7 (Auth) adiciona, todas opcionais salvo se o provedor/recurso for usado:
`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`,
`MICROSOFT_TENANT` (default `common`), `DJANGO_EMAIL_*` (SMTP transacional), `DJANGO_DEFAULT_FROM_EMAIL`,
e `ADMIN_VECTOR_PASSWORD` (só para `criar_admin_vector --password-from-env`).

## Architecture / File Map

- `manage.py` — Django entrypoint.
- `mcp_server.py` — servidor MCP (stdio); desde a Fase 9 é cliente HTTP de `/api/v1/` (ADR 0010), sem acesso a banco. Config `TRANSBORDO_API_URL`/`TRANSBORDO_API_KEY`.
- `config/` — projeto Django (settings por ambiente, `urls.py`, `wsgi.py`).
- `apps/core/` — identidade e tenancy: `models.py` (`Cooperativa`, `User` com `papel`), `tenancy.py`/`middleware.py`, `adapters.py` (allauth, sem signup), `permissions.py`, comandos `criar_admin_vector` e `sanitizar_pos_restore`.
- `apps/gestao/` — telas HTMX de gestão (Cooperativas, Usuários, Minha cooperativa, Conta). **Sem models**. Ver `apps/gestao/CLAUDE.md`.
- `apps/simulacao/` — Django port do domínio (models, engine, services), Carga de Dados (`planilha.py`), Assistente de IA (`assistente.py` + `ConversaIA`). Ver `apps/simulacao/CLAUDE.md`.
- `apps/integracoes/` — Face JSON (Fase 6): Django Ninja somente-leitura sobre `apps/simulacao/services.py`, `/api/v1/`, auth `X-API-Key` (`ApiKey`). Ver `apps/integracoes/CLAUDE.md`.
- `templates/` — templates Django (`base.html`, `cotton/`, telas de `account`/`socialaccount`/`gestao`/`simulacao`).

## Key Business Rules

- Cenário oficial = a `Cenario` row with `is_oficial=True` (a real row, like any other). Every descendant table's `cenario_id` is a real, non-null FK to a `Cenario.id`, including the official one. The single exception is `LogExecucao.cenario_id`, which is nullable specifically to mean "this execution ran against the official scenario" (see the field's own comment in `apps/simulacao/models.py`) — that convention does NOT apply to any other table.
- Daily mass balance: `Estoque Final = Estoque Inicial + Recebimento − Vendas ± Transbordo` (fábricas also subtract `Esmagamento`).
- Monthly forecast volumes are rateably split across the days of the month.
- Optimization objective priority (see `apps/simulacao/engine.py`): 1) avoid a fábrica running out of raw material (huge `Slack` coefficient) > 2) minimize total frete cost > 3) prefer draining armazéns currently "em safra".
- 1 saca = 60 kg — always use `KG_PER_TON` / `KG_PER_SACA` from `apps/simulacao/services.py`, never a magic `1000/60`.
- pt-BR number formatting is mandatory everywhere data is displayed: `.` for thousands, `,` for decimals, via `apps/simulacao/templatetags/simulacao_filters.py` — never display a raw float/currency without it.

## Testing / TDD

This codebase follows strict TDD (red → green) for all behavior changes: write a failing test in `apps/*/tests/` first, confirm it fails for the right reason, implement the minimal fix, confirm it passes. The Fase 1 code review (38 findings; all fixed or consciously deferred with documented rationale) set the rigor bar for this project.

## Related Docs

- `Especificacao_Sistema_Transbordo_Atualizada.md` — full functional/business spec (data model, optimization math, UI requirements).
- `docs/superpowers/specs/` — design specs por fase da migração Django; `docs/decisions/` — ADRs.
- `CHANGELOG.md` — histórico de versões (SemVer); `VERSION` — versão corrente.

## Roadmap Status

Fases 1–11 concluídas. `VERSION` / `CHANGELOG.md` na `1.0.0`. O produto Streamlit original (Comigo)
segue em produção à parte, congelado (ADR 0011). Próximas evoluções são do Transbordo — confirme o
escopo com o dono do projeto antes de começar trabalho novo.
