# Fase 5 — Fundação Django Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the Django 6 project skeleton (apps, settings, CI) plus the `Cooperativa`/`User`/`TenantManager` foundation that every later Fase 5 phase (port do domínio, UI, Procrastinate, auth, deploy) builds on — without touching the existing Streamlit/SQLAlchemy app, which keeps running unmodified until cutover (Fase 8).

**Architecture:** A new Django project (`config/`, `apps/core`, `apps/simulacao`, `apps/integracoes`) lives alongside the existing Streamlit files at the repo root. Multi-tenancy is schema-compartilhado: every tenant-scoped model will eventually inherit `apps.core.tenancy.CooperativaScopedModel`, whose `TenantManager` fails closed (empty queryset, never cross-tenant data) when no cooperativa is set in request context. `CooperativaScopeMiddleware` populates that context from `request.user.cooperativa_id` on every request. `apps.simulacao` and `apps.integracoes` are registered but stay empty in this phase — their models/engine port is Fase 5's next plan (Port do domínio).

**Tech Stack:** Django `>=6.0,<6.1`, PostgreSQL (via the already-pinned `psycopg2-binary`), `python-dotenv` (already pinned), `pytest-django`, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` (decisions #1, #3, #8; migration phase 1 "Fundação")

## Global Constraints

- Multi-tenancy is schema compartilhado + `cooperativa_id` (FK, `on_delete=PROTECT`) — never `django-tenants` (spec decision #1).
- All new development happens in the `Transbordo` repo (remote `origin`); never commit to the frozen `comigo` remote.
- Portuguese domain terms (`Cenario`, `Fabrica`, `Armazem`, `Rota`, `Safra`, `Cooperativa`, ...) are never translated — only the product brand name is in scope for the "Comigo"→"Transbordo" rename, and that rename is out of scope for this plan.
- CI is real from commit zero via GitHub Actions — this is a deliberate decision to not inherit the APP_Vector gap (spec decision #8).
- Documentation follows the APP_Vector convention: ADRs in `docs/decisions/`, numbered, `Status`/`Data`/`Contexto`/`Decisão`/`Consequências`, starting at `0001` (spec decision #9).
- Django `>=6.0,<6.1`, Python 3.12+ (this machine already runs 3.13.14 — no action needed).
- The existing Streamlit/SQLAlchemy app (`app.py`, `models.py`, `data_loader.py`, ...) and its `tests/` suite must keep working unmodified — the two stacks coexist in the same repo until Fase 8 (Cutover).

---

## File Structure

```
manage.py                          # new — Django entrypoint
config/
  __init__.py
  settings/
    __init__.py
    base.py                        # shared settings
    dev.py                         # DEBUG=True
    prod.py                        # DEBUG=False, proxy/SSL hardening
  urls.py
  wsgi.py
  asgi.py
apps/
  __init__.py
  core/
    __init__.py
    apps.py
    models.py                      # Cooperativa (Task 2), User (Task 3)
    admin.py
    tenancy.py                     # TenantManager, CooperativaScopedModel (Task 4)
    middleware.py                  # CooperativaScopeMiddleware (Task 4)
    migrations/__init__.py
    tests/
      __init__.py
      test_cooperativa.py          # Task 2
      test_user.py                 # Task 3
      test_tenancy.py              # Task 4
      test_middleware.py           # Task 4
  simulacao/
    __init__.py
    apps.py                        # registered, empty — models arrive in the next plan
    migrations/__init__.py
  integracoes/
    __init__.py
    apps.py                        # registered, empty — Django Ninja arrives in a later plan
    migrations/__init__.py
docs/decisions/
  0001-multi-tenancy-schema-compartilhado.md
  0002-settings-por-ambiente.md
  0003-tenant-isolation-fail-closed.md
  0004-ci-real-github-actions.md
.github/workflows/ci.yml
.env.example                       # new — documents DJANGO_DB_* alongside legacy DB_*
static/.gitkeep                    # new — keeps STATICFILES_DIRS from warning on an empty repo
requirements.txt                   # modified — adds Django
requirements-dev.txt                # modified — adds pytest-django
pytest.ini                          # modified — DJANGO_SETTINGS_MODULE, testpaths covers apps/
CLAUDE.md                           # modified — documents the coexisting Django stack
```

---

### Task 1: Django project skeleton (three apps, settings, CI plumbing)

**Files:**
- Create: `manage.py`, `config/__init__.py`, `config/settings/__init__.py`, `config/settings/base.py`, `config/settings/dev.py`, `config/settings/prod.py`, `config/urls.py`, `config/wsgi.py`, `config/asgi.py`
- Create: `apps/__init__.py`, `apps/core/__init__.py`, `apps/core/apps.py`, `apps/core/migrations/__init__.py`
- Create: `apps/simulacao/__init__.py`, `apps/simulacao/apps.py`, `apps/simulacao/migrations/__init__.py`
- Create: `apps/integracoes/__init__.py`, `apps/integracoes/apps.py`, `apps/integracoes/migrations/__init__.py`
- Create: `.env.example`, `static/.gitkeep`
- Modify: `requirements.txt`, `requirements-dev.txt`, `pytest.ini`, `CLAUDE.md`
- Create: `docs/decisions/0002-settings-por-ambiente.md`

**Interfaces:**
- Produces: `config.settings.dev` / `config.settings.prod` (importable settings modules selected via `DJANGO_SETTINGS_MODULE`), `INSTALLED_APPS` containing `apps.core`, `apps.simulacao`, `apps.integracoes`, `manage.py` as the Django CLI entrypoint. No `AUTH_USER_MODEL` yet (Task 3 sets it) and no custom `MIDDLEWARE` entries yet (Task 4 adds one).

- [ ] **Step 1: Scaffold the three apps**

`apps/__init__.py` (empty file — makes `apps` a namespace package so `apps.core`/`apps.simulacao`/`apps.integracoes` are importable).

`apps/core/__init__.py` — empty.
`apps/core/migrations/__init__.py` — empty.

`apps/core/apps.py`:
```python
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Núcleo'
```

`apps/simulacao/__init__.py` — empty.
`apps/simulacao/migrations/__init__.py` — empty.

`apps/simulacao/apps.py`:
```python
from django.apps import AppConfig


class SimulacaoConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.simulacao'
    verbose_name = 'Simulação'
```

`apps/integracoes/__init__.py` — empty.
`apps/integracoes/migrations/__init__.py` — empty.

`apps/integracoes/apps.py`:
```python
from django.apps import AppConfig


class IntegracoesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.integracoes'
    verbose_name = 'Integrações'
```

- [ ] **Step 2: Write the Django settings package**

`config/__init__.py` — empty.
`config/settings/__init__.py` — empty.

`config/settings/base.py`:
```python
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(BASE_DIR / '.env')

SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', 'change-me')
ALLOWED_HOSTS = (
    os.getenv('DJANGO_ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')
    if os.getenv('DJANGO_ALLOWED_HOSTS')
    else ['localhost', '127.0.0.1']
)

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'apps.core',
    'apps.simulacao',
    'apps.integracoes',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# DJANGO_DB_* é deliberadamente distinto de DB_* (usado pelo stack
# Streamlit/SQLAlchemy no mesmo .env) — ver docs/decisions/0002.
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DJANGO_DB_NAME', 'transbordo'),
        'USER': os.getenv('DJANGO_DB_USER', 'transbordo'),
        'PASSWORD': os.getenv('DJANGO_DB_PASSWORD', ''),
        'HOST': os.getenv('DJANGO_DB_HOST', 'localhost'),
        'PORT': os.getenv('DJANGO_DB_PORT', '5432'),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True
USE_THOUSAND_SEPARATOR = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'
MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
```

`config/settings/dev.py`:
```python
from .base import *  # noqa: F401,F403

DEBUG = True
```

`config/settings/prod.py`:
```python
import os

from .base import *  # noqa: F401,F403

DEBUG = False

# TLS termina no reverse proxy existente na frente da aplicação (Apache,
# já configurado em comigo.conf/comigo-le-ssl.conf) — o Django nunca fala
# HTTPS diretamente. Sem isso, request.is_secure() sempre volta False
# atrás do proxy. Serviço/whitenoise real ficam para a Fase 7 (Deploy).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS if host]  # noqa: F405
```

`config/urls.py`:
```python
"""URL configuration for the Transbordo project."""
from django.contrib import admin
from django.urls import path

urlpatterns = [
    path('admin/', admin.site.urls),
]
```

`config/wsgi.py`:
```python
"""WSGI config for the Transbordo project."""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.getenv('DJANGO_SETTINGS_MODULE', 'config.settings.dev'))

application = get_wsgi_application()
```

`config/asgi.py`:
```python
"""ASGI config for the Transbordo project."""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.getenv('DJANGO_SETTINGS_MODULE', 'config.settings.dev'))

application = get_asgi_application()
```

`manage.py`:
```python
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', os.getenv('DJANGO_SETTINGS_MODULE', 'config.settings.dev'))
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
```

`static/.gitkeep` — empty file (keeps `STATICFILES_DIRS` from triggering a `staticfiles.W004` check warning on a fresh checkout).

- [ ] **Step 3: Wire dependencies, env vars, and test config**

Append to `requirements.txt`:
```
Django>=6.0,<6.1
```

`requirements-dev.txt` (full file):
```
-r requirements.txt
pytest
pytest-django
```

`.env.example` (new file — no real secrets; documents both variable families side by side):
```
# Stack Streamlit/SQLAlchemy (legado) — ver .env real (não versionado) para valores.
# DB_USER=
# DB_PASSWORD=
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=comigo
# GEMINI_API_KEY=

# Stack Django (Fase 5) — DJANGO_DB_* é deliberadamente distinto de DB_*
# para os dois stacks nunca apontarem pro mesmo banco por acidente
# enquanto convivem no mesmo .env (ver docs/decisions/0002).
DJANGO_SECRET_KEY=change-me
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_DB_NAME=transbordo
DJANGO_DB_USER=transbordo
DJANGO_DB_PASSWORD=change-me
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5432
```

`pytest.ini` (full file — extends the existing config, does not replace the SQLAlchemy test discovery):
```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings.dev
testpaths = tests apps
python_files = test_*.py
pythonpath = .
```

- [ ] **Step 4: Install dependencies and verify the skeleton boots**

Run: `pip install -r requirements-dev.txt`
Expected: installs Django (and pytest-django) with no errors.

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 5: Document the decision and update CLAUDE.md**

`docs/decisions/0002-settings-por-ambiente.md`:
```markdown
# ADR 0002 — Settings por ambiente e variáveis DJANGO_DB_* separadas do stack legado

- Status: Aceito
- Data: 2026-08-22

## Contexto

O projeto Django precisa de configuração parametrizada por ambiente (dev/prod), convivendo no mesmo
repositório e no mesmo `.env` com o stack Streamlit/SQLAlchemy existente durante toda a migração
(Fases 1-7 do roteiro).

## Decisão

- Settings organizados em `config/settings/base.py`, `config/settings/dev.py` e `config/settings/prod.py`,
  selecionados via `DJANGO_SETTINGS_MODULE` (padrão herdado do APP_Vector, ADR 0002 de lá).
- Valores sensíveis carregados do mesmo `.env` já usado pelo stack Streamlit, via `python-dotenv`.
- Variáveis de banco do stack Django usam o prefixo `DJANGO_DB_*` (`DJANGO_DB_NAME`, `DJANGO_DB_USER`,
  `DJANGO_DB_PASSWORD`, `DJANGO_DB_HOST`, `DJANGO_DB_PORT`), deliberadamente distintas de `DB_*` (usadas
  por `data_loader.get_engine()` no stack SQLAlchemy) — para que os dois stacks nunca apontem para o
  mesmo banco por acidente enquanto convivem no mesmo `.env`.

## Consequências

- Dois bancos PostgreSQL distintos (ou dois nomes de banco distintos no mesmo servidor) precisam existir
  durante a migração: um para o stack legado (`DB_NAME`, hoje `comigo`) e outro para o stack Django
  (`DJANGO_DB_NAME`, sugerido `transbordo`) — o desenvolvedor precisa criar esse segundo banco localmente
  antes de rodar `manage.py migrate` pela primeira vez.
- `.env.example` documenta as duas famílias de variáveis lado a lado.
```

In `CLAUDE.md`, insert a new section immediately after `## Commands` (before `## Environment`):
```markdown
## Fase 5 — Fundação Django (em progresso)

Migração para Django 6 + HTMX em andamento (ver
`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` e
`docs/superpowers/plans/2026-08-22-fase5-fundacao-django.md`). Durante a coexistência com o app
Streamlit/SQLAlchemy existente, os dois stacks vivem no mesmo repositório:

- `python manage.py check` — sanity check do projeto Django.
- `pytest` — roda tanto os testes SQLAlchemy (`tests/`) quanto os testes Django (`apps/*/tests/`).
- O `.env` do stack Django usa variáveis `DJANGO_DB_*` (deliberadamente distintas de `DB_*`, que
  continuam servindo o stack Streamlit/SQLAlchemy) — ver `.env.example`.
- ADRs desta fase em `docs/decisions/`, começando em `0001`.
```

- [ ] **Step 6: Commit**

```bash
git add manage.py config apps requirements.txt requirements-dev.txt pytest.ini .env.example static/.gitkeep docs/decisions/0002-settings-por-ambiente.md CLAUDE.md
git commit -m "feat(fase5): scaffold Django project skeleton (core/simulacao/integracoes)"
```

---

### Task 2: `Cooperativa` model

**Files:**
- Modify: `apps/core/models.py` (create), `apps/core/admin.py` (create)
- Create: `apps/core/migrations/0001_cooperativa.py` (generated, not hand-written)
- Create: `apps/core/tests/__init__.py`, `apps/core/tests/test_cooperativa.py`
- Create: `docs/decisions/0001-multi-tenancy-schema-compartilhado.md`

**Interfaces:**
- Consumes: `apps.core` app registered in `INSTALLED_APPS` (Task 1).
- Produces: `apps.core.models.Cooperativa` with fields `nome` (str), `slug` (unique str), `ativo` (bool, default `True`), `dias_janela_safra_padrao` (nullable int) — the FK target every later tenant-scoped model (`Task 4`'s `CooperativaScopedModel`, and every Fase 5 model from the next plan) points to.

- [ ] **Step 1: Write the failing test**

`apps/core/tests/__init__.py` — empty.

`apps/core/tests/test_cooperativa.py`:
```python
from django.test import TestCase

from apps.core.models import Cooperativa


class CooperativaTests(TestCase):
    def test_criacao_com_campos_minimos(self):
        cooperativa = Cooperativa.objects.create(nome='Cooperativa Teste', slug='cooperativa-teste')

        self.assertTrue(cooperativa.ativo)
        self.assertIsNone(cooperativa.dias_janela_safra_padrao)

    def test_str_retorna_nome(self):
        cooperativa = Cooperativa.objects.create(nome='Cooperativa Teste', slug='cooperativa-teste')

        self.assertEqual(str(cooperativa), 'Cooperativa Teste')

    def test_slug_e_unico(self):
        Cooperativa.objects.create(nome='Primeira', slug='mesma-slug')

        with self.assertRaises(Exception):
            Cooperativa.objects.create(nome='Segunda', slug='mesma-slug')
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/core/tests/test_cooperativa.py -v`
Expected: FAIL/ERROR with `ImportError: cannot import name 'Cooperativa' from 'apps.core.models'` (module doesn't exist yet).

- [ ] **Step 3: Write the model**

`apps/core/models.py`:
```python
from django.db import models


class Cooperativa(models.Model):
    """Raiz do tenant: cada cooperativa é isolada das demais (ver apps.core.tenancy)."""

    nome = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    ativo = models.BooleanField(default=True)
    dias_janela_safra_padrao = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text=(
            'Parâmetro placeholder para a janela de safra padrão da cooperativa; '
            'semântica real definida quando SafraUnidade for portado (próxima fase).'
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Cooperativa'
        verbose_name_plural = 'Cooperativas'
        ordering = ['nome']

    def __str__(self):
        return self.nome
```

`apps/core/admin.py`:
```python
from django.contrib import admin

from apps.core.models import Cooperativa


@admin.register(Cooperativa)
class CooperativaAdmin(admin.ModelAdmin):
    list_display = ['nome', 'slug', 'ativo']
    prepopulated_fields = {'slug': ['nome']}
```

Run: `python manage.py makemigrations core`
Expected: creates `apps/core/migrations/0001_cooperativa.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/core/tests/test_cooperativa.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Document the tenancy decision**

`docs/decisions/0001-multi-tenancy-schema-compartilhado.md`:
```markdown
# ADR 0001 — Multi-tenancy: schema compartilhado + cooperativa_id

- Status: Aceito
- Data: 2026-08-22

## Contexto

O Transbordo evolui de um app de cooperativa única para um SaaS multi-cooperativa. É preciso isolar os
dados de cada cooperativa (tenant) sem reescrever o motor de otimização (`calculations.py`) nem adotar
uma solução operacionalmente pesada demais para o estágio atual do produto.

## Decisão

- Schema compartilhado: uma única base de dados, um único conjunto de tabelas, com `cooperativa_id`
  (FK, `on_delete=PROTECT`) propagado a `Cenario` e a todos os seus descendentes — mesmo tipo de
  migração aditiva que a correção A11 da Fase 1 já fez para `cenario_id` no stack SQLAlchemy.
- Isolamento automático via `TenantManager`/`CooperativaScopeMiddleware` (ver
  `docs/decisions/0003-tenant-isolation-fail-closed.md`): toda query em um model derivado de
  `CooperativaScopedModel` fica implicitamente escopada pela cooperativa do usuário autenticado.
- **Alternativa rejeitada**: `django-tenants` (schema-per-tenant) — isolamento mais forte, mas migrations
  por schema e integração menos comum com Procrastinate/HTMX; mais complexidade operacional do que o
  estágio atual do produto justifica.

## Consequências

- Toda tabela tenant-scoped precisa herdar `CooperativaScopedModel` (ou repetir o padrão manualmente) —
  esquecer isso é um vazamento de isolamento silencioso, por isso o teste de isolamento é obrigatório
  (ADR 0003).
- Uma cooperativa com volume desproporcional de dados compartilha a mesma tabela/índices das demais —
  aceitável no estágio atual; reavaliar se o volume por cooperativa crescer muito antes de uma eventual
  migração para schema-per-tenant.
```

- [ ] **Step 6: Commit**

```bash
git add apps/core/models.py apps/core/admin.py apps/core/migrations/0001_cooperativa.py apps/core/tests/ docs/decisions/0001-multi-tenancy-schema-compartilhado.md
git commit -m "feat(fase5): add Cooperativa model"
```

---

### Task 3: Custom `User` model

**Files:**
- Modify: `apps/core/models.py`, `apps/core/admin.py`, `config/settings/base.py`
- Create: `apps/core/migrations/0002_user.py` (generated, not hand-written)
- Create: `apps/core/tests/test_user.py`

**Interfaces:**
- Consumes: `apps.core.models.Cooperativa` (Task 2).
- Produces: `apps.core.models.User` with `cooperativa` (nullable FK to `Cooperativa`), `papel` (str, one of `User.PAPEL_ADMIN_VECTOR` / `User.PAPEL_ADMIN_COOPERATIVA` / `User.PAPEL_USUARIO_FABRICA` / `User.PAPEL_USUARIO_ARMAZEM`), enforced by `AUTH_USER_MODEL = 'core.User'`. `Task 4`'s middleware and tests depend on these exact constant names and on `cooperativa_id` being `None` only for `PAPEL_ADMIN_VECTOR`.

- [ ] **Step 1: Write the failing test**

`apps/core/tests/test_user.py`:
```python
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.core.models import Cooperativa, User


class UserTests(TestCase):
    def setUp(self):
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')

    def test_admin_vector_sem_cooperativa_e_valido(self):
        user = User(username='admin_vector', papel=User.PAPEL_ADMIN_VECTOR, cooperativa=None)

        user.full_clean(exclude=['password'])

    def test_admin_vector_com_cooperativa_e_invalido(self):
        user = User(username='admin_vector', papel=User.PAPEL_ADMIN_VECTOR, cooperativa=self.cooperativa)

        with self.assertRaises(ValidationError):
            user.full_clean(exclude=['password'])

    def test_usuario_fabrica_sem_cooperativa_e_invalido(self):
        user = User(username='usuario_fabrica', papel=User.PAPEL_USUARIO_FABRICA, cooperativa=None)

        with self.assertRaises(ValidationError):
            user.full_clean(exclude=['password'])

    def test_usuario_fabrica_com_cooperativa_e_valido(self):
        user = User(
            username='usuario_fabrica', papel=User.PAPEL_USUARIO_FABRICA, cooperativa=self.cooperativa
        )

        user.full_clean(exclude=['password'])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/core/tests/test_user.py -v`
Expected: FAIL/ERROR with `ImportError: cannot import name 'User' from 'apps.core.models'`.

- [ ] **Step 3: Write the model, set AUTH_USER_MODEL, register admin**

Append to `apps/core/models.py`:
```python
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError


class User(AbstractUser):
    """Identidade de login. `cooperativa=None` só é válido para o papel Admin Vector
    (cross-tenant); os demais papéis pertencem a exatamente uma cooperativa."""

    PAPEL_ADMIN_VECTOR = 'admin_vector'
    PAPEL_ADMIN_COOPERATIVA = 'admin_cooperativa'
    PAPEL_USUARIO_FABRICA = 'usuario_fabrica'
    PAPEL_USUARIO_ARMAZEM = 'usuario_armazem'
    PAPEL_CHOICES = [
        (PAPEL_ADMIN_VECTOR, 'Admin Vector'),
        (PAPEL_ADMIN_COOPERATIVA, 'Admin Cooperativa'),
        (PAPEL_USUARIO_FABRICA, 'Usuário Fábrica'),
        (PAPEL_USUARIO_ARMAZEM, 'Usuário Armazém'),
    ]

    cooperativa = models.ForeignKey(
        'core.Cooperativa', on_delete=models.PROTECT, null=True, blank=True, related_name='usuarios'
    )
    papel = models.CharField(max_length=20, choices=PAPEL_CHOICES)

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'

    def clean(self):
        super().clean()
        if self.papel == self.PAPEL_ADMIN_VECTOR and self.cooperativa_id is not None:
            raise ValidationError('Admin Vector não pertence a nenhuma cooperativa.')
        if self.papel != self.PAPEL_ADMIN_VECTOR and self.cooperativa_id is None:
            raise ValidationError('Este papel exige uma cooperativa.')
```

(`from django.db import models` already present at the top of `apps/core/models.py` from Task 2 — no need to add it again.)

In `config/settings/base.py`, add immediately after `INSTALLED_APPS`:
```python
AUTH_USER_MODEL = 'core.User'
```

Append to `apps/core/admin.py`:
```python
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.core.models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    fieldsets = DjangoUserAdmin.fieldsets + (('Transbordo', {'fields': ('cooperativa', 'papel')}),)
    list_display = DjangoUserAdmin.list_display + ('cooperativa', 'papel')
    list_filter = DjangoUserAdmin.list_filter + ('cooperativa', 'papel')
```

Run: `python manage.py makemigrations core`
Expected: creates `apps/core/migrations/0002_user.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/core/tests/test_user.py -v`
Expected: PASS (4 passed)

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).` (confirms `AUTH_USER_MODEL = 'core.User'` resolves correctly now that the model exists)

- [ ] **Step 5: Commit**

```bash
git add apps/core/models.py apps/core/admin.py apps/core/migrations/0002_user.py apps/core/tests/test_user.py config/settings/base.py
git commit -m "feat(fase5): add custom User model with cooperativa + papel"
```

---

### Task 4: `TenantManager` + `CooperativaScopedModel` + `CooperativaScopeMiddleware`

**Files:**
- Create: `apps/core/tenancy.py`, `apps/core/middleware.py`
- Create: `apps/core/tests/test_tenancy.py`, `apps/core/tests/test_middleware.py`
- Modify: `config/settings/base.py`
- Create: `docs/decisions/0003-tenant-isolation-fail-closed.md`

**Interfaces:**
- Consumes: `apps.core.models.Cooperativa` (Task 2), `apps.core.models.User` with `PAPEL_USUARIO_FABRICA` and `cooperativa_id` (Task 3).
- Produces: `apps.core.tenancy.CooperativaScopedModel` (abstract model — the base every tenant-scoped model in the next plan, e.g. `apps.simulacao.models.Fabrica`, will inherit), `apps.core.tenancy.TenantManager`, `apps.core.tenancy.definir_cooperativa_atual(cooperativa_id) -> Token`, `apps.core.tenancy.obter_cooperativa_atual() -> int | None`, `apps.core.tenancy.resetar_cooperativa_atual(token) -> None`, `apps.core.middleware.CooperativaScopeMiddleware`.

- [ ] **Step 1: Write the failing tenancy test**

`apps/core/tests/test_tenancy.py`:
```python
from django.db import connection, models
from django.test import TestCase
from django.test.utils import isolate_apps

from apps.core.models import Cooperativa
from apps.core.tenancy import (
    CooperativaScopedModel,
    definir_cooperativa_atual,
    resetar_cooperativa_atual,
)


@isolate_apps('core')
class TenantManagerIsolationTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class Item(CooperativaScopedModel):
            nome = models.CharField(max_length=100)

            class Meta:
                app_label = 'core'

        cls.Item = Item
        with connection.schema_editor() as editor:
            editor.create_model(cls.Item)

    @classmethod
    def tearDownClass(cls):
        with connection.schema_editor() as editor:
            editor.delete_model(cls.Item)
        super().tearDownClass()

    def setUp(self):
        self.coop_a = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        self.Item.all_cooperativas.create(cooperativa=self.coop_a, nome='Item A')
        self.Item.all_cooperativas.create(cooperativa=self.coop_b, nome='Item B')

    def test_scoped_manager_returns_empty_without_current_cooperativa(self):
        self.assertEqual(list(self.Item.objects.all()), [])

    def test_scoped_manager_filters_by_current_cooperativa(self):
        token = definir_cooperativa_atual(self.coop_a.id)
        try:
            nomes = list(self.Item.objects.values_list('nome', flat=True))
        finally:
            resetar_cooperativa_atual(token)
        self.assertEqual(nomes, ['Item A'])

    def test_scoped_manager_never_leaks_other_cooperativa(self):
        token = definir_cooperativa_atual(self.coop_a.id)
        try:
            vazou = self.Item.objects.filter(nome='Item B').exists()
        finally:
            resetar_cooperativa_atual(token)
        self.assertFalse(vazou)

    def test_all_cooperativas_manager_bypasses_scope(self):
        self.assertEqual(self.Item.all_cooperativas.count(), 2)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest apps/core/tests/test_tenancy.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'apps.core.tenancy'`.

- [ ] **Step 3: Write the tenancy module**

`apps/core/tenancy.py`:
```python
"""Escopo de tenant (cooperativa) para queries automaticamente isoladas.

Ver docs/decisions/0003-tenant-isolation-fail-closed.md: sem cooperativa
corrente definida, o manager escopado retorna queryset vazio (falha
fechada) em vez de vazar dados de todas as cooperativas.
"""
from contextvars import ContextVar

from django.db import models

_cooperativa_atual = ContextVar('cooperativa_atual', default=None)


def definir_cooperativa_atual(cooperativa_id):
    return _cooperativa_atual.set(cooperativa_id)


def obter_cooperativa_atual():
    return _cooperativa_atual.get()


def resetar_cooperativa_atual(token):
    _cooperativa_atual.reset(token)


class TenantManager(models.Manager):
    """Escopa automaticamente pela cooperativa corrente (contextvar).

    Sem cooperativa corrente definida, retorna queryset vazio — nunca
    todos os registros de todas as cooperativas.
    """

    def get_queryset(self):
        cooperativa_id = obter_cooperativa_atual()
        qs = super().get_queryset()
        if cooperativa_id is None:
            return qs.none()
        return qs.filter(cooperativa_id=cooperativa_id)


class CooperativaScopedModel(models.Model):
    """Base abstrata para models pertencentes a uma cooperativa.

    `objects` é escopado (TenantManager); `all_cooperativas` é a via de
    escape explícita para consultas cross-tenant deliberadas (ex.: Admin
    Vector). Nunca usar `all_cooperativas` a partir de uma view comum.
    """

    cooperativa = models.ForeignKey('core.Cooperativa', on_delete=models.PROTECT)

    objects = TenantManager()
    all_cooperativas = models.Manager()

    class Meta:
        abstract = True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest apps/core/tests/test_tenancy.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Write the failing middleware test**

`apps/core/tests/test_middleware.py`:
```python
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.core.middleware import CooperativaScopeMiddleware
from apps.core.models import Cooperativa, User
from apps.core.tenancy import obter_cooperativa_atual


class CooperativaScopeMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.cooperativa = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='usuaria_fabrica',
            cooperativa=self.cooperativa,
            papel=User.PAPEL_USUARIO_FABRICA,
        )

    def test_sets_cooperativa_from_authenticated_user_during_request(self):
        observado = {}

        def get_response(request):
            observado['cooperativa_id'] = obter_cooperativa_atual()
            return 'resposta'

        middleware = CooperativaScopeMiddleware(get_response)
        request = self.factory.get('/')
        request.user = self.user

        middleware(request)

        self.assertEqual(observado['cooperativa_id'], self.cooperativa.id)

    def test_resets_cooperativa_after_request(self):
        middleware = CooperativaScopeMiddleware(lambda request: 'resposta')
        request = self.factory.get('/')
        request.user = self.user

        middleware(request)

        self.assertIsNone(obter_cooperativa_atual())

    def test_anonymous_user_has_no_cooperativa(self):
        observado = {}

        def get_response(request):
            observado['cooperativa_id'] = obter_cooperativa_atual()
            return 'resposta'

        middleware = CooperativaScopeMiddleware(get_response)
        request = self.factory.get('/')
        request.user = AnonymousUser()

        middleware(request)

        self.assertIsNone(observado['cooperativa_id'])
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest apps/core/tests/test_middleware.py -v`
Expected: FAIL/ERROR with `ModuleNotFoundError: No module named 'apps.core.middleware'`.

- [ ] **Step 7: Write the middleware and register it**

`apps/core/middleware.py`:
```python
"""Middleware que expõe a cooperativa do usuário autenticado ao TenantManager
durante o ciclo de vida do request (ver apps.core.tenancy)."""
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual


class CooperativaScopeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        cooperativa_id = None
        if request.user.is_authenticated:
            cooperativa_id = request.user.cooperativa_id
        token = definir_cooperativa_atual(cooperativa_id)
        try:
            return self.get_response(request)
        finally:
            resetar_cooperativa_atual(token)
```

In `config/settings/base.py`, append to the end of `MIDDLEWARE`:
```python
    'apps.core.middleware.CooperativaScopeMiddleware',
```
(must stay after `'django.contrib.auth.middleware.AuthenticationMiddleware'` — it reads `request.user`.)

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest apps/core/tests/test_middleware.py -v`
Expected: PASS (3 passed)

Run: `python manage.py check`
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 9: Document the fail-closed decision**

`docs/decisions/0003-tenant-isolation-fail-closed.md`:
```markdown
# ADR 0003 — TenantManager falha fechado (sem cooperativa corrente = queryset vazio)

- Status: Aceito
- Data: 2026-08-22

## Contexto

O isolamento de tenant (ADR 0001) depende de um manager de queryset que escopa automaticamente por
cooperativa. É preciso decidir o comportamento quando nenhuma cooperativa corrente está definida (ex.:
requisição anônima, contexto de management command, bug de middleware).

## Decisão

- `apps.core.tenancy.TenantManager` (usado por `CooperativaScopedModel.objects`) resolve a cooperativa
  corrente de um `ContextVar`, populado por `CooperativaScopeMiddleware` a partir de
  `request.user.cooperativa_id`.
- **Falha fechada**: se a cooperativa corrente não estiver definida, o manager retorna `queryset.none()`
  — nunca todos os registros de todas as cooperativas.
- Consultas cross-tenant deliberadas (ex.: ferramentas do Admin Vector) usam explicitamente o manager
  `all_cooperativas` (sem escopo), nunca `objects`.
- Coberto por teste automatizado formal (`apps/core/tests/test_tenancy.py`): duas cooperativas, prova de
  que uma nunca enxerga dado da outra via `objects`, e que `all_cooperativas` intencionalmente enxerga
  ambas.

## Consequências

- Qualquer código que precise de acesso cross-tenant tem que optar explicitamente por
  `all_cooperativas` — fica óbvio na revisão de código quando isso acontece.
- Um bug que apague a cooperativa corrente do contexto (middleware não executado, contexto vazado entre
  requests) se manifesta como "página vazia" (visível, fácil de notar) em vez de "vazamento de dados de
  outra cooperativa" (silencioso, muito pior).
```

- [ ] **Step 10: Commit**

```bash
git add apps/core/tenancy.py apps/core/middleware.py apps/core/tests/test_tenancy.py apps/core/tests/test_middleware.py config/settings/base.py docs/decisions/0003-tenant-isolation-fail-closed.md
git commit -m "feat(fase5): add TenantManager, CooperativaScopedModel, CooperativaScopeMiddleware"
```

---

### Task 5: CI (GitHub Actions)

**Files:**
- Create: `.github/workflows/ci.yml`
- Create: `docs/decisions/0004-ci-real-github-actions.md`

**Interfaces:**
- Consumes: `manage.py check`, `python manage.py makemigrations --check --dry-run`, `pytest` (all from Tasks 1-4) plus the existing `tests/` suite (SQLAlchemy, unmodified).
- Produces: a CI workflow that runs on every push/PR to `main`.

- [ ] **Step 1: Write the workflow**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: transbordo
          POSTGRES_PASSWORD: transbordo
          POSTGRES_DB: transbordo
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U transbordo"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 10
    env:
      DJANGO_SETTINGS_MODULE: config.settings.dev
      DJANGO_SECRET_KEY: ci-test-secret-key
      DJANGO_DB_NAME: transbordo
      DJANGO_DB_USER: transbordo
      DJANGO_DB_PASSWORD: transbordo
      DJANGO_DB_HOST: localhost
      DJANGO_DB_PORT: 5432
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-dev.txt
      - name: Django system check
        run: python manage.py check
      - name: Verify no missing migrations
        run: python manage.py makemigrations --check --dry-run
      - name: Run tests
        run: pytest -v
```

- [ ] **Step 2: Verify the workflow is valid YAML and matches repo conventions**

Run: `python -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
Expected: no output (parses without error). If `yaml` isn't installed locally, skip this and rely on GitHub's own validation on push — the workflow syntax above follows the standard `actions/checkout`/`actions/setup-python`/service-container shape.

Run: `pytest -v` (full suite, one last time, from repo root)
Expected: all tests pass — both the pre-existing `tests/` (SQLAlchemy) suite and the new `apps/core/tests/` (Django) suite.

- [ ] **Step 3: Document the CI decision**

`docs/decisions/0004-ci-real-github-actions.md`:
```markdown
# ADR 0004 — CI real via GitHub Actions desde o commit zero

- Status: Aceito
- Data: 2026-08-22

## Contexto

O APP_Vector (projeto de referência) não tem pipeline de CI automatizado, só um gate manual documentado.
O Transbordo decide conscientemente não herdar essa lacuna.

## Decisão

- `.github/workflows/ci.yml` no repositório `Transbordo`, rodando a cada push/PR para `main`:
  `python manage.py check`, `python manage.py makemigrations --check --dry-run` e `pytest`.
- Job roda contra um container de serviço `postgres:16` (mesmo engine de produção), não SQLite — evita
  divergência de comportamento entre o banco de teste e o de produção.

## Consequências

- Todo PR/push para `main` tem sinal automático de "quebrou o quê" antes de qualquer revisão manual.
- O workflow precisa ser mantido conforme novas apps/migrações forem adicionadas nas próximas fases —
  não deveria exigir mudança estrutural, só tempo de execução crescente.
```

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml docs/decisions/0004-ci-real-github-actions.md
git commit -m "feat(fase5): add GitHub Actions CI workflow"
```

**Note (not a scripted step — depends on local machine state):** pushing this branch to `origin` and opening/merging a PR is a separate, explicitly-confirmed action outside this plan's automated steps — the CI workflow only proves itself once it actually runs on GitHub. Also, before running `python manage.py migrate` against a real local PostgreSQL instance (as opposed to the ephemeral test DB `pytest` uses), create the `transbordo` database and role locally first (matching whatever `DJANGO_DB_*` values you put in your real `.env`) — mirroring the existing `comigo` database, not replacing it.

---

## Self-Review Notes

- **Spec coverage:** Phase 1 "Fundação" from the spec's Fases de migração list — "projeto Django 6 no diretório local ..., apps core/simulacao/integracoes, settings base/dev/prod, CI (GitHub Actions) desde o commit zero, models Cooperativa+User+TenantManager" — is covered by Tasks 1-5 respectively. Spec decision #1 (multi-tenancy, rejected alternative) → ADR 0001 (Task 2). Spec decision #3 (apps structure) → Task 1's file structure. Spec decision #8's tenant-isolation-test requirement → `test_tenancy.py` (Task 4). Spec decision #9 (docs/ADRs starting at 0001) → Tasks 1-5's ADRs. Spec decisions #4 (UI/HTMX), #5 (auth/allauth), #6 (Procrastinate), #7 (Django Ninja), #10 (deploy) are explicitly out of scope for this plan — they belong to later Fase 5 migration phases (2-7) and get their own plans.
- **Ordering fix applied during drafting:** `AUTH_USER_MODEL` and the `CooperativaScopeMiddleware` entry are added to `config/settings/base.py` incrementally (Tasks 3 and 4 respectively), not upfront in Task 1 — pointing settings at a model or middleware module that doesn't exist yet would fail `manage.py check` immediately.
- **No placeholders:** every step above shows complete file contents or exact diffs; no "TBD"/"add appropriate handling" text remains.
