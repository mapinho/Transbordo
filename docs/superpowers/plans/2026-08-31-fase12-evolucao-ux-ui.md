# Fase 12 — Evolução (UX/UI) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Portar a fundação visual da suíte AgroVector (identidade Vector Consulting, daisyUI/Tailwind, header de dois níveis, home/dashboards) de `AppVector.git` para o Transbordo inteiro, e habilitar o Admin Vector a operar dentro de uma organização selecionada por sessão.

**Architecture:** Sem mudança de modelo de dados nem de migrations. Três eixos: (1) `templates/base.html` + componentes cotton + overrides reescritos para os tokens daisyUI (`vector`/`vector-dark`); (2) "organização corrente" resolvida por `apps/core/tenancy.py::obter_organizacao_corrente(request)` — para membros é idêntico a hoje, para Admin Vector vem de `session['org_corrente_id']`; (3) home nova em `apps/core` (rota `/`, novo `LOGIN_REDIRECT_URL`) com dashboard consolidado e home da organização, alimentada por `apps/core/services.py` (managers `all_cooperativas`). Rollout subagent-driven em 6 ondas numa branch única.

**Tech Stack:** Django 6, HTMX, django-cotton, daisyUI 5 + Tailwind 4 (Play CDN), django-tables2 + django-filter (novos), crispy-tailwind, Tabulator (re-tematizado), django-unfold (novo), PostgreSQL, pytest/pytest-django, `pyproject.toml` (PEP 621, pip).

**Spec:** `docs/superpowers/specs/2026-08-30-fase12-evolucao-ux-ui-design.md` — o plano argumenta a partir do SPEC; leia os dois.

## Global Constraints

Todo requisito de tarefa inclui implicitamente esta seção.

- **Sem migrations.** Nenhum model muda. Ao fim, `python manage.py makemigrations --check --dry-run` tem de sair limpo.
- **TDD estrito** (red → green): escreva o teste que falha, confirme que falha pelo motivo certo, implemente o mínimo, confirme verde. Testes em `apps/*/tests/`, arquivos `test_*.py`.
- **Banco real:** os testes usam PostgreSQL local via `DJANGO_DB_*` (`config.settings.dev`, já é o default do `pytest.ini`). Suíte atual = **309 passed**; ao fim ela continua verde + os novos testes.
- **Formatação pt-BR obrigatória** onde há dado numérico: filtros `moeda` / `volume` de `apps/simulacao/templatetags/simulacao_filters.py` (`.` milhar, `,` decimal). Nunca renderizar float/moeda cru.
- **1 saca = 60 kg:** usar `KG_PER_TON` (1000) e `KG_PER_SACA` (60) de `apps/simulacao/services.py`. Nunca um `1000/60` mágico.
- **Identidade Vector:** navy `--color-primary: #1F3060` (header sempre navy nos dois temas); link/texto interativo solto usa `text-accent` (nunca `text-primary`); `primary`/navy só para fundo preenchido ou borda. Semânticas iguais nos dois temas: `--color-accent`/`--color-info: #38bdf8`, `--color-success: #27c27a`, `--color-warning: #f59e0b`, `--color-error: #ef4444`.
- **Prefixo `localStorage`:** `vector-theme-pref` (não `av-*`, não `transbordo-*`).
- **Terminologia visível:** "Organização" (não "Cooperativa") em toda string de UI nova ou tocada. O model, a tabela e os managers continuam `Cooperativa` — rename é a próxima fase.
- **CDN, não assets locais:** `base.html` continua carregando daisyUI/Tailwind/HTMX por `<script>`/`<link>` de CDN, como nas Fases 10–11.
- **Tema verde "Grão & Aço" é removido** de toda a base de código (`data-theme="grao-e-aco"`, `--cor-primaria`, `--cor-borda`, `--cor-superficie`, `--cor-primaria-hover`, `--cor-acento`).
- **`apps/integracoes` (Face JSON), `apps/simulacao/services.py`, `apps/simulacao/engine.py`, `mcp_server.py` — intocados.**
- **`config/urls.py` mantém a ordem:** rotas específicas antes de `path('', include('apps.core.urls'))`.

## Substituições de token (regra única, referenciada por todas as tarefas de re-estilo de tela)

Ao portar uma tela do tema "Grão & Aço" para daisyUI, aplique estas trocas mecânicas. **REGRA-SUBST:**

| De | Para |
|---|---|
| `bg-[var(--cor-primaria)]` (+ `hover:bg-[var(--cor-primaria-hover)]`) num `<button>`/`<a>` de ação | `btn btn-primary` (remover as classes de padding/cor manuais) |
| `bg-[var(--cor-primaria)]` como fundo de faixa/chip | `bg-primary text-primary-content` |
| `text-[var(--cor-primaria)]` como cor de link/título clicável | `text-accent hover:underline` |
| `text-[var(--cor-primaria)]` num `<h1>`/`<h2>` não-clicável | `text-base-content` |
| `border-[var(--cor-borda)]`, `border-slate-100/200/300` | `border-base-300` |
| `bg-[var(--cor-superficie)]`, `bg-white` | `bg-base-100` |
| `bg-slate-50`, `bg-slate-100` | `bg-base-200` |
| `text-slate-900`, `text-slate-800`, `text-slate-700` | `text-base-content` |
| `text-slate-600`, `text-slate-500`, `text-slate-400` | `text-base-content/70` (ou `/60`, `/50` p/ tons mais fracos) |
| `divide-[var(--cor-borda)]`, `divide-slate-*` | `divide-base-300` |
| `text-red-600`, `text-red-700` | `text-error` |
| `<input>`/`<select>`/`<textarea>` com `border rounded px-2 py-1` ad-hoc | remover as classes — o bloco `@layer base` da `base.html` já estiliza os campos |
| `alert alert-error` / `alert alert-success` | mantêm-se (daisyUI já os define nos dois temas) |
| `<table class="table w-full">` | `<table class="table table-sm">` |
| "Cooperativa"/"cooperativa" em texto visível | "Organização"/"organização" |

Onde a tela já usa `btn btn-primary` / `badge` / `alert` daisyUI, deixe como está — só herdará as cores tema-corretas.

---

# Onda 1 — Fundação

Infra de packaging, pacotes novos, `base.html`, componentes cotton, overrides de template, assets estáticos. Nenhuma tela de conteúdo muda ainda (só herdam cores). Ao fim desta onda o app sobe, `manage.py check` passa, e a suíte de 309 continua verde (com os ajustes de asserção listados).

### Task 1: Migração para `pyproject.toml`

**Files:**
- Create: `pyproject.toml`
- Delete: `requirements.txt`, `requirements-dev.txt`
- Modify: `Dockerfile`, `.devcontainer/devcontainer.json`, `.github/workflows/ci.yml`
- Modify (refs de comando): `CLAUDE.md`, `README.md`, `docs/DEPLOY.md`

**Interfaces:**
- Produces: instalação via `pip install -e ".[dev]"` (dev) e `pip install .` (Docker). Extra `dev` = `pytest`, `pytest-django`. Versão lida de `VERSION` (`dynamic`).

- [ ] **Step 1: Escrever `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "transbordo"
description = "Sistema de Planejamento de Transbordo — SaaS de otimização logística soja (suíte AgroVector)"
requires-python = ">=3.10"
dynamic = ["version"]
dependencies = [
    "pandas==2.3.3",
    "openpyxl==3.1.5",
    "python-dotenv==1.2.2",
    "ortools==9.15.6755",
    "fastmcp==3.4.2",
    "mcp[cli]==1.28.0",
    "httpx>=0.27,<1.0",
    "google-genai==2.10.0",
    "Django>=6.0,<6.1",
    "django-htmx>=1.19,<2.0",
    "django-cotton>=2.7,<3.0",
    "django-crispy-forms>=2.7,<3.0",
    "crispy-tailwind>=1.0,<2.0",
    "django-tables2>=3.0,<4.0",
    "django-filter>=26.0,<27.0",
    "django-unfold>=0.104,<0.105",
    "procrastinate>=3.9,<4.0",
    "psycopg[binary]>=3.2,<4",
    "django-ninja>=1.4,<2.0",
    "django-allauth[socialaccount]>=65.0,<66.0",
    "gunicorn>=23,<24",
    "whitenoise>=6.6,<7",
]

[project.optional-dependencies]
dev = [
    "pytest",
    "pytest-django",
]

[tool.setuptools.dynamic]
version = { file = ["VERSION"] }

[tool.setuptools.packages.find]
include = ["apps*", "config*"]
```

- [ ] **Step 2: Remover os `requirements*.txt`**

```bash
git rm requirements.txt requirements-dev.txt
```

- [ ] **Step 3: Instalar e verificar**

```bash
pip install -e ".[dev]"
python -c "import django_tables2, django_filters, unfold; print('ok')"
python manage.py check
```
Expected: `ok`, e `System check identified no issues` (django-tables2/filter/unfold ainda não em `INSTALLED_APPS` — só confirma que instalaram).

- [ ] **Step 4: Atualizar o `Dockerfile`**

Trocar as linhas de dependência:
```dockerfile
# Dependências numa camada separada — o cache de build só reinstala quando
# pyproject.toml muda, não a cada alteração de código.
COPY pyproject.toml VERSION ./
RUN pip install --no-cache-dir .

COPY . .
```
(Remover as duas linhas `COPY requirements.txt .` / `RUN pip install ... -r requirements.txt`. O `COPY . .` seguinte permanece.)

- [ ] **Step 5: Atualizar `.devcontainer/devcontainer.json`**

Trocar o `updateContentCommand` para:
```json
"updateContentCommand": "pip3 install --user -e '.[dev]'; echo '✅ Dependências instaladas'",
```

- [ ] **Step 6: Atualizar `.github/workflows/ci.yml`**

Trocar o passo "Install dependencies":
```yaml
      - name: Install dependencies
        run: pip install -e ".[dev]"
```

- [ ] **Step 7: Atualizar refs de comando na documentação**

Em `CLAUDE.md` (bloco "## Commands"), `README.md` e `docs/DEPLOY.md`, trocar toda ocorrência de:
- `pip install -r requirements.txt` → `pip install -e ".[dev]"` (contexto dev) ou `pip install .` (contexto Docker/prod)
- `pip install -r requirements-dev.txt` → (remover a linha; `[dev]` já cobre)

- [ ] **Step 8: Rodar a suíte inteira**

Run: `pytest`
Expected: **309 passed** (packaging não muda comportamento).

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "build: requirements.txt -> pyproject.toml (PEP 621, pip)"
```

---

### Task 2: Instalar e configurar django-tables2, django-filter, django-unfold

**Files:**
- Modify: `config/settings/base.py`

**Interfaces:**
- Produces: `INSTALLED_APPS` com `unfold` (+ `unfold.contrib.filters`, `unfold.contrib.forms`) **antes** de `django.contrib.admin`, e `django_tables2` / `django_filters`. Setting `DJANGO_TABLES2_TEMPLATE = "django_tables2/tailwind.html"`. Branding Unfold (`UNFOLD` dict).

- [ ] **Step 1: Teste que falha**

Create `apps/core/tests/test_fase12_config.py`:
```python
from django.conf import settings
from django.test import TestCase


class Fase12ConfigTests(TestCase):
    def test_apps_de_ui_instalados(self):
        for app in ("django_tables2", "django_filters", "unfold"):
            self.assertIn(app, settings.INSTALLED_APPS)

    def test_unfold_antes_do_admin_contrib(self):
        apps = settings.INSTALLED_APPS
        self.assertLess(apps.index("unfold"), apps.index("django.contrib.admin"))

    def test_tables2_template_daisyui(self):
        self.assertEqual(settings.DJANGO_TABLES2_TEMPLATE, "django_tables2/tailwind.html")
```

- [ ] **Step 2: Rodar — falha**

Run: `pytest apps/core/tests/test_fase12_config.py -v`
Expected: FAIL (`django_tables2` não em INSTALLED_APPS; `DJANGO_TABLES2_TEMPLATE` inexistente).

- [ ] **Step 3: Editar `config/settings/base.py`**

No topo de `INSTALLED_APPS`, antes de `'django.contrib.admin'`:
```python
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'django.contrib.admin',
```
Depois do bloco allauth/htmx/cotton/crispy, junto aos demais de terceiros:
```python
    'django_tables2',
    'django_filters',
```
No fim do arquivo:
```python
DJANGO_TABLES2_TEMPLATE = 'django_tables2/tailwind.html'

UNFOLD = {
    'SITE_TITLE': 'Transbordo — Admin',
    'SITE_HEADER': 'Transbordo — Admin',
    'COLORS': {
        'primary': {
            '500': '31 48 96',
            '600': '31 48 96',
            '700': '42 64 128',
        },
    },
}
```

- [ ] **Step 4: Rodar — passa**

Run: `pytest apps/core/tests/test_fase12_config.py -v && python manage.py check`
Expected: 3 passed; check limpo.

- [ ] **Step 5: Suíte + migrations check**

Run: `python manage.py makemigrations --check --dry-run && pytest`
Expected: sem migrations pendentes; 312 passed.

- [ ] **Step 6: Commit**

```bash
git add config/settings/base.py apps/core/tests/test_fase12_config.py
git commit -m "chore: instala django-tables2/filter/unfold e configura settings"
```

---

### Task 3: Componentes cotton e overrides de template

**Files:**
- Modify: `templates/cotton/card.html`
- Create: `templates/cotton/lista_cartao.html`, `templates/cotton/resumo_numerico.html`, `templates/cotton/breadcrumb.html`, `templates/cotton/icon.html`
- Create: `templates/django_tables2/tailwind.html`, `templates/tailwind/field.html`, `templates/_paginacao.html`, `templates/_exportar.html`
- Create: `static/vector/css/tabulator-vector.css`, `static/vector/img/logo-vector.png`
- Create: `apps/core/tests/test_cotton_componentes.py`

**Interfaces:**
- Produces: `<c-card class id>`, `<c-lista-cartao titulo> + <c-slot name="acoes">`, `<c-resumo-numerico class>`, `<c-breadcrumb>` (slot = itens após "Início"), `<c-icon name="home|git-branch|upload|plus|arrow-right|building|users|external">` (SVG inline). Override `django_tables2/tailwind.html` requer no contexto: `table.prefix`, `table.list_url`, `table.tamanhos_pagina`, `table.prefixed_*_field` (padrão do django-tables2). `<c-breadcrumb>` faz `{% url 'core:home' %}` — **depende de `core:home` existir** (Task 5). Esta task cria os arquivos; o smoke que os exercita roda depois de Task 5.

- [ ] **Step 1: Copiar o logo**

```bash
mkdir -p static/vector/img static/vector/css
cp "C:/Users/mario/OneDrive/Documents/Projects/Desenvolvimento_Claude_Code/APP_Vector/static/vector/img/logo-vector.png" static/vector/img/logo-vector.png
```
Se o caminho de origem não existir, procurar `logo-vector*.png` sob `APP_Vector/static/` e copiar o encontrado para `static/vector/img/logo-vector.png`.

- [ ] **Step 2: `templates/cotton/card.html`** (re-estilo, mesma assinatura)

```html
<div class="rounded-lg border border-base-300 bg-base-100 p-8 {{ class }}"{% if id %} id="{{ id }}"{% endif %}>
  {{ slot }}
</div>
```

- [ ] **Step 3: `templates/cotton/lista_cartao.html`** (portado de AppVector, verbatim)

```html
<div class="card border border-base-300 bg-base-100 shadow-sm {{ class }}">
  <div class="card-body p-0">
    <div class="flex items-center justify-between gap-2 border-b border-base-300 px-4 py-3">
      <h2 class="text-sm font-semibold text-base-content">{{ titulo }}</h2>
      <div class="flex items-center gap-1">
        {{ acoes }}
      </div>
    </div>
    <div class="max-h-96 overflow-y-auto">
      {{ slot }}
    </div>
  </div>
</div>
```

- [ ] **Step 4: `templates/cotton/resumo_numerico.html`** (portado de AppVector, verbatim)

```html
<div class="stats stats-vertical w-full border border-base-300 bg-base-100 shadow-sm sm:stats-horizontal {{ class }}">
  {{ slot }}
</div>
```

- [ ] **Step 5: `templates/cotton/breadcrumb.html`** (portado de AppVector, verbatim)

```html
<nav aria-label="breadcrumb" class="c-breadcrumb mb-4 flex flex-wrap items-center gap-2 text-sm">
  <a href="{% url 'core:home' %}" class="text-base-content/60 hover:text-accent hover:underline">Início</a>
  {{ slot }}
</nav>
```

- [ ] **Step 6: `templates/cotton/icon.html`** (novo — catálogo SVG inline, stroke `currentColor`)

```html
{% comment %}<c-icon name="..."> — SVG inline estilo Lucide, herda cor/tamanho por classe.{% endcomment %}
<span class="inline-flex {{ class }}" aria-hidden="true">
{% if name == "home" %}<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 10.5 12 3l9 7.5"></path><path d="M5 9.5V21h14V9.5"></path></svg>
{% elif name == "git-branch" %}<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><line x1="6" y1="3" x2="6" y2="15"></line><circle cx="18" cy="6" r="3"></circle><circle cx="6" cy="18" r="3"></circle><path d="M18 9a9 9 0 0 1-9 9"></path></svg>
{% elif name == "upload" %}<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><path d="M17 8 12 3 7 8"></path><line x1="12" y1="3" x2="12" y2="15"></line></svg>
{% elif name == "plus" %}<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M5 12h14"></path></svg>
{% elif name == "arrow-right" %}<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14M13 6l6 6-6 6"></path></svg>
{% elif name == "building" %}<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="3" width="16" height="18" rx="1"></rect><path d="M9 8h1M14 8h1M9 12h1M14 12h1M9 21v-4h6v4"></path></svg>
{% elif name == "users" %}<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
{% elif name == "external" %}<svg class="h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><path d="M15 3h6v6M10 14 21 3"></path></svg>
{% endif %}
</span>
```

- [ ] **Step 7: `templates/django_tables2/tailwind.html`**

Copiar o arquivo de `APP_Vector/templates/django_tables2/tailwind.html` verbatim. Ele já usa só tokens `base-*` e `btn`.

- [ ] **Step 8: `templates/tailwind/field.html`** (override do crispy-tailwind — tokens daisyUI)

```html
{% if field.is_hidden %}
  {{ field }}
{% else %}
  <div id="div_{{ field.auto_id }}" class="mb-3">
    {% if field.label and form_show_labels %}
      <label for="{{ field.id_for_label }}">
        {{ field.label }}{% if field.field.required %} <span class="text-error">*</span>{% endif %}
      </label>
    {% endif %}
    {{ field }}
    {% if field.help_text %}<p class="mt-1 text-xs text-base-content/60">{{ field.help_text|safe }}</p>{% endif %}
    {% if field.errors %}<p class="mt-1 text-xs text-error">{{ field.errors|striptags }}</p>{% endif %}
  </div>
{% endif %}
```

- [ ] **Step 9: `templates/_paginacao.html`** e `templates/_exportar.html`

Copiar ambos de `APP_Vector/templates/` verbatim (já em tokens daisyUI / `btn`). São helpers opcionais — usados pelas telas de gestão em Onda 3.

- [ ] **Step 10: `static/vector/css/tabulator-vector.css`** (novo)

```css
/* Mapeia o Tabulator para os tokens daisyUI (--color-base-*) nos dois temas.
   Carregado por base.html depois do CSS oficial do Tabulator. */
.tabulator {
  background-color: var(--color-base-100);
  border-color: var(--color-base-300);
  color: var(--color-base-content);
  font-size: 0.875rem;
}
.tabulator .tabulator-header,
.tabulator .tabulator-header .tabulator-col {
  background-color: var(--color-base-200);
  border-color: var(--color-base-300);
  color: var(--color-base-content);
}
.tabulator .tabulator-row {
  background-color: var(--color-base-100);
  border-color: var(--color-base-300);
  color: var(--color-base-content);
}
.tabulator .tabulator-row.tabulator-row-even {
  background-color: var(--color-base-200);
}
.tabulator .tabulator-row:hover {
  background-color: var(--color-base-300);
}
.tabulator .tabulator-cell {
  border-color: var(--color-base-300);
}
.tabulator .tabulator-cell.tabulator-editing {
  border-color: var(--color-primary);
  outline: 1px solid var(--color-primary);
}
.tabulator .tabulator-footer {
  background-color: var(--color-base-200);
  border-color: var(--color-base-300);
  color: var(--color-base-content);
}
```

- [ ] **Step 11: Teste de render dos componentes**

Create `apps/core/tests/test_cotton_componentes.py`:
```python
from django.template import Context, Template
from django.test import TestCase


class CottonComponentesTests(TestCase):
    def _render(self, corpo):
        return Template("{% load cotton %}" + corpo).render(Context({}))

    def test_card_aceita_class_e_id(self):
        html = self._render('<c-card class="mb-6" id="x">oi</c-card>')
        self.assertIn("mb-6", html)
        self.assertIn('id="x"', html)
        self.assertIn("bg-base-100", html)

    def test_resumo_numerico(self):
        html = self._render("<c-resumo-numerico><div>1</div></c-resumo-numerico>")
        self.assertIn("stats", html)

    def test_icon_conhecido_e_desconhecido(self):
        self.assertIn("<svg", self._render('<c-icon name="home" />'))
        self.assertNotIn("<svg", self._render('<c-icon name="inexistente" />'))
```

- [ ] **Step 12: Rodar**

Run: `pytest apps/core/tests/test_cotton_componentes.py -v`
Expected: 3 passed. (`<c-breadcrumb>` **não** é testado aqui — precisa de `core:home`; entra no smoke da Task 10.)

- [ ] **Step 13: Commit**

```bash
git add templates/cotton templates/django_tables2 templates/tailwind templates/_paginacao.html templates/_exportar.html static/vector apps/core/tests/test_cotton_componentes.py
git commit -m "feat(ui): componentes cotton e overrides de template daisyUI (Fase 12)"
```

---

### Task 4: Reescrever `templates/base.html`

**Files:**
- Modify: `templates/base.html`
- Delete: `static/simulacao/js/modal.js`
- Modify: `apps/gestao/context_processors.py`
- Create: `apps/core/tests/test_base_template.py`

**Interfaces:**
- Consumes: contexto de `apps.gestao.context_processors.menu` — flags atuais (`menu_admin_vector`, `menu_admin_cooperativa`, `menu_gerir_usuarios`, `menu_membro_cooperativa`) **mais** `org`, `organizacoes_disponiveis`, `mostra_modulos` (adicionados aqui). `APP_VERSION` de `apps.core.context_processors.app_version`.
- Produces: `base.html` com `{% block title %}`, `{% block extra_head %}`, `{% block breadcrumb %}`, `{% block content %}`, `{% block extra_scripts %}`; header navy de dois níveis; `<dialog id="vector-modal">` + `<dialog id="vector-confirm">` + `window.vectorConfirm`; `hx-headers` CSRF global. Faz `{% url 'core:home' %}`, `{% url 'core:selecionar_organizacao' %}`, `{% url 'account_logout' %}` — **depende de `core:home` e `core:selecionar_organizacao` (Task 5)**. Portanto: Task 5 e Task 6 vêm antes do smoke; esta task cria o arquivo e roda `manage.py check` (que não resolve `{% url %}` em runtime) + um teste de presença de string via `Template` isolado não serve (usa `{% url %}`). **Reordenar:** executar Task 5 e Task 6 imediatamente antes desta, ou aceitar que o `pytest` completo só fecha verde ao fim da Task 6. O plano assume a segunda opção e marca o gate real no fim da Onda 1.

- [ ] **Step 1: Ampliar `apps/gestao/context_processors.py`**

```python
from apps.core import permissions
from apps.core.models import Cooperativa
from apps.core.tenancy import obter_organizacao_corrente


def menu(request):
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return {}
    org_id = obter_organizacao_corrente(request)
    org = Cooperativa.objects.filter(id=org_id).first() if org_id else None
    e_membro = permissions.papel_de(user) in permissions.MEMBROS_COOPERATIVA
    organizacoes_disponiveis = (
        Cooperativa.objects.filter(ativo=True).order_by('nome')
        if permissions.e_admin_vector(user) else None
    )
    return {
        'menu_admin_vector': permissions.e_admin_vector(user),
        'menu_admin_cooperativa': permissions.e_admin_cooperativa(user),
        'menu_gerir_usuarios': permissions.pode_gerir_usuarios(user),
        'menu_membro_cooperativa': e_membro,
        'org': org,
        'organizacoes_disponiveis': organizacoes_disponiveis,
        'mostra_modulos': e_membro or (permissions.e_admin_vector(user) and org is not None),
    }
```
(`obter_organizacao_corrente` é criada na Task 5 — se esta task rodar antes, stub temporário `return getattr(request.user, 'cooperativa_id', None)`; a Task 5 substitui.)

- [ ] **Step 2: Reescrever `templates/base.html`**

Estrutura completa (portada de `APP_Vector/templates/base.html`, adaptada aos nomes de rota do Transbordo):

```html
{% load static django_htmx %}<!doctype html>
<html lang="pt-br" data-theme="vector">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Sistema de Planejamento de Transbordo{% endblock %}</title>
  <script>
    (function () {
      var STORAGE_KEY = 'vector-theme-pref';
      var pref = localStorage.getItem(STORAGE_KEY) || 'system';
      var resolved = pref === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'vector-dark' : 'vector')
        : (pref === 'dark' ? 'vector-dark' : 'vector');
      document.documentElement.setAttribute('data-theme', resolved);
      document.documentElement.dataset.themePref = pref;
    })();
  </script>
  <link href="https://cdn.jsdelivr.net/npm/daisyui@5" rel="stylesheet" type="text/css">
  <script src="https://cdn.jsdelivr.net/npm/@tailwindcss/browser@4"></script>
  <style type="text/tailwindcss">
    /* @theme só registra os NOMES dos tokens junto ao Tailwind (faz bg-primary
       etc. existirem como utilities). O valor real que pinta a tela vem do
       <style> sem @layer abaixo — qualquer coisa dentro de uma @layer perde na
       cascata do CSS, não importa especificidade nem ordem (ADR 0020 de
       AppVector, reproduzido verbatim para as próximas sessões não reaprenderem). */
    @theme {
      --color-primary: #1F3060;
      --color-primary-hover: #2a4080;
      --color-primary-content: #ffffff;
      --color-secondary: #B2B5B7;
      --color-secondary-content: #1a2540;
      --color-accent: #38bdf8;
      --color-accent-content: #06283d;
      --color-neutral: #1F3060;
      --color-neutral-content: #ffffff;
      --color-base-100: #ffffff;
      --color-base-200: #E8ECF2;
      --color-base-300: #dde3ec;
      --color-base-content: #1a2540;
      --color-info: #38bdf8;
      --color-info-content: #06283d;
      --color-success: #27c27a;
      --color-success-content: #ffffff;
      --color-warning: #f59e0b;
      --color-warning-content: #1a1206;
      --color-error: #ef4444;
      --color-error-content: #ffffff;
    }
    @layer base {
      input:not([type="checkbox"], [type="radio"]), select, textarea {
        @apply w-full min-w-0 rounded-md border border-base-300 bg-base-100 px-3 py-2 text-sm text-base-content;
      }
      input:not([type="checkbox"], [type="radio"]):focus, select:focus, textarea:focus {
        @apply border-primary outline-none ring-1 ring-primary;
      }
      label { @apply mb-1 block text-sm font-medium text-base-content/80; }
      .c-breadcrumb > *:not(:first-child)::before {
        content: "/"; margin-right: 0.5rem; color: var(--color-base-content); opacity: .35;
      }
    }
  </style>
  <style>
    /* Fonte de verdade real das cores (sem @layer) — identidade Vector navy #1F3060. */
    :root {
      --color-primary: #1F3060; --color-primary-hover: #2a4080; --color-primary-content: #ffffff;
      --color-secondary: #B2B5B7; --color-secondary-content: #1a2540;
      --color-accent: #38bdf8; --color-accent-content: #06283d;
      --color-neutral: #1F3060; --color-neutral-content: #ffffff;
      --color-base-100: #ffffff; --color-base-200: #E8ECF2; --color-base-300: #dde3ec;
      --color-base-content: #1a2540;
      --color-info: #38bdf8; --color-info-content: #06283d;
      --color-success: #27c27a; --color-success-content: #ffffff;
      --color-warning: #f59e0b; --color-warning-content: #1a1206;
      --color-error: #ef4444; --color-error-content: #ffffff;
    }
    [data-theme="vector-dark"] {
      color-scheme: dark;
      --color-base-100: #0d1530; --color-base-200: #060d1a; --color-base-300: #08111f;
      --color-base-content: #d4dff0; --color-secondary-content: #08111f;
      --color-neutral: #08111f; --color-neutral-content: #d4dff0;
      --color-success-content: #06140d; --color-error-content: #2a0a0a;
    }
  </style>
  <link href="https://cdn.jsdelivr.net/npm/tabulator-tables@6/dist/css/tabulator.min.css" rel="stylesheet">
  <link href="{% static 'vector/css/tabulator-vector.css' %}" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js"></script>
  {% django_htmx_script %}
  <script src="https://cdn.jsdelivr.net/npm/luxon@3/build/global/luxon.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/tabulator-tables@6/dist/js/tabulator.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/imask@7/dist/imask.min.js"></script>
  <script src="{% static 'simulacao/js/grid_editor.js' %}"></script>
  {% block extra_head %}{% endblock %}
</head>
<body class="min-h-screen bg-base-200 text-base-content antialiased" hx-headers='{"X-CSRFToken": "{{ csrf_token }}"}'>
  <div id="htmx-error-toast" role="alert" class="alert alert-error fixed top-4 right-4 z-50 hidden w-auto max-w-md">
    <span id="htmx-error-toast-text"></span>
  </div>

  <header class="sticky top-0 z-40 bg-primary text-primary-content shadow-sm">
    <div class="navbar mx-auto max-w-7xl px-4 sm:px-6">
      <div class="navbar-start gap-3">
        <a href="{% url 'core:home' %}" class="flex items-center gap-3 no-underline">
          <img src="{% static 'vector/img/logo-vector.png' %}" alt="Vector Consulting" class="h-9 w-auto">
          <span class="hidden flex-col leading-tight sm:flex">
            <span class="text-sm font-semibold text-white">Sistema de Planejamento de Transbordo</span>
            <span class="text-[10px] uppercase tracking-wider text-primary-content/60">AgroVector</span>
          </span>
        </a>
        {% if user.is_authenticated %}
          <span class="mx-1 hidden h-5 border-l border-white/20 sm:block"></span>
          {% if organizacoes_disponiveis is not None %}
            <form method="post" action="{% url 'core:selecionar_organizacao' %}">
              {% csrf_token %}
              <select name="org_id" onchange="this.form.submit()"
                      class="max-w-[12rem] border-white/20 bg-primary text-xs text-primary-content">
                <option value="">— Consolidado —</option>
                {% for o in organizacoes_disponiveis %}
                  <option value="{{ o.id }}" {% if org and org.id == o.id %}selected{% endif %}>{{ o.nome }}</option>
                {% endfor %}
              </select>
            </form>
          {% elif org %}
            <span class="hidden text-xs text-primary-content/80 sm:inline">{{ org.nome }}</span>
          {% endif %}
        {% endif %}
      </div>

      <div class="navbar-end gap-1">
        {% if user.is_authenticated %}
          <div class="dropdown dropdown-end">
            <button type="button" tabindex="0" class="btn btn-ghost btn-sm text-primary-content">
              {{ user.get_full_name|default:user.email }}
              <svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m6 9 6 6 6-6"></path></svg>
            </button>
            <ul tabindex="0" class="dropdown-content menu menu-sm z-10 mt-3 w-56 rounded-box bg-base-100 p-2 text-base-content shadow-lg">
              <li><a href="{% url 'gestao:conta' %}">Minha conta</a></li>
              {% if menu_admin_cooperativa %}<li><a href="{% url 'gestao:minha_cooperativa' %}">Minha organização</a></li>{% endif %}
              {% if menu_gerir_usuarios %}<li><a href="{% url 'gestao:usuarios' %}">Usuários</a></li>{% endif %}
              {% if menu_admin_vector %}<li><a href="{% url 'gestao:cooperativas' %}">Organizações</a></li>{% endif %}
              {% if user.is_staff %}<li><a href="/admin/">Admin Django</a></li>{% endif %}
            </ul>
          </div>

          <div class="dropdown dropdown-end">
            <button type="button" tabindex="0" class="btn btn-ghost btn-circle btn-sm text-primary-content" title="Aparência" aria-label="Alternar tema">
              <svg id="vector-theme-icon-light" class="hidden h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"></path></svg>
              <svg id="vector-theme-icon-dark" class="hidden h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>
              <svg id="vector-theme-icon-system" class="hidden h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="12" rx="1"></rect><path d="M8 20h8M12 16v4"></path></svg>
            </button>
            <ul tabindex="0" class="dropdown-content menu menu-sm z-10 mt-3 w-44 rounded-box bg-base-100 p-2 text-base-content shadow-lg">
              <li><a onclick="vectorApplyTheme('light')">☀️ Claro</a></li>
              <li><a onclick="vectorApplyTheme('dark')">🌙 Escuro</a></li>
              <li><a onclick="vectorApplyTheme('system')">🖥️ Sistema</a></li>
            </ul>
          </div>

          <form method="post" action="{% url 'account_logout' %}">
            {% csrf_token %}
            <button type="submit" class="btn btn-ghost btn-circle btn-sm text-primary-content" title="Sair" aria-label="Sair">
              <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><path d="M16 17l5-5-5-5"></path><path d="M21 12H9"></path></svg>
            </button>
          </form>
        {% endif %}
      </div>
    </div>

    {% if mostra_modulos %}
      <nav class="border-t border-white/10 bg-black/10">
        <div class="mx-auto flex max-w-7xl flex-wrap items-center gap-1 px-4 text-sm sm:px-6">
          {% url 'core:home' as url_inicio %}
          {% url 'simulacao:cenarios_list' as url_cenarios %}
          {% url 'simulacao:carga' as url_carga %}
          <a href="{{ url_inicio }}" class="flex items-center gap-1.5 border-b-2 px-3 py-2.5 {% if request.path == url_inicio %}border-white font-semibold text-white{% else %}border-transparent text-primary-content/70 hover:text-white{% endif %}">
            <c-icon name="home" /> Início
          </a>
          <a href="{{ url_cenarios }}" class="flex items-center gap-1.5 border-b-2 px-3 py-2.5 {% if request.path|slice:':20' == '/simulacao/cenarios/' %}border-white font-semibold text-white{% else %}border-transparent text-primary-content/70 hover:text-white{% endif %}">
            <c-icon name="git-branch" /> Cenários
          </a>
          <a href="{{ url_carga }}" class="flex items-center gap-1.5 border-b-2 px-3 py-2.5 {% if request.path|slice:':17' == '/simulacao/carga/' %}border-white font-semibold text-white{% else %}border-transparent text-primary-content/70 hover:text-white{% endif %}">
            <c-icon name="upload" /> Carga de Dados
          </a>
        </div>
      </nav>
    {% endif %}
  </header>

  <main class="mx-auto my-8 max-w-7xl px-4 sm:px-6">
    {% if messages %}
      <div class="mb-4 space-y-2">
        {% for message in messages %}
          <div role="alert" class="alert text-sm {% if 'error' in message.tags %}alert-error{% elif 'success' in message.tags %}alert-success{% else %}alert-info{% endif %}">
            <span>{{ message }}</span>
          </div>
        {% endfor %}
      </div>
    {% endif %}
    {% block breadcrumb %}{% endblock %}
    {% block content %}{% endblock %}
  </main>

  <dialog id="vector-modal" class="modal">
    <div class="modal-box max-w-lg"><div id="vector-modal-body"></div></div>
    <form method="dialog" class="modal-backdrop"><button>Fechar</button></form>
  </dialog>
  <script>
    (function () {
      var modal = document.getElementById("vector-modal");
      var body = document.getElementById("vector-modal-body");
      document.body.addEventListener("htmx:afterSwap", function (e) {
        if (e.target === body && body.innerHTML.trim() && !modal.open) modal.showModal();
      });
    })();
  </script>

  <dialog id="vector-confirm" class="modal">
    <div class="modal-box max-w-sm">
      <p id="vector-confirm-message" class="py-2 text-sm text-base-content"></p>
      <div class="modal-action">
        <button type="button" class="btn btn-outline btn-sm" onclick="document.getElementById('vector-confirm').close()">Cancelar</button>
        <button type="button" id="vector-confirm-ok" class="btn btn-primary btn-sm">Confirmar</button>
      </div>
    </div>
    <form method="dialog" class="modal-backdrop"><button>Fechar</button></form>
  </dialog>
  <script>
    (function () {
      var dialog = document.getElementById("vector-confirm");
      var mensagem = document.getElementById("vector-confirm-message");
      var okBtn = document.getElementById("vector-confirm-ok");
      window.vectorConfirm = function (form, texto) {
        mensagem.textContent = texto;
        okBtn.onclick = function () { dialog.close(); form.submit(); };
        dialog.showModal();
      };
      document.body.addEventListener("htmx:confirm", function (evt) {
        if (!evt.detail.question) return;
        evt.preventDefault();
        mensagem.textContent = evt.detail.question;
        okBtn.onclick = function () { dialog.close(); evt.detail.issueRequest(true); };
        dialog.showModal();
      });
    })();
  </script>

  <script>
    document.body.addEventListener('htmx:responseError', function (evt) {
      var toast = document.getElementById('htmx-error-toast');
      document.getElementById('htmx-error-toast-text').textContent =
        (evt.detail.xhr && evt.detail.xhr.responseText) || 'Ocorreu um erro ao processar a solicitação.';
      toast.classList.remove('hidden');
      clearTimeout(toast._hideTimeout);
      toast._hideTimeout = setTimeout(function () { toast.classList.add('hidden'); }, 5000);
    });
    function vectorApplyTheme(pref) {
      localStorage.setItem('vector-theme-pref', pref);
      document.documentElement.dataset.themePref = pref;
      var resolved = pref === 'system'
        ? (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'vector-dark' : 'vector')
        : (pref === 'dark' ? 'vector-dark' : 'vector');
      document.documentElement.setAttribute('data-theme', resolved);
      vectorSyncThemeIcon();
    }
    function vectorSyncThemeIcon() {
      var pref = document.documentElement.dataset.themePref || 'system';
      ['light', 'dark', 'system'].forEach(function (name) {
        var icon = document.getElementById('vector-theme-icon-' + name);
        if (icon) icon.classList.toggle('hidden', name !== pref);
      });
    }
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function () {
      if (document.documentElement.dataset.themePref === 'system') vectorApplyTheme('system');
    });
    vectorSyncThemeIcon();
  </script>

  <footer class="mx-auto max-w-7xl px-4 py-3 text-xs text-base-content/40 sm:px-6">
    Transbordo v{{ APP_VERSION }}
  </footer>
  {% block extra_scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 3: Remover o `modal.js` morto**

```bash
git rm static/simulacao/js/modal.js
```
Confirmar que nenhum template ainda o referencia:
Run: `grep -rn "js/modal.js\|transbordo-modal" templates/ apps/`
Expected: sem resultados (o `<script src="{% static 'simulacao/js/modal.js' %}">` estava só na `base.html` antiga).

- [ ] **Step 4: Teste de fumaça da `base.html`**

Create `apps/core/tests/test_base_template.py`:
```python
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Cooperativa

User = get_user_model()


class BaseTemplateTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="Coop A", slug="coop-a")
        self.membro = User.objects.create_user(
            username="m", email="m@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )
        self.vector = User.objects.create_user(
            username="v", email="v@t.test", password="x", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def test_membro_ve_faixa_de_modulos_e_nao_ve_seletor(self):
        self.client.force_login(self.membro)
        html = self.client.get("/").content.decode()
        self.assertIn("Carga de Dados", html)
        self.assertIn("Coop A", html)
        self.assertNotIn('name="org_id"', html)
        self.assertNotIn("grao-e-aco", html)
        self.assertIn('data-theme="vector"', html)

    def test_admin_vector_sem_org_ve_seletor_e_so_o_modulo_inicio(self):
        self.client.force_login(self.vector)
        html = self.client.get("/").content.decode()
        self.assertIn('name="org_id"', html)
        self.assertIn("— Consolidado —", html)
        self.assertNotIn("Carga de Dados", html)
```
(Este teste **só passa depois da Task 5/6** — a rota `/` precisa existir. Marcado como parte do gate da Onda 1.)

- [ ] **Step 5: `manage.py check`**

Run: `python manage.py check`
Expected: limpo.

- [ ] **Step 6: Commit**

```bash
git add templates/base.html apps/gestao/context_processors.py apps/core/tests/test_base_template.py
git rm static/simulacao/js/modal.js
git commit -m "feat(ui): reescreve base.html com a fundação visual Vector (Fase 12)"
```

---

# Onda 2 — Tenancy e Home

### Task 5: `obter_organizacao_corrente` + `cooperativa_id_do_request` + middleware

**Files:**
- Modify: `apps/core/tenancy.py`
- Modify: `apps/core/middleware.py`
- Modify: `apps/core/tests/test_tenancy.py`, `apps/core/tests/test_middleware.py`

**Interfaces:**
- Produces:
  - `obter_organizacao_corrente(request) -> int | None` — membro: `request.user.cooperativa_id`; Admin Vector: `request.session['org_corrente_id']` validado contra `Cooperativa.objects.filter(ativo=True)` (id inválido/inativo → ignora e faz `session.pop('org_corrente_id', None)`); anônimo/sem request: `None`.
  - `cooperativa_id_do_request(request) -> int` — `obter_organizacao_corrente(request)` ou `raise PermissionDenied("Selecione uma organização.")` se `None`.

- [ ] **Step 1: Testes que falham** — em `apps/core/tests/test_tenancy.py`, nova classe:

```python
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, TestCase

from apps.core.models import Cooperativa, User
from apps.core.tenancy import cooperativa_id_do_request, obter_organizacao_corrente


class OrganizacaoCorrenteTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.coop = Cooperativa.objects.create(nome="A", slug="a")
        self.inativa = Cooperativa.objects.create(nome="Z", slug="z", ativo=False)
        self.membro = User.objects.create_user(
            username="m", email="m@t.test", papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.coop,
        )
        self.vector = User.objects.create_user(
            username="v", email="v@t.test", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def _req(self, user, session=None):
        r = self.rf.get("/")
        r.user = user
        r.session = session or {}
        return r

    def test_membro_usa_a_propria_cooperativa(self):
        self.assertEqual(obter_organizacao_corrente(self._req(self.membro)), self.coop.id)

    def test_admin_vector_sem_sessao_e_none(self):
        self.assertIsNone(obter_organizacao_corrente(self._req(self.vector)))

    def test_admin_vector_com_sessao_valida(self):
        r = self._req(self.vector, {"org_corrente_id": self.coop.id})
        self.assertEqual(obter_organizacao_corrente(r), self.coop.id)

    def test_admin_vector_id_inativo_e_limpo_da_sessao(self):
        r = self._req(self.vector, {"org_corrente_id": self.inativa.id})
        self.assertIsNone(obter_organizacao_corrente(r))
        self.assertNotIn("org_corrente_id", r.session)

    def test_cooperativa_id_do_request_levanta_sem_org(self):
        with self.assertRaises(PermissionDenied):
            cooperativa_id_do_request(self._req(self.vector))
```

- [ ] **Step 2: Rodar — falha** (`ImportError: cannot import name 'obter_organizacao_corrente'`).

- [ ] **Step 3: Implementar em `apps/core/tenancy.py`** (adicionar ao fim, antes das classes; importar dentro da função para evitar ciclo com `models`):

```python
def obter_organizacao_corrente(request):
    """id da organização na qual o request opera, ou None.

    Membro de organização -> a própria cooperativa. Admin Vector -> a
    seleção guardada em session['org_corrente_id'] (validada contra
    Cooperativa ativa; id inválido é descartado). Anônimo -> None.
    """
    user = getattr(request, 'user', None)
    if user is None or not user.is_authenticated:
        return None
    if getattr(user, 'cooperativa_id', None):
        return user.cooperativa_id
    from apps.core.permissions import e_admin_vector
    if not e_admin_vector(user):
        return None
    session = getattr(request, 'session', None)
    org_id = session.get('org_corrente_id') if session is not None else None
    if not org_id:
        return None
    from apps.core.models import Cooperativa
    if Cooperativa.objects.filter(id=org_id, ativo=True).exists():
        return org_id
    if session is not None:
        session.pop('org_corrente_id', None)
    return None


def cooperativa_id_do_request(request):
    """Como obter_organizacao_corrente, mas exige uma organização definida."""
    from django.core.exceptions import PermissionDenied
    org_id = obter_organizacao_corrente(request)
    if org_id is None:
        raise PermissionDenied('Selecione uma organização.')
    return org_id
```

- [ ] **Step 4: Atualizar `apps/core/middleware.py`**

```python
from apps.core.tenancy import (
    definir_cooperativa_atual,
    obter_organizacao_corrente,
    resetar_cooperativa_atual,
)


class CooperativaScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cooperativa_id = obter_organizacao_corrente(request)
        token = definir_cooperativa_atual(cooperativa_id)
        try:
            return self.get_response(request)
        finally:
            resetar_cooperativa_atual(token)
```

- [ ] **Step 5: Ampliar `apps/core/tests/test_middleware.py`** — nova classe cobrindo Admin Vector:

```python
class MiddlewareAdminVectorTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.coop = Cooperativa.objects.create(nome="A", slug="a")
        self.vector = User.objects.create_user(
            username="v", email="v@t.test", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def _run(self, session):
        observado = {}

        def get_response(request):
            observado["v"] = obter_cooperativa_atual()
            return "ok"

        req = self.factory.get("/")
        req.user = self.vector
        req.session = session
        CooperativaScopeMiddleware(get_response)(req)
        return observado["v"]

    def test_sem_sessao_scope_none(self):
        self.assertIsNone(self._run({}))

    def test_com_sessao_scope_definido(self):
        self.assertEqual(self._run({"org_corrente_id": self.coop.id}), self.coop.id)
```

- [ ] **Step 6: Rodar — passa**

Run: `pytest apps/core/tests/test_tenancy.py apps/core/tests/test_middleware.py -v`
Expected: tudo verde.

- [ ] **Step 7: Se o stub temporário foi usado na Task 4, revisar `context_processors.py`** para usar `obter_organizacao_corrente` de verdade (já está no código do Step 1 da Task 4).

- [ ] **Step 8: Commit**

```bash
git add apps/core/tenancy.py apps/core/middleware.py apps/core/tests/
git commit -m "feat(tenancy): organização corrente por sessão para Admin Vector"
```

---

### Task 6: `apps/core/urls.py`, view `home`, view `selecionar_organizacao`, `LOGIN_REDIRECT_URL`

**Files:**
- Create: `apps/core/urls.py`
- Modify: `apps/core/views.py`
- Modify: `config/urls.py`, `config/settings/base.py`
- Create: `templates/core/home_consolidado.html`, `templates/core/home_organizacao.html`
- Create: `apps/core/tests/test_home.py`, `apps/core/tests/test_selecionar_organizacao.py`
- Modify: `apps/simulacao/tests/test_login.py`

**Interfaces:**
- Consumes: `obter_organizacao_corrente` (Task 5); `apps/core/services.py::metricas_da_organizacao` / `metricas_consolidadas` (Task 7 — nesta task usar import tardio e um teste que só checa roteamento por papel; os testes de números ricos ficam na Task 7). **Reordenar:** fazer Task 7 antes desta, ou implementar `home` já chamando `services` (a Task 7 fornece). O plano faz Task 7 → Task 6.
- Produces: `core:home` (`name='home'`, `path('', ...)`, `@login_required`), `core:selecionar_organizacao` (`name='selecionar_organizacao'`, `@login_required @requer_admin_vector @require_POST`). `LOGIN_REDIRECT_URL = '/'`.

- [ ] **Step 1: Teste de roteamento que falha** — `apps/core/tests/test_home.py`:

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario

User = get_user_model()


class HomeRoutingTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="Coop A", slug="coop-a")
        Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Oficial", is_oficial=True)
        self.membro = User.objects.create_user(
            username="m", email="m@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )
        self.vector = User.objects.create_user(
            username="v", email="v@t.test", password="x", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def test_home_exige_login(self):
        self.assertIn("/accounts/login/", self.client.get(reverse("core:home")).url)

    def test_membro_ve_home_da_organizacao(self):
        self.client.force_login(self.membro)
        r = self.client.get(reverse("core:home"))
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, "core/home_organizacao.html")
        self.assertContains(r, "Coop A")

    def test_admin_vector_sem_org_ve_consolidado(self):
        self.client.force_login(self.vector)
        r = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(r, "core/home_consolidado.html")

    def test_admin_vector_com_org_ve_home_da_organizacao(self):
        self.client.force_login(self.vector)
        self.client.post(reverse("core:selecionar_organizacao"), {"org_id": self.coop.id})
        r = self.client.get(reverse("core:home"))
        self.assertTemplateUsed(r, "core/home_organizacao.html")

    def test_login_redireciona_para_raiz(self):
        r = self.client.post(reverse("account_login"), {"login": "m", "password": "x"})
        self.assertEqual(r.url, "/")
```

`apps/core/tests/test_selecionar_organizacao.py`:
```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa

User = get_user_model()


class SelecionarOrganizacaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="A", slug="a")
        self.inativa = Cooperativa.objects.create(nome="Z", slug="z", ativo=False)
        self.vector = User.objects.create_user(
            username="v", email="v@t.test", password="x", papel=User.PAPEL_ADMIN_VECTOR,
        )
        self.membro = User.objects.create_user(
            username="m", email="m@t.test", password="x",
            papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.coop,
        )

    def test_grava_e_limpa_sessao(self):
        self.client.force_login(self.vector)
        self.client.post(reverse("core:selecionar_organizacao"), {"org_id": self.coop.id})
        self.assertEqual(self.client.session["org_corrente_id"], self.coop.id)
        self.client.post(reverse("core:selecionar_organizacao"), {"org_id": ""})
        self.assertNotIn("org_corrente_id", self.client.session)

    def test_ignora_id_inativo(self):
        self.client.force_login(self.vector)
        self.client.post(reverse("core:selecionar_organizacao"), {"org_id": self.inativa.id})
        self.assertNotIn("org_corrente_id", self.client.session)

    def test_membro_recebe_403(self):
        self.client.force_login(self.membro)
        self.assertEqual(
            self.client.post(reverse("core:selecionar_organizacao"), {"org_id": self.coop.id}).status_code,
            403,
        )

    def test_get_nao_permitido(self):
        self.client.force_login(self.vector)
        self.assertEqual(self.client.get(reverse("core:selecionar_organizacao")).status_code, 405)
```

- [ ] **Step 2: Rodar — falha** (`NoReverseMatch: 'core'`).

- [ ] **Step 3: Adicionar em `apps/core/views.py`**

```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.core import services
from apps.core.models import Cooperativa
from apps.core.permissions import e_admin_vector, requer_admin_vector
from apps.core.tenancy import obter_organizacao_corrente


@login_required
def home(request):
    org_id = obter_organizacao_corrente(request)
    if org_id is None and e_admin_vector(request.user):
        return render(request, 'core/home_consolidado.html', {
            'metricas': services.metricas_consolidadas(),
        })
    org = Cooperativa.objects.filter(id=org_id).first()
    return render(request, 'core/home_organizacao.html', {
        'org': org,
        'metricas': services.metricas_da_organizacao(org_id) if org_id else None,
    })


@login_required
@requer_admin_vector
@require_POST
def selecionar_organizacao(request):
    org_id = (request.POST.get('org_id') or '').strip()
    if org_id and Cooperativa.objects.filter(id=org_id, ativo=True).exists():
        request.session['org_corrente_id'] = int(org_id)
    else:
        request.session.pop('org_corrente_id', None)
    return redirect('core:home')
```

- [ ] **Step 4: Criar `apps/core/urls.py`**

```python
from django.urls import path

from apps.core import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('organizacao/selecionar/', views.selecionar_organizacao, name='selecionar_organizacao'),
]
```

- [ ] **Step 5: Registrar em `config/urls.py`** — adicionar como **última** entrada:

```python
    path('', include('apps.core.urls')),
```

- [ ] **Step 6: `config/settings/base.py`** — `LOGIN_REDIRECT_URL = '/'` (linha 93).

- [ ] **Step 7: Ajustar `apps/simulacao/tests/test_login.py`** — em `test_login_valido_redireciona`, trocar `self.assertEqual(response.url, '/simulacao/cenarios/')` por `self.assertEqual(response.url, '/')`.

- [ ] **Step 8: Escrever os dois templates de home** (ver Task 8 para o conteúdo rico; nesta task um esqueleto mínimo que renderiza para os testes de roteamento passarem):

`templates/core/home_consolidado.html`:
```html
{% extends "base.html" %}
{% block title %}Início — Transbordo{% endblock %}
{% block content %}
  <h1 class="mb-4 text-xl font-semibold text-base-content">Visão consolidada</h1>
  {% include "core/_home_consolidado_conteudo.html" %}
{% endblock %}
```
`templates/core/home_organizacao.html`:
```html
{% extends "base.html" %}
{% block title %}Início — Transbordo{% endblock %}
{% block content %}
  <h1 class="mb-4 text-xl font-semibold text-base-content">
    Olá, {{ request.user.first_name|default:request.user.email }}
    {% if org %}<span class="text-base-content/60">· {{ org.nome }}</span>{% endif %}
  </h1>
  {% include "core/_home_organizacao_conteudo.html" %}
{% endblock %}
```
Criar `templates/core/_home_consolidado_conteudo.html` e `templates/core/_home_organizacao_conteudo.html` com um `<p>` placeholder — a Task 8 os preenche.

- [ ] **Step 9: Rodar — passa**

Run: `pytest apps/core/tests/test_home.py apps/core/tests/test_selecionar_organizacao.py apps/simulacao/tests/test_login.py apps/core/tests/test_base_template.py -v`
Expected: tudo verde.

- [ ] **Step 10: Commit**

```bash
git add apps/core/urls.py apps/core/views.py config/urls.py config/settings/base.py templates/core apps/core/tests/test_home.py apps/core/tests/test_selecionar_organizacao.py apps/simulacao/tests/test_login.py
git commit -m "feat(core): rota / com home por papel + seletor de organização"
```

---

### Task 7: `apps/core/services.py` — métricas dos dashboards

**Files:**
- Create: `apps/core/services.py`
- Create: `apps/core/tests/test_core_services.py`

**Interfaces:**
- Produces:
  - `metricas_da_organizacao(cooperativa_id: int) -> dict` com chaves: `fabricas: int`, `armazens: int`, `cenarios: int`, `toneladas: float | None`, `sacas: float | None`, `frete: float | None`, `ultima_simulacao: datetime | None`.
  - `metricas_consolidadas() -> dict` com `{'totais': {organizacoes, fabricas, armazens, toneladas, sacas, frete}, 'por_organizacao': [ {id, nome, fabricas, armazens, toneladas, frete, ultima_simulacao}, ... ]}`.
- Regras: contagens no cenário `is_oficial=True` da organização; `toneladas`/`frete` = `Σ` de `MovimentacaoDiaria` do cenário oficial; `sacas = toneladas * KG_PER_TON / KG_PER_SACA`. Sem cenário oficial → contagens 0, resultados `None`. Sem execução `sucesso` → resultados de massa continuam vindo da `MovimentacaoDiaria` atual (pode estar vazia → `0.0`); `ultima_simulacao` = `None`. Usa `all_cooperativas` (cross-tenant deliberado).

- [ ] **Step 1: Testes que falham** — `apps/core/tests/test_core_services.py`:

```python
import datetime

from django.test import TestCase

from apps.core import services
from apps.core.models import Cooperativa
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, LogExecucao, MovimentacaoDiaria,
)


class MetricasOrganizacaoTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="A", slug="a")
        self.oficial = Cenario.all_cooperativas.create(
            cooperativa=self.coop, nome="Oficial", is_oficial=True,
        )
        self.f = Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.oficial, nome="F1",
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )
        self.a = Armazem.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.oficial, nome="A1",
            capacidade_estatica=1, capacidade_expedicao_diaria=1, estoque_inicial=0,
        )

    def test_contagens_e_massa(self):
        MovimentacaoDiaria.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.oficial, data=datetime.date(2025, 1, 1),
            armazem=self.a, fabrica=self.f, quantidade_ton=120.0, custo_total=3000.0,
        )
        LogExecucao.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.oficial, status=LogExecucao.Status.SUCESSO,
        )
        m = services.metricas_da_organizacao(self.coop.id)
        self.assertEqual((m["fabricas"], m["armazens"], m["cenarios"]), (1, 1, 1))
        self.assertEqual(m["toneladas"], 120.0)
        self.assertEqual(m["sacas"], 120.0 * 1000 / 60)
        self.assertEqual(m["frete"], 3000.0)
        self.assertIsNotNone(m["ultima_simulacao"])

    def test_sem_execucao_sucesso_ultima_simulacao_none(self):
        m = services.metricas_da_organizacao(self.coop.id)
        self.assertIsNone(m["ultima_simulacao"])
        self.assertEqual(m["toneladas"], 0.0)

    def test_organizacao_sem_cenario_oficial(self):
        coop2 = Cooperativa.objects.create(nome="B", slug="b")
        m = services.metricas_da_organizacao(coop2.id)
        self.assertEqual(m["fabricas"], 0)
        self.assertIsNone(m["toneladas"])


class MetricasConsolidadasTests(TestCase):
    def test_totais_somam_as_linhas(self):
        for nome in ("A", "B"):
            c = Cooperativa.objects.create(nome=nome, slug=nome.lower())
            cen = Cenario.all_cooperativas.create(cooperativa=c, nome="Of", is_oficial=True)
            f = Fabrica.all_cooperativas.create(
                cooperativa=c, cenario=cen, nome="F", capacidade_estatica=1,
                capacidade_esmagamento_diaria=1, capacidade_recebimento_diaria=1,
                limite_caminhoes=1, carga_media_caminhao=1, estoque_inicial=0,
            )
            a = Armazem.all_cooperativas.create(
                cooperativa=c, cenario=cen, nome="A", capacidade_estatica=1,
                capacidade_expedicao_diaria=1, estoque_inicial=0,
            )
            MovimentacaoDiaria.all_cooperativas.create(
                cooperativa=c, cenario=cen, data=datetime.date(2025, 1, 1),
                armazem=a, fabrica=f, quantidade_ton=10.0, custo_total=100.0,
            )
        cons = services.metricas_consolidadas()
        self.assertEqual(cons["totais"]["organizacoes"], 2)
        self.assertEqual(cons["totais"]["toneladas"], 20.0)
        self.assertEqual(cons["totais"]["frete"], 200.0)
        self.assertEqual(len(cons["por_organizacao"]), 2)
```

- [ ] **Step 2: Rodar — falha** (`ModuleNotFoundError: apps.core.services`).

- [ ] **Step 3: Implementar `apps/core/services.py`**

```python
"""Métricas agregadas para os dashboards da home (Fase 12).

Cross-tenant deliberado: usa os managers `all_cooperativas`, não `objects`
(que é fail-closed pelo contextvar de tenant). Não deve ser chamado de uma
view comum — só das telas de home, que resolvem o escopo explicitamente.
"""
from django.db.models import Sum

from apps.core.models import Cooperativa
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, LogExecucao, MovimentacaoDiaria,
)
from apps.simulacao.services import KG_PER_SACA, KG_PER_TON


def _cenario_oficial(cooperativa_id):
    return (
        Cenario.all_cooperativas
        .filter(cooperativa_id=cooperativa_id, is_oficial=True)
        .first()
    )


def _ultima_simulacao(cooperativa_id, oficial):
    qs = LogExecucao.all_cooperativas.filter(
        cooperativa_id=cooperativa_id, status=LogExecucao.Status.SUCESSO,
    )
    from django.db.models import Q
    qs = qs.filter(Q(cenario__isnull=True) | Q(cenario_id=getattr(oficial, 'id', None)))
    log = qs.order_by('-data_execucao').first()
    return log.data_execucao if log else None


def metricas_da_organizacao(cooperativa_id):
    oficial = _cenario_oficial(cooperativa_id)
    cenarios = Cenario.all_cooperativas.filter(cooperativa_id=cooperativa_id).count()
    if oficial is None:
        return {
            'fabricas': 0, 'armazens': 0, 'cenarios': cenarios,
            'toneladas': None, 'sacas': None, 'frete': None, 'ultima_simulacao': None,
        }
    agg = MovimentacaoDiaria.all_cooperativas.filter(cenario_id=oficial.id).aggregate(
        ton=Sum('quantidade_ton'), frete=Sum('custo_total'),
    )
    toneladas = agg['ton'] or 0.0
    frete = agg['frete'] or 0.0
    return {
        'fabricas': Fabrica.all_cooperativas.filter(cenario_id=oficial.id).count(),
        'armazens': Armazem.all_cooperativas.filter(cenario_id=oficial.id).count(),
        'cenarios': cenarios,
        'toneladas': toneladas,
        'sacas': toneladas * KG_PER_TON / KG_PER_SACA,
        'frete': frete,
        'ultima_simulacao': _ultima_simulacao(cooperativa_id, oficial),
    }


def metricas_consolidadas():
    por_organizacao = []
    tot = {'organizacoes': 0, 'fabricas': 0, 'armazens': 0, 'toneladas': 0.0,
           'sacas': 0.0, 'frete': 0.0}
    for coop in Cooperativa.objects.filter(ativo=True).order_by('nome'):
        m = metricas_da_organizacao(coop.id)
        tot['organizacoes'] += 1
        tot['fabricas'] += m['fabricas']
        tot['armazens'] += m['armazens']
        tot['toneladas'] += m['toneladas'] or 0.0
        tot['sacas'] += m['sacas'] or 0.0
        tot['frete'] += m['frete'] or 0.0
        por_organizacao.append({
            'id': coop.id, 'nome': coop.nome,
            'fabricas': m['fabricas'], 'armazens': m['armazens'],
            'toneladas': m['toneladas'], 'frete': m['frete'],
            'ultima_simulacao': m['ultima_simulacao'],
        })
    return {'totais': tot, 'por_organizacao': por_organizacao}
```

- [ ] **Step 4: Rodar — passa**

Run: `pytest apps/core/tests/test_core_services.py -v`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add apps/core/services.py apps/core/tests/test_core_services.py
git commit -m "feat(core): services de métricas para os dashboards"
```

> **Nota de ordem:** rodar Task 7 **antes** de Task 6 Step 3 (a view `home` importa `apps.core.services`). Se o subagent-driver executar 6 antes de 7, o import quebra — nesse caso adicione `import apps.core.services` só depois da Task 7 e re-rode `pytest apps/core/tests/test_home.py`.

---

### Task 8: Conteúdo dos dashboards (consolidado + organização)

**Files:**
- Create: `apps/core/tables.py`
- Modify: `templates/core/_home_consolidado_conteudo.html`, `templates/core/_home_organizacao_conteudo.html`
- Modify: `apps/core/views.py`
- Modify: `apps/core/tests/test_home.py`

**Interfaces:**
- Consumes: `metricas` do contexto (Task 7). `moeda` / `volume` filtros (`{% load simulacao_filters %}`).
- Produces: `OrganizacoesTable(tables.Table)` em `apps/core/tables.py` — colunas Organização, Fábricas, Armazéns, Toneladas, Frete (R$), Última simulação; cada linha com um `<form method="post" action="{% url 'core:selecionar_organizacao' %}">` (botão que faz `POST org_id`). `home` passa `tabela = OrganizacoesTable(metricas['por_organizacao'])` ao consolidado.

- [ ] **Step 1: Teste que falha** — acrescentar a `test_home.py`:

```python
    def test_consolidado_mostra_totais_e_linha_por_org(self):
        from apps.simulacao.models import Fabrica
        Fabrica.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.coop.simulacao_cenarios.get(is_oficial=True),
            nome="F1", capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1, carga_media_caminhao=1,
            estoque_inicial=0,
        )
        self.client.force_login(self.vector)
        r = self.client.get(reverse("core:home"))
        self.assertContains(r, "Coop A")
        self.assertContains(r, "Organizações ativas")

    def test_home_org_sem_simulacao_renderiza_travessao(self):
        self.client.force_login(self.membro)
        r = self.client.get(reverse("core:home"))
        self.assertContains(r, "—")  # métricas de massa ausentes
```
(O `related_name` de `Cenario.cooperativa` é `simulacao_cenarios` — ver `CooperativaScopedModel.cooperativa` `related_name='%(app_label)s_%(class)ss'`.)

- [ ] **Step 2: Rodar — falha.**

- [ ] **Step 3: `apps/core/tables.py`**

```python
import django_tables2 as tables
from django.utils.html import format_html

from apps.simulacao.templatetags.simulacao_filters import moeda, volume


class OrganizacoesTable(tables.Table):
    nome = tables.Column(verbose_name="Organização")
    fabricas = tables.Column(verbose_name="Fábricas")
    armazens = tables.Column(verbose_name="Armazéns")
    toneladas = tables.Column(verbose_name="Toneladas")
    frete = tables.Column(verbose_name="Frete (R$)")
    ultima_simulacao = tables.Column(verbose_name="Última simulação")

    class Meta:
        template_name = "django_tables2/tailwind.html"
        attrs = {"class": "table table-sm"}
        orderable = False

    def render_toneladas(self, value):
        return volume(value) if value is not None else "—"

    def render_frete(self, value):
        return moeda(value) if value is not None else "—"

    def render_ultima_simulacao(self, value):
        return value.strftime("%d/%m/%Y %H:%M") if value else "nunca"

    def render_nome(self, value, record):
        return format_html(
            '<form method="post" action="/organizacao/selecionar/" class="inline">'
            '<input type="hidden" name="org_id" value="{}">'
            '<button type="submit" class="text-accent hover:underline">{}</button>'
            '</form>',
            record["id"], value,
        )
```
(Nota: o CSRF do `<form>` injetado por `format_html` — o `hx-headers` global não cobre POST de form nativo. Adicionar `{% csrf_token %}` não é possível dentro de `format_html`. Alternativa adotada: a tabela renderiza o link e o `POST` real é feito por um `<form>` externo por linha no template — ver Step 4. Portanto `render_nome` devolve só texto e o template envolve.)

**Correção de `render_nome`:** devolver `value` puro; o `<form>` fica no template (Step 4) usando `{% csrf_token %}`. Remover `render_nome` e `format_html`/imports não usados.

- [ ] **Step 4: `templates/core/_home_consolidado_conteudo.html`**

```html
{% load simulacao_filters %}
<c-resumo-numerico class="mb-6">
  <div class="stat"><div class="stat-title">Organizações ativas</div><div class="stat-value text-base-content">{{ metricas.totais.organizacoes }}</div></div>
  <div class="stat"><div class="stat-title">Fábricas</div><div class="stat-value text-base-content">{{ metricas.totais.fabricas }}</div></div>
  <div class="stat"><div class="stat-title">Armazéns</div><div class="stat-value text-base-content">{{ metricas.totais.armazens }}</div></div>
  <div class="stat"><div class="stat-title">Toneladas</div><div class="stat-value text-base-content">{{ metricas.totais.toneladas|volume }}</div></div>
  <div class="stat"><div class="stat-title">Sacas</div><div class="stat-value text-base-content">{{ metricas.totais.sacas|volume }}</div></div>
  <div class="stat"><div class="stat-title">Frete</div><div class="stat-value text-base-content">{{ metricas.totais.frete|moeda }}</div></div>
</c-resumo-numerico>

<c-card>
  <table class="table table-sm">
    <thead><tr>
      <th>Organização</th><th>Fábricas</th><th>Armazéns</th><th>Toneladas</th><th>Frete (R$)</th><th>Última simulação</th>
    </tr></thead>
    <tbody>
      {% for linha in metricas.por_organizacao %}
        <tr class="hover:bg-base-200">
          <td>
            <form method="post" action="{% url 'core:selecionar_organizacao' %}" class="inline">
              {% csrf_token %}
              <input type="hidden" name="org_id" value="{{ linha.id }}">
              <button type="submit" class="text-accent hover:underline">{{ linha.nome }}</button>
            </form>
          </td>
          <td>{{ linha.fabricas }}</td>
          <td>{{ linha.armazens }}</td>
          <td>{% if linha.toneladas is not None %}{{ linha.toneladas|volume }}{% else %}—{% endif %}</td>
          <td>{% if linha.frete is not None %}{{ linha.frete|moeda }}{% else %}—{% endif %}</td>
          <td>{% if linha.ultima_simulacao %}{{ linha.ultima_simulacao|date:"d/m/Y H:i" }}{% else %}nunca{% endif %}</td>
        </tr>
      {% empty %}
        <tr><td colspan="6" class="py-3 text-sm text-base-content/50">Nenhuma organização ativa.</td></tr>
      {% endfor %}
    </tbody>
  </table>
</c-card>
```
(Decisão: a tabela por organização usa `<table>` direto, não `django-tables2` — precisa de um `<form>`+`{% csrf_token %}` por linha, que não cabe num `render_` de coluna. `apps/core/tables.py` fica **fora** do escopo; apagar o arquivo criado no Step 3. django-tables2 é usado nas listagens de gestão, Onda 3, onde não há esse atrito.)

- [ ] **Step 5: `templates/core/_home_organizacao_conteudo.html`**

```html
{% load simulacao_filters %}
{% if metricas %}
  <c-resumo-numerico class="mb-6">
    <div class="stat"><div class="stat-title">Fábricas</div><div class="stat-value text-base-content">{{ metricas.fabricas }}</div></div>
    <div class="stat"><div class="stat-title">Armazéns</div><div class="stat-value text-base-content">{{ metricas.armazens }}</div></div>
    <div class="stat"><div class="stat-title">Cenários</div><div class="stat-value text-base-content">{{ metricas.cenarios }}</div></div>
    <div class="stat">
      <div class="stat-title">Última simulação</div>
      <div class="stat-value text-base-content">{% if metricas.ultima_simulacao %}{{ metricas.ultima_simulacao|date:"d/m/Y" }}{% else %}—{% endif %}</div>
    </div>
  </c-resumo-numerico>

  <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
    <c-lista-cartao titulo="Atalhos">
      <ul class="divide-y divide-base-300">
        <li class="px-4 py-2.5"><a href="{% url 'simulacao:cenarios_list' %}" class="flex items-center gap-2 text-sm text-base-content hover:text-accent hover:underline"><c-icon name="git-branch" /> Cenários</a></li>
        <li class="px-4 py-2.5"><a href="{% url 'simulacao:carga' %}" class="flex items-center gap-2 text-sm text-base-content hover:text-accent hover:underline"><c-icon name="upload" /> Carga de Dados</a></li>
      </ul>
    </c-lista-cartao>

    <c-lista-cartao titulo="Cenários recentes">
      <ul class="divide-y divide-base-300">
        {% for c in cenarios_recentes %}
          <li class="px-4 py-2.5">
            <a href="{% url 'simulacao:fabricas_grid' cenario_id=c.id %}" class="text-sm text-base-content hover:text-accent hover:underline">
              {{ c.nome }}{% if c.is_oficial %} <span class="badge badge-sm badge-primary">Oficial</span>{% endif %}
            </a>
          </li>
        {% empty %}
          <li class="px-4 py-6 text-center text-sm text-base-content/50">Nenhum cenário ainda.</li>
        {% endfor %}
      </ul>
    </c-lista-cartao>
  </div>
  {# TODO Fase 13: dashboard detalhado por papel (usuário de fábrica / de armazém). #}
{% else %}
  <c-card><p class="text-sm text-base-content/60">Selecione uma organização para ver os indicadores.</p></c-card>
{% endif %}
```

- [ ] **Step 6: `home` passa `cenarios_recentes`** — em `apps/core/views.py`, no ramo da organização:

```python
    cenarios_recentes = []
    if org_id:
        from apps.simulacao.models import Cenario
        cenarios_recentes = list(
            Cenario.all_cooperativas.filter(cooperativa_id=org_id).order_by('-is_oficial', '-data_criacao')[:8]
        )
    return render(request, 'core/home_organizacao.html', {
        'org': org,
        'metricas': services.metricas_da_organizacao(org_id) if org_id else None,
        'cenarios_recentes': cenarios_recentes,
    })
```
Apagar `apps/core/tables.py` (não usado). Remover o teste `test_consolidado...` a referência a tables se houver.

- [ ] **Step 7: Rodar**

Run: `pytest apps/core/tests/test_home.py -v && python manage.py check`
Expected: verde.

- [ ] **Step 8: Commit**

```bash
git add apps/core/views.py templates/core apps/core/tests/test_home.py
git commit -m "feat(core): conteúdo dos dashboards consolidado e da organização"
```

---

### Task 9: Ajustar `apps/core/permissions.py` e as views de `apps/simulacao` para o super-membro Admin Vector

**Files:**
- Modify: `apps/core/permissions.py`
- Modify: `apps/simulacao/views.py`
- Modify: `apps/core/tests/test_permissions.py`
- Modify: `apps/simulacao/tests/test_views_cenarios.py`

**Interfaces:**
- Consumes: `obter_organizacao_corrente`, `cooperativa_id_do_request` (Task 5).
- Produces:
  - `requer_membro_organizacao` — decorator ciente de `request`: passa se membro **ou** (Admin Vector **e** `obter_organizacao_corrente(request) is not None`); senão `PermissionDenied`.
  - `pode_editar_fabricas(user, request=None)` / `pode_editar_armazens(user, request=None)` — mantêm a regra atual **e** `True` para `e_admin_vector(user) and obter_organizacao_corrente(request)`.
  - `requer_edicao_fabricas` / `requer_edicao_armazens` — repassam `request` ao predicado.
- Substituições em `apps/simulacao/views.py`: `@papel_required(*MEMBROS_COOPERATIVA)` → `@requer_membro_organizacao` (9 views); `request.user.cooperativa_id` cru → `cooperativa_id_do_request(request)` em `cenarios_list`, `carga_upload`, `carga_preview`; `request.user.cooperativa` (objeto) → `Cooperativa.objects.get(id=cooperativa_id_do_request(request))` em `carga_preview` (`aplicar(..., cooperativa=...)`).

- [ ] **Step 1: Testes que falham** — em `test_permissions.py`, nova classe:

```python
class SuperMembroAdminVectorTests(TestCase):
    def setUp(self):
        self.rf = RequestFactory()
        self.coop = Cooperativa.objects.create(nome="A", slug="a")
        self.vector = User.objects.create_user(
            username="v2", email="v2@t.test", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def _req(self, session):
        r = self.rf.get("/")
        r.user = self.vector
        r.session = session
        return r

    def test_requer_membro_organizacao_com_org(self):
        @p.requer_membro_organizacao
        def view(request):
            return HttpResponse("ok")
        self.assertEqual(view(self._req({"org_corrente_id": self.coop.id})).status_code, 200)

    def test_requer_membro_organizacao_sem_org(self):
        @p.requer_membro_organizacao
        def view(request):
            return HttpResponse("ok")
        with self.assertRaises(PermissionDenied):
            view(self._req({}))

    def test_pode_editar_fabricas_admin_vector_com_org(self):
        self.assertTrue(p.pode_editar_fabricas(self.vector, self._req({"org_corrente_id": self.coop.id})))
        self.assertFalse(p.pode_editar_fabricas(self.vector, self._req({})))
```
Em `test_permissions.py::test_predicados`, os predicados `pode_editar_fabricas`/`pode_editar_armazens` continuam chamados com 1 arg — a assinatura nova tem `request=None` default, então `fn(user)` segue válido. Nenhuma mudança nesse teste.

- [ ] **Step 2: Rodar — falha.**

- [ ] **Step 3: Reescrever `apps/core/permissions.py`** (trechos):

```python
def pode_editar_fabricas(user, request=None):
    if e_admin_cooperativa(user) or e_usuario_fabrica(user):
        return True
    return bool(e_admin_vector(user) and _org_do_request(request))


def pode_editar_armazens(user, request=None):
    if e_admin_cooperativa(user) or e_usuario_armazem(user):
        return True
    return bool(e_admin_vector(user) and _org_do_request(request))


def _org_do_request(request):
    if request is None:
        return None
    from apps.core.tenancy import obter_organizacao_corrente
    return obter_organizacao_corrente(request)


def _predicado_required(predicado):
    def decorator(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            if not predicado(request.user, request):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return _wrapped
    return decorator


def requer_membro_organizacao(view):
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        user = request.user
        if papel_de(user) in MEMBROS_COOPERATIVA:
            return view(request, *args, **kwargs)
        if e_admin_vector(user) and _org_do_request(request) is not None:
            return view(request, *args, **kwargs)
        raise PermissionDenied('Selecione uma organização.')
    return _wrapped


requer_edicao_fabricas = _predicado_required(pode_editar_fabricas)
requer_edicao_armazens = _predicado_required(pode_editar_armazens)
requer_admin_vector = _predicado_required(lambda user, request=None: e_admin_vector(user))
```
Cuidado: `_predicado_required` agora chama `predicado(user, request)`. `requer_admin_vector` passa a usar um lambda de 2 args. `test_requer_admin_vector_decorator` no arquivo existente segue válido (ele chama a view com um request real).

- [ ] **Step 4: `apps/simulacao/views.py`**

- Import: trocar `from apps.core.permissions import (MEMBROS_COOPERATIVA, papel_required, requer_edicao_armazens, requer_edicao_fabricas)` por `from apps.core.permissions import (requer_edicao_armazens, requer_edicao_fabricas, requer_membro_organizacao)` e `from apps.core.models import Cooperativa`, `from apps.core.tenancy import cooperativa_id_do_request`.
- Trocar as 9 ocorrências de `@papel_required(*MEMBROS_COOPERATIVA)` por `@requer_membro_organizacao` (views: `cenarios_list`, `rotas_grid`, `previsoes_grid`, `safras_grid`, `carga_template`, `carga_upload`, `carga_preview`, `simulacao_tab`, `simulacao_executar`, `simulacao_status`, `assistente_tab`, `assistente_enviar`, `assistente_nova`). `fabricas_grid`/`armazens_grid` já usam `@requer_edicao_fabricas`/`@requer_edicao_armazens` — só herdam a nova assinatura.
- `cenarios_list`: `cooperativa_id = request.user.cooperativa_id` → `cooperativa_id = cooperativa_id_do_request(request)`.
- `carga_upload`: `cooperativa_id = request.user.cooperativa_id` → `cooperativa_id = cooperativa_id_do_request(request)`.
- `carga_preview`: `cooperativa_id = request.user.cooperativa_id` → idem; e `cooperativa=request.user.cooperativa` no `aplicar(...)` → `cooperativa=Cooperativa.objects.get(id=cooperativa_id)`.

- [ ] **Step 5: Teste de integração** — em `test_views_cenarios.py`, nova classe:

```python
class CenariosAdminVectorComOrgTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome="Coop A", slug="coop-a")
        Cenario.all_cooperativas.create(cooperativa=self.coop, nome="Oficial", is_oficial=True)
        self.vector = User.objects.create_user(
            username="v", email="v@t.test", password="x", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def test_com_org_selecionada_lista_cenarios(self):
        self.client.force_login(self.vector)
        s = self.client.session
        s["org_corrente_id"] = self.coop.id
        s.save()
        r = self.client.get(reverse("simulacao:cenarios_list"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Oficial")

    def test_sem_org_selecionada_403(self):
        self.client.force_login(self.vector)
        self.assertEqual(self.client.get(reverse("simulacao:cenarios_list")).status_code, 403)
```
(`test_admin_vector_recebe_403` existente continua válido — sem org na sessão.)

- [ ] **Step 6: Rodar as suítes afetadas**

Run: `pytest apps/core/tests/test_permissions.py apps/simulacao/tests/ -v`
Expected: verde.

- [ ] **Step 7: Commit**

```bash
git add apps/core/permissions.py apps/simulacao/views.py apps/core/tests/test_permissions.py apps/simulacao/tests/test_views_cenarios.py
git commit -m "feat(perms): Admin Vector com organização age como super-membro"
```

---

### Task 10: Gate da Onda 1+2 — smoke de render + suíte completa

**Files:**
- Create: `apps/core/tests/test_render_smoke.py`

**Interfaces:**
- Consumes: todas as rotas HTMX existentes + `core:home`.
- Produces: um teste parametrizado que faz `GET` em cada tela com um usuário de cada papel e exige `200` (ou `302` para login quando esperado), sem `TemplateDoesNotExist` / `NoReverseMatch`.

- [ ] **Step 1: Escrever `apps/core/tests/test_render_smoke.py`**

```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario

User = get_user_model()

ROTAS_MEMBRO = [
    ("core:home", {}),
    ("simulacao:cenarios_list", {}),
    ("simulacao:carga", {}),
    ("gestao:conta", {}),
]
ROTAS_CENARIO = [
    "simulacao:fabricas_grid", "simulacao:armazens_grid", "simulacao:rotas_grid",
    "simulacao:previsoes_grid", "simulacao:safras_grid", "simulacao:simulacao_tab",
    "simulacao:assistente_tab",
]


class RenderSmokeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coop = Cooperativa.objects.create(nome="Coop A", slug="coop-a")
        cls.cenario = Cenario.all_cooperativas.create(
            cooperativa=cls.coop, nome="Oficial", is_oficial=True,
        )
        cls.admin_coop = User.objects.create_user(
            username="ac", email="ac@t.test", password="x",
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=cls.coop,
        )
        cls.vector = User.objects.create_user(
            username="v", email="v@t.test", password="x", papel=User.PAPEL_ADMIN_VECTOR,
        )

    def test_telas_de_membro(self):
        self.client.force_login(self.admin_coop)
        for nome, kw in ROTAS_MEMBRO:
            r = self.client.get(reverse(nome, kwargs=kw))
            self.assertEqual(r.status_code, 200, nome)

    def test_abas_do_cenario(self):
        self.client.force_login(self.admin_coop)
        for nome in ROTAS_CENARIO:
            r = self.client.get(reverse(nome, kwargs={"cenario_id": self.cenario.id}))
            self.assertEqual(r.status_code, 200, nome)

    def test_home_consolidado_admin_vector(self):
        self.client.force_login(self.vector)
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)

    def test_gestao_admin_vector(self):
        self.client.force_login(self.vector)
        for nome in ("gestao:cooperativas", "gestao:usuarios", "gestao:conta"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200, nome)

    def test_auth_screens_anonimo(self):
        for nome in ("account_login", "account_reset_password"):
            self.assertEqual(self.client.get(reverse(nome)).status_code, 200, nome)
```

- [ ] **Step 2: Rodar o smoke**

Run: `pytest apps/core/tests/test_render_smoke.py -v`
Expected: verde. Se algum template quebrar por classe/token do tema antigo, corrigir o template pontualmente (as telas de conteúdo ainda estão pré-migração, mas devem **renderizar** — só herdam cores).

- [ ] **Step 3: Suíte completa + checks**

Run: `python manage.py check && python manage.py makemigrations --check --dry-run && pytest`
Expected: check limpo, sem migrations, **todos verdes** (309 originais − ajustes + novos ≈ 330+).

- [ ] **Step 4: Commit**

```bash
git add apps/core/tests/test_render_smoke.py
git commit -m "test: smoke de render de todas as telas por papel (Fase 12)"
```

---

# Onda 3 — Gestão

Migrar listagens de gestão para django-tables2 + django-filter, forms para crispy dentro de `<c-card>`, breadcrumb, terminologia "Organização". Aplicar **REGRA-SUBST** em todos os templates tocados.

### Task 11: `gestao/base_gestao.html` + breadcrumb + terminologia

**Files:**
- Modify: `templates/gestao/base_gestao.html`
- Modify: `templates/gestao/cooperativas.html`, `templates/gestao/usuarios.html`, `templates/gestao/minha_cooperativa.html`, `templates/gestao/conta.html`, `templates/gestao/cooperativa_form.html`, `templates/gestao/usuario_form.html`
- Modify: `apps/gestao/tests/test_menu.py`

- [ ] **Step 1: `base_gestao.html`**

```html
{% extends "base.html" %}
{% block content %}
  {% block gestao_content %}{% endblock %}
{% endblock %}
{% block breadcrumb %}{% block gestao_breadcrumb %}{% endblock %}{% endblock %}
```
(Largura agora vem do `<main class="max-w-7xl">` da `base.html`; remover o `max-w-4xl` interno.)

- [ ] **Step 2: Aplicar REGRA-SUBST + breadcrumb + "Organização" nos 6 templates de gestão**

Para cada um: trocar `text-[var(--cor-primaria)]` de títulos por `text-base-content`; "Cooperativa(s)" → "Organização/Organizações" no texto visível (não em `{% url %}` nem em nomes de variável); adicionar `{% block gestao_breadcrumb %}<c-breadcrumb><span>Organizações</span></c-breadcrumb>{% endblock %}` (ajustando o último item por tela). Ex. `cooperativas.html`:

```html
{% extends "gestao/base_gestao.html" %}
{% block title %}Organizações — Transbordo{% endblock %}
{% block gestao_breadcrumb %}<c-breadcrumb><span class="text-base-content/60">Organizações</span></c-breadcrumb>{% endblock %}
{% block gestao_content %}
  <div class="mb-4 flex items-center justify-between">
    <h1 class="text-lg font-semibold text-base-content">Organizações</h1>
    <a href="{% url 'gestao:cooperativa_nova' %}" class="btn btn-primary btn-sm">Nova</a>
  </div>
  {% include "gestao/_cooperativas_content.html" %}
{% endblock %}
```

- [ ] **Step 3: `test_menu.py`** — cobrir `org` e `organizacoes_disponiveis` no contexto:

```python
    def test_contexto_menu_admin_vector_tem_organizacoes(self):
        self._login(User.PAPEL_ADMIN_VECTOR, coop=False)
        resp = self.client.get(reverse("core:home"))
        self.assertIn("organizacoes_disponiveis", resp.context)
        self.assertIsNotNone(resp.context["organizacoes_disponiveis"])
        self.assertIsNone(resp.context["org"])

    def test_contexto_menu_membro_tem_org(self):
        self._login(User.PAPEL_ADMIN_COOPERATIVA)
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.context["org"], self.coop)
        self.assertIsNone(resp.context["organizacoes_disponiveis"])
```
Ajustar `test_admin_vector_ve_cooperativas_nao_ve_simulacao` e `test_admin_cooperativa_ve_todos_os_seus_links` se dependerem de strings antigas ("Cooperativas" no dropdown virou "Organizações").

- [ ] **Step 4: Rodar**

Run: `pytest apps/gestao/tests/ apps/core/tests/test_render_smoke.py -v`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add templates/gestao apps/gestao/tests/test_menu.py
git commit -m "feat(gestao): base + breadcrumb + terminologia Organização"
```

---

### Task 12: Listagens de gestão em django-tables2 + django-filter

**Files:**
- Create: `apps/gestao/tables.py`, `apps/gestao/filters.py`
- Modify: `apps/gestao/views.py`
- Modify: `templates/gestao/_cooperativas_content.html`, `templates/gestao/_usuarios_content.html`
- Modify: `apps/gestao/tests/test_cooperativas.py`, `apps/gestao/tests/test_usuarios.py`

**Interfaces:**
- Produces:
  - `CooperativaTable(tables.Table)` — colunas `nome` (linkify p/ `gestao:cooperativa_editar`), `slug`, `ativo`; `Meta.attrs = {"class": "table table-sm"}`, `template_name="django_tables2/tailwind.html"`.
  - `UsuarioTable` — colunas `username` (linkify p/ `gestao:usuario_editar`), `email`, `papel`, `cooperativa`, `is_active`.
  - `CooperativaFilter(django_filters.FilterSet)` — `nome` (icontains), `ativo`.
  - `UsuarioFilter` — `q` (username/email icontains via `method`), `papel`.
  - views `cooperativas` / `usuarios` montam `Table` + `Filter` e passam `tabela` no contexto; o template renderiza `{% render_table tabela %}`.

- [ ] **Step 1: Testes que falham** — em `test_cooperativas.py`:

```python
    def test_listagem_filtra_por_nome(self):
        Cooperativa.objects.create(nome="Zeta", slug="zeta")
        self.client.force_login(self.admin_vector)
        r = self.client.get(reverse("gestao:cooperativas"), {"nome": "Zeta"})
        self.assertContains(r, "Zeta")
        self.assertNotContains(r, ">Coop A<")

    def test_listagem_usa_tabela_daisyui(self):
        self.client.force_login(self.admin_vector)
        r = self.client.get(reverse("gestao:cooperativas"))
        self.assertContains(r, "table table-sm")
```
(Adaptar os nomes de fixture aos que já existem em `test_cooperativas.py`.)

- [ ] **Step 2: Rodar — falha.**

- [ ] **Step 3: `apps/gestao/tables.py`**

```python
import django_tables2 as tables

from apps.core.models import Cooperativa, User


class CooperativaTable(tables.Table):
    nome = tables.Column(linkify=("gestao:cooperativa_editar", {"cooperativa_id": tables.A("pk")}))

    class Meta:
        model = Cooperativa
        fields = ("nome", "slug", "ativo")
        attrs = {"class": "table table-sm"}
        template_name = "django_tables2/tailwind.html"
        empty_text = "Nenhuma organização."


class UsuarioTable(tables.Table):
    username = tables.Column(linkify=("gestao:usuario_editar", {"usuario_id": tables.A("pk")}))

    class Meta:
        model = User
        fields = ("username", "email", "papel", "cooperativa", "is_active")
        attrs = {"class": "table table-sm"}
        template_name = "django_tables2/tailwind.html"
        empty_text = "Nenhum usuário."
```

- [ ] **Step 4: `apps/gestao/filters.py`**

```python
import django_filters
from django.db.models import Q

from apps.core.models import Cooperativa, User


class CooperativaFilter(django_filters.FilterSet):
    nome = django_filters.CharFilter(lookup_expr="icontains")

    class Meta:
        model = Cooperativa
        fields = ["nome", "ativo"]


class UsuarioFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(method="busca", label="Busca")

    def busca(self, queryset, name, value):
        return queryset.filter(Q(username__icontains=value) | Q(email__icontains=value))

    class Meta:
        model = User
        fields = ["papel"]
```

- [ ] **Step 5: `apps/gestao/views.py`** — `cooperativas` e `usuarios`:

```python
from apps.gestao.filters import CooperativaFilter, UsuarioFilter
from apps.gestao.tables import CooperativaTable, UsuarioTable
import django_tables2 as tables2


@login_required
@requer_admin_vector
def cooperativas(request):
    f = CooperativaFilter(request.GET, queryset=Cooperativa.objects.all().order_by("nome"))
    tabela = CooperativaTable(f.qs)
    tables2.RequestConfig(request, paginate={"per_page": 25}).configure(tabela)
    ctx = {"tabela": tabela, "filtro": f}
    template = "gestao/_cooperativas_content.html" if request.htmx else "gestao/cooperativas.html"
    return render(request, template, ctx)


@login_required
def usuarios(request):
    _requer_gestor(request)
    f = UsuarioFilter(request.GET, queryset=usuarios_visiveis(request.user))
    tabela = UsuarioTable(f.qs)
    tables2.RequestConfig(request, paginate={"per_page": 25}).configure(tabela)
    ctx = {"tabela": tabela, "filtro": f}
    template = "gestao/_usuarios_content.html" if request.htmx else "gestao/usuarios.html"
    return render(request, ctx if False else template, ctx)
```
(corrigir o `render` do `usuarios` para `render(request, template, ctx)`.)

- [ ] **Step 6: `_cooperativas_content.html` / `_usuarios_content.html`**

```html
{% load render_table from django_tables2 %}
<form method="get" class="mb-3 flex flex-wrap items-end gap-2">
  {{ filtro.form.as_div }}
  <button type="submit" class="btn btn-outline btn-sm">Filtrar</button>
</form>
{% render_table tabela %}
```

- [ ] **Step 7: Rodar**

Run: `pytest apps/gestao/tests/ -v`
Expected: verde (ajustar asserts antigos que checavam `<table class="table w-full">` ou colunas manuais).

- [ ] **Step 8: Commit**

```bash
git add apps/gestao/tables.py apps/gestao/filters.py apps/gestao/views.py templates/gestao apps/gestao/tests/
git commit -m "feat(gestao): listagens em django-tables2 + django-filter"
```

---

### Task 13: Forms de gestão em crispy dentro de `<c-card>`

**Files:**
- Modify: `apps/gestao/forms.py`
- Modify: `templates/gestao/cooperativa_form.html`, `templates/gestao/usuario_form.html`, `templates/gestao/minha_cooperativa.html`, `templates/gestao/conta.html`

**Interfaces:**
- Produces: cada `Form` de gestão ganha `helper = FormHelper()` com `helper.form_tag = False` (o `<form>` fica no template, com `{% csrf_token %}` e os botões). Templates usam `{% load crispy_forms_tags %}` + `{% crispy form %}` dentro de `<c-card>`.

- [ ] **Step 1: Teste que falha** — `apps/gestao/tests/test_cooperativas.py`:

```python
    def test_form_renderiza_crispy_em_card(self):
        self.client.force_login(self.admin_vector)
        r = self.client.get(reverse("gestao:cooperativa_nova"))
        self.assertContains(r, "rounded-lg border border-base-300")  # <c-card>
        self.assertContains(r, 'id="id_nome"')
```

- [ ] **Step 2: `apps/gestao/forms.py`** — adicionar helper a `CooperativaForm`, `MinhaCooperativaForm`, `UsuarioForm`:

```python
from crispy_forms.helper import FormHelper


class _HelperMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.disable_csrf = True
```
Fazer `CooperativaForm(_HelperMixin, forms.ModelForm)` etc. (`UsuarioForm` já tem `__init__` com `gestor=` — encadear via `super().__init__`).

- [ ] **Step 3: `cooperativa_form.html`**

```html
{% extends "gestao/base_gestao.html" %}
{% load crispy_forms_tags %}
{% block title %}{{ titulo }} — Transbordo{% endblock %}
{% block gestao_breadcrumb %}<c-breadcrumb><a href="{% url 'gestao:cooperativas' %}" class="text-base-content/60 hover:text-accent">Organizações</a><span class="text-base-content/60">{{ titulo }}</span></c-breadcrumb>{% endblock %}
{% block gestao_content %}
  <h1 class="mb-4 text-lg font-semibold text-base-content">{{ titulo }}</h1>
  <c-card class="max-w-xl">
    <form method="post">
      {% csrf_token %}
      {% crispy form %}
      <div class="mt-4 flex gap-2">
        <button type="submit" class="btn btn-primary btn-sm">Salvar</button>
        <a href="{% url 'gestao:cooperativas' %}" class="btn btn-ghost btn-sm">Cancelar</a>
      </div>
    </form>
  </c-card>
{% endblock %}
```
Mesma estrutura para `usuario_form.html` (breadcrumb → `gestao:usuarios`), `minha_cooperativa.html` (breadcrumb "Minha organização", sem link pai) e `conta.html` (sem form crispy — é só exibição + links allauth; aplicar REGRA-SUBST e `<c-card>`).

- [ ] **Step 4: Rodar**

Run: `pytest apps/gestao/tests/ apps/core/tests/test_render_smoke.py -v`
Expected: verde.

- [ ] **Step 5: Commit**

```bash
git add apps/gestao/forms.py templates/gestao
git commit -m "feat(gestao): forms crispy em <c-card> + breadcrumb"
```

---

# Onda 4 — Cenários e grids

### Task 14: `simulacao/cenarios` — breadcrumb, form crispy, lista em `<c-lista-cartao>`

**Files:**
- Modify: `templates/simulacao/cenarios.html`, `templates/simulacao/_cenarios_content.html`
- Modify: `apps/simulacao/tests/test_views_cenarios.py`

- [ ] **Step 1: `_cenarios_content.html`** (aplicar REGRA-SUBST; `<c-card>` para o form, `<c-lista-cartao>` para a lista):

```html
<c-breadcrumb><span class="text-base-content/60">Cenários</span></c-breadcrumb>

<h1 class="mb-4 text-xl font-semibold text-base-content">Cenários</h1>

<c-card class="mb-6">
  <h2 class="mb-3 font-medium text-base-content">Criar novo cenário de simulação</h2>
  <form method="post" action="{% url 'simulacao:cenarios_list' %}" class="flex flex-wrap items-end gap-3">
    {% csrf_token %}
    <div>
      <label for="id_nome">Nome do novo cenário</label>
      <input type="text" id="id_nome" name="nome" required>
    </div>
    <div>
      <label for="id_origem_id">Clonar dados de qual cenário?</label>
      <select id="id_origem_id" name="origem_id">
        {% for cenario in cenarios %}<option value="{{ cenario.id }}">{{ cenario.nome }}</option>{% endfor %}
      </select>
    </div>
    <button type="submit" class="btn btn-primary">Criar cenário</button>
  </form>
</c-card>

<c-lista-cartao titulo="Escolher cenário para editar">
  <ul class="divide-y divide-base-300">
    {% for cenario in cenarios %}
      <li class="px-4 py-2.5">
        <a href="{% url 'simulacao:fabricas_grid' cenario_id=cenario.id %}" class="text-sm text-base-content hover:text-accent hover:underline">
          {{ cenario.nome }}
          {% if cenario.is_oficial %}<span class="badge badge-sm badge-primary">Oficial</span>{% endif %}
        </a>
      </li>
    {% endfor %}
  </ul>
</c-lista-cartao>

<p class="mt-6">
  <a href="{% url 'simulacao:carga' %}" class="text-accent hover:underline">Carregar dados por planilha</a>
</p>
```
`cenarios.html` fica `{% extends "base.html" %}{% block content %}{% include "simulacao/_cenarios_content.html" %}{% endblock %}` (inalterado na estrutura).

- [ ] **Step 2: Teste** — `assertContains(r, "badge badge-sm badge-primary")` quando há oficial; `assertNotContains(r, "cor-primaria")`.

- [ ] **Step 3: Rodar** `pytest apps/simulacao/tests/test_views_cenarios.py -v` — verde.

- [ ] **Step 4: Commit** `git commit -m "feat(cenarios): re-estilo daisyUI + breadcrumb"`

---

### Task 15: `_subnav.html` + cabeçalho de cenário

**Files:**
- Modify: `templates/simulacao/_subnav.html`
- Create: `templates/simulacao/_cenario_header.html`
- Modify: os 7 `_*_content.html` de aba para incluir o header

- [ ] **Step 1: `_cenario_header.html`**

```html
<c-card class="mb-4">
  <div class="flex flex-wrap items-center justify-between gap-2">
    <h1 class="text-lg font-semibold text-base-content">{{ cenario.nome }}</h1>
    {% if cenario.is_oficial %}
      <span class="badge badge-primary">Oficial</span>
    {% else %}
      <span class="badge badge-outline">Simulação</span>
    {% endif %}
  </div>
</c-card>
```

- [ ] **Step 2: `_subnav.html`** — trocar `tabs tabs-boxed` por `tabs tabs-bordered`, `tab-active` mantém (é daisyUI), envolver com o header:

```html
{% include "simulacao/_cenario_header.html" %}
<div role="tablist" class="tabs tabs-bordered mb-4">
  {# 7 <a role="tab"> — mesmos hx-get/hx-target/hx-push-url; classe: tab {% if active == 'X' %}tab-active{% endif %} #}
</div>
```
Manter os 7 links exatamente com os mesmos `{% url %}`, `hx-get`, `hx-target="#cenario-content"`, `hx-push-url="true"`.

- [ ] **Step 3: Render smoke das 7 abas** já coberto por `test_render_smoke.py::test_abas_do_cenario` — rodar.

- [ ] **Step 4: Commit** `git commit -m "feat(cenario): subnav re-estilizada + cabeçalho com badge"`

---

### Task 16: Grids Tabulator re-tematizados + botões

**Files:**
- Modify: os 7 `_*_content.html` (`_fabricas_content.html`, `_armazens_content.html`, `_rotas_content.html`, `_previsoes_content.html`, `_safras_content.html`, `_simulacao_content.html`, `_assistente_content.html`) e seus shells
- Modify: `static/simulacao/js/grid_editor.js` (só se referenciar cores hardcoded)

- [ ] **Step 1: Em cada `_*_content.html` de grid**, aplicar REGRA-SUBST nos botões: `class="rounded bg-[var(--cor-primaria)] ... text-white px-4 py-2 mt-4"` → `class="btn btn-primary mt-4"`. O `<div id="tabulator-*">` fica; o CSS `tabulator-vector.css` (Task 3) já re-tematiza.

- [ ] **Step 2: `grid_editor.js`** — `grep -n "#fff\|#000\|slate\|cor-primaria" static/simulacao/js/grid_editor.js`. Se houver cor hardcoded na config do Tabulator, trocar por classe/deixar o CSS resolver. Se não houver, nenhuma mudança.

- [ ] **Step 3: `_simulacao_content.html` / `_simulacao_status.html`** — status via daisyUI: `badge badge-info` (em andamento), `badge badge-success` (sucesso), `alert alert-error` (erro), `<progress class="progress progress-primary">` durante execução. Polling HTMX (`hx-get` + `hx-trigger="every 2s"`) **inalterado**.

- [ ] **Step 4: `_assistente_content.html` / `_assistente_transcript.html`** — bolhas do chat: `chat chat-start` / `chat chat-end` + `chat-bubble` (daisyUI); `<c-card>` no entorno; aviso de `GEMINI_API_KEY` ausente em `alert alert-warning`. Comportamento e escopo por cenário **inalterados**.

- [ ] **Step 5: Rodar** `pytest apps/simulacao/tests/ apps/core/tests/test_render_smoke.py -v` — verde.

- [ ] **Step 6: Commit** `git commit -m "feat(grids): Tabulator re-tematizado + status/chat daisyUI"`

---

### Task 17: Carga de dados

**Files:**
- Modify: `templates/simulacao/carga.html`, `_carga_content.html`, `carga_preview.html`, `_carga_preview_content.html`

- [ ] **Step 1: `_carga_content.html`** — upload form: `<c-card>` + campos sem estilo ad-hoc (bloco `@layer base`) + `btn btn-primary`. Breadcrumb `Início / Carga de Dados`.
- [ ] **Step 2: `_carga_preview_content.html`** — preview em `<table class="table table-sm">`; avisos/erros em `alert alert-warning`/`alert alert-error`; botão "Aplicar" `btn btn-primary`, "Cancelar" `btn btn-ghost`. REGRA-SUBST no resto.
- [ ] **Step 3: Rodar** `pytest apps/simulacao/tests/test_views_carga.py -v` — verde.
- [ ] **Step 4: Commit** `git commit -m "feat(carga): re-estilo daisyUI"`

---

# Onda 5 — Auth e admin

### Task 18: Telas de autenticação

**Files:**
- Modify: `templates/account/login.html`, `templates/account/email.html`, `templates/account/logout.html`, `templates/account/password_change.html`, `templates/account/password_reset.html`, `templates/account/password_reset_done.html`, `templates/account/password_reset_from_key.html`, `templates/account/password_reset_from_key_done.html`, `templates/socialaccount/authentication_error.html`, `templates/socialaccount/connections.html`, `templates/403.html`

- [ ] **Step 1: `login.html`** — centralizado, logo + `<c-card>`, form via campos daisyUI, botões SSO `btn btn-outline w-full`:

```html
{% extends "base.html" %}
{% load socialaccount %}
{% block title %}Entrar — Transbordo{% endblock %}
{% block content %}
  <div class="mx-auto mt-16 max-w-sm">
    <div class="mb-6 flex flex-col items-center gap-2">
      <img src="{% static 'vector/img/logo-vector.png' %}" alt="Vector Consulting" class="h-10">
      <span class="text-sm text-base-content/60">Sistema de Planejamento de Transbordo</span>
    </div>
    <c-card>
      {% if form.non_field_errors %}<div class="alert alert-error mb-3 text-sm">{{ form.non_field_errors }}</div>{% endif %}
      <form method="post" action="{% url 'account_login' %}" class="space-y-3">
        {% csrf_token %}
        {{ form.as_div }}
        {% if redirect_field_value %}<input type="hidden" name="{{ redirect_field_name }}" value="{{ redirect_field_value }}">{% endif %}
        <button type="submit" class="btn btn-primary w-full">Entrar</button>
      </form>
      <a href="{% url 'account_reset_password' %}" class="mt-2 block text-sm text-accent hover:underline">Esqueci minha senha</a>
      <div class="divider text-base-content/40">ou</div>
      <div class="space-y-2">
        <a href="{% provider_login_url 'google' %}" class="btn btn-outline w-full">Entrar com Google</a>
        <a href="{% provider_login_url 'microsoft' %}" class="btn btn-outline w-full">Entrar com Microsoft</a>
      </div>
    </c-card>
  </div>
{% endblock %}
```
(`{% load static %}` já vem da `base.html`? Não — cada template precisa do próprio `{% load %}`. Adicionar `{% load static socialaccount %}`.)

- [ ] **Step 2: Demais telas `account/*` + `socialaccount/*`** — `<c-card class="mx-auto mt-16 max-w-sm">`, REGRA-SUBST, botões `btn`. `403.html`: `text-error` no título, `<c-card>`.

- [ ] **Step 3: Rodar** — `test_login.py`, `test_views_cenarios.py::test_requer_login`, `test_render_smoke.py::test_auth_screens_anonimo` — verde. Confere `assertContains(response, 'Entrar com Google')` e `'Entrar com Microsoft'` (o `test_login.py` existente exige as duas strings).

- [ ] **Step 4: Commit** `git commit -m "feat(auth): reskin identidade Vector nas telas de conta"`

---

### Task 19: `/admin/` com django-unfold

**Files:**
- Modify: `apps/core/admin.py`, `apps/integracoes/admin.py`, `apps/simulacao/admin.py`
- Create: `apps/core/tests/test_admin_unfold.py`

**Interfaces:**
- Produces: todos os `ModelAdmin` do projeto herdam de `unfold.admin.ModelAdmin` (`core`: `CooperativaAdmin`; `integracoes`: `ApiKeyAdmin`; `simulacao`: 11 `*Admin`). `UserAdmin` herda de `unfold.admin.ModelAdmin` **e** mantém o comportamento de `DjangoUserAdmin` — usar `from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm` e `class UserAdmin(UnfoldUserAdmin)` onde `UnfoldUserAdmin` vem de `unfold.contrib...`; se não houver, herdar `(unfold.admin.ModelAdmin, DjangoUserAdmin)` nessa ordem (MRO: Unfold primeiro para o template, DjangoUserAdmin para fieldsets/forms). `procrastinate` fica com o admin padrão (não tocar).

- [ ] **Step 1: Teste que falha** — `apps/core/tests/test_admin_unfold.py`:

```python
from django.contrib import admin
from django.test import TestCase
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from apps.core.models import Cooperativa


class AdminUnfoldTests(TestCase):
    def test_cooperativa_admin_e_unfold(self):
        self.assertIsInstance(admin.site._registry[Cooperativa], UnfoldModelAdmin)

    def test_admin_index_renderiza(self):
        from django.contrib.auth import get_user_model
        u = get_user_model().objects.create_superuser(
            username="s", email="s@t.test", password="x", papel="admin_vector",
        )
        self.client.force_login(u)
        self.assertEqual(self.client.get("/admin/").status_code, 200)
```

- [ ] **Step 2: `apps/core/admin.py`**

```python
from unfold.admin import ModelAdmin as UnfoldModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm


@admin.register(Cooperativa)
class CooperativaAdmin(UnfoldModelAdmin):
    list_display = ('nome', 'slug', 'ativo')
    prepopulated_fields = {'slug': ['nome']}


@admin.register(User)
class UserAdmin(UnfoldModelAdmin, DjangoUserAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    fieldsets = DjangoUserAdmin.fieldsets + (('Transbordo', {'fields': ('cooperativa', 'papel')}),)
    add_fieldsets = DjangoUserAdmin.add_fieldsets + (('Transbordo', {'fields': ('email', 'cooperativa', 'papel')}),)
    list_display = DjangoUserAdmin.list_display + ('cooperativa', 'papel')
    list_filter = DjangoUserAdmin.list_filter + ('cooperativa', 'papel')
```

- [ ] **Step 3: `apps/integracoes/admin.py`** — `class ApiKeyAdmin(UnfoldModelAdmin)`.

- [ ] **Step 4: `apps/simulacao/admin.py`** — trocar `admin.ModelAdmin` por `UnfoldModelAdmin` em todos os 11; o `AllCooperativasAdminMixin` continua como primeira base: `class CenarioAdmin(AllCooperativasAdminMixin, UnfoldModelAdmin)` etc.

- [ ] **Step 5: Rodar**

Run: `pytest apps/core/tests/test_admin_unfold.py apps/ -k admin -v && python manage.py check`
Expected: verde; check limpo.

- [ ] **Step 6: Commit** `git commit -m "feat(admin): reskin do /admin/ com django-unfold"`

---

# Onda 6 — Documentação e release

### Task 20: ADR 0012 + guia normativo do design system

**Files:**
- Create: `docs/decisions/0012-design-system-agrovector.md`
- Create: `docs/design-system/README.md`

- [ ] **Step 1: `docs/decisions/0012-design-system-agrovector.md`** — seguir o formato dos ADRs 0001–0011 (Status: Aceito, Data: 2026-08-31, Contexto, Decisão, Consequências). Cobrir: adoção daisyUI 5 + Tailwind 4 Play CDN com os temas `vector`/`vector-dark`; o truque de cascata sem `@layer` (citar ADR 0020 de AppVector); django-tables2 + django-filter para listagens read-only; django-unfold no `/admin/`; seletor de organização por sessão (Abordagem A) vs. prefixo de URL (Abordagem B, rejeitada); `pyproject.toml`; e a política "doc normativo + cópia por produto" (sem pacote Python compartilhado — adiado).

- [ ] **Step 2: `docs/design-system/README.md`** — guia portável para os próximos produtos da suíte:
  - Tokens de cor (tabela completa, valores dos dois temas — copiar do `<style>` da `base.html`).
  - Anatomia da `base.html` (ordem dos `<link>`/`<script>`, os dois blocos `@theme`/`:root`, o script anti-flash, `hx-headers`, os dois `<dialog>`).
  - Catálogo dos componentes cotton (`<c-card>`, `<c-lista-cartao>`, `<c-resumo-numerico>`, `<c-breadcrumb>`, `<c-icon>`) com assinatura e exemplo.
  - Estrutura de header (dois níveis) e navegação (faixa de módulos, `{% block breadcrumb %}`).
  - Regras de uso: `text-accent` para link solto; `primary`/navy só fundo/borda; header sempre navy; tri-estado de tema com prefixo `vector-*`.
  - Overrides de template esperados (`django_tables2/tailwind.html`, `tailwind/field.html`).
  - Checklist "portando para um novo produto".

- [ ] **Step 3: Commit** `git commit -m "docs: ADR 0012 + guia normativo do design system AgroVector"`

---

### Task 21: Atualizar CLAUDE.md / README / DEPLOY / apps CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/DEPLOY.md`, `apps/gestao/CLAUDE.md`, `apps/simulacao/CLAUDE.md`
- Create: `apps/core/CLAUDE.md`

- [ ] **Step 1: `CLAUDE.md` raiz** — "Tech Stack" (+ daisyUI, django-tables2/filter, django-unfold); "Commands" (`pip install -e ".[dev]"`, sem `requirements*.txt`); nova seção "## Fase 12 — Evolução UX/UI (concluída)" resumindo: fundação visual portada de AppVector, header de dois níveis, home nova em `/`, seletor de organização por sessão, `pyproject.toml`, ADR 0012 + `docs/design-system/README.md`. Atualizar "Roadmap Status" (Fases 1–12, `1.1.0`).

- [ ] **Step 2: `apps/core/CLAUDE.md` (novo)** — file map de `apps/core` com o que a Fase 12 adicionou: `tenancy.py::obter_organizacao_corrente` / `cooperativa_id_do_request`, `views.py::home` / `selecionar_organizacao`, `urls.py` (`app_name='core'`, rota `/`), `services.py` (métricas via `all_cooperativas`), `tables.py` — não; `permissions.py` (super-membro Admin Vector).

- [ ] **Step 3: `apps/gestao/CLAUDE.md`** — `context_processors.menu()` agora devolve `org` / `organizacoes_disponiveis` / `mostra_modulos`; listagens em tables2/filter (`tables.py`, `filters.py`); "Organização" na UI.

- [ ] **Step 4: `apps/simulacao/CLAUDE.md`** — as views usam `requer_membro_organizacao` e `cooperativa_id_do_request(request)` (não `request.user.cooperativa_id` cru); grids herdam o escopo do contextvar.

- [ ] **Step 5: `README.md` / `docs/DEPLOY.md`** — comandos `pyproject.toml`; `LOGIN_REDIRECT_URL` agora é `/`.

- [ ] **Step 6: Commit** `git commit -m "docs: CLAUDE.md/README/DEPLOY para a Fase 12"`

---

### Task 22: CHANGELOG, VERSION, verificação manual, tag

**Files:**
- Modify: `CHANGELOG.md`, `VERSION`

- [ ] **Step 1: `VERSION`** → `1.1.0`.

- [ ] **Step 2: `CHANGELOG.md`** — nova seção `## [1.1.0] - 2026-08-31` com subseções (ordem Keep a Changelog): `### Added` (fundação visual daisyUI/Vector, header de dois níveis, home `/` com dashboards, seletor de organização por sessão para Admin Vector, `apps/core/services.py`, django-tables2/filter, django-unfold, componentes cotton `<c-lista-cartao>`/`<c-resumo-numerico>`/`<c-breadcrumb>`/`<c-icon>`, ADR 0012, `docs/design-system/README.md`, `pyproject.toml`); `### Changed` (`LOGIN_REDIRECT_URL` `/simulacao/cenarios/` → `/`; todas as ~25 telas re-estilizadas; `/admin/` com Unfold; terminologia "Organização" na UI); `### Removed` (tema "Grão & Aço", `static/simulacao/js/modal.js`, `requirements.txt`/`requirements-dev.txt`).

- [ ] **Step 3: Verificação manual** — rodar e registrar o resultado (num comentário no PR/commit ou no `CHANGELOG`):
  - `python manage.py runserver` + `python manage.py procrastinate worker`.
  - Login local; os dois dashboards; seletor de organização (Admin Vector entra/sai de uma organização; "— Consolidado —" volta ao dashboard); um grid editável salvando; uma simulação ponta a ponta; tema claro/escuro/sistema sem flash ao navegar; `/admin/` com Unfold.

- [ ] **Step 4: Checks finais**

Run: `python manage.py check && python manage.py makemigrations --check --dry-run && pytest`
Expected: check limpo, **sem migrations**, suíte inteira verde.

- [ ] **Step 5: Commit + tag**

```bash
git add CHANGELOG.md VERSION
git commit -m "docs: release 1.1.0 (Fase 12 — Evolução UX/UI)"
git tag -a v1.1.0 -m "Fase 12 — Evolução UX/UI"
```
(Não fazer push automático — o dono do projeto decide. Merge fast-forward em `main` ao fim da revisão de todas as ondas.)

---

## Self-Review

**1. Cobertura do SPEC:**

| Seção do SPEC | Task(s) |
|---|---|
| Decisão 1 — doc normativo + cópia | 20 |
| Decisão 2 — fundação visual 1:1 AppVector | 3, 4 |
| Decisão 2 — pacotes novos + config | 2 |
| Decisão 3 — header | 4 |
| Decisão 4 — faixa de módulos, subnav, breadcrumb | 4, 15 |
| Decisão 5 — organização por sessão (Abordagem A) | 5, 9 |
| Decisão 6 — home e dashboards | 6, 7, 8 |
| Decisão 7 — migração de telas (infra) | 3 |
| Decisão 7 — auth screens | 18 |
| Decisão 7 — gestão | 11, 12, 13 |
| Decisão 7 — cenários/grids/simulação/assistente/carga | 14, 15, 16, 17 |
| Decisão 7 — `/admin/` Unfold | 19 |
| Decisão 8 — `pyproject.toml` | 1 |
| Testes (tenancy/middleware/home/selecionar/services/permissions/menu) | 5, 6, 7, 8, 9, 11 |
| Testes — render smoke ~25 telas | 10 |
| Docs (ADR 0012, guia, CLAUDE.md, CHANGELOG, VERSION, tag) | 20, 21, 22 |
| Verificação manual | 22 |

**2. Placeholders:** o único `TODO` intencional é o comentário `{# TODO Fase 13 #}` em `_home_organizacao_conteudo.html` — é requisito explícito do SPEC ("comentário no template marcando que o dashboard detalhado por papel entra na próxima fase"), não um buraco de plano.

**3. Consistência de tipos:**
- `obter_organizacao_corrente(request) -> int | None` e `cooperativa_id_do_request(request) -> int` — usados igual em middleware (Task 5), context processor (Task 4), views de simulação (Task 9), home (Task 6).
- `metricas_da_organizacao` retorna as chaves `fabricas/armazens/cenarios/toneladas/sacas/frete/ultima_simulacao` — consumidas em `_home_organizacao_conteudo.html` (Task 8) com exatamente esses nomes.
- `metricas_consolidadas()['por_organizacao']` = lista de dicts com `id/nome/fabricas/armazens/toneladas/frete/ultima_simulacao` — consumidas no `<table>` de `_home_consolidado_conteudo.html`.
- `requer_membro_organizacao` (decorator), `pode_editar_fabricas(user, request=None)` / `pode_editar_armazens(user, request=None)` — assinaturas idênticas entre Task 9 (def) e uso nas views/decorators.
- `_predicado_required` passa a chamar `predicado(user, request)` — `requer_admin_vector` reescrito como lambda de 2 args na mesma task; nenhum outro chamador de `_predicado_required`.

**4. Ambiguidades resolvidas inline:**
- `apps/core/tables.py` foi **descartado** (Task 8 Step 6): a tabela por organização precisa de `<form>`+`{% csrf_token %}` por linha, incompatível com `render_` de coluna do django-tables2 — usa `<table>` direto. django-tables2 fica só nas listagens de gestão (Task 12).
- Ordem Task 6 ↔ Task 7: a view `home` importa `apps.core.services` — **executar Task 7 antes de Task 6** (nota explícita ao fim da Task 7).
- Gate real da suíte verde: fim da Onda 2 (Task 10), não fim de cada task da Onda 1 — `base.html` faz `{% url 'core:home' %}` que só resolve depois da Task 6.

## Execution Handoff

**Plano completo e salvo em `docs/superpowers/plans/2026-08-31-fase12-evolucao-ux-ui.md`. Duas opções de execução:**

**1. Subagent-Driven (recomendado)** — um subagent novo por task, revisão em dois estágios entre tasks, iteração rápida. Casa com o rollout em ondas do SPEC.

**2. Inline Execution** — executo as tasks nesta sessão via `executing-plans`, em lotes com checkpoints de revisão.

**Qual abordagem?**
