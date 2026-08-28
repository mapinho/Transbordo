# CLAUDE.md

Project memory for Claude Code. Keep this file accurate as the codebase changes — it is the fastest path to context for any future session.

## Project Overview

**Comigo** is a logistics planning & optimization system for soy "transbordo" (transshipment) at a single agricultural cooperative. It plans daily movement of soy between Armazéns (warehouses, origins) and Fábricas (crushing plants, destinations) to minimize freight cost while guaranteeing plants never run out of raw material. It also supports "what-if" scenario simulation (deep-cloned from the official baseline) and exposes the same data through an MCP server and an in-app Gemini-powered chat assistant.

The long-term direction (see `Relatorio_Revisao_Codigo_Fase1.md` and the "Roteiro Comigo" roadmap) is evolving this from a single-cooperative Streamlit app into a multi-cooperative SaaS product (Django 6 + HTMX), so avoid decisions that make that migration harder without a documented reason.

## Tech Stack

- Python 3.10+ (developed against 3.13)
- Streamlit — UI, re-runs the whole script on every interaction
- SQLAlchemy 2.0 — ORM, legacy `Column()` declarative style, retrofit-typed with `Mapped[...]` annotations (no `mapped_column()` migration done yet)
- PostgreSQL — production database; SQLite in-memory — test database (`tests/conftest.py`)
- Google OR-Tools — MILP solver (SCIP/GLOP) for the daily transbordo optimization
- Pandas / Plotly — data processing & charts
- FastMCP — MCP server exposing read-only logistics reports to LLM clients
- google-genai (Gemini) — native in-app AI assistant via function calling, over the same report layer as the MCP server

## Commands

```bash
# Install
pip install -r requirements.txt
pip install -r requirements-dev.txt   # adds pytest, for local dev only

# Run the app
streamlit run app.py

# Run the MCP server standalone (stdio transport)
python mcp_server.py

# Tests (SQLite in-memory, no external DB needed)
pytest tests/ -v

# Compile check (fast sanity check across all production modules)
python -m py_compile app.py app_logic.py data_loader.py logistics_services.py \
  ai_assistant.py mcp_server.py models.py calculations.py scenarios.py utils.py
```

## Fase 5 — Fundação Django (em progresso)

Migração para Django 6 + HTMX em andamento (ver
`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` e
`docs/superpowers/plans/2026-08-22-fase5-fundacao-django.md`). Durante a coexistência com o app
Streamlit/SQLAlchemy existente, os dois stacks vivem no mesmo repositório:

- `python manage.py check` — sanity check do projeto Django.
- `pytest` — roda tanto os testes SQLAlchemy (`tests/`) quanto os testes Django (`apps/*/tests/`). Os
  testes Django (`apps/*/tests/`) precisam de um PostgreSQL local alcançável via `DJANGO_DB_*` (crie o
  banco/role antes de rodar `pytest` pela primeira vez — ver `docs/decisions/0002-...`); os testes
  SQLAlchemy (`tests/`) continuam usando SQLite em memória, sem essa dependência.
- O `.env` do stack Django usa variáveis `DJANGO_DB_*` (deliberadamente distintas de `DB_*`, que
  continuam servindo o stack Streamlit/SQLAlchemy) — ver `.env.example`.
- ADRs desta fase em `docs/decisions/`, começando em `0001`.
- `python manage.py procrastinate worker` — worker assíncrono (Procrastinate); precisa estar rodando,
  junto com `runserver`, para a aba "Simulação" executar de fato (ver ADR 0007).

## Environment

A `.env` file at the project root is **required** — there is no hardcoded credential fallback (removed in the Fase 1 review; see `data_loader.py:get_engine()`):

```env
DB_USER=...
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=5432
DB_NAME=comigo
GEMINI_API_KEY=...   # optional — only needed for the "Assistente de IA" tab
```

On Streamlit Cloud, credentials are read from `st.secrets` instead of `.env`.

## Architecture / File Map

- `app.py` — Streamlit entrypoint and all UI pages (Dashboard, Carga de Dados, Cenários, Assistente de IA). Wraps the DB session in `app_logic.db_session_scope()` so it's always closed, even on error.
- `app_logic.py` — Streamlit-free pure logic extracted from `app.py` (`sync_*_from_row`, `build_editable_*_df`, `get_movement_totals`, `db_session_scope`), so it's unit-testable without importing `streamlit`.
- `models.py` — SQLAlchemy ORM, 9 tables: `Cenario`, `Fabrica`, `Armazem`, `Rota`, `PrevisaoFabrica`, `PrevisaoArmazem`, `SafraUnidade`, `MovimentacaoDiaria`, `LogExecucao`, `ResumoMensalFabrica`, `ResumoMensalArmazem`. Columns carry an `info` dict (`label`, `type`, `format`, `hidden`) that drives UI generation.
- `calculations.py` — OR-Tools daily optimization engine (`otimizar_dia`); shared safra-window lookup `obter_janela_safra`.
- `scenarios.py` — scenario deep-clone (`clone_scenario`); fully transactional, rolls back on any failure.
- `data_loader.py` — `get_engine()` / `init_db()` (connection + credential resolution) and the four Excel importers (fábricas, armazéns, rotas, previsões). Loaders are row-tolerant: bad rows are collected and reported, not fatal.
- `logistics_services.py` — read-only report layer shared by `mcp_server.py` and `ai_assistant.py` (DRY). Bulk-query only, no N+1 lookups.
- `mcp_server.py` — FastMCP server; thin `@mcp.tool()` wrappers over `logistics_services.py`.
- `ai_assistant.py` — Gemini function-calling wrapper over the same `logistics_services.py` functions, used by the in-app chat tab.
- `utils.py` — `format_dataframe` (pt-BR display formatting), `get_model_column_config`, `build_df_from_model`, `append_totals_row`, `export_to_excel`.
- `templates/` — pre-generated Excel templates for data upload.
- `tests/` — pytest suite; `conftest.py` provides an in-memory SQLite `session` fixture plus minimal valid `cenario`/`fabrica`/`armazem`/`rota` fixtures.
- `config/`, `apps/core|simulacao|integracoes/`, `manage.py` — novo projeto Django (Fase 5, em progresso); ver a seção Fase 5 acima.
- `apps/simulacao/` — Django port do domínio (models, engine, services), Carga de Dados e espelhamento de dados legado. Ver `apps/simulacao/CLAUDE.md` para o detalhe por arquivo.

## Key Business Rules

- Cenário oficial = a `Cenario` row with `is_oficial=True` (a real row, like any other). Every descendant table's `cenario_id` is a real, non-null FK to a `Cenario.id`, including the official one. The single exception is `LogExecucao.cenario_id`, which is nullable specifically to mean "this execution ran against the official scenario" (see the field's own comment in `models.py`) — that convention does NOT apply to any other table.
- Daily mass balance: `Estoque Final = Estoque Inicial + Recebimento − Vendas ± Transbordo` (fábricas also subtract `Esmagamento`).
- Monthly forecast volumes are rateably split across the days of the month.
- Optimization objective priority (see `calculations.py`): 1) avoid a fábrica running out of raw material (huge `Slack` coefficient) > 2) minimize total frete cost > 3) prefer draining armazéns currently "em safra".
- 1 saca = 60 kg — always use `KG_PER_TON` / `KG_PER_SACA` from `logistics_services.py`, never a magic `1000/60`.
- pt-BR number formatting is mandatory everywhere data is displayed: `.` for thousands, `,` for decimals, via `utils.format_dataframe` — never display a raw float/currency without it.

## Testing / TDD

This codebase follows strict TDD (red → green) for all behavior changes: write a failing test in `tests/` first, confirm it fails for the right reason, implement the minimal fix, confirm it passes. See `Relatorio_Revisao_Codigo_Fase1.md` for the full audit trail of the Fase 1 code review (38 findings; all fixed or consciously deferred with documented rationale) — it's a good reference for the level of rigor expected on this project.

## Related Docs

- `Especificacao_Sistema_Transbordo_Atualizada.md` — full functional/business spec (data model, optimization math, UI requirements).
- `INSTRUCOES_MCP.md` — how to wire the MCP server into Claude Desktop, Gemini CLI, Cursor/Cline, and Vertex AI.
- `Relatorio_Revisao_Codigo_Fase1.md` — Fase 1 code review findings and fix log.
- `GEMINI.md` — equivalent project-memory file for Gemini CLI; content overlaps this file and should be kept roughly in sync when architecture changes.
- `conductor/` — historical implementation plans (MCP server, AI assistant). Already implemented; kept for design-rationale context.

## Roadmap Status

Fase 1 (revisão de código) is complete. The full 5-phase roadmap (documentação, performance/simplificação, otimização, migração para SaaS multi-cooperativa com Django 6 + HTMX) is tracked in the "Roteiro Comigo" artifact and in conversation history — check with the project owner for the current phase before starting new work.

One outstanding **manual, production-only** task from Fase 1: before relying on the new `NOT NULL` constraint on `cenario_id` (7 tables), confirm there are zero `cenario_id IS NULL` rows in the real production database, then run the corresponding `ALTER TABLE ... ALTER COLUMN cenario_id SET NOT NULL` migrations (see finding A11). **Update 2026-08-24:** the zero-NULL check was verified during the Fase 5 espelhamento work across **all 7 tables** — `fabricas` (0/14), `armazens` (0/119), `rotas` (0/238), `safras_unidades` (0/133), `movimentacoes_diarias` (0/13299), `resumo_mensal_fabrica` (0/188), `resumo_mensal_armazem` (0/1598) — zero nulls in every one (see `docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md`). Two caveats before acting on this: the `ALTER TABLE ... SET NOT NULL` itself has **not** been run — applying it to production is the project owner's call — and the check ran against the local `comigo` database, which is not necessarily the production instance this task refers to. Re-run the same check against production before migrating.
