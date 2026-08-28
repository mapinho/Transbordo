# Fase 8 — Versionamento + limpeza — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce a SemVer scheme (`VERSION` file, `APP_VERSION` in Django, `/healthz/` + footer, `CHANGELOG.md`) and remove the accumulated non-code cruft, without touching the still-in-production Streamlit/SQLAlchemy stack.

**Architecture:** A one-line `VERSION` file at the repo root is the single source of truth; `config/settings/base.py` reads it into `APP_VERSION` at import (fail-loud if absent). A tiny `apps/core/context_processors.py` exposes it to templates; a stub `/healthz/` view returns it as JSON. Cleanup is a delete sweep of a fixed list, plus a `grep` pass to fix dangling references in `README.md` / `CLAUDE.md`.

**Tech Stack:** Django 6, `pytest`/`pytest-django`, plain `requirements.txt` (no `pyproject.toml`).

**Spec:** `docs/superpowers/specs/2026-08-28-fase8-versionamento-limpeza-design.md`

## Global Constraints

- **Do NOT touch the Streamlit/SQLAlchemy stack**: `app.py`, `app_logic.py`, `models.py`, `calculations.py`, `scenarios.py`, `data_loader.py`, `logistics_services.py`, `utils.py`, `generate_templates.py`, `ai_assistant.py`, `mcp_server.py`, `tests/`. That removal is Fase 11 (Cutover).
- SemVer `MAJOR.MINOR.PATCH`. This phase is `0.8.0`. `v1.0.0` is the cutover. The `VERSION` file holds `0.8.0` (no `v` prefix).
- `APP_VERSION` must **fail loudly** if `VERSION` is missing — never fall back to a default (same discipline as the `.env` requirement, `data_loader.py:get_engine()`).
- TDD: failing test first, run it, confirm it fails for the right reason, minimal implementation, confirm green. Commit after each green task.
- Django tests are plain `django.test.TestCase` with per-test `setUp` fixtures (no `apps/*/conftest.py`). They need a reachable Postgres via `DJANGO_DB_*` (see `docs/decisions/0002-...`).
- `git` history preserves everything — "remove" means delete from the working tree, not rewrite history.
- Commit style: `feat:` / `chore:` / `docs:`, pt-BR summary. End every commit message with:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`

---

## File Structure

**New files:**
- `VERSION` — one line, `0.8.0`. Source of truth for the app version.
- `CHANGELOG.md` — Keep a Changelog format, sections `[0.1.0]`–`[0.8.0]`.
- `apps/core/context_processors.py` — `app_version(request)` → `{"APP_VERSION": settings.APP_VERSION}`.
- `apps/core/views.py` — `healthz(request)` → `JsonResponse({"version": settings.APP_VERSION})`. (Create the file if it doesn't exist; it's a natural home for a project-level health view.)
- `apps/core/tests/test_version.py` — `APP_VERSION` reads `VERSION`; missing-file behavior.
- `apps/core/tests/test_healthz.py` — `/healthz/` returns the version.
- `apps/core/tests/test_context_processor.py` — footer renders the version.
- `apps/core/tests/test_cleanup_guard.py` — the delete list is gone, kept docs have no dangling refs.

**Modified files:**
- `config/settings/base.py` — add `APP_VERSION` after `BASE_DIR`; register the context processor.
- `config/urls.py` — add `path('healthz/', healthz)`.
- `templates/base.html` — footer showing `v{{ APP_VERSION }}`.
- `.gitignore` — add `exportacao/`.
- `README.md` — drop the `INSTRUCOES_MCP.md` reference.
- `CLAUDE.md` — remove the `Related Docs` bullets for `INSTRUCOES_MCP.md`, `Relatorio_Revisao_Codigo_Fase1.md`, `GEMINI.md`, `conductor/`; drop the `Relatorio_Revisao_Codigo_Fase1.md` file reference at lines ~9 and ~118 (keep the sentence).

**Deleted files** (Task 5): `GEMINI.md`, `.gemini/settings.json`, `code-reviewer/` (3 files), `INSTRUCOES_MCP.md`, `toolspec.json`, `conductor/` (2 files), the **7 completed-phase** plan files under `docs/superpowers/plans/` (`2026-08-22-fase5-fundacao-django.md`, `2026-08-22-fase5-port-dominio.md`, `2026-08-23-fase5-ui-dados-cenarios.md`, `2026-08-24-espelhamento-dados-legado.md`, `2026-08-25-carga-de-dados.md`, `2026-08-26-fase5-simulacao-assincrona.md`, `2026-08-28-fase6-face-json.md`), `Relatorio_Revisao_Codigo_Fase1.md`, `analise_mineiros.py`, `Relatorio_Analise_Impacto_Vendas_Mineiros.md`, `Cenário de Simulação.txt`, `Especificação Transbordo.txt`, `exportacao/*.xlsx` (4 files).

> **Keep** the plans for phases not yet executed: `2026-08-28-fase8-versionamento-limpeza.md` (this one), `2026-08-28-fase9a-mcp-http.md`, `2026-08-28-fase9b-assistente-ia.md`. Going forward, each phase's plan is deleted when that phase completes.

---

## Task 1: `VERSION` file + `APP_VERSION` setting

**Files:**
- Create: `VERSION`
- Create: `apps/core/tests/__init__.py` (if missing), `apps/core/tests/test_version.py`
- Modify: `config/settings/base.py:6-7` (right after `BASE_DIR` / `load_dotenv`)

**Interfaces:**
- Produces: `django.conf.settings.APP_VERSION` — a `str` like `"0.8.0"`, read once at settings import from `BASE_DIR / 'VERSION'`. Raises `RuntimeError` with a clear message if the file is absent.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_version.py`:

```python
from pathlib import Path

from django.conf import settings
from django.test import TestCase


class AppVersionTests(TestCase):
    def test_app_version_matches_version_file(self):
        version_file = Path(settings.BASE_DIR) / 'VERSION'
        self.assertTrue(version_file.exists(), 'VERSION file must exist at repo root')
        self.assertEqual(settings.APP_VERSION, version_file.read_text().strip())

    def test_app_version_is_semver_shaped(self):
        parts = settings.APP_VERSION.split('.')
        self.assertEqual(len(parts), 3)
        self.assertTrue(all(p.isdigit() for p in parts), settings.APP_VERSION)
```

- [ ] **Step 2: Run it, confirm failure**

Run: `pytest apps/core/tests/test_version.py -v`
Expected: FAIL — `AttributeError: 'Settings' object has no attribute 'APP_VERSION'`.

- [ ] **Step 3: Create `VERSION` and wire the setting**

Create `VERSION` with exactly:

```
0.8.0
```

Edit `config/settings/base.py`, immediately after line 7 (`load_dotenv(BASE_DIR / '.env')`):

```python

_version_file = BASE_DIR / 'VERSION'
if not _version_file.exists():
    raise RuntimeError(
        f"Arquivo VERSION ausente em {_version_file}. É a fonte de verdade da versão da aplicação "
        f"(ver docs/superpowers/specs/2026-08-28-fase8-versionamento-limpeza-design.md)."
    )
APP_VERSION = _version_file.read_text().strip()
```

- [ ] **Step 4: Run it, confirm pass**

Run: `pytest apps/core/tests/test_version.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add VERSION config/settings/base.py apps/core/tests/
git commit -m "feat: versão da aplicação via arquivo VERSION (APP_VERSION nas settings)"
```

---

## Task 2: `/healthz/` stub returning the version

**Files:**
- Create/Modify: `apps/core/views.py`
- Create: `apps/core/tests/test_healthz.py`
- Modify: `config/urls.py`

**Interfaces:**
- Consumes: `settings.APP_VERSION` (Task 1).
- Produces: `GET /healthz/` → `200` `application/json` `{"version": "<APP_VERSION>"}`. Named URL `healthz`. This is a **stub** — the full `SELECT 1` / container `HEALTHCHECK` is Fase 10; this task only adds the version field.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_healthz.py`:

```python
from django.conf import settings
from django.test import TestCase


class HealthzTests(TestCase):
    def test_healthz_returns_version_json(self):
        response = self.client.get('/healthz/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        self.assertEqual(response.json(), {'version': settings.APP_VERSION})

    def test_healthz_needs_no_auth(self):
        # no login — must still answer
        self.assertEqual(self.client.get('/healthz/').status_code, 200)
```

- [ ] **Step 2: Run it, confirm failure**

Run: `pytest apps/core/tests/test_healthz.py -v`
Expected: FAIL — `404` (route not registered).

- [ ] **Step 3: Implement**

Create (or append to) `apps/core/views.py`:

```python
from django.conf import settings
from django.http import JsonResponse


def healthz(request):
    """Stub de health check — só a versão por enquanto. O SELECT 1 e o
    HEALTHCHECK do container entram na Fase 10 (Deploy)."""
    return JsonResponse({'version': settings.APP_VERSION})
```

Edit `config/urls.py`:

```python
from apps.core.views import healthz

urlpatterns = [
    path('admin/', admin.site.urls),
    path('healthz/', healthz, name='healthz'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('simulacao/', include('apps.simulacao.urls')),
    path('api/v1/', integracoes_api.urls),
]
```

- [ ] **Step 4: Run it, confirm pass**

Run: `pytest apps/core/tests/test_healthz.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/core/views.py config/urls.py apps/core/tests/test_healthz.py
git commit -m "feat: endpoint /healthz/ stub expondo a versão"
```

---

## Task 3: version in the base-template footer

**Files:**
- Create: `apps/core/context_processors.py`
- Modify: `config/settings/base.py` (TEMPLATES context_processors list, ~line 59-63)
- Modify: `templates/base.html`
- Create: `apps/core/tests/test_context_processor.py`

**Interfaces:**
- Consumes: `settings.APP_VERSION`.
- Produces: every template rendered with a `RequestContext` has `APP_VERSION` available. `templates/base.html` renders a footer `<footer>… v{{ APP_VERSION }}</footer>`.

- [ ] **Step 1: Write the failing test**

Create `apps/core/tests/test_context_processor.py`:

```python
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Cooperativa

User = get_user_model()


class VersionFooterTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='u', password='senha-forte-123',
            cooperativa=self.coop, papel=User.PAPEL_ADMIN_COOPERATIVA,
        )

    def test_footer_shows_version(self):
        self.client.force_login(self.user)
        response = self.client.get('/simulacao/cenarios/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'v{settings.APP_VERSION}')
```

- [ ] **Step 2: Run it, confirm failure**

Run: `pytest apps/core/tests/test_context_processor.py -v`
Expected: FAIL — `v0.8.0` not found in the response.

- [ ] **Step 3: Implement**

Create `apps/core/context_processors.py`:

```python
from django.conf import settings


def app_version(request):
    return {'APP_VERSION': settings.APP_VERSION}
```

Edit `config/settings/base.py`, in the `TEMPLATES[0]['OPTIONS']['context_processors']` list, add after `'django.contrib.messages.context_processors.messages',`:

```python
                'apps.core.context_processors.app_version',
```

Edit `templates/base.html`, immediately before the closing `</body>` (after the last `<script>` block, before `{% block extra_scripts %}`):

```html
    <footer class="px-6 py-3 text-xs text-slate-400 border-t border-[var(--cor-borda)]">
        Transbordo v{{ APP_VERSION }}
    </footer>
```

- [ ] **Step 4: Run it, confirm pass**

Run: `pytest apps/core/tests/test_context_processor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/core/context_processors.py config/settings/base.py templates/base.html apps/core/tests/test_context_processor.py
git commit -m "feat: versão no rodapé do template base via context processor"
```

---

## Task 4: `CHANGELOG.md` back-fill

**Files:**
- Create: `CHANGELOG.md`

**Interfaces:** none (documentation).

- [ ] **Step 1: Write `CHANGELOG.md`**

Create `CHANGELOG.md`:

```markdown
# Changelog

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/).
Versionamento: [SemVer](https://semver.org/lang/pt-BR/). `v1.0.0` marca o cutover (Streamlit desligado).

## [0.8.0] - 2026-XX-XX

### Added
- Esquema de versionamento SemVer: arquivo `VERSION`, `APP_VERSION` nas settings, `/healthz/` (stub) e rodapé expondo a versão. Este `CHANGELOG.md`.

### Removed
- Lixo acumulado da migração: `GEMINI.md` + `.gemini/`, skill `code-reviewer/`, `INSTRUCOES_MCP.md` + `toolspec.json`, `conductor/`, `docs/superpowers/plans/*`, `Relatorio_Revisao_Codigo_Fase1.md`, análises one-off (`analise_mineiros.py`, `Relatorio_Analise_Impacto_Vendas_Mineiros.md`), notas de scratch `.txt`, `exportacao/*.xlsx`. O stack Streamlit/SQLAlchemy **não** foi tocado (sai na Fase 11).

## [0.7.0] - 2026-XX-XX
### Added
- Fase 7 — Auth: allauth (Google + Microsoft + local), papéis, sem auto-cadastro.

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
```

> The `0.1.0`–`0.5.0` dates are approximate — refine from `git log` if a date is easy to pin, otherwise leave as written; the CHANGELOG is an index, not an audit log.

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: CHANGELOG.md com back-fill das Fases 1-8"
```

---

## Task 5: cleanup sweep

**Files:**
- Delete: the full list in "File Structure → Deleted files".
- Modify: `.gitignore`, `README.md`, `CLAUDE.md`.

**Interfaces:** none — removes docs/notes/one-off scripts. No `.py` of the live Django or Streamlit apps.

- [ ] **Step 1: Write the failing guard test**

Create `apps/core/tests/test_cleanup_guard.py`:

```python
from pathlib import Path

from django.conf import settings
from django.test import TestCase

REMOVIDOS = [
    'GEMINI.md', '.gemini/settings.json',
    'code-reviewer/SKILL.md', 'code-reviewer/scripts/review.py',
    'INSTRUCOES_MCP.md', 'toolspec.json',
    'conductor/ai-assistant-plan.md', 'conductor/mcp-server.md',
    'Relatorio_Revisao_Codigo_Fase1.md',
    'analise_mineiros.py', 'Relatorio_Analise_Impacto_Vendas_Mineiros.md',
    'Cenário de Simulação.txt', 'Especificação Transbordo.txt',
]


class CleanupGuardTests(TestCase):
    def test_cruft_is_gone(self):
        root = Path(settings.BASE_DIR)
        ainda_existem = [p for p in REMOVIDOS if (root / p).exists()]
        self.assertEqual(ainda_existem, [], f'ainda presentes: {ainda_existem}')

    def test_no_dangling_references_in_kept_docs(self):
        root = Path(settings.BASE_DIR)
        nomes = ['GEMINI.md', 'INSTRUCOES_MCP.md', 'toolspec.json',
                 'Relatorio_Revisao_Codigo_Fase1.md', 'conductor/']
        for doc in ['CLAUDE.md', 'README.md']:
            texto = (root / doc).read_text(encoding='utf-8')
            hits = [n for n in nomes if n in texto]
            self.assertEqual(hits, [], f'{doc} ainda referencia: {hits}')
```

- [ ] **Step 2: Run it, confirm failure**

Run: `pytest apps/core/tests/test_cleanup_guard.py -v`
Expected: FAIL — both tests (files still present, docs still reference them).

- [ ] **Step 3: Delete the files**

```bash
git rm -r GEMINI.md .gemini/ code-reviewer/ INSTRUCOES_MCP.md toolspec.json \
  conductor/ Relatorio_Revisao_Codigo_Fase1.md \
  analise_mineiros.py Relatorio_Analise_Impacto_Vendas_Mineiros.md \
  "Cenário de Simulação.txt" "Especificação Transbordo.txt" \
  exportacao/detalhamento_mensal_replanejado.xlsx \
  exportacao/movimentacoes_diarias_replanejado.xlsx \
  exportacao/resumo_armazens_replanejado.xlsx \
  exportacao/resumo_fabricas_replanejado.xlsx
git rm docs/superpowers/plans/2026-08-22-fase5-fundacao-django.md \
  docs/superpowers/plans/2026-08-22-fase5-port-dominio.md \
  docs/superpowers/plans/2026-08-23-fase5-ui-dados-cenarios.md \
  docs/superpowers/plans/2026-08-24-espelhamento-dados-legado.md \
  docs/superpowers/plans/2026-08-25-carga-de-dados.md \
  docs/superpowers/plans/2026-08-26-fase5-simulacao-assincrona.md \
  docs/superpowers/plans/2026-08-28-fase6-face-json.md
```

Do NOT delete `2026-08-28-fase8-*`, `2026-08-28-fase9a-*`, `2026-08-28-fase9b-*` — those phases have not run yet.

- [ ] **Step 4: Add `exportacao/` to `.gitignore`**

Edit `.gitignore`, add the line `exportacao/` under `media/`:

```
staticfiles/
media/
exportacao/
```

- [ ] **Step 5: Fix `README.md`**

Edit `README.md` line ~53 — remove `— veja \`INSTRUCOES_MCP.md\``, leaving:

```markdown
- `mcp_server.py`: Servidor MCP (FastMCP) para integração com LLMs externos.
```

- [ ] **Step 6: Fix `CLAUDE.md`**

In `CLAUDE.md`:
- Line ~9: change `(see \`Relatorio_Revisao_Codigo_Fase1.md\` and the "Roteiro Comigo" roadmap)` → `(see \`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md\`)`.
- Line ~118: change `See \`Relatorio_Revisao_Codigo_Fase1.md\` for the full audit trail of the Fase 1 code review (38 findings; ...)` → `The Fase 1 code review (38 findings; all fixed or consciously deferred) set the rigor bar for this project.` (drop the file reference, keep the point).
- In `## Related Docs`, delete these bullets: `INSTRUCOES_MCP.md`, `Relatorio_Revisao_Codigo_Fase1.md`, `GEMINI.md`, `conductor/`.

- [ ] **Step 7: Run the guard test + full suite**

Run: `pytest apps/core/tests/test_cleanup_guard.py -v`
Expected: PASS (2 tests).

Run: `python manage.py check`
Expected: no issues.

Run: `grep -rn "GEMINI\|INSTRUCOES_MCP\|toolspec\|conductor/\|code-reviewer\|Relatorio_Revisao\|analise_mineiros\|Relatorio_Analise" --include='*.md' --include='*.yml' --include='*.py' --include='Dockerfile' . | grep -v "\.venv\|\.claude/\|CHANGELOG\|test_cleanup_guard\|docs/superpowers/specs"`
Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "chore: remove lixo acumulado da migração (docs, skill code-reviewer, notas one-off)"
```

---

## Task 6: tag the release

**Files:** none (git tag only).

- [ ] **Step 1: Full suite green**

Run: `pytest`
Expected: all pass (Django + SQLAlchemy). No test referenced a deleted file.

Run: `python manage.py check` → no issues.

- [ ] **Step 2: Update the CHANGELOG date + create the tag**

Edit `CHANGELOG.md`: replace `## [0.8.0] - 2026-XX-XX` with today's date.

```bash
git add CHANGELOG.md
git commit -m "docs: data do release 0.8.0 no CHANGELOG"
git tag -a v0.8.0 -m "Fase 8 — versionamento + limpeza"
```

> Do NOT push the tag automatically — that is a release action. Report to the operator that `v0.8.0` is created locally and awaits `git push origin v0.8.0`.

---

## Self-Review

**Spec coverage:**

| Spec item | Task |
|-----------|------|
| `VERSION` file + `APP_VERSION` (fail-loud) | Task 1 |
| `/healthz/` exposes version (stub only) | Task 2 |
| Footer shows version | Task 3 |
| `CHANGELOG.md` back-fill 0.1.0–0.8.0 | Task 4 |
| Delete: GEMINI.md + .gemini/ + CLAUDE.md ref | Task 5 |
| Delete: code-reviewer/ | Task 5 |
| Delete: INSTRUCOES_MCP.md + toolspec.json | Task 5 |
| Delete: conductor/, plans/, Relatorio_Revisao_Codigo_Fase1.md | Task 5 |
| Delete: analise_mineiros.py + its report, .txt scratch | Task 5 |
| Delete: exportacao/*.xlsx + gitignore exportacao/ | Task 5 |
| Kept: specs/, decisions/, Especificacao_Sistema_Transbordo_Atualizada.md, Streamlit stack | Global Constraints + not in delete list |
| grep sweep for dangling references | Task 5 Step 7 + `test_cleanup_guard` |
| tag v0.8.0 | Task 6 |
| Streamlit/SQLAlchemy untouched | Global Constraints; no task touches it |

**Placeholder scan:** The CHANGELOG carries `2026-XX-XX` for phases not yet dated — intentional, resolved for `0.8.0` in Task 6 Step 2; older phase dates are approximate by design (noted in Task 4).

**Type consistency:** `settings.APP_VERSION` is a `str` produced in Task 1, consumed identically in Tasks 2 (JSON value) and 3 (template var). `healthz` view name is `healthz` in Task 2 and not referenced elsewhere.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-28-fase8-versionamento-limpeza.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.

**2. Inline Execution** — batch execution with checkpoints via executing-plans.

**Which approach?**
