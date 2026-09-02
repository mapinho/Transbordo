# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/). `v1.0.0` = o repo larga o stack Streamlit legado (ADR 0011).

## [1.3.0] - 2026-09-02

Fase 14 — Painel de Movimentação de Estoque: aba "Estoque" por cenário sobre as tabelas de balanço mensal (`ResumoMensal*`), com a visão agregada do sistema que faltava. Nenhuma mudança de regra de negócio ou de model, sem migrations. Ver a spec 2026-09-02.

### Added
- Aba "Estoque" por cenário (habilitada após a 1ª simulação): três visões via combo — Sistema (totais mensais + rodapé), Por armazém, Por fábrica; card de pico do cenário ("pior momento do sistema"); comparação com um 2º cenário (colunas Δ% nas 3 visões, card com Δ); filtros de mês (`type=month`) / armazém / fábrica; exportação Excel e CSV; gráfico de linha Saldo total / Excedente total por mês; sinalização visual de excedente (`> 0`) e ruptura (`saldo < 0`).
- `apps/simulacao/estoque.py` (motor de agregação ORM sobre `ResumoMensal*`), `apps/simulacao/forms.py::EstoqueForm`.

### Changed
- `templates/simulacao/_subnav.html` ganha a 9ª aba "Estoque".
- Templatetag `cenario_tem_resultado` renomeado para `cenario_tem_simulacao` (a checagem serve às abas Resultados e Estoque).

## [1.2.0] - 2026-09-01

Fase 13 — Painel de Resultados: nova aba "Resultados" por cenário (movimentações e sumarizações, comparação entre cenários, exportação e gráfico). Nenhuma mudança de regra de negócio ou de model — a fase não cria migrations. Ver ADR 0013.

### Added
- Aba "Resultados" por cenário (habilitada após a 1ª simulação): listagem de movimentações diárias e sumarizações (diárias e mensais) via dois combos Período (Diário / Mensal / Total) × Agrupar por (Fábrica+Armazém / Fábrica / Armazém / nada); card-resumo do cenário; comparação com um segundo cenário (colunas Δ%, `text-error` ↑ / `text-success` ↓); filtros de data / armazém / fábrica; exportação Excel (openpyxl) e CSV do recorte; gráfico de barras mensal / linha diária.
- `apps/simulacao/resultados.py` (motor de agregação ORM da UI), `apps/simulacao/forms.py` (`ResultadosForm`), templatetags `variacao` / `item` / `cenario_tem_resultado`.
- Chart.js 4.x via CDN como padrão de gráfico da suíte AgroVector (ADR 0013), carregado sob demanda.

### Changed
- `templates/simulacao/_subnav.html` ganha a 8ª aba "Resultados".

## [1.1.0] - 2026-08-31

Fase 12 — Evolução UX/UI: padrão visual da suíte AgroVector (portado do AppVector), home nova com dashboards e seletor de organização por sessão para o Admin Vector. Nenhuma mudança de regra de negócio ou de model. Ver ADR 0012 e `docs/design-system/README.md`.

### Added
- Fundação visual daisyUI 5 + Tailwind 4: temas `vector` / `vector-dark`, header navy de dois níveis (barra da suíte + faixa de módulos com subnav e breadcrumb), tri-estado de preferência de tema (`vector-theme-pref`: claro / escuro / sistema) sem flash ao navegar.
- Home `/` (`core:home`): dashboard consolidado para o Admin Vector (métricas por organização) e home da organização para os demais papéis.
- Seletor de organização por sessão para o Admin Vector: `obter_organizacao_corrente` / `cooperativa_id_do_request` em `apps.core.tenancy`, conceito de super-membro, "— Consolidado —" volta ao dashboard.
- `apps/core/services.py` — métricas dos dashboards (`metricas_da_organizacao`, `metricas_consolidadas`).
- django-tables2 + django-filter nas listagens de gestão; django-unfold no `/admin/`.
- Componentes cotton `<c-lista-cartao>`, `<c-resumo-numerico>`, `<c-breadcrumb>`, `<c-icon>`.
- ADR 0012 (padrão de UX/UI AgroVector) e `docs/design-system/README.md`.
- `pyproject.toml` (PEP 621) como fonte única de dependências.

### Changed
- `LOGIN_REDIRECT_URL`: `/simulacao/cenarios/` → `/`.
- ~25 telas re-estilizadas para o padrão AgroVector (auth, gestão, cenários/grids/simulação/assistente/carga de dados).
- `/admin/` agora usa django-unfold.
- Terminologia visível na UI: "Cooperativa" → "Organização" (o model `Cooperativa` permanece inalterado).

### Removed
- Tema "Grão & Aço" (`data-theme="grao-e-aco"`, variáveis `--cor-*`).
- `static/simulacao/js/modal.js` — código morto.
- `requirements.txt` / `requirements-dev.txt` — substituídos por `pyproject.toml`.

## [1.0.0] - 2026-08-30

### Removed
- Fase 11 — Cutover: stack Streamlit/SQLAlchemy legado deste repo — `app.py` + 9 módulos irmãos da raiz, suíte `tests/` (SQLAlchemy), ferramenta de espelhamento (`apps/simulacao/legado.py` + comando `espelhar_legado`). Deps `streamlit`, `SQLAlchemy`, `psycopg2-binary`, `plotly`. Confs Apache `comigo*.conf`. O Streamlit em produção é o `Comigo.git`, separado e congelado (ADR 0011).
- Serviço `comigo` (Streamlit) do `docker-compose.yml` e `CMD streamlit run` do `Dockerfile` — o
  Streamlit de produção roda num container próprio a partir do repo Comigo.git; este compose só serve o
  stack Django (`CMD` do `Dockerfile` agora é `gunicorn`).

### Added
- Comando `python manage.py sanitizar_pos_restore` (higieniza resíduo de dev após restaurar um dump de desenvolvimento em produção) + runbook "Migração de dados dev→prod" em `docs/DEPLOY.md`. Também trunca `socialaccount_socialapp` (SocialApps de dev) e pede confirmação interativa (`sim`) salvo com `--noinput`; ausência de tabela não é fatal.
- Dependência `psycopg[binary]` explícita (era transitiva do procrastinate).
- ADR 0011 — Comigo e Transbordo como dois produtos permanentes independentes.

### Changed
- `web` publica em `127.0.0.1:8060` no host (era `:8000`) — evita colidir com o container órfão
  `comigo_mcp`. Porta interna do container e o healthcheck seguem em `8000`; Apache faz proxy p/ `:8060`.
- Suíte de testes do `mcp_server.py` movida de `tests/` para `apps/integracoes/tests/test_mcp_server.py` (o `mcp_server.py`, cliente HTTP de `/api/v1/`, continua no repo).

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
