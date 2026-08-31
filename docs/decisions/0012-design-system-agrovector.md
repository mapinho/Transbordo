# ADR 0012 — Design system AgroVector: daisyUI/Unfold, seletor de organização por sessão, `pyproject.toml`

- Status: Aceito
- Data: 2026-08-31

## Contexto

As Fases 1–11 portaram o produto (Comigo/Streamlit) para um stack Django 6 + HTMX multi-tenant, hoje
em produção em `transbordo.vectorconsulting.com.br`. A UI dessa migração foi deliberadamente mínima:
`templates/base.html` primitiva, tema verde "Grão & Aço", navegação plana de um nível, sem home nem
dashboard (o login caía direto em `/simulacao/cenarios/`), e o Admin Vector (papel cross-tenant,
`cooperativa=None`) sem tela de entrada — o `TenantManager` devolve `.none()` para ele.

O produto passa a ser comercializado como **"Sistema de Planejamento de Transbordo"**, primeiro de uma
suíte (**AgroVector**) de sistemas de planejamento com o mesmo padrão de UX/UI. A referência é a UI do
**Sistema de Gestão de Projetos da Vector** (repo `AppVector.git`), que os usuários já avaliaram como
agradável, e que por sua vez evoluiu da UI do **Sistema de Manutenção Automotiva** (`ManAuto`).

A Fase 12 estabelece esse padrão e o aplica por inteiro ao Transbordo. Ver
`docs/superpowers/specs/2026-08-30-fase12-evolucao-ux-ui-design.md`.

## Decisão

### 1. Padrão da suíte = doc normativo + implementação de referência (sem pacote compartilhado)

A fase produz dois artefatos duráveis além do código:

- **`docs/design-system/README.md`** — guia normativo portável: tokens de cor, anatomia da
  `base.html`, catálogo dos componentes cotton, estrutura de header/menu, regras de uso.
- **A própria implementação no Transbordo** — `templates/base.html`, `templates/cotton/*`, os overrides
  de template, `static/vector/*` e os trechos relevantes de `apps/core` (tenancy, home, services).

Cada produto futuro da suíte **copia** esses arquivos e segue o guia. Sem dependência entre
repositórios, sem versionamento de pacote, sem CI de publicação — a formalização do que
`AppVector` → `ManAuto` já fizeram informalmente.

Rejeitado nesta fase: **pacote Python instalável** (`vector-ui` ou similar). O ganho real (ponto único
de evolução) só aparece com ≥3 produtos consumindo; o custo agora (empacotar templates/static,
versionar, resolver o acoplamento com `apps.core`) é desproporcional. A decisão de empacotar fica para
uma fase futura, quando houver duas implementações reais maduras (AppVector + Transbordo) para comparar.

### 2. Fundação visual: daisyUI 5 + Tailwind 4 via Play CDN, temas `vector` / `vector-dark`

`templates/base.html` reescrita seguindo `AppVector/templates/base.html` e a **ADR 0020 desse repo**:

- `<link href="https://cdn.jsdelivr.net/npm/daisyui@5">` +
  `<script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4">`. Sem build step, sem assets
  locais (segue como na Fase 10; trocar CDN por assets locais fica para depois).
- O bloco `@theme` (dentro de `<style type="text/tailwindcss">`) registra só os **nomes** dos tokens
  junto ao Tailwind — é o que faz `bg-primary`, `text-accent` etc. existirem como utilities.
- O bloco `:root` / `[data-theme="vector-dark"]` **sem `@layer`**, logo depois do CSS do daisyUI, é a
  **fonte de verdade real** das cores. Necessário porque qualquer regra dentro de uma `@layer` perde
  na cascata do CSS para qualquer regra fora de `@layer`, não importa especificidade nem ordem (achado
  empírico documentado na ADR 0020 de AppVector; reproduzido aqui verbatim, com comentário no arquivo,
  para as próximas sessões não reaprenderem).
- Token `--color-primary: #1F3060` (navy Vector, **sempre** — o header é sempre navy nos dois temas).
  Semânticas iguais nos dois temas; `--color-base-*` e alguns `*-content` mudam entre claro e escuro.
  O tema verde "Grão & Aço" (`data-theme="grao-e-aco"`, `--cor-primaria`) foi **removido** de toda a
  base de código.
- Script anti-flash inline no `<head>`: lê `localStorage['vector-theme-pref']` (`light`/`dark`/`system`),
  resolve contra `prefers-color-scheme` quando `system`, aplica `data-theme` no `<html>` antes do
  primeiro paint. Prefixo `vector-*` (não `av-*` do ManAuto nem `transbordo-*`) — padroniza a suíte no
  nome já usado pela implementação mais madura.
- `<body hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>` global para o CSRF do HTMX (`django_htmx`
  segue carregado para o resto). `<dialog id="vector-modal">` + `<dialog id="vector-confirm">`
  compartilhados, portados 1:1. `static/simulacao/js/modal.js` foi removido (código morto —
  referenciava um `#transbordo-modal` que nunca existiu no DOM).

### 3. django-tables2 + django-filter para listagens read-only

Listagens somente-leitura (Organizações, Usuários) passam a usar **django-tables2** (`Table` por
model, `template_name = 'django_tables2/tailwind.html'`) + **django-filter** (`FilterSet` por model).
Override `templates/django_tables2/tailwind.html` re-tematizado (classes daisyUI: `table table-sm`,
paginação `join`/`btn`). `DJANGO_TABLES2_TEMPLATE = 'django_tables2/tailwind.html'` em settings.

Formulários seguem com **crispy-tailwind** (já instalado; `CRISPY_TEMPLATE_PACK = 'tailwind'`) dentro
de `<c-card>`, com override `templates/tailwind/field.html`. Grids editáveis seguem em **Tabulator**,
re-tematizado por `static/vector/css/tabulator-vector.css` (mapeia as classes do Tabulator para
`--color-base-*` nos dois temas).

### 4. django-unfold no `/admin/`

**django-unfold** faz o reskin do Django admin. `unfold` + `unfold.contrib.filters` +
`unfold.contrib.forms` **antes** de `django.contrib.admin` em `INSTALLED_APPS`; branding em
`UNFOLD = {...}` no settings (título "Transbordo — Admin", cor primária navy). Os `ModelAdmin` de
`apps/core`, `apps/integracoes` e `apps/simulacao` herdam de `unfold.admin.ModelAdmin`; o admin do
`procrastinate` fica com o admin padrão.

### 5. "Organização corrente" por sessão (Abordagem A) — rejeitada a Abordagem B (prefixo de URL)

O Admin Vector precisava de uma forma de entrar numa organização para ver/editar seu dado operacional.

- **Abordagem A (escolhida)**: a organização corrente é resolvida por request em
  `apps/core/tenancy.py::obter_organizacao_corrente(request)` — membro → `request.user.cooperativa_id`;
  Admin Vector → `request.session['org_corrente_id']` (validado contra `Cooperativa` ativa; id
  inválido/inativo é descartado da sessão); anônimo → `None`. O `CooperativaScopeMiddleware` alimenta
  o contextvar de tenant a partir dessa função (para membros, comportamento idêntico ao de antes). A
  view `core:selecionar_organizacao` (`@requer_admin_vector`, `require_POST`) grava/limpa a sessão.
  Admin Vector com organização selecionada age como **super-membro** dela: novo decorator
  `requer_membro_organizacao` e parâmetro `request` opcional em `pode_editar_fabricas` /
  `pode_editar_armazens`. As ~5 views de `apps/simulacao` que liam `request.user.cooperativa_id` cru
  passam a usar o helper `cooperativa_id_do_request(request)`.
- **Abordagem B (rejeitada)**: prefixo `/org/<slug>/` em todas as URLs (estilo ManAuto). É um refactor
  de URL que toca todos os templates, `urls.py`, `LOGIN_REDIRECT_URL` e boa parte da suíte de testes —
  desproporcional agora, e melhor revisitado quando o model organizacional (`Cooperativa` →
  `Organizacao`, item 2 do pedido) for retrabalhado.

A **Face JSON** (`apps/integracoes`) não muda — resolve tenant por `X-API-Key` → `ApiKey.cooperativa`;
o seletor de sessão é exclusivo das telas HTMX.

### 6. `requirements.txt` / `requirements-dev.txt` → `pyproject.toml`

Novo `pyproject.toml` (PEP 621): `[project]` com `name`, `dynamic = ["version"]` (lida de `VERSION`),
`requires-python = ">=3.10"`, `dependencies` (o conteúdo de `requirements.txt`) e
`[project.optional-dependencies] dev` (`pytest`, `pytest-django`). `requirements.txt` e
`requirements-dev.txt` removidos. Install: `pip install -e ".[dev]"` (dev) / `pip install .` (Docker).
Sem adotar resolvedor novo (Poetry/uv/PDM) — `pip` + `pyproject.toml` direto, mesmo padrão de AppVector
e ManAuto.

## Consequências

- Novas dependências de produção: `django-tables2`, `django-filter`, `django-unfold`
  (+ `django-crispy-forms`/`crispy-tailwind`, que já eram declaradas). Ver `pyproject.toml`.
- Nova rota `/` (`apps.core.views.home`) é o `LOGIN_REDIRECT_URL` (era `/simulacao/cenarios/`). Duas
  telas: dashboard consolidado (Admin Vector sem organização) e home da organização.
- Novo `apps/core/services.py` (métricas dos dashboards) usa os managers `all_cooperativas`
  deliberadamente cross-tenant — só as telas de home podem chamá-lo, nunca uma view comum (ADR 0006).
- `apps/core/context_processors` / `apps/gestao/context_processors.menu()` agora devolvem `org`,
  `organizacoes_disponiveis` e `mostra_modulos` para o header.
- Nenhum model muda — a fase **não cria migrations**. `Cooperativa` continua `Cooperativa` no código,
  tabela e managers; a UI já usa "Organização" nos textos visíveis.
- A `base.html` depende do Play CDN do Tailwind/daisyUI em runtime (risco herdado da Fase 10).
- O guia `docs/design-system/README.md` vira documento normativo da suíte: mudança de token, de
  componente cotton ou de regra de uso atualiza o guia **e** esta implementação de referência.
- Renumeração: esta é a ADR 0012; as ADRs vão de 0001 a 0012.
