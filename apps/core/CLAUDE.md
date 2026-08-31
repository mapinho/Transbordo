# apps/core — file map

Identidade, tenancy, autorização por papel e — desde a Fase 12 — a home e os dashboards. Ver o
`CLAUDE.md` raiz para o contexto do projeto, `docs/decisions/` (ADRs `0001`, `0003`, `0006`, `0009`,
`0012`) e as specs das Fases 5, 7 e 12.

- `models.py` — `Cooperativa` (raiz do tenant: `nome`, `slug`, `ativo`, `dias_janela_safra_padrao`
  placeholder) e `User` (`AbstractUser` + `email` único obrigatório + `cooperativa` FK nullable +
  `papel`). `User` **não** é `CooperativaScopedModel` (auth roda antes de qualquer escopo; `cooperativa`
  é nullable só para Admin Vector). `CheckConstraint` `user_papel_cooperativa_coerentes` + `clean()`
  garantem: `admin_vector` ⇒ sem cooperativa; qualquer outro papel ⇒ com cooperativa.
- `tenancy.py` — escopo de tenant por contextvar (`TenantManager` fail-closed → `.none()` sem
  cooperativa corrente; `CooperativaScopedModel` com `objects` escopado + `all_cooperativas` cru).
  **Fase 12** adicionou:
  - `obter_organizacao_corrente(request) -> int | None` — resolve a organização do request: membro →
    `request.user.cooperativa_id`; Admin Vector → `request.session['org_corrente_id']` (validado contra
    `Cooperativa` ativa; id inválido/inativo é descartado da sessão); anônimo → `None`.
  - `cooperativa_id_do_request(request)` — igual, mas levanta `PermissionDenied('Selecione uma
    organização.')` se `None`. É o helper que as ~5 views de `apps/simulacao` que liam
    `request.user.cooperativa_id` cru passaram a usar.
- `middleware.py` — `CooperativaScopeMiddleware` (o último de `MIDDLEWARE`, o mais interno). Alimenta o
  contextvar a partir de `obter_organizacao_corrente(request)` (era `user.cooperativa_id` cru); reseta
  no `finally`. Para membro, comportamento idêntico ao de antes.
- `permissions.py` — funções puras + decorators finos (ADR 0009). **Fase 12** adicionou:
  - `requer_membro_organizacao` — substitui `@papel_required(*MEMBROS_COOPERATIVA)` nas views de
    `apps/simulacao`: passa se o usuário for membro **ou** (Admin Vector **e** organização corrente
    não-nula). Admin Vector sem organização → `PermissionDenied('Selecione uma organização.')`.
  - `pode_editar_fabricas` / `pode_editar_armazens` ganharam `request=None` opcional e retornam `True`
    também para Admin Vector com organização selecionada (super-membro). `requer_edicao_*` repassam o
    `request`.
  - `pode_gerir_usuarios`, `requer_admin_vector`, `papel_required` — inalterados.
- `views.py`:
  - `healthz` — health check sem auth: `APP_VERSION` + `SELECT 1` (503 se o banco cair). Montado em
    `config/urls.py` (`/healthz/`); usado pelo HEALTHCHECK do container e pelo poll do `deploy.sh`.
  - `home` (`@login_required`, `name='core:home'`) — resolve `obter_organizacao_corrente`. Sem
    organização **e** Admin Vector → `core/home_consolidado.html` (`services.metricas_consolidadas()`).
    Senão → `core/home_organizacao.html` (`services.metricas_da_organizacao(org_id)` + até 8 cenários
    recentes via `Cenario.all_cooperativas`, oficial primeiro). É o `LOGIN_REDIRECT_URL` (`/`).
  - `selecionar_organizacao` (`@login_required`, `@requer_admin_vector`, `require_POST`) — grava
    `session['org_corrente_id']` (id numérico de `Cooperativa` ativa) ou limpa; redireciona para
    `core:home`. É o alvo do `<select>` do header e das linhas do dashboard consolidado.
- `urls.py` — `app_name = 'core'`; `path('', home, name='home')` e
  `path('organizacao/selecionar/', selecionar_organizacao, name='selecionar_organizacao')`. Incluído na
  raiz por `config/urls.py`.
- `services.py` — **Fase 12**, métricas dos dashboards. Funções puras usando `all_cooperativas`
  (cross-tenant deliberado — só as telas de home chamam, nunca uma view comum; ver ADR 0006):
  - `metricas_da_organizacao(cooperativa_id) -> dict` — fábricas/armazéns = `count()` no cenário
    oficial; toneladas/frete = `Σ MovimentacaoDiaria` do oficial; sacas = `toneladas * KG_PER_TON /
    KG_PER_SACA`; `ultima_simulacao` = `max(LogExecucao.data_execucao)` com `status=SUCESSO` e
    (`cenario` = oficial **ou** `cenario_id IS NULL`). Organização sem cenário oficial → zeros e `None`
    (nunca 500); sem execução de sucesso → métricas de resultado = `None` (renderizado "—").
  - `metricas_consolidadas() -> {totais, por_organizacao}` — uma linha por `Cooperativa` ativa; os
    totais são a soma das linhas.
- `context_processors.py` — `app_version(request)` (`APP_VERSION`). O menu do header vem de
  `apps/gestao/context_processors.menu` (`org`, `organizacoes_disponiveis`, `mostra_modulos` + flags de
  papel).
- `adapters.py` — allauth: `NoSignupAccountAdapter` (cadastro fechado) + `AssociateByEmailSocialAdapter`
  (liga o login social ao `User` pré-criado por e-mail; nunca cria `User`). ADR 0009.
- `admin.py` — `Cooperativa` e `User` em `unfold.admin.ModelAdmin` (Fase 12, django-unfold).
- `management/commands/` — `criar_admin_vector <username> --email <email>` (cria o único `admin_vector`;
  recusa um segundo); `sanitizar_pos_restore` (higieniza resíduo de dev após restore em prod — ver
  `docs/DEPLOY.md`).
- `tests/` — inclui, da Fase 12: `test_tenancy.py` / `test_middleware.py` (Admin Vector com/sem
  organização), `test_home.py`, `test_selecionar_organizacao.py`, `test_core_services.py`,
  `test_permissions.py` (super-membro), `test_base_template.py`, `test_cotton_componentes.py`,
  `test_admin_unfold.py`, `test_fase12_config.py`, `test_render_smoke.py` (as ~25 telas por papel).
