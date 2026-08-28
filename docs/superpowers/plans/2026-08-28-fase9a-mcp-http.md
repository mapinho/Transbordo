# Fase 9a — `mcp_server.py` → cliente HTTP — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `mcp_server.py` so its 9 tools call the Fase 6 JSON API (`/api/v1/`) over HTTP with an `X-API-Key`, instead of importing `logistics_services.py` and hitting Postgres directly.

**Architecture:** `mcp_server.py` stays a standalone stdio script at the repo root (it runs as a subprocess spawned by an MCP client, not as part of Django). It reads `TRANSBORDO_API_URL` + `TRANSBORDO_API_KEY` from the environment (`.env` fallback in dev), and each `@mcp.tool()` becomes a thin `httpx.get(...)` wrapper over `_get(path, **params)`. Tool names, parameters, and docstrings are unchanged — only the bodies. Non-2xx responses become a `fastmcp` `ToolError` with a human-readable message.

**Tech Stack:** FastMCP (`fastmcp==3.4.2`), `httpx` (new dependency), `python-dotenv` (already present).

**Spec:** `docs/superpowers/specs/2026-08-28-fase9-migracao-mcp-ia-design.md` (Plano 9a section).

## Global Constraints

- `mcp_server.py` stays at the **repo root**, standalone. It must NOT import Django, `apps.*`, `logistics_services`, or SQLAlchemy after this plan.
- Tool **signatures do not change** — same 9 names, same parameters, same return type annotations, same docstrings the LLM sees. Only the function body changes.
- Config from env: `TRANSBORDO_API_URL` (base, e.g. `http://localhost:8000/api/v1`, trailing slash tolerated/normalized) and `TRANSBORDO_API_KEY`. Read via `os.environ` with a `python-dotenv` `.env` fallback. **Missing either → fail loudly at import**, do not start a half-working server.
- No write endpoints — all 9 tools are read-only (matches the Fase 6 API).
- This plan does NOT depend on Fase 7 (Auth). It can run any time after Fase 6.
- TDD: failing test first, run it, confirm the failure reason, minimal implementation, confirm green. Commit after each green task.
- `mcp_server.py` tests live in `tests/` (the existing pytest dir) but must NOT use the SQLAlchemy `session` fixture or the DB — they patch `httpx`.
- Commit style: `feat(mcp):` / `test(mcp):` / `docs:`, pt-BR summary. End every commit message with:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`

---

## File Structure

**Modified:**
- `mcp_server.py` — full rewrite of the body (config block + `_get` helper + 9 tool bodies + module docstring). ~150 lines.
- `requirements.txt` — add `httpx>=0.27,<1.0`.
- `README.md` — add a `## MCP` section (replaces the `INSTRUCOES_MCP.md` deleted in Fase 8).

**New:**
- `tests/test_mcp_server.py` — pytest, patches `httpx.get`.
- `docs/decisions/0009-mcp-http-ia-in-process.md` — ADR (covers both 9a and 9b).

**Endpoint map** (from Fase 6, `apps/integracoes/api.py`):

| tool | method + path | params |
|---|---|---|
| `list_scenarios()` | `GET {BASE}/cenarios/` | — |
| `get_daily_movements(scenario_id, start_date?, end_date?, origin_id?, destination_id?, limit=150)` | `GET {BASE}/cenarios/{scenario_id}/movimentacoes/` | `start_date, end_date, origin_id, destination_id, limit` as query |
| `get_monthly_summary(scenario_id, start_date?, end_date?)` | `GET {BASE}/cenarios/{scenario_id}/resumo-mensal/` | `start_date, end_date` |
| `get_factories_summary(scenario_id)` | `GET {BASE}/cenarios/{scenario_id}/fabricas/resumo/` | — |
| `get_warehouses_summary(scenario_id)` | `GET {BASE}/cenarios/{scenario_id}/armazens/resumo/` | — |
| `compare_factories(scenario_id)` | `GET {BASE}/cenarios/{scenario_id}/fabricas/comparacao/` | — |
| `compare_warehouses(scenario_id)` | `GET {BASE}/cenarios/{scenario_id}/armazens/comparacao/` | — |
| `get_stock_excesses_report(scenario_id)` | `GET {BASE}/cenarios/{scenario_id}/alertas/excedentes/` | — |
| `get_stock_ruptures_report(scenario_id)` | `GET {BASE}/cenarios/{scenario_id}/alertas/rupturas/` | — |

---

## Task 1: config block + `_get` helper + `httpx` dependency

**Files:**
- Modify: `mcp_server.py` (top of file), `requirements.txt`
- Create: `tests/test_mcp_server.py`

**Interfaces:**
- Produces (module-level in `mcp_server.py`):
  - `BASE_URL: str` — `TRANSBORDO_API_URL` normalized (no trailing slash).
  - `API_KEY: str` — `TRANSBORDO_API_KEY`.
  - `_get(path: str, **params) -> list | dict` — GET `f"{BASE_URL}{path}"` with `X-API-Key` header, `None`-valued params dropped, `timeout=30`. Maps `401 → ToolError("Chave de API inválida ou inativa (TRANSBORDO_API_KEY).")`, `404 → ToolError("Cenário não encontrado para esta cooperativa.")`, other `>=400 → ToolError(<detail or text>)`. Returns `resp.json()` on 2xx.
  - Import failure: if `TRANSBORDO_API_URL` or `TRANSBORDO_API_KEY` is unset/empty, raise `RuntimeError` with a message naming both vars.

- [ ] **Step 1: Add the dependency**

Edit `requirements.txt`, add after `mcp[cli]==1.28.0`:

```
httpx>=0.27,<1.0
```

Run: `python -m pip install -r requirements.txt`
Expected: `httpx` installs.

- [ ] **Step 2: Write the failing test**

Create `tests/test_mcp_server.py`:

```python
import importlib
from unittest.mock import MagicMock, patch

import pytest


def _load_mcp(monkeypatch, url='http://localhost:8000/api/v1/', key='k-test'):
    monkeypatch.setenv('TRANSBORDO_API_URL', url)
    monkeypatch.setenv('TRANSBORDO_API_KEY', key)
    import mcp_server
    return importlib.reload(mcp_server)


def test_missing_env_raises_at_import(monkeypatch):
    monkeypatch.delenv('TRANSBORDO_API_URL', raising=False)
    monkeypatch.delenv('TRANSBORDO_API_KEY', raising=False)
    import mcp_server
    with pytest.raises(RuntimeError, match='TRANSBORDO_API'):
        importlib.reload(mcp_server)


def test_base_url_strips_trailing_slash(monkeypatch):
    m = _load_mcp(monkeypatch, url='http://x/api/v1/')
    assert m.BASE_URL == 'http://x/api/v1'


def test_get_sends_key_header_and_drops_none_params(monkeypatch):
    m = _load_mcp(monkeypatch, key='segredo')
    resp = MagicMock(status_code=200)
    resp.json.return_value = [{'id': 1}]
    with patch.object(m.httpx, 'get', return_value=resp) as mock_get:
        out = m._get('/cenarios/1/movimentacoes/', start_date='2026-01-01', end_date=None, limit=150)
    assert out == [{'id': 1}]
    args, kwargs = mock_get.call_args
    assert args[0] == 'http://localhost:8000/api/v1/cenarios/1/movimentacoes/'
    assert kwargs['headers']['X-API-Key'] == 'segredo'
    assert kwargs['params'] == {'start_date': '2026-01-01', 'limit': 150}


def test_get_maps_401_and_404(monkeypatch):
    m = _load_mcp(monkeypatch)
    for code, fragment in [(401, 'Chave de API'), (404, 'não encontrado')]:
        resp = MagicMock(status_code=code)
        resp.json.return_value = {'detail': 'x'}
        with patch.object(m.httpx, 'get', return_value=resp):
            with pytest.raises(m.ToolError, match=fragment):
                m._get('/cenarios/')
```

- [ ] **Step 3: Run it, confirm failure**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL — `AttributeError` / `ImportError` (no `BASE_URL`, `_get`, `ToolError` yet).

- [ ] **Step 4: Implement the top of `mcp_server.py`**

Replace lines 1–8 of `mcp_server.py` with:

```python
"""Comigo/Transbordo — servidor MCP (stdio).

Cliente HTTP da face JSON (`/api/v1/`, Fase 6). Configuração por variáveis de
ambiente (com fallback para `.env` em dev):

    TRANSBORDO_API_URL   base da API, ex. https://transbordo.exemplo.com/api/v1
    TRANSBORDO_API_KEY   chave X-API-Key (carrega a cooperativa)

Exemplo de bloco `mcp.json` de um cliente (Claude Desktop / Cursor):

    {
      "mcpServers": {
        "transbordo": {
          "command": "python",
          "args": ["/caminho/para/mcp_server.py"],
          "env": {
            "TRANSBORDO_API_URL": "https://transbordo.exemplo.com/api/v1",
            "TRANSBORDO_API_KEY": "..."
          }
        }
      }
    }
"""
import os

import httpx
from dotenv import load_dotenv
from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

load_dotenv()

BASE_URL = (os.getenv("TRANSBORDO_API_URL") or "").rstrip("/")
API_KEY = os.getenv("TRANSBORDO_API_KEY") or ""
if not BASE_URL or not API_KEY:
    raise RuntimeError(
        "Defina TRANSBORDO_API_URL e TRANSBORDO_API_KEY no ambiente (ou no .env) — "
        "o servidor MCP agora fala com a face JSON /api/v1/ por HTTP."
    )

mcp = FastMCP(
    "Comigo Logistica MCP Server",
    instructions="Servidor MCP para consulta e analise de simulacoes e movimentacoes logisticas de soja da Comigo.",
)


def _get(path: str, **params):
    """GET tipado contra a face JSON. Params None sao descartados."""
    limpos = {k: v for k, v in params.items() if v is not None}
    resp = httpx.get(
        f"{BASE_URL}{path}",
        params=limpos,
        headers={"X-API-Key": API_KEY},
        timeout=30,
    )
    if resp.status_code == 401:
        raise ToolError("Chave de API inválida ou inativa (TRANSBORDO_API_KEY).")
    if resp.status_code == 404:
        raise ToolError("Cenário não encontrado para esta cooperativa.")
    if resp.status_code >= 400:
        try:
            raise ToolError(resp.json().get("detail", resp.text))
        except ValueError:
            raise ToolError(resp.text or f"Erro HTTP {resp.status_code}")
    return resp.json()
```

> Confirm `from fastmcp.exceptions import ToolError` is the right import for `fastmcp==3.4.2`. If not, use `from fastmcp import ToolError` or the exception class the installed version exposes; the test imports it as `m.ToolError` so re-export it at module level (`ToolError = ToolError`) if needed.

- [ ] **Step 5: Run it, confirm pass**

Run: `pytest tests/test_mcp_server.py -v`
Expected: PASS (the 4 tests written so far — the per-tool tests come in Task 2).

- [ ] **Step 6: Commit**

```bash
git add mcp_server.py requirements.txt tests/test_mcp_server.py
git commit -m "feat(mcp): config por env + helper _get HTTP contra /api/v1/"
```

---

## Task 2: rewrite the 9 tool bodies

**Files:**
- Modify: `mcp_server.py` (the 9 `@mcp.tool()` functions)
- Modify: `tests/test_mcp_server.py` (add per-tool URL assertions)

**Interfaces:**
- Consumes: `_get` (Task 1).
- Produces: the 9 tools, same signatures as today (`mcp_server.py` lines 10–115 in the pre-plan version), bodies now `return _get(...)`. `list_scenarios` takes no args. The others pass `scenario_id` in the path and filters as kwargs.

- [ ] **Step 1: Write the failing per-tool tests**

Append to `tests/test_mcp_server.py`:

```python
CASES = [
    ("list_scenarios", (), {}, "/cenarios/"),
    ("get_daily_movements", (7,), {}, "/cenarios/7/movimentacoes/"),
    ("get_monthly_summary", (7,), {}, "/cenarios/7/resumo-mensal/"),
    ("get_factories_summary", (7,), {}, "/cenarios/7/fabricas/resumo/"),
    ("get_warehouses_summary", (7,), {}, "/cenarios/7/armazens/resumo/"),
    ("compare_factories", (7,), {}, "/cenarios/7/fabricas/comparacao/"),
    ("compare_warehouses", (7,), {}, "/cenarios/7/armazens/comparacao/"),
    ("get_stock_excesses_report", (7,), {}, "/cenarios/7/alertas/excedentes/"),
    ("get_stock_ruptures_report", (7,), {}, "/cenarios/7/alertas/rupturas/"),
]


def _fn(m, nome):
    obj = getattr(m, nome)
    return obj.fn if hasattr(obj, "fn") else obj


@pytest.mark.parametrize("nome,args,kwargs,path", CASES)
def test_tool_hits_expected_endpoint(monkeypatch, nome, args, kwargs, path):
    m = _load_mcp(monkeypatch)
    resp = MagicMock(status_code=200)
    resp.json.return_value = []
    with patch.object(m.httpx, "get", return_value=resp) as mock_get:
        _fn(m, nome)(*args, **kwargs)
    assert mock_get.call_args[0][0] == f"http://localhost:8000/api/v1{path}"


def test_daily_movements_forwards_filters(monkeypatch):
    m = _load_mcp(monkeypatch)
    resp = MagicMock(status_code=200)
    resp.json.return_value = []
    with patch.object(m.httpx, "get", return_value=resp) as mock_get:
        _fn(m, "get_daily_movements")(7, start_date="2026-01-01", origin_id=3, limit=50)
    assert mock_get.call_args[1]["params"] == {"start_date": "2026-01-01", "origin_id": 3, "limit": 50}
```

> `@mcp.tool()` may wrap the function so the callable is at `.fn` — `_fn` handles both. Confirm against `fastmcp==3.4.2` during Step 2; if the decorator returns the plain function, the `hasattr(..., "fn")` branch simply never triggers.

- [ ] **Step 2: Run it, confirm failure**

Run: `pytest tests/test_mcp_server.py -v`
Expected: FAIL — the parametrized cases (tools still call `logistics_services`).

- [ ] **Step 3: Rewrite the tool bodies**

Replace the 9 `@mcp.tool()` functions (everything from `@mcp.tool()` / `def list_scenarios` down to the end of `get_stock_ruptures_report`, keeping the trailing `if __name__ == "__main__": mcp.run(transport="stdio")`). Keep every docstring verbatim from the current file — they are the LLM-facing tool descriptions. New bodies:

```python
@mcp.tool()
def list_scenarios() -> list[dict]:
    """<manter a docstring atual, verbatim>"""
    return _get("/cenarios/")


@mcp.tool()
def get_daily_movements(
    scenario_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
    origin_id: int | None = None,
    destination_id: int | None = None,
    limit: int = 150,
) -> list[dict]:
    """<manter a docstring atual, verbatim>"""
    return _get(
        f"/cenarios/{scenario_id}/movimentacoes/",
        start_date=start_date,
        end_date=end_date,
        origin_id=origin_id,
        destination_id=destination_id,
        limit=limit,
    )


@mcp.tool()
def get_monthly_summary(
    scenario_id: int,
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """<manter a docstring atual, verbatim>"""
    return _get(
        f"/cenarios/{scenario_id}/resumo-mensal/",
        start_date=start_date,
        end_date=end_date,
    )


@mcp.tool()
def get_factories_summary(scenario_id: int) -> list[dict]:
    """<manter a docstring atual, verbatim>"""
    return _get(f"/cenarios/{scenario_id}/fabricas/resumo/")


@mcp.tool()
def get_warehouses_summary(scenario_id: int) -> list[dict]:
    """<manter a docstring atual, verbatim>"""
    return _get(f"/cenarios/{scenario_id}/armazens/resumo/")


@mcp.tool()
def compare_factories(scenario_id: int) -> list[dict]:
    """<manter a docstring atual, verbatim>"""
    return _get(f"/cenarios/{scenario_id}/fabricas/comparacao/")


@mcp.tool()
def compare_warehouses(scenario_id: int) -> list[dict]:
    """<manter a docstring atual, verbatim>"""
    return _get(f"/cenarios/{scenario_id}/armazens/comparacao/")


@mcp.tool()
def get_stock_excesses_report(scenario_id: int) -> list[dict]:
    """<manter a docstring atual, verbatim>"""
    return _get(f"/cenarios/{scenario_id}/alertas/excedentes/")


@mcp.tool()
def get_stock_ruptures_report(scenario_id: int) -> list[dict]:
    """<manter a docstring atual, verbatim>"""
    return _get(f"/cenarios/{scenario_id}/alertas/rupturas/")


if __name__ == "__main__":
    mcp.run(transport="stdio")
```

Delete the now-dead `import logistics_services` line.

- [ ] **Step 4: Run it, confirm pass**

Run: `pytest tests/test_mcp_server.py -v`
Expected: PASS (all cases).

Run: `python -m py_compile mcp_server.py`
Expected: no error.

Run: `TRANSBORDO_API_URL=http://x/api/v1 TRANSBORDO_API_KEY=k python -c "import mcp_server; print('ok')"`
Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add mcp_server.py tests/test_mcp_server.py
git commit -m "feat(mcp): 9 tools chamam /api/v1/ por HTTP, sem logistics_services"
```

---

## Task 3: `## MCP` section in the README + ADR 0009

**Files:**
- Modify: `README.md`
- Create: `docs/decisions/0009-mcp-http-ia-in-process.md`

**Interfaces:** none (docs).

- [ ] **Step 1: Add the README section**

In `README.md`, replace the `mcp_server.py` bullet with a `## MCP` section:

```markdown
## MCP

`mcp_server.py` é um servidor MCP (stdio) que expõe os 9 relatórios de logística como *tools* para
clientes LLM (Claude Desktop, Cursor, Gemini CLI). Desde a Fase 9 ele é um **cliente HTTP** da face
JSON — não acessa o banco diretamente.

Configuração (variáveis de ambiente, ou `.env` em dev):

| var | valor |
|---|---|
| `TRANSBORDO_API_URL` | base da API, ex. `https://transbordo.exemplo.com/api/v1` |
| `TRANSBORDO_API_KEY` | uma `ApiKey` ativa (criada via `python manage.py shell` ou admin) — carrega a cooperativa |

Bloco `mcp.json` do cliente:

    {
      "mcpServers": {
        "transbordo": {
          "command": "python",
          "args": ["/caminho/para/mcp_server.py"],
          "env": {
            "TRANSBORDO_API_URL": "https://transbordo.exemplo.com/api/v1",
            "TRANSBORDO_API_KEY": "..."
          }
        }
      }
    }
```

- [ ] **Step 2: Write ADR 0009**

Create `docs/decisions/0009-mcp-http-ia-in-process.md`:

```markdown
# ADR 0009 — MCP consome /api/v1/ por HTTP; Assistente de IA roda in-process no Django

- Status: Aceito
- Data: 2026-XX-XX

## Contexto

A Fase 9 migra `mcp_server.py` e `ai_assistant.py` para pararem de consultar `logistics_services.py`
(SQLAlchemy) diretamente. A face JSON da Fase 6 (`/api/v1/`, `apps/integracoes/`) é a alternativa. Os
dois consumidores têm naturezas diferentes.

## Decisão

- **`mcp_server.py` → cliente HTTP de `/api/v1/`.** É uma ferramenta remota: roda como subprocesso
  stdio na máquina de um analista, disparado pelo cliente LLM. O modelo `ApiKey` da Fase 6 (uma chave
  por cooperativa, consumidor automatizado externo — ADR 0008) foi desenhado para isso. Config por
  `TRANSBORDO_API_URL` + `TRANSBORDO_API_KEY`. O script deixa de precisar de Django/Postgres na máquina
  do analista.
- **`ai_assistant.py` → portado para uma aba "Assistente de IA" por cenário no app Django**
  (`ConversaIA` model, `apps/simulacao/assistente.py`), chamando `apps/simulacao/services.py` **em
  processo** com a cooperativa do usuário logado. Fazer a aba falar HTTP com a própria `/api/v1/` do
  mesmo processo seria latência + uma `ApiKey` para conversar consigo mesma. Ver Plano 9b.
- Alternativa rejeitada (ambos in-process): forçaria o Django inteiro + credenciais de banco na máquina
  do analista, quebrando o modelo stdio-subprocess; e a face JSON ficaria sem consumidor real.

## Consequências

- Nova dependência: `httpx` em `requirements.txt`.
- `mcp_server.py` passa a depender de a API estar no ar — erro 5xx/timeout vira `ToolError` legível.
- `get_monthly_summary` via MCP passa a receber sempre `{resumo_mensal: [], detalhe_rotas: []}` no caso
  vazio (a `/api/v1/` normaliza o achado legado — ver spec da Fase 6).
- Sem rate limiting na `/api/v1/` (risco herdado da Fase 6) — reavaliar antes de expor a chave a
  analistas fora do time.
```

- [ ] **Step 3: Commit**

```bash
git add README.md docs/decisions/0009-mcp-http-ia-in-process.md
git commit -m "docs: seção MCP no README + ADR 0009 (split MCP HTTP / IA in-process)"
```

---

## Task 4: manual verification

**Files:** none.

- [ ] **Step 1: End-to-end against a running API**

With Fase 6 merged and a real `ApiKey`:

```bash
python manage.py runserver &
python -c "from apps.core.models import Cooperativa; from apps.integracoes.models import ApiKey; \
  print(ApiKey.objects.create(cooperativa=Cooperativa.objects.first(), nome='mcp-verify').chave)"
export TRANSBORDO_API_URL=http://127.0.0.1:8000/api/v1
export TRANSBORDO_API_KEY=<a chave impressa>
```

Then exercise the server with the FastMCP inspector or a minimal client, calling each of the 9 tools,
and confirm each result matches the equivalent `curl -H "X-API-Key: $TRANSBORDO_API_KEY"
"$TRANSBORDO_API_URL/..."`. Record the comparison in the task report. Stop the server.

- [ ] **Step 2: Full suite**

Run: `pytest`
Expected: green (Django + SQLAlchemy + `tests/test_mcp_server.py`). `python -m py_compile mcp_server.py` clean.

---

## Self-Review

**Spec coverage:**

| Spec item (Plano 9a) | Task |
|---|---|
| `mcp_server.py` reescrito como cliente `httpx` + `_get` + tratamento de erro | Tasks 1–2 |
| Config por env `TRANSBORDO_API_URL` / `TRANSBORDO_API_KEY`, fail-loud | Task 1 |
| Testes com `httpx` mockado (URL/params/header por tool) + `ToolError` 401/404/4xx | Tasks 1–2 |
| Docstring de setup + seção `## MCP` no README | Tasks 1 (docstring) + 3 (README) |
| `httpx` em `requirements.txt` | Task 1 |
| ADR 0009 | Task 3 |
| Verificação campo-a-campo contra `/api/v1/` | Task 4 |
| Não importa Django/`logistics_services`/SQLAlchemy | Global Constraints + Task 2 Step 3 (delete the import) |
| Não depende da Fase 7 | Global Constraints |

**Placeholder scan:** `<manter a docstring atual, verbatim>` in Task 2 Step 3 is an explicit instruction to copy the 9 docstrings verbatim from the current `mcp_server.py` (they are the LLM-facing tool descriptions and must not be paraphrased) — not a plan gap. ADR date `2026-XX-XX` filled at execution.

**Type consistency:** `_get(path, **params)` defined in Task 1, called identically in all 9 tool bodies (Task 2). `ToolError` imported once (Task 1), raised in `_get` and asserted in tests as `m.ToolError`. `BASE_URL` / `API_KEY` module-level, set once.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-08-28-fase9a-mcp-http.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks.

**2. Inline Execution** — batch execution with checkpoints via executing-plans.

**Which approach?**
