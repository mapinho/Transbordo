# Fase 12 — Evolução (UX/UI) — Design

- Status: Em revisão (aguarda aprovação do dono do projeto)
- Data: 2026-08-30
- Roteiro: primeira fase de evolução pós-Cutover; ver ADR 0011 e "Roadmap Status" no `CLAUDE.md` raiz

## Contexto e objetivo

As Fases 1–11 portaram o produto da cooperativa Comigo (Streamlit) para um stack Django 6 + HTMX
multi-tenant, hoje em produção em `transbordo.vectorconsulting.com.br`. A UI dessa migração foi
deliberadamente mínima: `templates/base.html` primitiva, tema verde "Grão & Aço", navegação plana de
um nível, **sem home nem dashboard** (o login cai direto em `/simulacao/cenarios/`), e o Admin Vector
(papel cross-tenant, `cooperativa=None`) sem tela de entrada — o `TenantManager` devolve `.none()`
para ele, então hoje ele não enxerga dado operacional de nenhuma organização.

O produto passa a ser comercializado como SaaS sob o nome oficial **"Sistema de Planejamento de
Transbordo"**, primeiro de uma suíte (**AgroVector**) de sistemas de planejamento que serão
desenvolvidos com o mesmo padrão de UX/UI. As funcionalidades, hoje modeladas para cooperativas de
soja, passam a servir qualquer organização com fábricas de esmagamento abastecidas por armazéns
geograficamente distribuídos.

Objetivo desta fase: **estabelecer o padrão de UX/UI da suíte** e aplicá-lo por inteiro ao Transbordo —
identidade visual Vector Consulting, header/menu/dashboard padronizados, e a infraestrutura de
componentes que os próximos produtos vão copiar. A referência é a UI do **Sistema de Gestão de
Projetos da Vector** (repo `AppVector.git`), que os usuários já avaliaram como agradável; ela por sua
vez evoluiu da UI do **Sistema de Manutenção Automotiva** (`ManAuto`), também em produção.

Os itens 2–5 do pedido original (aperfeiçoamento das estruturas organizacionais; novos parâmetros do
motor de cálculo; predição/dimensionamento de recebimento dos produtores; predição/dimensionamento de
venda de grãos) são **fases seguintes** e estão fora deste SPEC.

## Escopo

**Dentro:**

- Reescrita de `templates/base.html` portando a fundação visual de `AppVector` (daisyUI 5 + Tailwind 4
  via Play CDN; tema `vector`/`vector-dark` + estado "sistema"; script anti-flash; modal e confirm
  compartilhados; CSRF HTMX global).
- Header de dois níveis: logotipo Vector + nome do sistema + supra-marca "AgroVector" + organização
  corrente (esquerda); dropdown do usuário com conta e gestão do tenant, ícone de aparência, ícone de
  sair (direita). Segunda linha = faixa de módulos com ícone + label e estado ativo.
- **Home nova** (`/`, `apps.core`), que vira o `LOGIN_REDIRECT_URL`, com duas telas:
  **dashboard consolidado** (Admin Vector sem organização) e **home da organização** (membro, ou Admin
  Vector com organização selecionada).
- **Seletor de organização** no header para o Admin Vector, resolvido por sessão (Abordagem A abaixo);
  ajustes localizados em `apps/core/tenancy.py`, `middleware.py`, `permissions.py` e nas ~5 views de
  `apps/simulacao` que liam `request.user.cooperativa_id` cru.
- Migração de **todas** as ~25 telas para os componentes do padrão: django-cotton (já instalado),
  **django-tables2 + django-filter** (novos) para listagens read-only, crispy-tailwind (já instalado)
  para formulários, Tabulator (mantido) re-tematizado para os grids editáveis.
- **django-unfold** (novo) para o reskin do `/admin/`.
- `requirements.txt` / `requirements-dev.txt` → **`pyproject.toml`** (runtime + `[project.optional-dependencies] dev`).
- ADR `0012-design-system-agrovector.md` + guia normativo portável `docs/design-system/README.md`.
- `VERSION` → `1.1.0`, `CHANGELOG.md`, tag `v1.1.0` (não pushed automaticamente).

**Fora:**

- Rename do model `Cooperativa` → `Organizacao` (item 2, próxima fase). A UI **já usa** "Organização"
  nos textos visíveis; código, tabela e managers continuam `Cooperativa` até lá.
- Dashboard detalhado por papel para usuários de organização (o item 1 pede explicitamente "próxima
  fase"). Esta fase entrega só a home mínima com atalhos e alguns números.
- Prefixo `/org/<slug>/` nas URLs (Abordagem B, rejeitada abaixo).
- Qualquer mudança no motor de otimização, nos serviços de relatório (`services.py`), na Face JSON
  (`apps/integracoes`) ou no `mcp_server.py`.
- Migrations de banco — **nenhum model muda** nesta fase.
- Deploy server-side automatizado — segue manual, como nas Fases 10–11.
- Extração de um pacote Python compartilhado (`vector-ui` ou similar) — decisão adiada; o padrão é
  "doc normativo + cópia por produto" por ora.
- Trocar as tags de CDN de `base.html` por assets locais (segue como na Fase 10).

## Decisões de arquitetura

### 1. Padrão da suíte = doc normativo + implementação de referência (sem pacote compartilhado)

Esta fase produz dois artefatos duráveis além do código:

- **`docs/design-system/README.md`** — guia normativo portável: tokens de cor, anatomia da
  `base.html`, catálogo dos componentes cotton, estrutura de header/menu/dashboard, e as regras de uso
  (ex.: `text-accent` para link solto, `primary`/navy só para fundo preenchido ou borda; header sempre
  navy nos dois temas; tri-estado de tema com `localStorage`).
- **A própria implementação no Transbordo** — `templates/base.html`, `templates/cotton/*`, os
  overrides de template, e os trechos relevantes de `apps/core` (tenancy, home, services).

Cada produto futuro da suíte **copia** esses arquivos e segue o guia. Sem dependência entre repositórios,
sem versionamento de pacote, sem CI de publicação. É a formalização do que `AppVector` → `ManAuto` já
fizeram informalmente. A decisão de empacotar (ou não) fica para uma fase futura, quando houver duas
implementações reais maduras (AppVector + Transbordo) para comparar.

Rejeitado nesta fase: **pacote Python instalável**. Ganho real (ponto único de evolução) só aparece
com ≥3 produtos consumindo; o custo agora (empacotar templates/static, versionar, resolver o
acoplamento com `apps.core`) é desproporcional.

### 2. Fundação visual portada 1:1 de AppVector

`templates/base.html` reescrita seguindo `AppVector/templates/base.html` e a ADR 0020 **desse** repo:

- `<link href="https://cdn.jsdelivr.net/npm/daisyui@5">` + `<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4">`.
- Bloco `@theme` registra os **nomes** dos tokens junto ao Tailwind (faz `bg-primary` etc. existirem
  como utilities). O bloco `:root` / `[data-theme="vector-dark"]` **sem `@layer`** logo depois do
  daisyUI é a fonte de verdade real das cores — necessário porque qualquer coisa dentro de uma
  `@layer` perde na cascata do CSS, não importa especificidade nem ordem (achado empírico documentado
  na ADR 0020 de AppVector; reproduzido aqui verbatim para as próximas sessões não reaprenderem).
- Tokens idênticos aos de AppVector: `--color-primary: #1F3060` (navy, sempre — o header é sempre
  navy), semânticas `--color-accent`/`--color-info: #38bdf8`, `--color-success: #27c27a`,
  `--color-warning: #f59e0b`, `--color-error: #ef4444` (iguais nos dois temas);
  `--color-base-100/200/300` e `--color-*-content` mudam entre claro e escuro. O tema verde
  "Grão & Aço" (`--cor-primaria`, `data-theme="grao-e-aco"`) é **removido** de toda a base de código.
- Script anti-flash: lê `localStorage['vector-theme-pref']` (`light`/`dark`/`system`), resolve contra
  `prefers-color-scheme` quando `system`, aplica `data-theme` no `<html>` antes do primeiro paint.
  Prefixo `vector-*` (não `av-*` do ManAuto nem `transbordo-*`) — padroniza a suíte no nome já usado
  pela implementação mais madura.
- `<body ... hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>` global (substitui o `django_htmx`
  script de CSRF por request, mantém `django_htmx` para o resto).
- `<dialog id="vector-modal">` + `<dialog id="vector-confirm">` compartilhados, portados 1:1 (incluindo
  os scripts inline de `showModal()` no `htmx:afterSwap` e de interceptação do `htmx:confirm`).
  `static/simulacao/js/modal.js` é **removido** — é código morto hoje (referencia
  `#transbordo-modal`, que nunca existiu no DOM) e a versão de AppVector o substitui.
- `templates/base.html` some com o `#htmx-error-toast` atual em favor do bloco `messages` +
  `alert-error` do padrão AppVector para erros de servidor; erros de rede HTMX continuam com um toast,
  re-estilizado com `alert alert-error`.

Pacotes novos: `django-tables2`, `django-filter`, `django-unfold`. Config:
`DJANGO_TABLES2_TEMPLATE = 'django_tables2/tailwind.html'`; `unfold` + `unfold.contrib.filters` /
`unfold.contrib.forms` antes de `django.contrib.admin` em `INSTALLED_APPS`; branding Unfold (logo
navy, título "Transbordo — Admin") em `settings`.

### 3. Header

`<header>` sticky navy (`bg-primary text-primary-content shadow-sm`), `max-w-7xl`.

**Esquerda:** logo Vector (`h-9`, `static/vector/img/logo-vector.png`) + coluna "Sistema de
Planejamento de Transbordo" (semibold) / "AgroVector" (uppercase, 10px, opacidade 60%) + separador +
**organização corrente**:

- Membro de organização → texto estático `{{ org.nome }}`.
- Admin Vector → `<select>` com as organizações ativas + opção "— Consolidado —"; `onchange` faz
  `POST` para `core:selecionar_organizacao`, que grava/limpa `session['org_corrente_id']` e redireciona
  para `core:home`.

**Direita** (exatamente três elementos):

1. Nome do usuário (`{{ user.get_full_name|default:user.email }}`) + **dropdown** `dropdown-end`, itens
   gated por papel:
   - Minha conta (dados + links allauth: senha, e-mails, contas sociais) — qualquer autenticado
   - Minha organização — `admin_cooperativa`
   - Usuários — `admin_cooperativa` ou `admin_vector`
   - Organizações — `admin_vector`
   - Admin Django (`/admin/`) — `is_staff`
2. Ícone de aparência + dropdown (☀️ Claro / 🌙 Escuro / 🖥️ Sistema), portado 1:1 (troca o ícone
   conforme a preferência ativa).
3. Ícone de sair — `POST` para `account_logout` (isolado, sem dropdown).

**Segunda linha:** faixa de módulos (Decisão 4).

`apps/gestao/context_processors.py:menu()` passa a devolver, além dos flags de papel atuais
(`menu_admin_vector` etc.): `org` (organização corrente resolvida, ou `None`) e
`organizacoes_disponiveis` (queryset de `Cooperativa.objects.filter(ativo=True)`, só quando Admin
Vector).

### 4. Navegação

**Faixa de módulos** (segunda linha do header; portada do padrão AppVector: `border-t border-white/10
bg-black/10`, cada item `<a>` com `<c-icon>` + label, estado ativo `border-b-2 border-white
font-semibold` vs `border-transparent text-primary-content/70`):

| Papel | Itens |
|---|---|
| Membro de organização | Início · Cenários · Carga de Dados |
| Admin Vector — sem organização | Início (dashboard consolidado) |
| Admin Vector — com organização selecionada | Início · Cenários · Carga de Dados |

Gestão (Organizações, Usuários, Minha organização, Conta) **não** entra na faixa — vive no dropdown do
usuário. Ícones: Início=`home`, Cenários=`git-branch`, Carga de Dados=`upload`.

**Subnav do cenário** (`templates/simulacao/_subnav.html`): mantém as 7 abas atuais (Fábricas ·
Armazéns · Rotas · Previsões · Datas de Safra · Simulação · Assistente) e o swap HTMX em
`#cenario-content` com `hx-push-url`. Muda só o estilo (`tabs tabs-boxed` → padrão daisyUI
tema-correto) e ganha, acima das abas, um **cabeçalho de cenário** dentro de `<c-card>`: nome +
`badge` "Oficial" / "Simulação".

**Breadcrumb:** `{% block breadcrumb %}` na `base.html` (logo antes de `{% block content %}`) +
`<c-breadcrumb>` (Início sempre primeiro, link para `core:home`; separador "/" via CSS). Ex.:
`Início / Cenários / Safra 24/25 / Fábricas`. A home deixa o bloco vazio.

### 5. "Organização corrente" por sessão (Abordagem A)

Escolhida sobre a Abordagem B (prefixo `/org/<slug>/` nas URLs, estilo ManAuto) porque B é um refactor
de URL que toca todos os templates, `urls.py`, `LOGIN_REDIRECT_URL` e boa parte da suíte de testes —
desproporcional agora, e melhor revisitado quando o model organizacional for retrabalhado (item 2).

**`apps/core/tenancy.py`** — novo `obter_organizacao_corrente(request) -> int | None`:

- membro de organização → `request.user.cooperativa_id`;
- Admin Vector → `request.session.get('org_corrente_id')`, validado contra
  `Cooperativa.objects.filter(ativo=True)` (id inválido/inativo é ignorado e removido da sessão);
- anônimo → `None`.

**`apps/core/middleware.py`** — `CooperativaScopeMiddleware` passa a alimentar o contextvar a partir
de `obter_organizacao_corrente(request)` em vez de `user.cooperativa_id` cru. Para membros, o
comportamento é idêntico ao de hoje.

**`apps/core/views.py`** — nova view `selecionar_organizacao` (`@login_required`,
`@requer_admin_vector`, `require_POST`): grava/limpa `session['org_corrente_id']` e redireciona para
`core:home`.

**`apps/core/permissions.py`** — Admin Vector com organização selecionada age como **super-membro**
daquela organização:

- Novo decorator `requer_membro_organizacao` (ciente do `request`), que substitui
  `@papel_required(*MEMBROS_COOPERATIVA)` nas views de `apps/simulacao`: passa se o usuário for membro
  **ou** (for Admin Vector **e** `obter_organizacao_corrente(request)` não-nulo). Admin Vector sem
  organização selecionada recebe `PermissionDenied` com mensagem "Selecione uma organização".
- `pode_editar_fabricas` / `pode_editar_armazens` ganham um parâmetro opcional `request=None`;
  retornam `True` também para `e_admin_vector(user) and obter_organizacao_corrente(request)`. Os
  decorators `requer_edicao_fabricas` / `requer_edicao_armazens` repassam o `request`.
- `pode_gerir_usuarios`, `requer_admin_vector`, `papel_required` — inalterados.

**Views de `apps/simulacao/views.py`** — os ~5 pontos que leem `request.user.cooperativa_id` cru
(`cenarios_list` e afins) passam a usar um helper único `cooperativa_id_do_request(request)`
(= `obter_organizacao_corrente(request)`, com `PermissionDenied` se `None`). Os grids editáveis já
usam `Model.objects` (escopado pelo contextvar via middleware) — herdam o novo escopo de graça.

**`apps/integracoes` (Face JSON)** — **sem mudança**. A API resolve tenant por `X-API-Key` →
`ApiKey.cooperativa`; o seletor de sessão é exclusivo das telas HTMX.

### 6. Home e dashboards

Nova rota `apps/core.views.home` (`name='home'`, `@login_required`), registrada em `config/urls.py`
como `path('', ...)`, e definida como `LOGIN_REDIRECT_URL = '/'`. Resolve `obter_organizacao_corrente`
e renderiza:

**6a. Dashboard consolidado** (`templates/core/home_consolidado.html`) — só Admin Vector sem
organização:

- `<c-resumo-numerico>`: Organizações ativas · Fábricas · Armazéns · Toneladas transbordadas · Sacas ·
  Frete total (R$).
- Tabela por organização (django-tables2): uma linha por organização ativa — Organização · Fábricas ·
  Armazéns · Toneladas · Frete (R$) · Última simulação (data / "nunca"). Clicar na linha faz `POST`
  para `core:selecionar_organizacao` com aquele id.
- Formatação pt-BR obrigatória via `apps/simulacao/templatetags/simulacao_filters.py`.

**6b. Home da organização** (`templates/core/home_organizacao.html`) — membro, ou Admin Vector com
organização selecionada:

- Saudação "Olá, {primeiro nome}" + nome da organização.
- `<c-resumo-numerico>`: Fábricas · Armazéns · Cenários · Última simulação do oficial (data).
- `<c-lista-cartao titulo="Atalhos">`: cartões-link para Cenários, Carga de Dados e Assistente (via
  cenário oficial).
- `<c-lista-cartao titulo="Cenários recentes">`: últimos cenários, cada um linkando para a grade de
  Fábricas.
- Comentário no template marcando que o dashboard detalhado por papel entra na próxima fase.

**Fonte dos números** — novo `apps/core/services.py`, funções puras usando os managers
`all_cooperativas` (sem contextvar de tenant, cross-tenant deliberado):

- `metricas_da_organizacao(cooperativa_id) -> dict` e `metricas_consolidadas() -> {totais, por_organizacao}`.
- Fábricas / Armazéns = `count()` no **cenário oficial** (`is_oficial=True`) da organização.
- Toneladas = `Σ MovimentacaoDiaria.quantidade_ton` do cenário oficial;
  Sacas = `toneladas * KG_PER_TON / KG_PER_SACA` (1000/60, constantes de `services.py`);
  Frete (R$) = `Σ MovimentacaoDiaria.custo_total`.
- `MovimentacaoDiaria` é reescrita a cada execução do engine, então seu conteúdo atual = resultado da
  última simulação bem-sucedida. Organização sem execução `sucesso` → métricas de resultado = `None`
  (renderizadas como "—").
- "Última simulação" = `max(LogExecucao.data_execucao)` com `status='sucesso'` e (`cenario` = oficial
  **ou** `cenario_id IS NULL` — a convenção "rodou contra o oficial", ver comentário do campo em
  `apps/simulacao/models.py`).
- Totais do consolidado = soma das linhas por organização.

Organização sem cenário oficial (`is_oficial=True` inexistente) → linha com zeros e "—"; nunca 500.

### 7. Migração das telas

Config já pronta: `crispy_tailwind`, `CRISPY_TEMPLATE_PACK='tailwind'`.

**Infraestrutura de template:**

| Arquivo | Ação |
|---|---|
| `templates/base.html` | Reescrito (Decisões 2–4) |
| `static/simulacao/js/modal.js` | Removido (código morto) |
| `templates/cotton/card.html` | Re-estilo para os tokens daisyUI, mantendo a assinatura atual (`border-base-300 bg-base-100 rounded-lg p-8 {{ class }}`, com `id` opcional) |
| `templates/cotton/lista_cartao.html`, `resumo_numerico.html`, `breadcrumb.html` | Novos (portados de AppVector) |
| `templates/cotton/icon.html` | Novo — `<c-icon name="...">`, catálogo de SVG inline Lucide-style |
| `templates/django_tables2/tailwind.html`, `templates/tailwind/field.html`, `templates/_paginacao.html`, `templates/_exportar.html` | Novos overrides (portados) |
| `static/vector/css/tabulator-vector.css` | Novo — mapeia as classes do Tabulator para `--color-base-*` nos dois temas |
| `static/vector/img/logo-vector.png` | Novo (copiado de AppVector) |

**Telas:**

| Grupo | Telas | Ação |
|---|---|---|
| Auth | `account/login` + 8 `account/*` + `socialaccount/authentication_error`, `socialaccount/connections` + `403.html` | Reskin identidade Vector; login com logo + `<c-card>`; forms via crispy |
| Home | `core/home_consolidado.html`, `core/home_organizacao.html` | Novas (Decisão 6) |
| Gestão | `gestao/cooperativas` (+`_cooperativas_content`), `gestao/usuarios` (+`_usuarios_content`) | Listagens → django-tables2 + django-filter; breadcrumb; textos → "Organizações" |
| Gestão | `gestao/cooperativa_form`, `gestao/usuario_form`, `gestao/minha_cooperativa`, `gestao/conta` | Forms → crispy dentro de `<c-card>`; breadcrumb; "Minha organização" |
| Gestão | `gestao/base_gestao.html` | `max-w-7xl`, `{% block breadcrumb %}` |
| Cenários | `simulacao/cenarios` (+`_cenarios_content`) | Breadcrumb; form "novo cenário" crispy em `<c-card>`; lista em `<c-lista-cartao>` |
| Cenário | 7 shells (`fabricas.html` … `assistente.html`) + `_*_content.html` + `_subnav.html` | Subnav re-estilizada; cabeçalho de cenário em `<c-card>`; grids Tabulator re-tematizados; botões `btn btn-primary` |
| Simulação | `simulacao/simulacao` (+`_simulacao_content`, `_simulacao_status`) | Status via `badge` / `progress` / `alert` daisyUI; polling HTMX inalterado |
| Assistente | `simulacao/assistente` (+`_assistente_content`, `_assistente_transcript`) | Reskin do chat (bolhas, `<c-card>`); comportamento e escopo por cenário inalterados |
| Carga | `simulacao/carga`, `simulacao/carga_preview` (+ `_carga_content`, `_carga_preview_content`) | Upload form crispy; preview com `table` / `alert` daisyUI |

**`/admin/` (django-unfold):** `apps/core/admin.py` (3 registros), `apps/integracoes/admin.py` (2),
`apps/simulacao/admin.py` (23) → `unfold.admin.ModelAdmin`. `procrastinate` fica com o admin padrão.

### 8. `pyproject.toml`

- Novo `pyproject.toml` com `[project]` (nome, versão lida de `VERSION` ou fixa, `requires-python`),
  `dependencies` (o conteúdo atual de `requirements.txt`) e `[project.optional-dependencies] dev`
  (`pytest`, `pytest-django`, o que estiver em `requirements-dev.txt`).
- `requirements.txt` e `requirements-dev.txt` removidos.
- Atualizados: `Dockerfile` (`pip install .` em vez de `pip install -r requirements.txt`),
  `.devcontainer/`, workflow de CI, e as referências de comando em `CLAUDE.md` / `README.md` /
  `docs/DEPLOY.md`.
- Sem adotar um resolvedor novo (Poetry/uv/PDM) — `pip` + `pyproject.toml` (PEP 621) direto, mesmo
  padrão de AppVector e ManAuto.

## Testes

TDD (red → green), testes em `apps/*/tests/`, PostgreSQL local via `DJANGO_DB_*`.

- **`apps/core/tests/`**: `test_tenancy.py` e `test_middleware.py` ganham Admin Vector com/sem
  organização selecionada; novos `test_home.py` (consolidado vs organização, roteamento por papel),
  `test_selecionar_organizacao.py` (grava/limpa sessão, rejeita não-Admin-Vector, ignora id inativo),
  `test_core_services.py` (`metricas_*` com `all_cooperativas`, organização sem execução → `None`,
  soma dos totais bate).
- **`apps/core/tests/test_permissions.py`**: Admin Vector com organização passa nos gates de membro e
  de edição; sem organização → `PermissionDenied`.
- **`apps/simulacao/tests/`**: a suíte atual roda igual (fixtures de membro); + casos de
  Admin-Vector-com-organização em `cenarios_list` e num grid editável (salvando).
- **`apps/gestao/tests/test_menu.py`**: cobre `org` e `organizacoes_disponiveis` no contexto;
  listagens migradas para tables2/filter revalidadas (colunas, filtro, paginação).
- **Render smoke**: todas as ~25 telas via Django test client (200, sem `NoReverseMatch` /
  `TemplateDoesNotExist`), com usuário de cada papel.
- Meta: a suíte continua verde (hoje **309**) + os novos testes. Sem snapshot visual automatizado.

## Verificação manual (a registrar no fim da fase)

- `python manage.py runserver` + `python manage.py procrastinate worker`.
- Login local; os dois dashboards; seletor de organização (Admin Vector entra e sai de uma
  organização, "— Consolidado —" volta ao dashboard); um grid editável salvando; uma simulação
  ponta-a-ponta; tema claro / escuro / sistema sem flash ao navegar; `/admin/` com Unfold.
- `python manage.py check` e `python manage.py makemigrations --check --dry-run` limpos — esta fase
  **não cria migrations**.

## Docs (skill `sync-specs-skills` aplicável)

- Este SPEC.
- ADR `docs/decisions/0012-design-system-agrovector.md` — adoção daisyUI/Unfold/tables2/filter,
  seletor de organização por sessão (Abordagem A), `pyproject.toml`, e a decisão "doc normativo +
  cópia" para a suíte.
- **Guia normativo portável** `docs/design-system/README.md`.
- Atualizar: `CLAUDE.md` raiz (Tech Stack, Commands para `pyproject`, seção "Fase 12"),
  `README.md`, **novo** `apps/core/CLAUDE.md` (tenancy + home + services + seletor de organização),
  `apps/gestao/CLAUDE.md` (context processor, telas migradas), `apps/simulacao/CLAUDE.md`
  (helper de organização corrente), `docs/DEPLOY.md` (comandos).
- `CHANGELOG.md` + `VERSION` → `1.1.0`; tag `v1.1.0` (anotada, local — não pushed automaticamente).

## Rollout

Branch única `fase12-evolucao-ux-ui`. Execução subagent-driven em ondas, review por onda:

1. **Fundação** — `pyproject.toml`, pacotes novos, `base.html`, componentes cotton, overrides de
   template, `tabulator-vector.css`, logo.
2. **Tenancy + home** — `obter_organizacao_corrente`, middleware, `permissions.py`,
   `selecionar_organizacao`, `apps/core/services.py`, rota `/` e as duas telas de home, ajuste das
   views de `simulacao`.
3. **Gestão** — listagens em tables2/filter, forms crispy, textos "Organização".
4. **Cenários + grids** — cenários, 7 shells + subnav + cabeçalho de cenário, Tabulator re-tema,
   simulação, assistente, carga.
5. **Auth + admin** — telas allauth/socialaccount/403, django-unfold.
6. **Docs** — ADR, guia, CLAUDE.md/README/DEPLOY, CHANGELOG, VERSION, tag.

Merge fast-forward em `main` ao fim, tag `v1.1.0`. Sem deploy server-side automático.
