# Fase 5 — UI: Dados & Cenários Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first real Django UI surface for Comigo/Transbordo: login, a Cenário list/creation screen, and five Tabulator-based spreadsheet-style editing screens (Fábricas, Armazéns, Rotas, Previsões, Datas de Safra) inside a Cenário — porting the "Dados & Cenários" tab of the Streamlit app (`app.py`) to Django+HTMX, using visual foundation adapted from the sibling `APP_Vector` project.

**Architecture:** `apps/simulacao/views.py` gets one function-based view per screen, each following the `request.htmx` branch (full page vs. partial — APP_Vector's ADR 0015 lesson). Grid screens share one client-side module (`static/simulacao/js/grid_editor.js`, Tabulator + IMask.js) driven by a per-view Python column-config list, and one server-side upsert contract (`POST` with a `linhas_json` field, one `transaction.atomic()` block per grid — all rows save or none do). `apps/simulacao/services.py` gains `clone_scenario`, a 1:1 port of `scenarios.clone_scenario` (SQLAlchemy) discovered as a missing prerequisite during this phase's brainstorm. Views use `Model.objects` (the tenant-scoped, fail-closed `TenantManager`) throughout — never `all_cooperativas` — the opposite convention from `engine.py`/`services.py` (ADR 0006), and deliberately so: a view has an authenticated `request.user.cooperativa_id` to scope by; a `cenario_id` guessed in a URL for another cooperativa must 404, not leak.

**Tech Stack:** Django 6 (already installed), `django-htmx`, `django-cotton`, `django-crispy-forms` + `crispy-tailwind` (new this phase), Tailwind v4 + daisyUI 5 via CDN, Tabulator (CDN) + IMask.js (CDN) for the editable grids, `pytest-django` (already installed, Fase 5 Fundação).

**Spec:** `docs/superpowers/specs/2026-08-23-fase5-ui-dados-cenarios-design.md` (this plan implements it in full — read it for the "why" behind every decision below; this plan only restates what's needed to build each task).

## Global Constraints

- Multi-tenancy: every new view resolves its `Cenario`/model instances via `Model.objects` (the `TenantManager`, fail-closed on missing tenant context) — **never** `Model.all_cooperativas` from a view (spec §3). `clone_scenario` (a domain function, not a view) is the one exception and uses `all_cooperativas` internally per ADR 0006, with its own explicit `cooperativa_id` ownership check.
- Every grid view branches on `request.htmx`: full page (extends `base.html`) without it, partial only with it (APP_Vector ADR 0015 — omitting this branch nests a full page inside the swap target).
- Grid saves are all-or-nothing: one `transaction.atomic()` per `POST`, no partial commits (a deliberate improvement over the Streamlit original's per-row try/except-and-continue).
- pt-BR number formatting (`.` thousands, `,` decimals) in every editable numeric grid cell, both display and input (IMask.js) — this is the entire reason Tabulator/IMask exist in this phase (spec §4, "lacuna real do APP_Vector").
- JSON handed to a `<script>` tag for the grid config/rows always goes through Django's `json_script` template filter — never `json.dumps(...)|safe` (that pattern is XSS-unsafe the moment any text field contains `</script>`).
- No task in this plan modifies `tests/`, any root-level `.py` file (`app.py`, `models.py`, `calculations.py`, `logistics_services.py`, `data_loader.py`, `scenarios.py`, ...), or `apps/core/`. The existing Streamlit/SQLAlchemy stack keeps working unmodified — same rule the Fase 5 Fundação and Port do domínio plans already followed.
- No `django-tables2`/`django-filter`/`django-import-export`/`django-unfold` in this phase — not exercised by any screen here (spec §"Escopo", YAGNI).
- Portuguese domain terms (`Cenario`, `Fabrica`, `Armazem`, `Rota`, `Safra`, ...) stay untranslated in code identifiers; UI copy is Portuguese throughout (matches the Streamlit original).

---

## File Structure

```
requirements.txt                          # Task 1 — 4 new packages
config/settings/base.py                   # Task 1 (INSTALLED_APPS, MIDDLEWARE, crispy) → Task 2 (LOGIN_URL/LOGIN_REDIRECT_URL)
config/urls.py                            # Task 2 (django.contrib.auth.urls) → Task 4 (apps.simulacao.urls include)
templates_django/base.html                # Task 1
templates_django/cotton/card.html         # Task 1
templates_django/registration/login.html  # Task 2
static/simulacao/js/modal.js              # Task 1
static/simulacao/js/grid_editor.js        # Task 5 (Tabulator+IMask.js, shared by Tasks 5-9)
apps/simulacao/templatetags/__init__.py           # Task 1
apps/simulacao/templatetags/simulacao_filters.py  # Task 1 — |moeda, |volume
apps/simulacao/services.py                # Task 3 (append clone_scenario) — existing file, Fase 2
apps/simulacao/urls.py                    # Task 4 (create, cenarios_list) → Tasks 5-9 (append one path each)
apps/simulacao/views.py                   # Task 4 (create, cenarios_list) → Tasks 5-9 (append one view each)
apps/simulacao/columns.py                 # Task 5 (create, FABRICA_COLUMNS) → Tasks 6-9 (append one constant each)
templates/simulacao/cenarios.html          # Task 4
templates/simulacao/_cenarios_content.html # Task 4
templates/simulacao/_subnav.html           # Task 5 (create, 1 tab) → Tasks 6-9 (append 1 tab each)
templates/simulacao/fabricas.html          # Task 5
templates/simulacao/_fabricas_content.html # Task 5
templates/simulacao/armazens.html          # Task 6
templates/simulacao/_armazens_content.html # Task 6
templates/simulacao/rotas.html             # Task 7
templates/simulacao/_rotas_content.html    # Task 7
templates/simulacao/previsoes.html         # Task 8
templates/simulacao/_previsoes_content.html # Task 8
templates/simulacao/safras.html            # Task 9
templates/simulacao/_safras_content.html   # Task 9
apps/simulacao/tests/test_templatetags.py  # Task 1
apps/simulacao/tests/test_login.py         # Task 2
apps/simulacao/tests/test_services_clone_scenario.py  # Task 3
apps/simulacao/tests/test_views_cenarios.py     # Task 4
apps/simulacao/tests/test_views_fabricas.py     # Task 5
apps/simulacao/tests/test_views_armazens.py     # Task 6
apps/simulacao/tests/test_views_rotas.py        # Task 7
apps/simulacao/tests/test_views_previsoes.py    # Task 8
apps/simulacao/tests/test_views_safras.py       # Task 9
```

---

### Task 1: Fundação visual (pacotes, settings, `base.html`, cotton, filtros pt-BR, modal)

**Files:**
- Modify: `requirements.txt`, `config/settings/base.py`
- Create: `templates_django/base.html`, `templates_django/cotton/card.html`, `static/simulacao/js/modal.js`
- Create: `apps/simulacao/templatetags/__init__.py`, `apps/simulacao/templatetags/simulacao_filters.py`
- Create: `apps/simulacao/tests/test_templatetags.py`

**Interfaces:**
- Consumes: nothing from earlier Fase 5 work (this is the first task).
- Produces: `base.html` (all later templates `{% extends "base.html" %}`), `<c-card>` cotton component, template filters `|moeda`/`|volume` (used by every grid template from Task 5 on), `static/simulacao/js/modal.js` (available but not wired to anything yet — this phase's grids don't need a confirm dialog per spec §"Decisões em aberto").

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_templatetags.py`:
```python
from decimal import Decimal

from django.template import Context, Template
from django.test import SimpleTestCase


class MoedaFilterTests(SimpleTestCase):
    def _render(self, valor):
        template = Template("{% load simulacao_filters %}{{ valor|moeda }}")
        return template.render(Context({"valor": valor}))

    def test_formata_com_duas_casas_e_separador_pt_br(self):
        self.assertEqual(self._render(1234.5), "R$ 1.234,50")

    def test_valor_negativo(self):
        self.assertEqual(self._render(-42.0), "R$ -42,00")

    def test_none_retorna_vazio(self):
        self.assertEqual(self._render(None), "")

    def test_aceita_decimal(self):
        self.assertEqual(self._render(Decimal("10")), "R$ 10,00")


class VolumeFilterTests(SimpleTestCase):
    def _render(self, valor):
        template = Template("{% load simulacao_filters %}{{ valor|volume }}")
        return template.render(Context({"valor": valor}))

    def test_formata_com_uma_casa_e_separador_pt_br(self):
        self.assertEqual(self._render(1234.5), "1.234,5")

    def test_milhar_grande(self):
        self.assertEqual(self._render(1234567.89), "1.234.567,9")

    def test_none_retorna_vazio(self):
        self.assertEqual(self._render(None), "")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_templatetags.py -v`
Expected: FAIL with `TemplateSyntaxError: 'simulacao_filters' is not a registered tag library` (module doesn't exist yet).

- [ ] **Step 3: Add the packages and settings**

Append to `requirements.txt`:
```
django-htmx>=1.19,<2.0
django-cotton>=2.7,<3.0
django-crispy-forms>=2.7,<3.0
crispy-tailwind>=1.0,<2.0
```

Run: `pip install -r requirements.txt`

Modify `config/settings/base.py` — replace the `INSTALLED_APPS` list:
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_htmx',
    'django_cotton',
    'crispy_forms',
    'crispy_tailwind',
    'apps.core',
    'apps.simulacao',
    'apps.integracoes',
]
```

Replace the `MIDDLEWARE` list (adds `HtmxMiddleware` right after `AuthenticationMiddleware`, before `CooperativaScopeMiddleware` — HTMX detection doesn't depend on tenant scoping, but keeping the existing tenant middleware last preserves its documented position):
```python
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django_htmx.middleware.HtmxMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'apps.core.middleware.CooperativaScopeMiddleware',
]
```

Add after `STATIC_ROOT = BASE_DIR / 'staticfiles'`:
```python
STATICFILES_DIRS += [BASE_DIR / 'static'] if (BASE_DIR / 'static').exists() else []
CRISPY_ALLOWED_TEMPLATE_PACKS = ['tailwind']
CRISPY_TEMPLATE_PACK = 'tailwind'
```

(`STATICFILES_DIRS` already exists earlier in the file as `[BASE_DIR / 'static']` — check first: if it's already exactly that, skip the append line above and just add the two `CRISPY_*` lines. `django-cotton` needs no `TEMPLATES['DIRS']` change — it auto-discovers `templates/cotton/` and `templates_django/cotton/` inside every installed app's/project's template dirs already configured.)

- [ ] **Step 4: Write `base.html`**

`templates_django/base.html`:
```html
{% load static %}
{% load django_htmx %}
<!DOCTYPE html>
<html lang="pt-br" data-theme="grao-e-aco">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{% block title %}Transbordo{% endblock %}</title>
    <script src="https://cdn.jsdelivr.net/npm/htmx.org@2.0.4/dist/htmx.min.js"></script>
    {% django_htmx_script %}
    <script src="https://cdn.tailwindcss.com/4"></script>
    <link href="https://cdn.jsdelivr.net/npm/daisyui@5" rel="stylesheet" type="text/css">
    <style>
        :root {
            --cor-primaria: #2f6f3e;      /* verde — Grão & Aço */
            --cor-primaria-hover: #24572f;
            --cor-acento: #b8860b;        /* âmbar */
            --cor-superficie: #ffffff;
            --cor-borda: #e2e8f0;
        }
        [data-theme="grao-e-aco-escuro"] {
            --cor-superficie: #1e293b;
            --cor-borda: #334155;
        }
    </style>
    {% block extra_head %}{% endblock %}
</head>
<body class="min-h-screen bg-slate-50 text-slate-900">
    <nav class="border-b border-[--cor-borda] bg-[--cor-superficie] px-6 py-3 flex items-center justify-between">
        <span class="font-semibold text-[--cor-primaria]">Comigo — Transbordo</span>
        {% if request.user.is_authenticated %}
        <form method="post" action="{% url 'logout' %}">
            {% csrf_token %}
            <button type="submit" class="text-sm text-slate-600 hover:underline">Sair ({{ request.user.username }})</button>
        </form>
        {% endif %}
    </nav>
    <main class="p-6">
        {% if messages %}
        <ul class="mb-4">
            {% for message in messages %}
            <li class="rounded border border-[--cor-borda] bg-white px-4 py-2 mb-2">{{ message }}</li>
            {% endfor %}
        </ul>
        {% endif %}
        {% block content %}{% endblock %}
    </main>
    <script src="{% static 'simulacao/js/modal.js' %}"></script>
    {% block extra_scripts %}{% endblock %}
</body>
</html>
```

- [ ] **Step 5: Write the cotton card component**

`templates_django/cotton/card.html`:
```html
<div class="rounded-lg border border-[--cor-borda] bg-[--cor-superficie] p-6 {{ attrs.class }}">
    {{ slot }}
</div>
```

- [ ] **Step 6: Write the shared modal/confirm JS (adapted from APP_Vector, unused by any screen yet)**

`static/simulacao/js/modal.js`:
```javascript
// Modal e confirm compartilhados (#transbordo-modal / #transbordo-confirm),
// padrão adaptado do APP_Vector. Nenhuma tela desta fase usa isto ainda
// (ver spec 2026-08-23-fase5-ui-dados-cenarios-design.md, "Decisões em
// aberto") -- fica pronto para quando alguma ação futura precisar.
document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (evt.detail.target.id === 'transbordo-modal') {
        document.getElementById('transbordo-modal').showModal();
    }
});

document.body.addEventListener('htmx:confirm', function (evt) {
    if (!evt.detail.target.hasAttribute('data-confirm-custom')) return;
    evt.preventDefault();
    const dialogo = document.getElementById('transbordo-confirm');
    if (!dialogo) { evt.detail.issueRequest(true); return; }
    dialogo.showModal();
    dialogo.querySelector('[data-confirm-ok]').onclick = function () {
        dialogo.close();
        evt.detail.issueRequest(true);
    };
    dialogo.querySelector('[data-confirm-cancel]').onclick = function () {
        dialogo.close();
    };
});
```

- [ ] **Step 7: Write the pt-BR template filters**

`apps/simulacao/templatetags/__init__.py`: empty.

`apps/simulacao/templatetags/simulacao_filters.py`:
```python
from django import template

register = template.Library()


def _formatar_pt_br(valor, casas_decimais):
    if valor is None or valor == '':
        return ''
    numero = float(valor)
    texto = f"{numero:,.{casas_decimais}f}"
    return texto.replace(',', 'X').replace('.', ',').replace('X', '.')


@register.filter
def moeda(valor):
    """Porte de `utils.format_valor`: 'R$ 1.234,50'."""
    if valor is None or valor == '':
        return ''
    return f"R$ {_formatar_pt_br(valor, 2)}"


@register.filter
def volume(valor):
    """Porte de `utils.format_volume`: '1.234,5'."""
    return _formatar_pt_br(valor, 1)
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_templatetags.py -v`
Expected: PASS (7 passed)

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 9: Commit**

```bash
git add requirements.txt config/settings/base.py templates_django/ static/simulacao/ apps/simulacao/templatetags/ apps/simulacao/tests/test_templatetags.py
git commit -m "feat(fase5): visual foundation adapted from APP_Vector (base.html, cotton, pt-BR filters)"
```

---

### Task 2: Login básico

**Files:**
- Modify: `config/settings/base.py`, `config/urls.py`
- Create: `templates_django/registration/login.html`
- Create: `apps/simulacao/tests/test_login.py`

**Interfaces:**
- Consumes: `base.html` (Task 1).
- Produces: `/accounts/login/`, `/accounts/logout/` (Django's built-in auth URLs — `base.html`'s logout form from Task 1 already targets `{% url 'logout' %}`, which only resolves once this task's `include('django.contrib.auth.urls')` lands). `LOGIN_URL`/`LOGIN_REDIRECT_URL` settings consumed by every `@login_required` view from Task 4 on.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_login.py`:
```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa

User = get_user_model()


class LoginTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )

    def test_pagina_de_login_renderiza(self):
        response = self.client.get(reverse('login'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<form')

    def test_login_valido_redireciona(self):
        response = self.client.post(reverse('login'), {
            'username': 'usuaria', 'password': 'senha-forte-123',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/simulacao/cenarios/')

    def test_login_invalido_nao_autentica(self):
        response = self.client.post(reverse('login'), {
            'username': 'usuaria', 'password': 'senha-errada',
        })

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.wsgi_request.user.is_authenticated)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_login.py -v`
Expected: FAIL with `NoReverseMatch: Reverse for 'login' not found`.

- [ ] **Step 3: Wire up auth URLs and settings**

Modify `config/urls.py`:
```python
"""URL configuration for the Transbordo project."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
]
```

Add to `config/settings/base.py`, after `AUTH_USER_MODEL = 'core.User'`:
```python
LOGIN_URL = '/accounts/login/'
LOGIN_REDIRECT_URL = '/simulacao/cenarios/'
LOGOUT_REDIRECT_URL = '/accounts/login/'
```

- [ ] **Step 4: Write the login template**

`templates_django/registration/login.html`:
```html
{% extends "base.html" %}
{% block content %}
<div class="max-w-sm mx-auto mt-16">
    <c-card>
        <h1 class="text-lg font-semibold mb-4">Entrar</h1>
        <form method="post">
            {% csrf_token %}
            {% if form.errors %}
            <p class="text-red-600 text-sm mb-3">Usuário ou senha inválidos.</p>
            {% endif %}
            <div class="mb-3">
                <label for="{{ form.username.id_for_label }}" class="block text-sm mb-1">Usuário</label>
                {{ form.username }}
            </div>
            <div class="mb-4">
                <label for="{{ form.password.id_for_label }}" class="block text-sm mb-1">Senha</label>
                {{ form.password }}
            </div>
            <button type="submit" class="w-full rounded bg-[--cor-primaria] hover:bg-[--cor-primaria-hover] text-white py-2">
                Entrar
            </button>
        </form>
    </c-card>
</div>
{% endblock %}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_login.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add config/urls.py config/settings/base.py templates_django/registration/ apps/simulacao/tests/test_login.py
git commit -m "feat(fase5): login basico (django.contrib.auth), sem SSO"
```

---

### Task 3: Port de `clone_scenario` para `apps/simulacao/services.py`

**Files:**
- Modify: `apps/simulacao/services.py`
- Create: `apps/simulacao/tests/test_services_clone_scenario.py`

**Interfaces:**
- Consumes: `Cenario`, `Fabrica`, `Armazem`, `Rota`, `PrevisaoFabrica`, `PrevisaoArmazem`, `SafraUnidade` (Fase 2).
- Produces: `apps.simulacao.services.clone_scenario(cooperativa_id: int, scenario_name: str, source_scenario_id: int) -> int` — consumed by Task 4's view.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_services_clone_scenario.py`:
```python
import datetime

from django.test import TestCase

from apps.core.models import Cooperativa
from apps.simulacao import services
from apps.simulacao.models import (
    Armazem, Cenario, Fabrica, PrevisaoArmazem, PrevisaoFabrica, Rota, SafraUnidade,
)


class CloneScenarioTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.origem = Cenario.all_cooperativas.create(
            cooperativa=self.cooperativa, nome='Oficial', is_oficial=True,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.origem, nome='Fábrica 1',
            capacidade_estatica=1000, capacidade_esmagamento_diaria=100,
            capacidade_recebimento_diaria=100, limite_caminhoes=10,
            carga_media_caminhao=30, estoque_inicial=500,
        )
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.origem, nome='Armazém 1',
            capacidade_estatica=800, capacidade_expedicao_diaria=50, estoque_inicial=200,
        )
        Rota.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.origem,
            armazem=self.armazem, fabrica=self.fabrica,
            distancia_km=120, custo_frete_ton=45, custo_frete_entressafra=30,
        )
        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, fabrica=self.fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=300, vendas=100,
        )
        PrevisaoArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, armazem=self.armazem,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=200, vendas=50,
        )
        SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.origem,
            entidade_tipo='Armazém', entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 1, 15), data_fim=datetime.date(2026, 4, 15),
        )

    def test_clona_fabricas_armazens_rotas_previsoes_e_safras(self):
        novo_id = services.clone_scenario(self.cooperativa.id, 'Simulação 1', self.origem.id)

        novo = Cenario.all_cooperativas.get(id=novo_id)
        self.assertEqual(novo.nome, 'Simulação 1')
        self.assertFalse(novo.is_oficial)

        fabricas = list(Fabrica.all_cooperativas.filter(cenario_id=novo_id))
        self.assertEqual(len(fabricas), 1)
        self.assertEqual(fabricas[0].nome, 'Fábrica 1')
        self.assertNotEqual(fabricas[0].id, self.fabrica.id)

        armazens = list(Armazem.all_cooperativas.filter(cenario_id=novo_id))
        self.assertEqual(len(armazens), 1)

        rotas = list(Rota.all_cooperativas.filter(cenario_id=novo_id))
        self.assertEqual(len(rotas), 1)
        self.assertEqual(rotas[0].armazem_id, armazens[0].id)
        self.assertEqual(rotas[0].fabrica_id, fabricas[0].id)

        previsoes_fab = list(PrevisaoFabrica.all_cooperativas.filter(fabrica_id=fabricas[0].id))
        self.assertEqual(len(previsoes_fab), 1)
        self.assertEqual(previsoes_fab[0].recebimento_produtor, 300)

        previsoes_arm = list(PrevisaoArmazem.all_cooperativas.filter(armazem_id=armazens[0].id))
        self.assertEqual(len(previsoes_arm), 1)

        safras = list(SafraUnidade.all_cooperativas.filter(cenario_id=novo_id))
        self.assertEqual(len(safras), 1)
        self.assertEqual(safras[0].entidade_id, armazens[0].id)

    def test_rejeita_cenario_de_origem_de_outra_cooperativa(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')

        with self.assertRaises(ValueError):
            services.clone_scenario(outra_cooperativa.id, 'Simulação 1', self.origem.id)

        self.assertEqual(Cenario.all_cooperativas.filter(cooperativa=outra_cooperativa).count(), 0)

    def test_nome_duplicado_na_mesma_cooperativa_falha(self):
        services.clone_scenario(self.cooperativa.id, 'Simulação 1', self.origem.id)

        with self.assertRaises(Exception):
            services.clone_scenario(self.cooperativa.id, 'Simulação 1', self.origem.id)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_services_clone_scenario.py -v`
Expected: FAIL with `AttributeError: module 'apps.simulacao.services' has no attribute 'clone_scenario'`.

- [ ] **Step 3: Write `clone_scenario`**

Append to `apps/simulacao/services.py` (add `from django.db import transaction` and `Rota, SafraUnidade` to the existing `from apps.simulacao.models import (...)` block at the top of the file):
```python
def clone_scenario(cooperativa_id: int, scenario_name: str, source_scenario_id: int) -> int:
    """Porte 1:1 de `scenarios.clone_scenario` (SQLAlchemy). Diferente das
    demais funções deste módulo, recebe um ID de origem potencialmente
    vindo de fora (o cenário a clonar) -- valida explicitamente que
    pertence a `cooperativa_id` antes de tocar em qualquer dado (ver ADR
    0006 e spec 2026-08-23, §5)."""
    try:
        origem = Cenario.all_cooperativas.get(id=source_scenario_id, cooperativa_id=cooperativa_id)
    except Cenario.DoesNotExist:
        raise ValueError(
            f"Cenário de origem {source_scenario_id} não encontrado para esta cooperativa."
        )

    with transaction.atomic():
        novo = Cenario.all_cooperativas.create(
            cooperativa_id=cooperativa_id, nome=scenario_name, is_oficial=False,
        )

        fabrica_map = {}
        for f in Fabrica.all_cooperativas.filter(cenario_id=origem.id):
            nova = Fabrica.all_cooperativas.create(
                cooperativa_id=cooperativa_id, cenario_id=novo.id, nome=f.nome,
                capacidade_estatica=f.capacidade_estatica,
                capacidade_esmagamento_diaria=f.capacidade_esmagamento_diaria,
                capacidade_recebimento_diaria=f.capacidade_recebimento_diaria,
                limite_caminhoes=f.limite_caminhoes,
                carga_media_caminhao=f.carga_media_caminhao,
                estoque_inicial=f.estoque_inicial,
            )
            fabrica_map[f.id] = nova.id

        armazem_map = {}
        for a in Armazem.all_cooperativas.filter(cenario_id=origem.id):
            nova = Armazem.all_cooperativas.create(
                cooperativa_id=cooperativa_id, cenario_id=novo.id, nome=a.nome,
                capacidade_estatica=a.capacidade_estatica,
                capacidade_expedicao_diaria=a.capacidade_expedicao_diaria,
                estoque_inicial=a.estoque_inicial,
            )
            armazem_map[a.id] = nova.id

        for r in Rota.all_cooperativas.filter(cenario_id=origem.id):
            if r.armazem_id in armazem_map and r.fabrica_id in fabrica_map:
                Rota.all_cooperativas.create(
                    cooperativa_id=cooperativa_id, cenario_id=novo.id,
                    armazem_id=armazem_map[r.armazem_id], fabrica_id=fabrica_map[r.fabrica_id],
                    distancia_km=r.distancia_km, custo_frete_ton=r.custo_frete_ton,
                    custo_frete_entressafra=r.custo_frete_entressafra,
                )

        if fabrica_map:
            for p in PrevisaoFabrica.all_cooperativas.filter(fabrica_id__in=fabrica_map.keys()):
                PrevisaoFabrica.all_cooperativas.create(
                    cooperativa_id=cooperativa_id, fabrica_id=fabrica_map[p.fabrica_id],
                    mes_referencia=p.mes_referencia,
                    recebimento_produtor=p.recebimento_produtor, vendas=p.vendas,
                )

        if armazem_map:
            for p in PrevisaoArmazem.all_cooperativas.filter(armazem_id__in=armazem_map.keys()):
                PrevisaoArmazem.all_cooperativas.create(
                    cooperativa_id=cooperativa_id, armazem_id=armazem_map[p.armazem_id],
                    mes_referencia=p.mes_referencia,
                    recebimento_produtor=p.recebimento_produtor, vendas=p.vendas,
                )

        for s in SafraUnidade.all_cooperativas.filter(cenario_id=origem.id):
            if s.entidade_tipo == 'Armazém':
                novo_entidade_id = armazem_map.get(s.entidade_id)
            else:
                novo_entidade_id = fabrica_map.get(s.entidade_id)
            if novo_entidade_id:
                SafraUnidade.all_cooperativas.create(
                    cooperativa_id=cooperativa_id, cenario_id=novo.id,
                    entidade_tipo=s.entidade_tipo, entidade_id=novo_entidade_id,
                    data_inicio=s.data_inicio, data_fim=s.data_fim,
                )

    return novo.id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_services_clone_scenario.py -v`
Expected: PASS (3 passed)

Run: `pytest apps/simulacao/ -v`
Expected: all still passing (no regression in Fase 2's tests).

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/services.py apps/simulacao/tests/test_services_clone_scenario.py
git commit -m "feat(fase5): port clone_scenario to services.py"
```

---

### Task 4: Tela de Cenários (listagem + criação por clonagem)

**Files:**
- Create: `apps/simulacao/views.py`, `apps/simulacao/urls.py`
- Create: `templates/simulacao/cenarios.html`, `templates/simulacao/_cenarios_content.html`
- Create: `apps/simulacao/tests/test_views_cenarios.py`
- Modify: `config/urls.py`

**Interfaces:**
- Consumes: `services.list_scenarios(cooperativa_id)` (Fase 2), `services.clone_scenario(...)` (Task 3), `login_required`/`base.html` (Tasks 1-2).
- Produces: URL `simulacao:cenarios_list` (`/simulacao/cenarios/`) — the target every grid task's "voltar" link and `LOGIN_REDIRECT_URL` point to.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_views_cenarios.py`:
```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario

User = get_user_model()


class CenariosListViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.oficial = Cenario.all_cooperativas.create(
            cooperativa=self.cooperativa, nome='Oficial', is_oficial=True,
        )

    def test_requer_login(self):
        response = self.client.get(reverse('simulacao:cenarios_list'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response.url)

    def test_pagina_completa_lista_cenarios(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('simulacao:cenarios_list'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html')
        self.assertContains(response, 'Oficial')

    def test_nao_mostra_cenario_de_outra_cooperativa(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        Cenario.all_cooperativas.create(cooperativa=outra_cooperativa, nome='Cenário B')
        self.client.force_login(self.user)

        response = self.client.get(reverse('simulacao:cenarios_list'))

        self.assertNotContains(response, 'Cenário B')

    def test_post_cria_cenario_por_clonagem(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse('simulacao:cenarios_list'), {
            'nome': 'Simulação Nova', 'origem_id': self.oficial.id,
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Cenario.all_cooperativas.filter(cooperativa=self.cooperativa, nome='Simulação Nova').exists())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_views_cenarios.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'apps.simulacao.views'`.

- [ ] **Step 3: Write the view, URLs, and templates**

`apps/simulacao/views.py`:
```python
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.simulacao import services
from apps.simulacao.models import Cenario


@login_required
def cenarios_list(request):
    cooperativa_id = request.user.cooperativa_id

    if request.method == 'POST':
        nome = request.POST.get('nome', '').strip()
        origem_id = request.POST.get('origem_id')
        if nome and origem_id:
            services.clone_scenario(cooperativa_id, nome, int(origem_id))
        return redirect('simulacao:cenarios_list')

    cenarios = services.list_scenarios(cooperativa_id)
    context = {'cenarios': cenarios}
    template = 'simulacao/_cenarios_content.html' if request.htmx else 'simulacao/cenarios.html'
    return render(request, template, context)
```

`apps/simulacao/urls.py`:
```python
from django.urls import path

from apps.simulacao import views

app_name = 'simulacao'

urlpatterns = [
    path('cenarios/', views.cenarios_list, name='cenarios_list'),
]
```

Modify `config/urls.py` — add the include:
```python
"""URL configuration for the Transbordo project."""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('django.contrib.auth.urls')),
    path('simulacao/', include('apps.simulacao.urls')),
]
```

`templates/simulacao/cenarios.html`:
```html
{% extends "base.html" %}
{% block content %}
{% include "simulacao/_cenarios_content.html" %}
{% endblock %}
```

`templates/simulacao/_cenarios_content.html`:
```html
<h1 class="text-xl font-semibold mb-4">Cenários</h1>

<c-card class="mb-6">
    <h2 class="font-medium mb-3">Criar Novo Cenário de Simulação</h2>
    <form method="post" action="{% url 'simulacao:cenarios_list' %}" class="flex gap-3 items-end">
        {% csrf_token %}
        <div>
            <label class="block text-sm mb-1" for="id_nome">Nome do Novo Cenário</label>
            <input type="text" id="id_nome" name="nome" required class="border rounded px-2 py-1">
        </div>
        <div>
            <label class="block text-sm mb-1" for="id_origem_id">Clonar dados de qual cenário?</label>
            <select id="id_origem_id" name="origem_id" class="border rounded px-2 py-1">
                {% for cenario in cenarios %}
                <option value="{{ cenario.id }}">{{ cenario.nome }}</option>
                {% endfor %}
            </select>
        </div>
        <button type="submit" class="rounded bg-[--cor-primaria] hover:bg-[--cor-primaria-hover] text-white px-4 py-2">
            Criar Cenário
        </button>
    </form>
</c-card>

<c-card>
    <h2 class="font-medium mb-3">Escolher Cenário para Editar</h2>
    <ul class="divide-y divide-[--cor-borda]">
        {% for cenario in cenarios %}
        <li class="py-2">
            <a href="{% url 'simulacao:cenarios_list' %}{{ cenario.id }}/fabricas/" class="text-[--cor-primaria] hover:underline">
                {{ cenario.nome }}{% if cenario.is_oficial %} (Oficial){% endif %}
            </a>
        </li>
        {% endfor %}
    </ul>
</c-card>
```

(The `fabricas/` link above is written by-hand rather than `{% url %}` because `simulacao:fabricas_grid` doesn't exist until Task 5 — Task 5 replaces this with a proper `{% url 'simulacao:fabricas_grid' cenario_id=cenario.id %}` once that name is registered.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_views_cenarios.py -v`
Expected: PASS (4 passed)

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/cenarios.html templates/simulacao/_cenarios_content.html apps/simulacao/tests/test_views_cenarios.py config/urls.py
git commit -m "feat(fase5): tela de Cenarios (listagem + criacao por clonagem)"
```

---

### Task 5: Grade de Fábricas (+ fundação do editor Tabulator/IMask, sub-navegação)

**Files:**
- Create: `static/simulacao/js/grid_editor.js`
- Create: `apps/simulacao/columns.py`
- Create: `templates/simulacao/_subnav.html`, `templates/simulacao/fabricas.html`, `templates/simulacao/_fabricas_content.html`
- Modify: `apps/simulacao/views.py`, `apps/simulacao/urls.py`, `templates/simulacao/_cenarios_content.html`, `templates_django/base.html`
- Create: `apps/simulacao/tests/test_views_fabricas.py`

**Interfaces:**
- Consumes: `Cenario`, `Fabrica` (Fase 2), `login_required` pattern (Task 4).
- Produces: URL `simulacao:fabricas_grid` (`/simulacao/cenarios/<cenario_id>/fabricas/`); `apps.simulacao.columns.FABRICA_COLUMNS`; `static/simulacao/js/grid_editor.js`'s `initGridEditor(tableElementId, colunasElementId, linhasElementId, formId)` — the shared entry point every later grid template calls; `templates/simulacao/_subnav.html` (starts with 1 tab, grows through Task 9).

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_views_fabricas.py`:
```python
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario, Fabrica

User = get_user_model()


class FabricasGridViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica 1',
            capacidade_estatica=1000, capacidade_esmagamento_diaria=100,
            capacidade_recebimento_diaria=100, limite_caminhoes=10,
            carga_media_caminhao=30, estoque_inicial=500,
        )
        self.url = reverse('simulacao:fabricas_grid', kwargs={'cenario_id': self.cenario.id})

    def test_requer_login(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_pagina_completa_sem_htmx(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '<html')

    def test_partial_com_htmx_nao_repete_html_base(self):
        self.client.force_login(self.user)

        response = self.client.get(self.url, HTTP_HX_REQUEST='true')

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '<html')
        self.assertContains(response, 'Fábrica 1')

    def test_cenario_de_outra_cooperativa_404(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        cenario_b = Cenario.all_cooperativas.create(cooperativa=outra_cooperativa, nome='Cenário B')
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('simulacao:fabricas_grid', kwargs={'cenario_id': cenario_b.id})
        )

        self.assertEqual(response.status_code, 404)

    def test_post_atualiza_fabrica_existente(self):
        self.client.force_login(self.user)
        linhas = [{
            'id': self.fabrica.id,
            'capacidade_estatica': 1500, 'capacidade_esmagamento_diaria': 120,
            'capacidade_recebimento_diaria': 110, 'limite_caminhoes': 12,
            'carga_media_caminhao': 32, 'estoque_inicial': 600,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.fabrica.refresh_from_db()
        self.assertEqual(self.fabrica.capacidade_estatica, 1500)
        self.assertEqual(self.fabrica.limite_caminhoes, 12)

    def test_post_com_valor_invalido_nao_salva_nada(self):
        self.client.force_login(self.user)
        linhas = [{
            'id': self.fabrica.id,
            'capacidade_estatica': 'não-é-um-número', 'capacidade_esmagamento_diaria': 120,
            'capacidade_recebimento_diaria': 110, 'limite_caminhoes': 12,
            'carga_media_caminhao': 32, 'estoque_inicial': 600,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 400)
        self.fabrica.refresh_from_db()
        self.assertEqual(self.fabrica.capacidade_estatica, 1000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_views_fabricas.py -v`
Expected: FAIL with `NoReverseMatch: 'simulacao' is not a registered namespace` or similar (URL doesn't exist yet).

- [ ] **Step 3: Write the column config, the shared JS, the view, and templates**

`apps/simulacao/columns.py`:
```python
"""Config explícito de colunas por grade Tabulator (ver spec
2026-08-23-fase5-ui-dados-cenarios-design.md, §4 -- não é introspecção
genérica do model, são grades fixas com necessidades diferentes o
bastante para não valer a abstração)."""

FABRICA_COLUMNS = [
    {"field": "id", "label": "ID", "type": "number", "editable": False, "visible": False},
    {"field": "nome", "label": "Fábrica", "type": "text", "editable": False},
    {"field": "capacidade_estatica", "label": "Capacidade Estática (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "capacidade_esmagamento_diaria", "label": "Esmagamento Diário (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "capacidade_recebimento_diaria", "label": "Recebimento Diário (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "limite_caminhoes", "label": "Limite de Caminhões", "type": "number", "editable": True, "decimals": 0},
    {"field": "carga_media_caminhao", "label": "Carga Média (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "estoque_inicial", "label": "Estoque Inicial (Ton)", "type": "number", "editable": True, "decimals": 1},
]
```

`static/simulacao/js/grid_editor.js`:
```javascript
function formatarNumeroPtBr(cell, decimais) {
    const valor = cell.getValue();
    if (valor === null || valor === undefined || valor === "") return "";
    return Number(valor).toLocaleString("pt-BR", {
        minimumFractionDigits: decimais, maximumFractionDigits: decimais,
    });
}

function editorNumeroPtBr(decimais) {
    return function (cell, onRendered, success, cancel) {
        const input = document.createElement("input");
        input.value = cell.getValue() ?? "";
        input.classList.add("tabulator-editor-numero");
        const mask = IMask(input, {
            mask: Number, radix: ",", thousandsSeparator: ".",
            scale: decimais, padFractionalZeros: false, normalizeZeros: true,
        });
        onRendered(function () { input.focus(); });
        function salvar() {
            success(mask.unmaskedValue === "" ? null : Number(mask.unmaskedValue));
        }
        input.addEventListener("blur", salvar);
        input.addEventListener("keydown", function (e) {
            if (e.key === "Enter") salvar();
            if (e.key === "Escape") cancel();
        });
        return input;
    };
}

function construirColunasTabulator(colunas) {
    return colunas.map(function (col) {
        if (col.visible === false) {
            return { title: col.label, field: col.field, visible: false };
        }
        if (col.type === "number" && col.editable) {
            const decimais = col.decimals ?? 1;
            return {
                title: col.label, field: col.field, hozAlign: "right",
                formatter: function (cell) { return formatarNumeroPtBr(cell, decimais); },
                editor: editorNumeroPtBr(decimais),
            };
        }
        if (col.type === "date" && col.editable) {
            return {
                title: col.label, field: col.field, editor: "date",
                editorParams: { format: "dd/MM/yyyy" },
                formatter: "date", formatterParams: { outputFormat: "dd/MM/yyyy" },
            };
        }
        return { title: col.label, field: col.field, editable: false };
    });
}

function initGridEditor(tableElementId, colunasElementId, linhasElementId, formId) {
    const colunas = JSON.parse(document.getElementById(colunasElementId).textContent);
    const linhas = JSON.parse(document.getElementById(linhasElementId).textContent);

    const table = new Tabulator("#" + tableElementId, {
        data: linhas, layout: "fitColumns", columns: construirColunasTabulator(colunas),
    });

    document.getElementById(formId).addEventListener("htmx:configRequest", function (evt) {
        evt.detail.parameters.linhas_json = JSON.stringify(table.getData());
    });

    return table;
}
```

Modify `templates_django/base.html` — add Tabulator/IMask CDN tags right before `{% block extra_head %}{% endblock %}`:
```html
    <link href="https://cdn.jsdelivr.net/npm/tabulator-tables@6/dist/css/tabulator.min.css" rel="stylesheet">
    <script src="https://cdn.jsdelivr.net/npm/tabulator-tables@6/dist/js/tabulator.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/imask@7/dist/imask.min.js"></script>
    <script src="{% static 'simulacao/js/grid_editor.js' %}"></script>
```

`templates/simulacao/_subnav.html`:
```html
<div class="tabs tabs-boxed mb-4">
    <a href="{% url 'simulacao:fabricas_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:fabricas_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'fabricas' %}tab-active{% endif %}">Fábricas</a>
</div>
```

`templates/simulacao/fabricas.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="cenario-content">
    {% include "simulacao/_fabricas_content.html" %}
</div>
{% endblock %}
```

`templates/simulacao/_fabricas_content.html`:
```html
{% include "simulacao/_subnav.html" %}

<form hx-post="{% url 'simulacao:fabricas_grid' cenario_id=cenario.id %}" hx-target="#cenario-content" hx-swap="outerHTML" id="form-fabricas">
    {% csrf_token %}
    <div id="tabulator-fabricas"></div>
    <button type="submit" class="rounded bg-[--cor-primaria] hover:bg-[--cor-primaria-hover] text-white px-4 py-2 mt-4">
        Salvar Alterações Fábricas
    </button>
</form>

{{ columns|json_script:"colunas-fabricas" }}
{{ rows|json_script:"linhas-fabricas" }}
<script>
    initGridEditor("tabulator-fabricas", "colunas-fabricas", "linhas-fabricas", "form-fabricas");
</script>
```

Modify `apps/simulacao/views.py` — replace the top-of-file import block with:
```python
import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render

from apps.simulacao import services
from apps.simulacao.columns import FABRICA_COLUMNS
from apps.simulacao.models import Cenario, Fabrica
```

Append below `cenarios_list`:
```python
@login_required
def fabricas_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_fabricas(cenario, linhas)
        except (ValueError, TypeError, Fabrica.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar fábricas: {exc}")

    fabricas = list(Fabrica.objects.filter(cenario_id=cenario.id).order_by('nome'))
    rows = [
        {
            "id": f.id, "nome": f.nome,
            "capacidade_estatica": f.capacidade_estatica,
            "capacidade_esmagamento_diaria": f.capacidade_esmagamento_diaria,
            "capacidade_recebimento_diaria": f.capacidade_recebimento_diaria,
            "limite_caminhoes": f.limite_caminhoes,
            "carga_media_caminhao": f.carga_media_caminhao,
            "estoque_inicial": f.estoque_inicial,
        }
        for f in fabricas
    ]
    context = {"cenario": cenario, "active": "fabricas", "columns": FABRICA_COLUMNS, "rows": rows}
    template = 'simulacao/_fabricas_content.html' if request.htmx else 'simulacao/fabricas.html'
    return render(request, template, context)


def _salvar_fabricas(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            fabrica_id = linha.get('id')
            if not fabrica_id:
                continue
            fabrica = Fabrica.objects.get(id=fabrica_id, cenario_id=cenario.id)
            fabrica.capacidade_estatica = float(linha['capacidade_estatica'])
            fabrica.capacidade_esmagamento_diaria = float(linha['capacidade_esmagamento_diaria'])
            fabrica.capacidade_recebimento_diaria = float(linha['capacidade_recebimento_diaria'])
            fabrica.limite_caminhoes = int(linha['limite_caminhoes'])
            fabrica.carga_media_caminhao = float(linha['carga_media_caminhao'])
            fabrica.estoque_inicial = float(linha['estoque_inicial'])
            fabrica.full_clean()
            fabrica.save()
```

Modify `apps/simulacao/urls.py` — append the new path:
```python
    path('cenarios/<int:cenario_id>/fabricas/', views.fabricas_grid, name='fabricas_grid'),
```

Modify `templates/simulacao/_cenarios_content.html` — replace the hand-written link with a real one:
```html
            <a href="{% url 'simulacao:fabricas_grid' cenario_id=cenario.id %}" class="text-[--cor-primaria] hover:underline">
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_views_fabricas.py -v`
Expected: PASS (6 passed)

Run: `pytest apps/simulacao/ -v`
Expected: all still passing.

- [ ] **Step 5: Commit**

```bash
git add static/simulacao/js/grid_editor.js apps/simulacao/columns.py templates/simulacao/_subnav.html templates/simulacao/fabricas.html templates/simulacao/_fabricas_content.html apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/_cenarios_content.html templates_django/base.html apps/simulacao/tests/test_views_fabricas.py
git commit -m "feat(fase5): grade de Fabricas + fundacao Tabulator/IMask"
```

---

### Task 6: Grade de Armazéns (+ criação de linha nova)

**Files:**
- Modify: `apps/simulacao/columns.py`, `apps/simulacao/views.py`, `apps/simulacao/urls.py`, `templates/simulacao/_subnav.html`
- Create: `templates/simulacao/armazens.html`, `templates/simulacao/_armazens_content.html`
- Create: `apps/simulacao/tests/test_views_armazens.py`

**Interfaces:**
- Consumes: `Armazem` (Fase 2), `initGridEditor` / `_subnav.html` pattern (Task 5).
- Produces: URL `simulacao:armazens_grid`; `apps.simulacao.columns.ARMAZEM_COLUMNS`.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_views_armazens.py`:
```python
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario

User = get_user_model()


class ArmazensGridViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém 1',
            capacidade_estatica=800, capacidade_expedicao_diaria=50, estoque_inicial=200,
        )
        self.url = reverse('simulacao:armazens_grid', kwargs={'cenario_id': self.cenario.id})
        self.client.force_login(self.user)

    def test_pagina_completa(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Armazém 1')

    def test_post_atualiza_armazem_existente_incluindo_nome(self):
        linhas = [{
            'id': self.armazem.id, 'nome': 'Armazém Renomeado',
            'capacidade_estatica': 900, 'capacidade_expedicao_diaria': 60, 'estoque_inicial': 250,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.armazem.refresh_from_db()
        self.assertEqual(self.armazem.nome, 'Armazém Renomeado')
        self.assertEqual(self.armazem.capacidade_estatica, 900)

    def test_post_sem_id_cria_novo_armazem(self):
        linhas = [{
            'id': None, 'nome': 'Armazém Novo',
            'capacidade_estatica': 500, 'capacidade_expedicao_diaria': 40, 'estoque_inicial': 0,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        novo = Armazem.objects.get(cenario_id=self.cenario.id, nome='Armazém Novo')
        self.assertEqual(novo.capacidade_estatica, 500)

    def test_post_linha_sem_id_e_sem_nome_e_ignorada(self):
        linhas = [{'id': None, 'nome': '', 'capacidade_estatica': 1, 'capacidade_expedicao_diaria': 1, 'estoque_inicial': 0}]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Armazem.objects.filter(cenario_id=self.cenario.id).count(), 1)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_views_armazens.py -v`
Expected: FAIL with `NoReverseMatch`.

- [ ] **Step 3: Implement**

Append to `apps/simulacao/columns.py`:
```python
ARMAZEM_COLUMNS = [
    {"field": "id", "label": "ID", "type": "number", "editable": False, "visible": False},
    {"field": "nome", "label": "Armazém", "type": "text", "editable": True},
    {"field": "capacidade_estatica", "label": "Capacidade Estática (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "capacidade_expedicao_diaria", "label": "Expedição Diária (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "estoque_inicial", "label": "Estoque Inicial (Ton)", "type": "number", "editable": True, "decimals": 1},
]
```

Modify `apps/simulacao/views.py` — add `Armazem` to the model import (`from apps.simulacao.models import Armazem, Cenario, Fabrica`) and `ARMAZEM_COLUMNS` to the columns import (`from apps.simulacao.columns import ARMAZEM_COLUMNS, FABRICA_COLUMNS`), then append:
```python
@login_required
def armazens_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_armazens(cenario, linhas)
        except (ValueError, TypeError, Armazem.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar armazéns: {exc}")

    armazens = list(Armazem.objects.filter(cenario_id=cenario.id).order_by('nome'))
    rows = [
        {
            "id": a.id, "nome": a.nome,
            "capacidade_estatica": a.capacidade_estatica,
            "capacidade_expedicao_diaria": a.capacidade_expedicao_diaria,
            "estoque_inicial": a.estoque_inicial,
        }
        for a in armazens
    ]
    context = {"cenario": cenario, "active": "armazens", "columns": ARMAZEM_COLUMNS, "rows": rows}
    template = 'simulacao/_armazens_content.html' if request.htmx else 'simulacao/armazens.html'
    return render(request, template, context)


def _salvar_armazens(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            armazem_id = linha.get('id')
            if armazem_id:
                armazem = Armazem.objects.get(id=armazem_id, cenario_id=cenario.id)
            else:
                if not linha.get('nome'):
                    continue
                armazem = Armazem(cooperativa_id=cenario.cooperativa_id, cenario_id=cenario.id)
            armazem.nome = linha['nome']
            armazem.capacidade_estatica = float(linha['capacidade_estatica'])
            armazem.capacidade_expedicao_diaria = float(linha['capacidade_expedicao_diaria'])
            armazem.estoque_inicial = float(linha.get('estoque_inicial') or 0)
            armazem.full_clean()
            armazem.save()
```

Modify `apps/simulacao/urls.py` — append:
```python
    path('cenarios/<int:cenario_id>/armazens/', views.armazens_grid, name='armazens_grid'),
```

Modify `templates/simulacao/_subnav.html` — append a second tab inside the same `<div class="tabs tabs-boxed mb-4">`:
```html
    <a href="{% url 'simulacao:armazens_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:armazens_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'armazens' %}tab-active{% endif %}">Armazéns</a>
```

`templates/simulacao/armazens.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="cenario-content">
    {% include "simulacao/_armazens_content.html" %}
</div>
{% endblock %}
```

`templates/simulacao/_armazens_content.html`:
```html
{% include "simulacao/_subnav.html" %}

<form hx-post="{% url 'simulacao:armazens_grid' cenario_id=cenario.id %}" hx-target="#cenario-content" hx-swap="outerHTML" id="form-armazens">
    {% csrf_token %}
    <div id="tabulator-armazens"></div>
    <button type="submit" class="rounded bg-[--cor-primaria] hover:bg-[--cor-primaria-hover] text-white px-4 py-2 mt-4">
        Salvar Alterações Armazéns
    </button>
</form>

{{ columns|json_script:"colunas-armazens" }}
{{ rows|json_script:"linhas-armazens" }}
<script>
    initGridEditor("tabulator-armazens", "colunas-armazens", "linhas-armazens", "form-armazens");
</script>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_views_armazens.py -v`
Expected: PASS (4 passed)

Run: `pytest apps/simulacao/ -v`
Expected: all still passing.

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/columns.py apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/_subnav.html templates/simulacao/armazens.html templates/simulacao/_armazens_content.html apps/simulacao/tests/test_views_armazens.py
git commit -m "feat(fase5): grade de Armazens (com criacao de linha nova)"
```

---

### Task 7: Grade de Rotas (com resolução de Origem/Destino)

**Files:**
- Modify: `apps/simulacao/columns.py`, `apps/simulacao/views.py`, `apps/simulacao/urls.py`, `templates/simulacao/_subnav.html`
- Create: `templates/simulacao/rotas.html`, `templates/simulacao/_rotas_content.html`
- Create: `apps/simulacao/tests/test_views_rotas.py`

**Interfaces:**
- Consumes: `Rota`, `Armazem`, `Fabrica` (Fase 2); grid pattern (Task 5).
- Produces: URL `simulacao:rotas_grid`; `apps.simulacao.columns.ROTA_COLUMNS`.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_views_rotas.py`:
```python
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, Fabrica, Rota

User = get_user_model()


class RotasGridViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém 1',
            capacidade_estatica=800, capacidade_expedicao_diaria=50, estoque_inicial=200,
        )
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica 1',
            capacidade_estatica=1000, capacidade_esmagamento_diaria=100,
            capacidade_recebimento_diaria=100, limite_caminhoes=10,
            carga_media_caminhao=30, estoque_inicial=500,
        )
        self.rota = Rota.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            armazem=self.armazem, fabrica=self.fabrica,
            distancia_km=120, custo_frete_ton=45, custo_frete_entressafra=30,
        )
        self.url = reverse('simulacao:rotas_grid', kwargs={'cenario_id': self.cenario.id})
        self.client.force_login(self.user)

    def test_pagina_mostra_origem_e_destino_pelo_nome(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Armazém 1')
        self.assertContains(response, 'Fábrica 1')

    def test_post_atualiza_custos_e_distancia(self):
        linhas = [{
            'id': self.rota.id,
            'distancia_km': 150, 'custo_frete_ton': 50, 'custo_frete_entressafra': 35,
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.rota.refresh_from_db()
        self.assertEqual(self.rota.distancia_km, 150)
        self.assertEqual(self.rota.custo_frete_entressafra, 35)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_views_rotas.py -v`
Expected: FAIL with `NoReverseMatch`.

- [ ] **Step 3: Implement**

Append to `apps/simulacao/columns.py`:
```python
ROTA_COLUMNS = [
    {"field": "id", "label": "ID", "type": "number", "editable": False, "visible": False},
    {"field": "origem", "label": "Origem", "type": "text", "editable": False},
    {"field": "destino", "label": "Destino", "type": "text", "editable": False},
    {"field": "distancia_km", "label": "Distância (km)", "type": "number", "editable": True, "decimals": 1},
    {"field": "custo_frete_ton", "label": "Custo Safra (R$/Ton)", "type": "number", "editable": True, "decimals": 2},
    {"field": "custo_frete_entressafra", "label": "Custo Entressafra (R$/Ton)", "type": "number", "editable": True, "decimals": 2},
]
```

Modify `apps/simulacao/views.py` — add `Rota` to the model import and `ROTA_COLUMNS` to the columns import, then append:
```python
@login_required
def rotas_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_rotas(cenario, linhas)
        except (ValueError, TypeError, Rota.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar rotas: {exc}")

    rotas = list(Rota.objects.filter(cenario_id=cenario.id).select_related('armazem', 'fabrica'))
    rows = [
        {
            "id": r.id, "origem": r.armazem.nome, "destino": r.fabrica.nome,
            "distancia_km": r.distancia_km,
            "custo_frete_ton": r.custo_frete_ton,
            "custo_frete_entressafra": r.custo_frete_entressafra,
        }
        for r in rotas
    ]
    context = {"cenario": cenario, "active": "rotas", "columns": ROTA_COLUMNS, "rows": rows}
    template = 'simulacao/_rotas_content.html' if request.htmx else 'simulacao/rotas.html'
    return render(request, template, context)


def _salvar_rotas(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            rota_id = linha.get('id')
            if not rota_id:
                continue
            rota = Rota.objects.get(id=rota_id, cenario_id=cenario.id)
            rota.distancia_km = float(linha['distancia_km'])
            rota.custo_frete_ton = float(linha['custo_frete_ton'])
            rota.custo_frete_entressafra = float(linha['custo_frete_entressafra'])
            rota.full_clean()
            rota.save()
```

Modify `apps/simulacao/urls.py` — append:
```python
    path('cenarios/<int:cenario_id>/rotas/', views.rotas_grid, name='rotas_grid'),
```

Modify `templates/simulacao/_subnav.html` — append a third tab:
```html
    <a href="{% url 'simulacao:rotas_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:rotas_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'rotas' %}tab-active{% endif %}">Rotas</a>
```

`templates/simulacao/rotas.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="cenario-content">
    {% include "simulacao/_rotas_content.html" %}
</div>
{% endblock %}
```

`templates/simulacao/_rotas_content.html`:
```html
{% include "simulacao/_subnav.html" %}

<form hx-post="{% url 'simulacao:rotas_grid' cenario_id=cenario.id %}" hx-target="#cenario-content" hx-swap="outerHTML" id="form-rotas">
    {% csrf_token %}
    <div id="tabulator-rotas"></div>
    <button type="submit" class="rounded bg-[--cor-primaria] hover:bg-[--cor-primaria-hover] text-white px-4 py-2 mt-4">
        Salvar Alterações Rotas
    </button>
</form>

{{ columns|json_script:"colunas-rotas" }}
{{ rows|json_script:"linhas-rotas" }}
<script>
    initGridEditor("tabulator-rotas", "colunas-rotas", "linhas-rotas", "form-rotas");
</script>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_views_rotas.py -v`
Expected: PASS (2 passed)

Run: `pytest apps/simulacao/ -v`
Expected: all still passing.

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/columns.py apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/_subnav.html templates/simulacao/rotas.html templates/simulacao/_rotas_content.html apps/simulacao/tests/test_views_rotas.py
git commit -m "feat(fase5): grade de Rotas"
```

---

### Task 8: Grade de Previsões (Fábrica + Armazém, 2 sub-grades)

**Files:**
- Modify: `apps/simulacao/columns.py`, `apps/simulacao/views.py`, `apps/simulacao/urls.py`, `templates/simulacao/_subnav.html`, `static/simulacao/js/grid_editor.js`
- Create: `templates/simulacao/previsoes.html`, `templates/simulacao/_previsoes_content.html`
- Create: `apps/simulacao/tests/test_views_previsoes.py`

**Interfaces:**
- Consumes: `PrevisaoFabrica`, `PrevisaoArmazem` (Fase 2); grid pattern (Task 5).
- Produces: URL `simulacao:previsoes_grid`; `apps.simulacao.columns.PREVISAO_FABRICA_COLUMNS`/`PREVISAO_ARMAZEM_COLUMNS`; `initGridEditor`'s new optional 5th argument (`paramName`), needed because this is the first screen with two Tabulator tables sharing one `<form>`.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_views_previsoes.py`:
```python
import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, Fabrica, PrevisaoArmazem, PrevisaoFabrica

User = get_user_model()


class PrevisoesGridViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.fabrica = Fabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Fábrica 1',
            capacidade_estatica=1000, capacidade_esmagamento_diaria=100,
            capacidade_recebimento_diaria=100, limite_caminhoes=10,
            carga_media_caminhao=30, estoque_inicial=500,
        )
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém 1',
            capacidade_estatica=800, capacidade_expedicao_diaria=50, estoque_inicial=200,
        )
        self.previsao_fab = PrevisaoFabrica.all_cooperativas.create(
            cooperativa=self.cooperativa, fabrica=self.fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=300, vendas=100,
        )
        self.previsao_arm = PrevisaoArmazem.all_cooperativas.create(
            cooperativa=self.cooperativa, armazem=self.armazem,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=200, vendas=50,
        )
        self.url = reverse('simulacao:previsoes_grid', kwargs={'cenario_id': self.cenario.id})
        self.client.force_login(self.user)

    def test_pagina_mostra_as_duas_sub_grades(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Fábrica 1')
        self.assertContains(response, 'Armazém 1')

    def test_post_atualiza_ambas_previsoes_numa_transacao(self):
        linhas_fabrica = [{'id': self.previsao_fab.id, 'recebimento_produtor': 350, 'vendas': 120}]
        linhas_armazem = [{'id': self.previsao_arm.id, 'recebimento_produtor': 250, 'vendas': 60}]

        response = self.client.post(self.url, {
            'linhas_fabrica_json': json.dumps(linhas_fabrica),
            'linhas_armazem_json': json.dumps(linhas_armazem),
        })

        self.assertEqual(response.status_code, 200)
        self.previsao_fab.refresh_from_db()
        self.previsao_arm.refresh_from_db()
        self.assertEqual(self.previsao_fab.recebimento_produtor, 350)
        self.assertEqual(self.previsao_arm.vendas, 60)

    def test_previsao_de_outra_cooperativa_nao_aparece(self):
        outra_cooperativa = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        outro_cenario = Cenario.all_cooperativas.create(cooperativa=outra_cooperativa, nome='Cenário B')
        outra_fabrica = Fabrica.all_cooperativas.create(
            cooperativa=outra_cooperativa, cenario=outro_cenario, nome='Fábrica B',
            capacidade_estatica=1, capacidade_esmagamento_diaria=1,
            capacidade_recebimento_diaria=1, limite_caminhoes=1,
            carga_media_caminhao=1, estoque_inicial=0,
        )
        PrevisaoFabrica.all_cooperativas.create(
            cooperativa=outra_cooperativa, fabrica=outra_fabrica,
            mes_referencia=datetime.date(2026, 1, 1), recebimento_produtor=999, vendas=999,
        )

        response = self.client.get(self.url)

        self.assertNotContains(response, 'Fábrica B')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_views_previsoes.py -v`
Expected: FAIL with `NoReverseMatch`.

- [ ] **Step 3: Implement**

First, modify `static/simulacao/js/grid_editor.js`'s `initGridEditor` function — this screen is the first with two Tabulator tables sharing one `<form>`, so the previous hardcoded `linhas_json` parameter name would make the second table's data silently overwrite the first's. Add an optional 5th argument:
```javascript
function initGridEditor(tableElementId, colunasElementId, linhasElementId, formId, paramName) {
    paramName = paramName || "linhas_json";
    const colunas = JSON.parse(document.getElementById(colunasElementId).textContent);
    const linhas = JSON.parse(document.getElementById(linhasElementId).textContent);

    const table = new Tabulator("#" + tableElementId, {
        data: linhas, layout: "fitColumns", columns: construirColunasTabulator(colunas),
    });

    document.getElementById(formId).addEventListener("htmx:configRequest", function (evt) {
        evt.detail.parameters[paramName] = JSON.stringify(table.getData());
    });

    return table;
}
```
(This is a backward-compatible change: Tasks 5-7's calls omit the 5th argument and keep using `"linhas_json"` exactly as before — their tests must still pass unmodified.)

Append to `apps/simulacao/columns.py`:
```python
PREVISAO_FABRICA_COLUMNS = [
    {"field": "id", "label": "ID", "type": "number", "editable": False, "visible": False},
    {"field": "fabrica", "label": "Fábrica", "type": "text", "editable": False},
    {"field": "mes_referencia", "label": "Mês", "type": "text", "editable": False},
    {"field": "recebimento_produtor", "label": "Recebimento Produtor (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "vendas", "label": "Vendas (Ton)", "type": "number", "editable": True, "decimals": 1},
]

PREVISAO_ARMAZEM_COLUMNS = [
    {"field": "id", "label": "ID", "type": "number", "editable": False, "visible": False},
    {"field": "armazem", "label": "Armazém", "type": "text", "editable": False},
    {"field": "mes_referencia", "label": "Mês", "type": "text", "editable": False},
    {"field": "recebimento_produtor", "label": "Recebimento Produtor (Ton)", "type": "number", "editable": True, "decimals": 1},
    {"field": "vendas", "label": "Vendas (Ton)", "type": "number", "editable": True, "decimals": 1},
]
```

Modify `apps/simulacao/views.py` — add `PrevisaoArmazem, PrevisaoFabrica` to the model import and `PREVISAO_ARMAZEM_COLUMNS, PREVISAO_FABRICA_COLUMNS` to the columns import, then append:
```python
@login_required
def previsoes_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas_fabrica = json.loads(request.POST.get('linhas_fabrica_json', '[]'))
        linhas_armazem = json.loads(request.POST.get('linhas_armazem_json', '[]'))
        try:
            _salvar_previsoes(cenario, linhas_fabrica, linhas_armazem)
        except (ValueError, TypeError, PrevisaoFabrica.DoesNotExist, PrevisaoArmazem.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar previsões: {exc}")

    previsoes_fab = list(
        PrevisaoFabrica.objects.filter(fabrica__cenario_id=cenario.id).select_related('fabrica')
    )
    previsoes_arm = list(
        PrevisaoArmazem.objects.filter(armazem__cenario_id=cenario.id).select_related('armazem')
    )
    rows_fabrica = [
        {
            "id": p.id, "fabrica": p.fabrica.nome, "mes_referencia": p.mes_referencia.strftime('%Y-%m'),
            "recebimento_produtor": p.recebimento_produtor, "vendas": p.vendas,
        }
        for p in previsoes_fab
    ]
    rows_armazem = [
        {
            "id": p.id, "armazem": p.armazem.nome, "mes_referencia": p.mes_referencia.strftime('%Y-%m'),
            "recebimento_produtor": p.recebimento_produtor, "vendas": p.vendas,
        }
        for p in previsoes_arm
    ]
    context = {
        "cenario": cenario, "active": "previsoes",
        "columns_fabrica": PREVISAO_FABRICA_COLUMNS, "rows_fabrica": rows_fabrica,
        "columns_armazem": PREVISAO_ARMAZEM_COLUMNS, "rows_armazem": rows_armazem,
    }
    template = 'simulacao/_previsoes_content.html' if request.htmx else 'simulacao/previsoes.html'
    return render(request, template, context)


def _salvar_previsoes(cenario, linhas_fabrica, linhas_armazem):
    with transaction.atomic():
        for linha in linhas_fabrica:
            previsao_id = linha.get('id')
            if not previsao_id:
                continue
            previsao = PrevisaoFabrica.objects.get(id=previsao_id, fabrica__cenario_id=cenario.id)
            previsao.recebimento_produtor = float(linha['recebimento_produtor'])
            previsao.vendas = float(linha['vendas'])
            previsao.full_clean()
            previsao.save()
        for linha in linhas_armazem:
            previsao_id = linha.get('id')
            if not previsao_id:
                continue
            previsao = PrevisaoArmazem.objects.get(id=previsao_id, armazem__cenario_id=cenario.id)
            previsao.recebimento_produtor = float(linha['recebimento_produtor'])
            previsao.vendas = float(linha['vendas'])
            previsao.full_clean()
            previsao.save()
```

Modify `apps/simulacao/urls.py` — append:
```python
    path('cenarios/<int:cenario_id>/previsoes/', views.previsoes_grid, name='previsoes_grid'),
```

Modify `templates/simulacao/_subnav.html` — append a fourth tab:
```html
    <a href="{% url 'simulacao:previsoes_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:previsoes_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'previsoes' %}tab-active{% endif %}">Previsões</a>
```

`templates/simulacao/previsoes.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="cenario-content">
    {% include "simulacao/_previsoes_content.html" %}
</div>
{% endblock %}
```

`templates/simulacao/_previsoes_content.html`:
```html
{% include "simulacao/_subnav.html" %}

<form hx-post="{% url 'simulacao:previsoes_grid' cenario_id=cenario.id %}" hx-target="#cenario-content" hx-swap="outerHTML" id="form-previsoes">
    {% csrf_token %}

    <h3 class="font-medium mb-2">Fábricas</h3>
    <div id="tabulator-previsoes-fabrica" class="mb-6"></div>

    <h3 class="font-medium mb-2">Armazéns</h3>
    <div id="tabulator-previsoes-armazem" class="mb-6"></div>

    <button type="submit" class="rounded bg-[--cor-primaria] hover:bg-[--cor-primaria-hover] text-white px-4 py-2">
        Salvar Previsões
    </button>
</form>

{{ columns_fabrica|json_script:"colunas-previsoes-fabrica" }}
{{ rows_fabrica|json_script:"linhas-previsoes-fabrica" }}
{{ columns_armazem|json_script:"colunas-previsoes-armazem" }}
{{ rows_armazem|json_script:"linhas-previsoes-armazem" }}
<script>
    initGridEditor("tabulator-previsoes-fabrica", "colunas-previsoes-fabrica", "linhas-previsoes-fabrica", "form-previsoes", "linhas_fabrica_json");
    initGridEditor("tabulator-previsoes-armazem", "colunas-previsoes-armazem", "linhas-previsoes-armazem", "form-previsoes", "linhas_armazem_json");
</script>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_views_previsoes.py -v`
Expected: PASS (3 passed)

Run: `pytest apps/simulacao/ -v`
Expected: all still passing — specifically re-check Tasks 5-7's view tests still pass with the `paramName` change (they rely on the default).

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/columns.py apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/_subnav.html templates/simulacao/previsoes.html templates/simulacao/_previsoes_content.html static/simulacao/js/grid_editor.js apps/simulacao/tests/test_views_previsoes.py
git commit -m "feat(fase5): grade de Previsoes (fabrica + armazem)"
```

---

### Task 9: Grade de Datas de Safra

**Files:**
- Modify: `apps/simulacao/columns.py`, `apps/simulacao/views.py`, `apps/simulacao/urls.py`, `templates/simulacao/_subnav.html`
- Create: `templates/simulacao/safras.html`, `templates/simulacao/_safras_content.html`
- Create: `apps/simulacao/tests/test_views_safras.py`

**Interfaces:**
- Consumes: `SafraUnidade`, `Armazem`, `Fabrica` (Fase 2); grid pattern (Task 5), `paramName` support (Task 8).
- Produces: URL `simulacao:safras_grid`; `apps.simulacao.columns.SAFRA_COLUMNS`. Last task of this plan.

- [ ] **Step 1: Write the failing tests**

`apps/simulacao/tests/test_views_safras.py`:
```python
import datetime
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Armazem, Cenario, SafraUnidade

User = get_user_model()


class SafrasGridViewTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria', password='senha-forte-123',
            cooperativa=self.cooperativa, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.cooperativa, nome='Cenário Teste')
        self.armazem = Armazem.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario, nome='Armazém 1',
            capacidade_estatica=800, capacidade_expedicao_diaria=50, estoque_inicial=200,
        )
        self.safra = SafraUnidade.all_cooperativas.create(
            cooperativa=self.cooperativa, cenario=self.cenario,
            entidade_tipo='Armazém', entidade_id=self.armazem.id,
            data_inicio=datetime.date(2026, 1, 15), data_fim=datetime.date(2026, 4, 15),
        )
        self.url = reverse('simulacao:safras_grid', kwargs={'cenario_id': self.cenario.id})
        self.client.force_login(self.user)

    def test_pagina_mostra_nome_da_unidade(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Armazém 1')

    def test_post_atualiza_datas(self):
        linhas = [{
            'id': self.safra.id,
            'data_inicio': '2026-02-01', 'data_fim': '2026-05-01',
        }]

        response = self.client.post(self.url, {'linhas_json': json.dumps(linhas)})

        self.assertEqual(response.status_code, 200)
        self.safra.refresh_from_db()
        self.assertEqual(self.safra.data_inicio, datetime.date(2026, 2, 1))
        self.assertEqual(self.safra.data_fim, datetime.date(2026, 5, 1))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest apps/simulacao/tests/test_views_safras.py -v`
Expected: FAIL with `NoReverseMatch`.

- [ ] **Step 3: Implement**

Append to `apps/simulacao/columns.py`:
```python
SAFRA_COLUMNS = [
    {"field": "id", "label": "ID", "type": "number", "editable": False, "visible": False},
    {"field": "tipo", "label": "Tipo", "type": "text", "editable": False},
    {"field": "unidade", "label": "Unidade", "type": "text", "editable": False},
    {"field": "data_inicio", "label": "Início", "type": "date", "editable": True},
    {"field": "data_fim", "label": "Fim", "type": "date", "editable": True},
]
```

Modify `apps/simulacao/views.py` — add `SafraUnidade` to the model import, `SAFRA_COLUMNS` to the columns import, `import datetime` at the top of the file, then append:
```python
@login_required
def safras_grid(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)

    if request.method == 'POST':
        linhas = json.loads(request.POST.get('linhas_json', '[]'))
        try:
            _salvar_safras(cenario, linhas)
        except (ValueError, TypeError, SafraUnidade.DoesNotExist) as exc:
            return HttpResponseBadRequest(f"Erro ao salvar datas de safra: {exc}")

    safras = list(SafraUnidade.objects.filter(cenario_id=cenario.id))
    armazem_ids = {s.entidade_id for s in safras if s.entidade_tipo == 'Armazém'}
    fabrica_ids = {s.entidade_id for s in safras if s.entidade_tipo != 'Armazém'}
    armazens_map = {a.id: a.nome for a in Armazem.objects.filter(id__in=armazem_ids)} if armazem_ids else {}
    fabricas_map = {f.id: f.nome for f in Fabrica.objects.filter(id__in=fabrica_ids)} if fabrica_ids else {}

    rows = []
    for s in safras:
        if s.entidade_tipo == 'Armazém':
            unidade_nome = armazens_map.get(s.entidade_id, 'N/A')
        else:
            unidade_nome = fabricas_map.get(s.entidade_id, 'N/A')
        rows.append({
            "id": s.id, "tipo": s.entidade_tipo, "unidade": unidade_nome,
            "data_inicio": s.data_inicio.strftime('%Y-%m-%d'),
            "data_fim": s.data_fim.strftime('%Y-%m-%d'),
        })

    context = {"cenario": cenario, "active": "safras", "columns": SAFRA_COLUMNS, "rows": rows}
    template = 'simulacao/_safras_content.html' if request.htmx else 'simulacao/safras.html'
    return render(request, template, context)


def _salvar_safras(cenario, linhas):
    with transaction.atomic():
        for linha in linhas:
            safra_id = linha.get('id')
            if not safra_id:
                continue
            safra = SafraUnidade.objects.get(id=safra_id, cenario_id=cenario.id)
            safra.data_inicio = datetime.date.fromisoformat(linha['data_inicio'])
            safra.data_fim = datetime.date.fromisoformat(linha['data_fim'])
            safra.full_clean()
            safra.save()
```

Modify `apps/simulacao/urls.py` — append:
```python
    path('cenarios/<int:cenario_id>/safras/', views.safras_grid, name='safras_grid'),
```

Modify `templates/simulacao/_subnav.html` — append the fifth and final tab:
```html
    <a href="{% url 'simulacao:safras_grid' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:safras_grid' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'safras' %}tab-active{% endif %}">Datas de Safra</a>
```

`templates/simulacao/safras.html`:
```html
{% extends "base.html" %}
{% block content %}
<div id="cenario-content">
    {% include "simulacao/_safras_content.html" %}
</div>
{% endblock %}
```

`templates/simulacao/_safras_content.html`:
```html
{% include "simulacao/_subnav.html" %}

<form hx-post="{% url 'simulacao:safras_grid' cenario_id=cenario.id %}" hx-target="#cenario-content" hx-swap="outerHTML" id="form-safras">
    {% csrf_token %}
    <div id="tabulator-safras"></div>
    <button type="submit" class="rounded bg-[--cor-primaria] hover:bg-[--cor-primaria-hover] text-white px-4 py-2 mt-4">
        Salvar Datas
    </button>
</form>

{{ columns|json_script:"colunas-safras" }}
{{ rows|json_script:"linhas-safras" }}
<script>
    initGridEditor("tabulator-safras", "colunas-safras", "linhas-safras", "form-safras");
</script>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest apps/simulacao/tests/test_views_safras.py -v`
Expected: PASS (2 passed)

Run: `pytest apps/simulacao/ -v` and `pytest -v` (full repo suite)
Expected: all passing.

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Commit**

```bash
git add apps/simulacao/columns.py apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/_subnav.html templates/simulacao/safras.html templates/simulacao/_safras_content.html apps/simulacao/tests/test_views_safras.py
git commit -m "feat(fase5): grade de Datas de Safra"
```
