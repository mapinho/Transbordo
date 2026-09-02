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
rebuilt on Django 6 + HTMX across Fases 5–12. It is now sold as SaaS as the "Sistema de Planejamento
de Transbordo", the first product of the **AgroVector** suite (shared UX/UI standard). See ADR 0011 and
ADR 0012.

## Tech Stack

- Python 3.10+ (developed against 3.13)
- Django 6 + HTMX + django-cotton — server-rendered UI
- daisyUI 5 + Tailwind 4 (Play CDN) — temas `vector` / `vector-dark` da suíte AgroVector (ADR 0012, `docs/design-system/README.md`)
- django-tables2 + django-filter — listagens somente-leitura; crispy-tailwind — formulários; Tabulator — grids editáveis
- Chart.js 4.x (CDN) — gráficos, carregado sob demanda (ADR 0013)
- django-unfold — reskin do Django admin em `/admin/`
- PostgreSQL — production and test database (tests use a real local PostgreSQL via `DJANGO_DB_*`)
- Google OR-Tools — MILP solver (SCIP/GLOP) for the daily transbordo optimization
- pandas — usado pelo engine de otimização e pela camada de services
- FastMCP — MCP server exposing read-only logistics reports to LLM clients
- Django Ninja — Face JSON (Fase 6): read-only REST API over `apps/simulacao/services.py`, mounted at `/api/v1/`
- google-genai (Gemini) — native in-app AI assistant via function calling, over the same report layer as the MCP server

## Commands

```bash
# Install (editable, com o extra de dev: pytest, pytest-django)
pip install -e ".[dev]"

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
- ADRs em `docs/decisions/`, de `0001` a `0013`.
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

## Fase 12 — Evolução UX/UI (concluída)

Padrão de UX/UI da suíte **AgroVector** portado de `AppVector.git` e aplicado por inteiro ao Transbordo.
Ver `docs/superpowers/specs/2026-08-30-fase12-evolucao-ux-ui-design.md`, **ADR 0012** e o guia normativo
portável `docs/design-system/README.md`. Nenhum model muda — a fase **não cria migrations**.

- **Fundação visual** (`templates/base.html` reescrita): daisyUI 5 + Tailwind 4 via Play CDN; temas
  `vector` / `vector-dark` + estado "sistema"; o truque de cascata **sem `@layer`** (dois blocos de
  `<style>` — `@theme` registra os nomes, `:root` sem `@layer` pinta a tela; ADR 0020 de AppVector);
  script anti-flash lendo `localStorage['vector-theme-pref']`; `hx-headers` CSRF global;
  `#vector-modal` / `#vector-confirm` compartilhados. Tema verde "Grão & Aço" e
  `static/simulacao/js/modal.js` removidos.
- **Componentes cotton** novos em `templates/cotton/`: `<c-card>`, `<c-lista-cartao>`,
  `<c-resumo-numerico>`, `<c-breadcrumb>`, `<c-icon>`. Overrides `templates/django_tables2/tailwind.html`
  e `templates/tailwind/field.html`; `static/vector/css/tabulator-vector.css`; `static/vector/img/`.
- **Header de dois níveis** (sempre navy): logo Vector + nome do sistema + supra-marca "AgroVector" +
  organização corrente (esquerda); dropdown do usuário + ícone de aparência + sair (direita). Segunda
  linha = faixa de módulos (`{% if mostra_modulos %}`). Breadcrumb no `{% block breadcrumb %}`.
- **Home nova** em `/` (`apps.core.views.home`), agora o `LOGIN_REDIRECT_URL` (era
  `/simulacao/cenarios/`): dashboard consolidado (Admin Vector sem organização) e home da organização
  (membro, ou Admin Vector com organização selecionada). Números via `apps/core/services.py`
  (`metricas_da_organizacao` / `metricas_consolidadas`, managers `all_cooperativas`).
- **Seletor de organização por sessão** (Abordagem A, ADR 0012): `apps/core/tenancy.py`
  (`obter_organizacao_corrente` / `cooperativa_id_do_request`), `middleware.py`, `permissions.py`
  (`requer_membro_organizacao`, `pode_editar_*(request=...)`), view `core:selecionar_organizacao`. Admin
  Vector com organização selecionada age como super-membro dela. Face JSON inalterada.
- **`/admin/` com django-unfold**; **listagens de gestão** em django-tables2 + django-filter; UI usa
  "Organização" nos textos (o model segue `Cooperativa` até a próxima fase).
- **`pyproject.toml`** (PEP 621, `pip`) substitui `requirements.txt` / `requirements-dev.txt`.

## Fase 13 — Painel de Resultados (concluída)

Até agora os resultados de uma simulação só saíam via Face JSON / MCP / Assistente de IA — a UI mostrava
apenas o status da execução. A Fase 13 adiciona a **aba "Resultados"** por cenário (a nova aba, 8 no
total, entre "Simulação" e "Assistente"), habilitada só depois da 1ª simulação com sucesso. Ver
**ADR 0013** e `docs/superpowers/specs/2026-09-01-fase13-painel-resultados-design.md`. Nenhum model
muda — a fase **não cria migrations**. `VERSION` → `1.2.0`.

- **`apps/simulacao/resultados.py`** — motor de agregação por ORM da UI (`agregar` /
  `totais_do_recorte` / `cenarios_comparaveis` / `aplicar_comparacao` / `dados_grafico`). Usa `.objects`
  escopado pelo contextvar, **não** `all_cooperativas`; **duplica de propósito** parte de `services.py`
  (`get_monthly_summary` / `get_daily_movements`), que fica congelado alimentando MCP/API.
  `apps/simulacao/forms.py` — `ResultadosForm` (`Form` puro: datas + `armazem_ids` / `fabrica_ids`).
- **Dois combos**: Período (Diário / Mensal / Total) × Agrupar por (Fábrica+Armazém / Fábrica / Armazém /
  nada) = 9 formas de uma mesma tabela. Card-resumo do recorte no topo.
- **Comparação** com um 2º cenário: colunas Δ% (`text-error` ↑ quando maior, `text-success` ↓ quando
  menor; "novo" quando ausente no comparado); a linha crua (Diário × Fábrica+Armazém) não recebe Δ.
- **Filtros** de data / armazém / fábrica; **exportação** Excel (openpyxl) e CSV do recorte;
  **gráfico Chart.js** (barras na visão mensal, linha na diária-total) — ADR 0013 eleva o Chart.js a
  padrão de gráfico da suíte AgroVector, carregado sob demanda por CDN.
- Views `resultados_tab` / `resultados_export` + parciais HTMX com 3 alvos de swap
  (`resultados-area` / `resultados-tabela` / conteúdo completo); templatetags `variacao` / `item` /
  `cenario_tem_simulacao` (renomeado na Fase 14) em `apps/simulacao/templatetags/simulacao_filters.py`.

## Fase 14 — Painel de Movimentação de Estoque (concluída)

A aba "Resultados" (Fase 13) mostra as movimentações; faltava a visão consolidada do balanço mensal de
estoque do sistema. A Fase 14 adiciona a **aba "Estoque"** por cenário (a 9ª aba, entre "Resultados" e
"Assistente"), habilitada só depois da 1ª simulação com sucesso, sobre as tabelas de balanço mensal
(`ResumoMensalArmazem` / `ResumoMensalFabrica`). Ver
`docs/superpowers/specs/2026-09-02-fase14-painel-estoque-design.md`. Nenhum model muda — a fase **não
cria migrations** e **não tem ADR novo** (Chart.js já é ADR 0013). `VERSION` → `1.3.0`.

- **`apps/simulacao/estoque.py`** — motor de agregação por ORM da aba (`agregar` / `card_de_pico` /
  `card_com_delta` / `cenarios_comparaveis` / `aplicar_comparacao` / `dados_grafico` /
  `normalizar_visao`). Usa `.objects` escopado pelo contextvar, **não** `all_cooperativas`; **duplica
  de propósito** parte de `services.py` (`get_factories_summary` / `get_warehouses_summary` /
  `compare_*`), que fica congelado alimentando MCP/Face JSON/Assistente. `apps/simulacao/forms.py` —
  `EstoqueForm` (`Form` puro: mês `type=month` + multi de armazém / fábrica).
- **Combo Visão**: Sistema (totais mensais + rodapé `<tfoot>`) / Por armazém / Por fábrica — uma mesma
  tabela em três recortes. **Card de pico** no topo: "pior momento do sistema" (pico de excedente,
  saldo mínimo mensal e "ruptura em MM/AAAA" quando o saldo fica negativo).
- **Comparação** com um 2º cenário: colunas Δ% nas 3 visões + card com Δ.
- **Filtros** de mês / armazém / fábrica; **exportação** Excel (openpyxl) e CSV do recorte
  (`EXPORT_MAX=50_000`); **gráfico Chart.js** de linha (Saldo total / Excedente total por mês, série
  do comparado opcional), carregado sob demanda.
- **Sinalização**: célula Excedente `text-error` quando `> 0`; célula Saldo `text-error` + ⚠ e linha
  `bg-error/5` quando `< 0` (ruptura).
- Views `estoque_tab` / `estoque_export` + parciais HTMX com 3 alvos de swap (`estoque-area` /
  `estoque-tabela` / conteúdo completo) + helpers `_estoque_params` / `_estoque_template`; 9ª aba
  "Estoque" em `templates/simulacao/_subnav.html`. Templatetag `cenario_tem_resultado` renomeado para
  `cenario_tem_simulacao` (serve às abas Resultados e Estoque).

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
- `pyproject.toml` — PEP 621; runtime deps + `[project.optional-dependencies] dev`; versão lida de `VERSION`. Substitui os `requirements*.txt` (Fase 12).
- `mcp_server.py` — servidor MCP (stdio); desde a Fase 9 é cliente HTTP de `/api/v1/` (ADR 0010), sem acesso a banco. Config `TRANSBORDO_API_URL`/`TRANSBORDO_API_KEY`.
- `config/` — projeto Django (settings por ambiente, `urls.py`, `wsgi.py`).
- `apps/core/` — identidade, tenancy, home e dashboards. `models.py` (`Cooperativa`, `User` com `papel`), `tenancy.py`/`middleware.py` (organização corrente por sessão), `permissions.py`, `views.py` (`home`, `selecionar_organizacao`, `healthz`), `services.py` (métricas), `adapters.py` (allauth, sem signup), comandos `criar_admin_vector` e `sanitizar_pos_restore`. Ver `apps/core/CLAUDE.md`.
- `apps/gestao/` — telas HTMX de gestão (Organizações, Usuários, Minha organização, Conta). **Sem models**. `tables.py`/`filters.py` (django-tables2/filter), `context_processors.py` (menu do header). Ver `apps/gestao/CLAUDE.md`.
- `apps/simulacao/` — Django port do domínio (models, engine, services), Carga de Dados (`planilha.py`), Assistente de IA (`assistente.py` + `ConversaIA`). Ver `apps/simulacao/CLAUDE.md`.
- `apps/integracoes/` — Face JSON (Fase 6): Django Ninja somente-leitura sobre `apps/simulacao/services.py`, `/api/v1/`, auth `X-API-Key` (`ApiKey`). Ver `apps/integracoes/CLAUDE.md`.
- `templates/` — templates Django (`base.html` fundação Vector, `cotton/`, overrides `django_tables2/` e `tailwind/`, telas de `core`/`account`/`socialaccount`/`gestao`/`simulacao`). `static/vector/` — logo + `tabulator-vector.css`.
- `docs/design-system/README.md` — guia normativo portável do design system AgroVector (ADR 0012).

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

Fases 1–14 concluídas. `VERSION` / `CHANGELOG.md` sobem para `1.3.0` no encerramento da Fase 14
(tag `v1.3.0`, anotada, local — não pushed automaticamente). O produto Streamlit original (Comigo)
segue em produção à parte, congelado (ADR 0011). Próximas evoluções são do Transbordo (estruturas
organizacionais; novos parâmetros do motor; predição de recebimento/venda) — confirme o escopo com o
dono do projeto antes de começar trabalho novo.
