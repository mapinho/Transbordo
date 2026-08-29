# Fase 9b — Aba "Assistente de IA" no Django — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port `ai_assistant.py` (Gemini function-calling over the 9 report functions) from the Streamlit "Assistente de IA" tab into the Django app, as a **per-cenário** tab that calls `apps/simulacao/services.py` in-process with the logged-in user's cooperativa, with conversation history persisted in a new `ConversaIA` model.

**Architecture:** A `ConversaIA` model (`CooperativaScopedModel`) stores one conversation per row (`cenario`, `usuario`, `mensagens` JSON, `ativa` flag). `apps/simulacao/assistente.py` holds the Gemini loop: `responder(conversa, mensagem)` rebuilds a `google-genai` chat from `conversa.mensagens`, sends the new message with auto-function-calling enabled, where the 9 tools are closures bound to `conversa.cenario` that delegate to `services.py`. Three HTMX views (`assistente_tab` / `assistente_enviar` / `assistente_nova`) back a tab in the cenário subnav.

**Tech Stack:** Django 6, HTMX, `google-genai` (already a dependency), `pytest`/`pytest-django`.

**Spec:** `docs/superpowers/specs/2026-08-28-fase9-migracao-mcp-ia-design.md` (Plano 9b section). Split rationale: ADR 0010 (written in Plano 9a).

## Global Constraints

- **Depends on Fase 7 (Auth)** — the views need `request.user` and `request.user.cooperativa_id`. Do not start this plan before Fase 7 is merged.
- **Do NOT touch the root `ai_assistant.py`** — the Streamlit app still imports it until Fase 11 (Cutover). The Gemini loop is deliberately duplicated across the two data layers for the coexistence window.
- **Do NOT touch `apps/simulacao/services.py`** (shared module; ADR 0006 — it already takes `cooperativa_id`/`scenario_id` explicitly).
- `ConversaIA` is a `CooperativaScopedModel` — `objects` is tenant-scoped; tests must prove cooperativa B never sees cooperativa A's conversations.
- `GEMINI_API_KEY` moves to `settings.GEMINI_API_KEY` (`os.getenv('GEMINI_API_KEY', '')`, may be empty). When empty, the tab renders a clear notice instead of raising.
- The tab operates on **one cenário** (the tab's context) — the 9 tool closures drop `scenario_id` from their signatures; the model can't pass the wrong scenario.
- Tests mock the `google-genai` client — never call the real Gemini API in the suite.
- The Django tenancy contextvar is set by `CooperativaScopeMiddleware` from `request.user` (see `apps/core/middleware.py`) — views use tenant-scoped `get_object_or_404(Cenario, id=...)` exactly like the other cenário tabs.
- TDD: failing test first, run it, confirm the failure reason, minimal implementation, confirm green. Commit after each green task.
- Commit style: `feat(simulacao):` / `test(simulacao):`, pt-BR summary. End every commit message with:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`

---

## File Structure

**New files:**
- `apps/simulacao/assistente.py` — the Gemini loop: `SYSTEM_PROMPT`, `_fazer_ferramentas(cenario) -> list[callable]`, `responder(conversa, mensagem_usuario) -> str`, `_get_client()`, `AssistenteIndisponivel`.
- `apps/simulacao/migrations/00XX_conversaia.py` — generated.
- `apps/simulacao/tests/test_models_conversaia.py`
- `apps/simulacao/tests/test_assistente.py`
- `apps/simulacao/tests/test_views_assistente.py`
- `templates/simulacao/assistente.html`
- `templates/simulacao/_assistente_content.html`
- `templates/simulacao/_assistente_transcript.html`

**Modified files:**
- `apps/simulacao/models.py` — add `ConversaIA`.
- `apps/simulacao/views.py` — add `assistente_tab`, `assistente_enviar`, `assistente_nova`.
- `apps/simulacao/urls.py` — 3 routes.
- `templates/simulacao/_subnav.html` — an "Assistente" tab entry.
- `config/settings/base.py` — `GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')`.

---

## Task 1: `ConversaIA` model + migration

**Files:**
- Modify: `apps/simulacao/models.py`
- Create: `apps/simulacao/migrations/00XX_conversaia.py` (generated), `apps/simulacao/tests/test_models_conversaia.py`

**Interfaces:**
- Produces: `apps.simulacao.models.ConversaIA` — `CooperativaScopedModel` subclass. Fields:
  - `cenario` (`ForeignKey('simulacao.Cenario', on_delete=CASCADE, related_name='conversas_ia')`)
  - `usuario` (`ForeignKey(settings.AUTH_USER_MODEL, on_delete=CASCADE, related_name='conversas_ia')`)
  - `titulo` (`CharField(max_length=120, blank=True)`)
  - `mensagens` (`JSONField(default=list)`) — `[{"papel": "user"|"assistant", "conteudo": str, "ts": iso8601}]`
  - `ativa` (`BooleanField(default=True)`)
  - `created_at` (`DateTimeField(auto_now_add=True)`), `updated_at` (`DateTimeField(auto_now=True)`)
  - `Meta.ordering = ['-updated_at']`
  - `__str__` → `self.titulo or f'Conversa {self.pk}'`
  - Method `adicionar(papel: str, conteudo: str) -> None` — appends `{"papel", "conteudo", "ts": timezone.now().isoformat()}` to `mensagens` (does not save).

- [ ] **Step 1: Write the failing test**

Create `apps/simulacao/tests/test_models_conversaia.py`:

```python
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.core.models import Cooperativa
from apps.core.tenancy import definir_cooperativa_atual, resetar_cooperativa_atual
from apps.simulacao.models import Cenario, ConversaIA

User = get_user_model()


class ConversaIAModelTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='u', password='x', cooperativa=self.coop,
            papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='C1')

    def test_defaults_and_adicionar(self):
        c = ConversaIA.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, usuario=self.user,
        )
        self.assertEqual(c.mensagens, [])
        self.assertTrue(c.ativa)
        c.adicionar('user', 'olá')
        c.adicionar('assistant', 'oi')
        c.save()
        c.refresh_from_db()
        self.assertEqual([m['papel'] for m in c.mensagens], ['user', 'assistant'])
        self.assertIn('ts', c.mensagens[0])

    def test_tenant_isolation(self):
        ConversaIA.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, usuario=self.user,
        )
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')

        token = definir_cooperativa_atual(coop_b.id)
        try:
            self.assertEqual(ConversaIA.objects.count(), 0)
        finally:
            resetar_cooperativa_atual(token)

        token = definir_cooperativa_atual(self.coop.id)
        try:
            self.assertEqual(ConversaIA.objects.count(), 1)
        finally:
            resetar_cooperativa_atual(token)
```

- [ ] **Step 2: Run it, confirm failure**

Run: `pytest apps/simulacao/tests/test_models_conversaia.py -v`
Expected: FAIL — `ImportError: cannot import name 'ConversaIA'`.

- [ ] **Step 3: Add the model**

In `apps/simulacao/models.py`, add `from django.conf import settings` to the imports if not present (`timezone` is already imported), then add:

```python
class ConversaIA(CooperativaScopedModel):
    """Histórico persistido de uma conversa com o Assistente de IA, por
    cenário e por usuário. Ver Fase 9b."""

    cenario = models.ForeignKey(
        'simulacao.Cenario', on_delete=models.CASCADE, related_name='conversas_ia',
    )
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='conversas_ia',
    )
    titulo = models.CharField(max_length=120, blank=True)
    mensagens = models.JSONField(default=list)
    ativa = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Conversa IA'
        verbose_name_plural = 'Conversas IA'
        ordering = ['-updated_at']

    def __str__(self):
        return self.titulo or f'Conversa {self.pk}'

    def adicionar(self, papel: str, conteudo: str) -> None:
        self.mensagens.append({
            'papel': papel,
            'conteudo': conteudo,
            'ts': timezone.now().isoformat(),
        })
```

- [ ] **Step 4: Generate the migration**

Run: `python manage.py makemigrations simulacao`
Expected: creates `apps/simulacao/migrations/00XX_conversaia.py` with `CreateModel` for `ConversaIA`. Open it, confirm the `cooperativa`/`cenario`/`usuario` FKs and `mensagens` default `list`.

- [ ] **Step 5: Run it, confirm pass**

Run: `pytest apps/simulacao/tests/test_models_conversaia.py -v`
Expected: PASS (2 tests).

Run: `python manage.py migrate simulacao` → applies cleanly.

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/models.py apps/simulacao/migrations/ apps/simulacao/tests/test_models_conversaia.py
git commit -m "feat(simulacao): model ConversaIA (histórico persistido do Assistente de IA)"
```

---

## Task 2: `apps/simulacao/assistente.py` — Gemini loop, in-process tools

**Files:**
- Create: `apps/simulacao/assistente.py`
- Modify: `config/settings/base.py`
- Create: `apps/simulacao/tests/test_assistente.py`

**Interfaces:**
- Consumes: `apps.simulacao.services` (9 report functions), `apps.simulacao.models.ConversaIA`, `settings.GEMINI_API_KEY`, `google.genai`.
- Produces:
  - `apps.simulacao.assistente.SYSTEM_PROMPT: str` — ported verbatim from the root `ai_assistant.py` (`SYSTEM_PROMPT`).
  - `apps.simulacao.assistente._fazer_ferramentas(cenario) -> list[callable]` — 9 closures over `cenario`. Each carries a docstring (copied from the root `ai_assistant.py` tool wrappers, minus the `st.toast` line) and delegates to `services.<fn>(cooperativa_id=cenario.cooperativa_id, scenario_id=cenario.id, ...)`. `scenario_id` is **not** a parameter of the closures; `list_scenarios` passes only `cooperativa_id`.
  - `apps.simulacao.assistente._get_client() -> genai.Client` — `genai.Client(api_key=settings.GEMINI_API_KEY)`. Raises `AssistenteIndisponivel` if the key is empty.
  - `apps.simulacao.assistente.AssistenteIndisponivel(Exception)` — raised when `GEMINI_API_KEY` is unset.
  - `apps.simulacao.assistente.responder(conversa: ConversaIA, mensagem_usuario: str) -> str` — appends the user turn to `conversa.mensagens`, rebuilds a `genai` chat from the prior turns as `history`, sends `mensagem_usuario` with `tools=_fazer_ferramentas(conversa.cenario)` and auto-function-calling, appends the assistant turn, sets `conversa.titulo` from the first user message if blank, saves `conversa`, returns the assistant text. On any error, appends an assistant turn with a readable message and returns it (never raises to the view).

- [ ] **Step 1: Write the failing tests**

Create `apps/simulacao/tests/test_assistente.py`:

```python
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.core.models import Cooperativa
from apps.simulacao import assistente, services
from apps.simulacao.models import Cenario, ConversaIA

User = get_user_model()


class FerramentasTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='C1')

    def test_closures_bind_cenario_and_delegate_to_services(self):
        ferramentas = {f.__name__: f for f in assistente._fazer_ferramentas(self.cenario)}
        self.assertEqual(
            set(ferramentas),
            {'list_scenarios', 'get_daily_movements', 'get_monthly_summary',
             'get_factories_summary', 'get_warehouses_summary', 'compare_factories',
             'compare_warehouses', 'get_stock_excesses_report', 'get_stock_ruptures_report'},
        )
        with patch.object(services, 'get_stock_excesses_report', return_value=[]) as spy:
            ferramentas['get_stock_excesses_report']()
        spy.assert_called_once_with(scenario_id=self.cenario.id)

        with patch.object(services, 'list_scenarios', return_value=[]) as spy:
            ferramentas['list_scenarios']()
        spy.assert_called_once_with(cooperativa_id=self.coop.id)


@override_settings(GEMINI_API_KEY='')
class AssistenteIndisponivelTests(TestCase):
    def test_get_client_raises_without_key(self):
        with self.assertRaises(assistente.AssistenteIndisponivel):
            assistente._get_client()


@override_settings(GEMINI_API_KEY='fake-key')
class ResponderTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='u', password='x', cooperativa=self.coop,
            papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='C1')
        self.conversa = ConversaIA.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, usuario=self.user,
        )

    def _fake_client(self, texto='Resposta do assistente.'):
        chat = MagicMock()
        chat.send_message.return_value = MagicMock(text=texto)
        client = MagicMock()
        client.chats.create.return_value = chat
        return client

    def test_persists_both_turns_and_sets_title(self):
        with patch.object(assistente, '_get_client', return_value=self._fake_client()):
            out = assistente.responder(self.conversa, 'Quais fábricas têm excedente?')
        self.assertEqual(out, 'Resposta do assistente.')
        self.conversa.refresh_from_db()
        papeis = [m['papel'] for m in self.conversa.mensagens]
        self.assertEqual(papeis, ['user', 'assistant'])
        self.assertEqual(self.conversa.mensagens[0]['conteudo'], 'Quais fábricas têm excedente?')
        self.assertTrue(self.conversa.titulo)

    def test_gemini_error_becomes_assistant_message_not_exception(self):
        chat = MagicMock()
        chat.send_message.side_effect = RuntimeError('boom')
        client = MagicMock()
        client.chats.create.return_value = chat
        with patch.object(assistente, '_get_client', return_value=client):
            out = assistente.responder(self.conversa, 'oi')
        self.assertIn('erro', out.lower())
        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.mensagens[-1]['papel'], 'assistant')
```

- [ ] **Step 2: Run it, confirm failure**

Run: `pytest apps/simulacao/tests/test_assistente.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'apps.simulacao.assistente'`.

- [ ] **Step 3: Add `GEMINI_API_KEY` to settings**

Edit `config/settings/base.py`, after the `ALLOWED_HOSTS` block:

```python
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
```

- [ ] **Step 4: Implement `apps/simulacao/assistente.py`**

Create `apps/simulacao/assistente.py`:

```python
"""Assistente de IA (Gemini function-calling) sobre apps/simulacao/services.py.

Port da lógica de `ai_assistant.py` (raiz, usada pelo Streamlit) para o app
Django: as ferramentas chamam `services.py` em processo, com a cooperativa e o
cenário fixados pelo contexto da aba. Ver Fase 9b e ADR 0010.
"""
from django.conf import settings
from google import genai
from google.genai import types

from apps.simulacao import services
from apps.simulacao.models import ConversaIA

SYSTEM_PROMPT = """<colar VERBATIM o SYSTEM_PROMPT de ai_assistant.py>"""

_MODELO = "gemini-2.5-flash"


class AssistenteIndisponivel(Exception):
    """GEMINI_API_KEY não configurada."""


def _get_client() -> genai.Client:
    if not settings.GEMINI_API_KEY:
        raise AssistenteIndisponivel(
            "GEMINI_API_KEY não configurada — o Assistente de IA está indisponível."
        )
    return genai.Client(api_key=settings.GEMINI_API_KEY)


def _fazer_ferramentas(cenario):
    """9 closures ligadas a `cenario`, delegando para services.py em processo.
    O cenário é fixo pela aba, então as tools não recebem `scenario_id`."""
    cid = cenario.cooperativa_id
    sid = cenario.id

    def list_scenarios() -> list[dict]:
        """<docstring de ai_assistant.list_scenarios, sem a linha st.toast>"""
        return services.list_scenarios(cooperativa_id=cid)

    def get_daily_movements(
        start_date: str | None = None,
        end_date: str | None = None,
        origin_id: int | None = None,
        destination_id: int | None = None,
        limit: int = 150,
    ) -> list[dict]:
        """<docstring de ai_assistant.get_daily_movements, sem st.toast>"""
        return services.get_daily_movements(
            scenario_id=sid, start_date=start_date, end_date=end_date,
            origin_id=origin_id, destination_id=destination_id, limit=limit,
        )

    def get_monthly_summary(
        start_date: str | None = None, end_date: str | None = None,
    ) -> dict:
        """<docstring de ai_assistant.get_monthly_summary, sem st.toast>"""
        return services.get_monthly_summary(
            scenario_id=sid, start_date=start_date, end_date=end_date,
        )

    def get_factories_summary() -> list[dict]:
        """<docstring de ai_assistant.get_factories_summary, sem st.toast>"""
        return services.get_factories_summary(scenario_id=sid)

    def get_warehouses_summary() -> list[dict]:
        """<docstring de ai_assistant.get_warehouses_summary, sem st.toast>"""
        return services.get_warehouses_summary(scenario_id=sid)

    def compare_factories() -> list[dict]:
        """<docstring de ai_assistant.compare_factories, sem st.toast>"""
        return services.compare_factories(scenario_id=sid)

    def compare_warehouses() -> list[dict]:
        """<docstring de ai_assistant.compare_warehouses, sem st.toast>"""
        return services.compare_warehouses(scenario_id=sid)

    def get_stock_excesses_report() -> list[dict]:
        """<docstring de ai_assistant.get_stock_excesses_report, sem st.toast>"""
        return services.get_stock_excesses_report(scenario_id=sid)

    def get_stock_ruptures_report() -> list[dict]:
        """<docstring de ai_assistant.get_stock_ruptures_report, sem st.toast>"""
        return services.get_stock_ruptures_report(scenario_id=sid)

    return [
        list_scenarios, get_daily_movements, get_monthly_summary,
        get_factories_summary, get_warehouses_summary, compare_factories,
        compare_warehouses, get_stock_excesses_report, get_stock_ruptures_report,
    ]


def _historico(conversa: ConversaIA) -> list[types.Content]:
    papel_para_role = {'user': 'user', 'assistant': 'model'}
    return [
        types.Content(
            role=papel_para_role[m['papel']],
            parts=[types.Part(text=m['conteudo'])],
        )
        for m in conversa.mensagens
    ]


def responder(conversa: ConversaIA, mensagem_usuario: str) -> str:
    conversa.adicionar('user', mensagem_usuario)
    if not conversa.titulo:
        conversa.titulo = mensagem_usuario[:120]

    try:
        client = _get_client()
        chat = client.chats.create(
            model=_MODELO,
            history=_historico(conversa)[:-1],  # tudo menos a mensagem recém-adicionada
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                tools=_fazer_ferramentas(conversa.cenario),
                temperature=0.2,
            ),
        )
        resposta = chat.send_message(mensagem_usuario).text or ''
    except AssistenteIndisponivel as exc:
        resposta = str(exc)
    except Exception as exc:  # noqa: BLE001 — nunca propaga para a view
        resposta = f"Ocorreu um erro ao consultar a inteligência artificial: {exc}"

    conversa.adicionar('assistant', resposta)
    conversa.save()
    return resposta
```

> Verify the `google-genai` API used by the root `ai_assistant.py` (`client.chats.create(model=, config=GenerateContentConfig(system_instruction=, tools=, temperature=))`, `chat.send_message(text)`) still matches the installed `google-genai==2.10.0`, and that `chats.create` accepts `history=`. If `history=` is not supported by this version, fall back to `client.models.generate_content(...)` with an explicit message list and a manual function-call loop — keep the same `responder()` signature and behavior.

- [ ] **Step 5: Run it, confirm pass**

Run: `pytest apps/simulacao/tests/test_assistente.py -v`
Expected: PASS (5 tests).

- [ ] **Step 6: Commit**

```bash
git add apps/simulacao/assistente.py config/settings/base.py apps/simulacao/tests/test_assistente.py
git commit -m "feat(simulacao): loop Gemini in-process (assistente.py) sobre services.py"
```

---

## Task 3: views, URLs, subnav, templates

**Files:**
- Modify: `apps/simulacao/views.py`, `apps/simulacao/urls.py`, `templates/simulacao/_subnav.html`
- Create: `templates/simulacao/assistente.html`, `templates/simulacao/_assistente_content.html`, `templates/simulacao/_assistente_transcript.html`
- Create: `apps/simulacao/tests/test_views_assistente.py`

**Interfaces:**
- Consumes: `assistente.responder`, `ConversaIA`, `get_object_or_404(Cenario, ...)`.
- Produces:
  - `GET /simulacao/cenarios/<int:cenario_id>/assistente/` → `assistente_tab` — full page (or `_assistente_content.html` partial for HTMX). Context: `cenario`, `active='assistente'`, `conversa` (the `ativa=True` one for `(cenario, request.user)`, created if none), `conversas` (past ones), `assistente_disponivel` (bool `settings.GEMINI_API_KEY != ''`).
  - `POST /simulacao/cenarios/<int:cenario_id>/assistente/enviar/` → `assistente_enviar` — reads `mensagem`, calls `assistente.responder(conversa, mensagem)`, returns `_assistente_transcript.html` partial. `require_POST`, `login_required`.
  - `POST /simulacao/cenarios/<int:cenario_id>/assistente/nova/` → `assistente_nova` — sets the current `ativa` conversation `ativa=False`, creates a fresh one, returns the `_assistente_content.html` partial. `require_POST`, `login_required`.
  - URL names: `simulacao:assistente_tab`, `simulacao:assistente_enviar`, `simulacao:assistente_nova`.

- [ ] **Step 1: Write the failing tests**

Create `apps/simulacao/tests/test_views_assistente.py`:

```python
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.core.models import Cooperativa
from apps.simulacao.models import Cenario, ConversaIA

User = get_user_model()


class AssistenteViewsTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop A', slug='coop-a')
        self.user = User.objects.create_user(
            username='u', password='senha-forte-123', cooperativa=self.coop,
            papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='C1')
        self.url_tab = reverse('simulacao:assistente_tab', kwargs={'cenario_id': self.cenario.id})
        self.url_enviar = reverse('simulacao:assistente_enviar', kwargs={'cenario_id': self.cenario.id})
        self.url_nova = reverse('simulacao:assistente_nova', kwargs={'cenario_id': self.cenario.id})

    def test_requer_login(self):
        self.assertEqual(self.client.get(self.url_tab).status_code, 302)

    def test_tab_cria_conversa_ativa_na_primeira_visita(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url_tab)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            ConversaIA.all_cooperativas.filter(
                cenario=self.cenario, usuario=self.user, ativa=True).count(),
            1,
        )

    def test_enviar_persiste_turnos(self):
        self.client.force_login(self.user)
        self.client.get(self.url_tab)  # cria a conversa ativa
        with patch('apps.simulacao.views.assistente.responder', return_value='resposta') as spy:
            response = self.client.post(self.url_enviar, {'mensagem': 'olá'})
        self.assertEqual(response.status_code, 200)
        spy.assert_called_once()
        self.assertContains(response, 'resposta')

    def test_nova_arquiva_a_ativa(self):
        self.client.force_login(self.user)
        self.client.get(self.url_tab)
        antiga = ConversaIA.all_cooperativas.get(
            cenario=self.cenario, usuario=self.user, ativa=True)
        self.client.post(self.url_nova)
        antiga.refresh_from_db()
        self.assertFalse(antiga.ativa)
        self.assertEqual(
            ConversaIA.all_cooperativas.filter(
                cenario=self.cenario, usuario=self.user, ativa=True).count(),
            1,
        )

    def test_isolamento_cross_tenant(self):
        coop_b = Cooperativa.objects.create(nome='Coop B', slug='coop-b')
        user_b = User.objects.create_user(
            username='b', password='senha-forte-123', cooperativa=coop_b,
            papel=User.PAPEL_ADMIN_COOPERATIVA,
        )
        self.client.force_login(user_b)
        self.assertEqual(self.client.get(self.url_tab).status_code, 404)

    @override_settings(GEMINI_API_KEY='')
    def test_tab_mostra_aviso_sem_chave(self):
        self.client.force_login(self.user)
        response = self.client.get(self.url_tab)
        self.assertContains(response, 'indisponível')
```

- [ ] **Step 2: Run it, confirm failure**

Run: `pytest apps/simulacao/tests/test_views_assistente.py -v`
Expected: FAIL — `NoReverseMatch` for `simulacao:assistente_tab`.

- [ ] **Step 3: Implement the views**

In `apps/simulacao/views.py`: add `ConversaIA` to the `from apps.simulacao.models import ...` line; add `from apps.simulacao import assistente` near the other `apps.simulacao` imports; `settings` is imported via `from django.conf import settings` (add if absent). Add, near the other cenário-tab views:

```python
def _conversa_ativa(cenario, usuario):
    conversa = (
        ConversaIA.objects.filter(cenario=cenario, usuario=usuario, ativa=True)
        .order_by('-updated_at').first()
    )
    if conversa is None:
        conversa = ConversaIA.objects.create(
            cooperativa_id=cenario.cooperativa_id, cenario=cenario, usuario=usuario,
        )
    return conversa


def _assistente_context(request, cenario):
    return {
        'cenario': cenario,
        'active': 'assistente',
        'conversa': _conversa_ativa(cenario, request.user),
        'conversas': ConversaIA.objects.filter(
            cenario=cenario, usuario=request.user, ativa=False,
        ).order_by('-updated_at')[:20],
        'assistente_disponivel': bool(settings.GEMINI_API_KEY),
    }


@login_required
def assistente_tab(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    context = _assistente_context(request, cenario)
    template = 'simulacao/_assistente_content.html' if request.htmx else 'simulacao/assistente.html'
    return render(request, template, context)


@login_required
@require_POST
def assistente_enviar(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    mensagem = request.POST.get('mensagem', '').strip()
    conversa = _conversa_ativa(cenario, request.user)
    if mensagem:
        assistente.responder(conversa, mensagem)
    return render(request, 'simulacao/_assistente_transcript.html',
                  {'conversa': conversa, 'cenario': cenario})


@login_required
@require_POST
def assistente_nova(request, cenario_id):
    cenario = get_object_or_404(Cenario, id=cenario_id)
    ConversaIA.objects.filter(cenario=cenario, usuario=request.user, ativa=True).update(ativa=False)
    return render(request, 'simulacao/_assistente_content.html',
                  _assistente_context(request, cenario))
```

- [ ] **Step 4: URLs**

In `apps/simulacao/urls.py`, add before the `carga/` routes:

```python
    path('cenarios/<int:cenario_id>/assistente/', views.assistente_tab, name='assistente_tab'),
    path('cenarios/<int:cenario_id>/assistente/enviar/', views.assistente_enviar, name='assistente_enviar'),
    path('cenarios/<int:cenario_id>/assistente/nova/', views.assistente_nova, name='assistente_nova'),
```

- [ ] **Step 5: Subnav entry**

In `templates/simulacao/_subnav.html`, add after the "Simulação" tab (before the closing `</div>`):

```html
    <a href="{% url 'simulacao:assistente_tab' cenario_id=cenario.id %}"
       hx-get="{% url 'simulacao:assistente_tab' cenario_id=cenario.id %}"
       hx-target="#cenario-content" hx-push-url="true"
       class="tab {% if active == 'assistente' %}tab-active{% endif %}">Assistente</a>
```

- [ ] **Step 6: Templates**

Create `templates/simulacao/assistente.html`:

```html
{% extends "base.html" %}
{% block content %}
<div id="cenario-content">
    {% include "simulacao/_assistente_content.html" %}
</div>
{% endblock %}
```

Create `templates/simulacao/_assistente_content.html`:

```html
{% include "simulacao/_subnav.html" %}

{% if not assistente_disponivel %}
<p class="rounded border border-[var(--cor-borda)] bg-amber-50 px-4 py-2 mb-4">
    O Assistente de IA está <strong>indisponível</strong> — a chave <code>GEMINI_API_KEY</code> não está configurada.
</p>
{% endif %}

<div class="flex gap-6">
    <div class="flex-1">
        <div id="assistente-transcript">
            {% include "simulacao/_assistente_transcript.html" %}
        </div>
        <form hx-post="{% url 'simulacao:assistente_enviar' cenario_id=cenario.id %}"
              hx-target="#assistente-transcript" hx-swap="innerHTML"
              hx-on::after-request="this.reset()"
              class="mt-4 flex gap-2">
            {% csrf_token %}
            <input type="text" name="mensagem" required autocomplete="off"
                   placeholder="Pergunte sobre este cenário…"
                   class="input input-bordered flex-1" {% if not assistente_disponivel %}disabled{% endif %}>
            <button type="submit" class="rounded bg-[var(--cor-primaria)] hover:bg-[var(--cor-primaria-hover)] text-white px-4 py-2"
                    {% if not assistente_disponivel %}disabled{% endif %}>Enviar</button>
        </form>
    </div>
    <aside class="w-56 shrink-0">
        <form hx-post="{% url 'simulacao:assistente_nova' cenario_id=cenario.id %}"
              hx-target="#cenario-content" hx-swap="innerHTML" class="mb-3">
            {% csrf_token %}
            <button type="submit" class="text-sm text-[var(--cor-primaria)] hover:underline">+ Nova conversa</button>
        </form>
        <ul class="text-sm space-y-1">
            {% for c in conversas %}
            <li class="truncate text-slate-500">{{ c.titulo|default:"(sem título)" }}</li>
            {% endfor %}
        </ul>
    </aside>
</div>
```

Create `templates/simulacao/_assistente_transcript.html`:

```html
<div class="space-y-3">
    {% for m in conversa.mensagens %}
    <div class="{% if m.papel == 'user' %}text-right{% endif %}">
        <span class="inline-block rounded px-3 py-2 {% if m.papel == 'user' %}bg-[var(--cor-primaria)] text-white{% else %}bg-white border border-[var(--cor-borda)]{% endif %}">{{ m.conteudo|linebreaksbr }}</span>
    </div>
    {% empty %}
    <p class="text-slate-400 text-sm">Nenhuma mensagem ainda.</p>
    {% endfor %}
</div>
```

- [ ] **Step 7: Run the tests, confirm pass**

Run: `pytest apps/simulacao/tests/test_views_assistente.py -v`
Expected: PASS (6 tests).

Run: `python manage.py check` → no issues.

- [ ] **Step 8: Full suite**

Run: `pytest`
Expected: green (Django + SQLAlchemy).

- [ ] **Step 9: Commit**

```bash
git add apps/simulacao/views.py apps/simulacao/urls.py templates/simulacao/ apps/simulacao/tests/test_views_assistente.py
git commit -m "feat(simulacao): aba Assistente de IA por cenário (HTMX, histórico persistido)"
```

---

## Task 4: manual verification

**Files:** none.

- [ ] **Step 1: Manual smoke**

`python manage.py runserver`, log in, open a cenário's **Assistente** tab. With `GEMINI_API_KEY` set:
- ask "quais fábricas estão com excedente de estoque neste cenário?" → confirm the answer references real data (the tool call hit `services.get_stock_excesses_report` with the tab's `scenario_id`);
- reload the page → the transcript is still there;
- "+ Nova conversa" → the transcript clears, the old one appears in the sidebar list;
- log in as a user of another cooperativa, hit the same cenário URL → 404.

With `GEMINI_API_KEY` empty → the tab shows the "indisponível" notice and the input is disabled.

Record results in the task report.

---

## Self-Review

**Spec coverage:**

| Spec item (Plano 9b) | Task |
|---|---|
| `ConversaIA` model (`cenario`, `usuario`, `mensagens` JSON, `ativa`, timestamps, `Meta.ordering`) + migration + tenant-isolation tests | Task 1 |
| `apps/simulacao/assistente.py` — Gemini loop, tools call `services.py` in-process with `cooperativa_id`/`scenario_id` | Task 2 |
| `google-genai` kept; `GEMINI_API_KEY` → `settings`; graceful notice when absent | Tasks 2 (settings + `AssistenteIndisponivel`) + 3 (`assistente_disponivel` in template) |
| `responder(conversa, mensagem_usuario) -> str` — appends both turns, saves, returns text, never raises | Task 2 |
| Views `assistente_tab` / `assistente_enviar` / `assistente_nova`, `@login_required`, tenant-scoped `get_object_or_404` | Task 3 |
| URLs `cenarios/<id>/assistente/…` + subnav tab | Task 3 |
| Templates: full + `_content` partial + `_transcript` partial (HTMX) | Task 3 |
| Tests: login required, tenant isolation, message round-trip (Gemini mocked), history persists, "Nova conversa" archives | Tasks 1–3 |
| Root `ai_assistant.py` untouched | Global Constraints; no task touches it |
| `services.py` untouched | Global Constraints; no task touches it |

**Placeholder scan:** `<colar VERBATIM o SYSTEM_PROMPT de ai_assistant.py>` and `<docstring de ai_assistant.X, sem a linha st.toast>` in Task 2 Step 4 are explicit "copy verbatim from the existing file" instructions — the system prompt and tool docstrings are the model-facing text and must not be paraphrased. Not plan gaps. Migration filename `00XX_conversaia.py` resolved by `makemigrations` in Task 1.

**Type consistency:** `ConversaIA.mensagens` items are `{"papel", "conteudo", "ts"}` — produced by `adicionar()` (Task 1), consumed by `_historico()` (Task 2) and `_assistente_transcript.html` (Task 3), all via `m['papel']` / `m['conteudo']`. `responder(conversa, mensagem_usuario)` signature identical in Task 2 (def), Task 2 tests, and Task 3 view calls. `_conversa_ativa(cenario, usuario)` defined and used only in `views.py` (Task 3).

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-28-fase9b-assistente-ia.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.

**2. Inline Execution** — batch execution with checkpoints via executing-plans.

**Which approach?**
