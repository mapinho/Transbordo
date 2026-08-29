# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/). `v1.0.0` marca o cutover (Streamlit desligado).

## [0.10.0] - 2026-08-29

### Added
- Fase 10 — Deploy: stack Django em produção ao lado do Streamlit. Imagem `python:3.13-slim` com `gunicorn` + WhiteNoise (`collectstatic` no build); serviços compose `web` / `worker` (Procrastinate) / `migrate`; vhosts Apache para `transbordo.vectorconsulting.com.br`; `/healthz/` faz `SELECT 1` real (503 se o banco cair); `deploy.sh` como runbook + `docs/DEPLOY.md`.

### Removed
- Serviço `mcp` (SSE) do `docker-compose.yml` — sem uso desde a Fase 9a (ADR 0010).

## [0.9.0] - 2026-08-29

### Changed
- Fase 9 — Migração MCP/IA (ADR 0010). `mcp_server.py` virou cliente HTTP puro de `/api/v1/` (config `TRANSBORDO_API_URL`/`TRANSBORDO_API_KEY`, sem acesso a banco). `ai_assistant.py` foi portado para a aba "Assistente de IA" por cenário no app Django (`apps/simulacao/assistente.py` + model `ConversaIA`), chamando `services.py` em processo com a cooperativa do usuário logado.

### Added
- Dependência `httpx`. `GEMINI_API_KEY` em `settings`. Seção `## MCP` no `README.md`.

## [0.8.0] - 2026-08-29

### Added
- Esquema de versionamento SemVer: arquivo `VERSION`, `APP_VERSION` nas settings, `/healthz/` (stub) e rodapé expondo a versão. Este `CHANGELOG.md`.

### Removed
- Lixo acumulado da migração: `GEMINI.md` + `.gemini/`, skill `code-reviewer/`, `INSTRUCOES_MCP.md` + `toolspec.json`, `conductor/`, `docs/superpowers/plans/*` das fases já executadas, `Relatorio_Revisao_Codigo_Fase1.md`, análises one-off (`analise_mineiros.py`, `Relatorio_Analise_Impacto_Vendas_Mineiros.md`), notas de scratch `.txt`, `exportacao/*.xlsx`. O stack Streamlit/SQLAlchemy **não** foi tocado (sai na Fase 11).

## [0.7.0] - 2026-08-29

### Added
- Fase 7 — Auth: allauth (Google + Microsoft + local), papéis, sem auto-cadastro. `apps/gestao` (Cooperativas, Usuários, Minha cooperativa, Conta). Comando `criar_admin_vector`. ADR 0009.

## [0.6.0] - 2026-08-28
### Added
- Fase 6 — Face JSON: `apps/integracoes/`, 9 endpoints GET Django Ninja sob `/api/v1/`, auth `X-API-Key` (`ApiKey` model). OpenAPI em `/api/v1/docs`. ADR 0008.

## [0.5.0] - 2026-08-26
### Added
- Fase 5.5 — Simulação assíncrona: task Procrastinate `executar_simulacao`, polling HTMX de status via `LogExecucao`. ADR 0007.

## [0.4.0] - 2026-08-25
### Added
- Fase 5.4 — Carga de Dados: importador `.xlsx` de 5 abas (upload/preview/confirmação).

## [0.3.0] - 2026-08-24
### Added
- Fase 5.3 — UI HTMX/Tailwind/daisyUI para cenários/fábricas/armazéns/rotas/previsões/safras; espelhamento de dados legado (`espelhar_legado`).

## [0.2.0] - 2026-08-22
### Added
- Fase 5.2 — Port do domínio: `engine.py`, `services.py`, 11 models com `cooperativa_id`, testes de isolamento de tenant. ADRs 0005/0006.

## [0.1.0] - 2026-08-22
### Added
- Fase 5.1 — Fundação Django 6: apps `core`/`simulacao`/`integracoes`, settings por ambiente, CI GitHub Actions, models `Cooperativa`/`User`/`TenantManager`. ADRs 0001–0004.
