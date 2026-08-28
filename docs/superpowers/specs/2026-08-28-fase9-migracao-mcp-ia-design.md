# Fase 9 — Migração MCP / IA

## Contexto e objetivo

`mcp_server.py` (FastMCP, stdio) e `ai_assistant.py` (Gemini function-calling) hoje consultam
`logistics_services.py` (SQLAlchemy) **diretamente em processo**, sobre o stack legado de cooperativa
única. A Fase 6 (`docs/superpowers/specs/2026-08-26-fase6-face-json-design.md`, ADR 0008) construiu a
"face JSON" — `apps/integracoes/`, 9 endpoints GET sob `/api/v1/` sobre `apps/simulacao/services.py`,
autenticados por `X-API-Key` — mas deliberadamente **não** migrou os consumidores, para não misturar
"construir a API" com "trocar quem a consome".

Esta fase migra os dois. Depende da Fase 7 (Auth): a aba de IA no Django precisa de `request.user` e da
cooperativa do usuário logado.

## Escopo

**Dentro:**
- `mcp_server.py` reescrito como **cliente HTTP puro** de `/api/v1/`: sem `import logistics_services`,
  sem acesso a banco, config por variáveis de ambiente `TRANSBORDO_API_URL` + `TRANSBORDO_API_KEY`.
- `ai_assistant.py` **portado para o app Django** como uma aba "Assistente de IA" **por cenário**,
  chamando `apps/simulacao/services.py` em processo com a cooperativa do usuário logado. Histórico de
  conversa **persistido** num model novo `ConversaIA`.
- ADR 0009 registrando a decisão de split (MCP=HTTP, IA=in-process).
- Documentação de setup do MCP nova (docstring de `mcp_server.py` + seção `## MCP` no `README.md`),
  substituindo o `INSTRUCOES_MCP.md` removido na Fase 8.
- `httpx` adicionado a `requirements.txt`.

**Fora:**
- Endpoints de escrita na `/api/v1/` — os 9 são de leitura, `mcp_server.py` só lê, `clone_scenario`
  continua sendo ação de UI. Sem mudança na face JSON da Fase 6.
- Remover `logistics_services.py` / `ai_assistant.py` da raiz — o Streamlit ainda os usa até o Cutover
  (Fase 11). O loop de function-calling do Gemini fica **brevemente duplicado** entre a versão legada
  (raiz, SQLAlchemy) e a nova (`apps/simulacao/assistente.py`, ORM Django). Aceitável: o stack legado
  tem data de morte marcada.
- Auth de usuário final / allauth — é a Fase 7, pré-requisito desta.
- Multi-cooperativa no `mcp_server.py` — ele permanece "uma cooperativa por configuração" (a `ApiKey`
  carrega a cooperativa; o script só repassa).

## Levantamento

`mcp_server.py` expõe 9 `@mcp.tool()`, um por função de `logistics_services.py`, que são exatamente as 9
funções que `apps/simulacao/services.py` portou e que a `/api/v1/` da Fase 6 expõe 1:1:

| tool MCP | endpoint `/api/v1/` |
|---|---|
| `list_scenarios()` | `GET /cenarios/` (cooperativa vem da key) |
| `get_daily_movements(scenario_id, start_date?, end_date?, origin_id?, destination_id?, limit=150)` | `GET /cenarios/{id}/movimentacoes/` (filtros como query params) |
| `get_monthly_summary(scenario_id, start_date?, end_date?)` | `GET /cenarios/{id}/resumo-mensal/` |
| `get_factories_summary(scenario_id)` | `GET /cenarios/{id}/fabricas/resumo/` |
| `get_warehouses_summary(scenario_id)` | `GET /cenarios/{id}/armazens/resumo/` |
| `compare_factories(scenario_id)` | `GET /cenarios/{id}/fabricas/comparacao/` |
| `compare_warehouses(scenario_id)` | `GET /cenarios/{id}/armazens/comparacao/` |
| `get_stock_excesses_report(scenario_id)` | `GET /cenarios/{id}/alertas/excedentes/` |
| `get_stock_ruptures_report(scenario_id)` | `GET /cenarios/{id}/alertas/rupturas/` |

`ai_assistant.py` declara essas mesmas 9 funções ao Gemini como *function declarations* e, quando o
modelo pede uma chamada, executa `logistics_services.<fn>(...)` e devolve o resultado ao modelo. É
chamado pela aba "Assistente de IA" do Streamlit (`app.py`), que mantém o histórico em `st.session_state`.

## Decisões de arquitetura

### 1. Split por natureza do consumidor: MCP=HTTP, IA=in-process

*Ver ADR 0009.*

- **`mcp_server.py` é uma ferramenta remota.** Roda como subprocesso stdio na máquina de um analista,
  disparado pelo cliente LLM (Claude Desktop / Cursor / Gemini CLI). O modelo `ApiKey` da Fase 6 (uma
  chave por cooperativa, consumidor automatizado externo — ADR 0008) foi desenhado exatamente para
  isso. HTTP contra `/api/v1/` é o encaixe natural: o analista recebe uma chave, aponta o `mcp.json`
  para `https://transbordo…/api/v1/`, e o `mcp_server.py` não precisa de Django nem Postgres na máquina
  dele.
- **`ai_assistant.py` vira parte do app Django.** Depois do Cutover o Streamlit não existe — se a
  lógica não for para dentro do Django, a funcionalidade some. Como aba Django, ela chama
  `services.py` **em processo** com `cenario.cooperativa_id`; fazer ela falar HTTP com a própria `/api/v1/`
  do mesmo processo seria latência e uma `ApiKey` para conversar consigo mesma.
- Alternativa rejeitada (ambos in-process): forçaria `mcp_server.py` a carregar o Django inteiro +
  credenciais de banco na máquina do analista, quebrando o modelo stdio-subprocess; e a face JSON
  ficaria sem consumidor real.
- Alternativa rejeitada (ambos HTTP): a aba de IA chamando a si mesma por HTTP.

### 2. `mcp_server.py` — cliente HTTP, config por env, fica na raiz

- Continua um script standalone na raiz (roda como subprocesso stdio, **não** é parte do Django). Perde
  `import logistics_services`; ganha `import httpx`.
- Config:
  - `TRANSBORDO_API_URL` (ex. `https://transbordo.exemplo.com/api/v1` ou `http://localhost:8000/api/v1`
    em dev) — sem barra final, o código normaliza.
  - `TRANSBORDO_API_KEY` — a chave `X-API-Key`. Carrega a cooperativa; o script não tem noção de tenant.
  - Lidas de `os.environ`, com fallback para `.env` via `python-dotenv` (já é dependência) em dev.
  - Se qualquer uma faltar: erro claro no startup do servidor MCP (não silencia).
- Cada `@mcp.tool()` vira um wrapper fino:
  ```python
  def _get(path: str, **params) -> dict | list:
      resp = httpx.get(f"{BASE_URL}{path}", params={k: v for k, v in params.items() if v is not None},
                       headers={"X-API-Key": API_KEY}, timeout=30)
      if resp.status_code == 401:
          raise ToolError("Chave de API inválida ou inativa (TRANSBORDO_API_KEY).")
      if resp.status_code == 404:
          raise ToolError("Cenário não encontrado para esta cooperativa.")
      if resp.status_code >= 400:
          raise ToolError(resp.json().get("detail", resp.text))
      return resp.json()
  ```
  As assinaturas das 9 tools (nomes, parâmetros, docstrings) **não mudam** — só o corpo.
- `get_monthly_summary`: a `/api/v1/` já normaliza o formato vazio legado para
  `{resumo_mensal: [], detalhe_rotas: []}` (achado da Fase 6). O cliente MCP passa a receber sempre esse
  formato — melhoria, documentada.
- Docs de setup: docstring de módulo em `mcp_server.py` com um exemplo de bloco `mcp.json`
  (`command`, `args`, `env` com as duas variáveis) + uma seção `## MCP` no `README.md`. Substitui o
  `INSTRUCOES_MCP.md`.

### 3. `ai_assistant.py` — aba "Assistente de IA" por cenário

- **Model novo `ConversaIA`** em `apps/simulacao/models.py`, herda `CooperativaScopedModel`:
  - `cenario` (FK → `Cenario`, `on_delete=CASCADE`)
  - `usuario` (FK → `settings.AUTH_USER_MODEL`, `on_delete=CASCADE`)
  - `titulo` (`CharField`, gerado da primeira mensagem ou "Conversa de <data>")
  - `mensagens` (`JSONField`, default `list`) — lista de `{"papel": "user"|"assistant", "conteudo": str, "ts": iso8601}`
  - `ativa` (`BooleanField`, default `True`) — a aba mostra a conversa ativa; "Nova conversa" seta
    `ativa=False` na atual e cria outra
  - `created_at` / `updated_at`
  - `Meta.ordering = ['-updated_at']`
  - Migration + testes de isolamento de tenant (cooperativa B nunca enxerga `ConversaIA` da A).
- **Module novo `apps/simulacao/assistente.py`** — o loop de function-calling do Gemini portado:
  - As *function declarations* mapeiam para as 9 funções de `apps/simulacao/services.py`.
  - Ao executar uma chamada de função, invoca `services.<fn>(cooperativa_id=cenario.cooperativa_id,
    scenario_id=cenario.id, ...)` — em processo, sem HTTP. (As assinaturas de `services.py` já recebem
    `cooperativa_id`/`scenario_id` explícitos — ADR 0006.)
  - `google-genai` mantido. `GEMINI_API_KEY` → `settings.GEMINI_API_KEY` (já no `.env` — ver
    `CLAUDE.md`). Se ausente, a aba mostra um aviso claro em vez de quebrar.
  - Função pública: `responder(conversa: ConversaIA, mensagem_usuario: str) -> str` — anexa a mensagem
    do usuário, roda o loop, anexa a resposta do assistente, salva `conversa`, retorna o texto.
- **Views novas** em `apps/simulacao/views.py` (padrão das outras abas, `@login_required`,
  `get_object_or_404(Cenario, id=cenario_id)` tenant-scoped):
  - `assistente_tab(request, cenario_id)` — GET, renderiza a aba com a `ConversaIA` ativa (cria uma se
    não houver) e a lista de conversas passadas do par (cenário, usuário).
  - `assistente_enviar(request, cenario_id)` — POST (`require_POST`), lê `mensagem`, chama
    `assistente.responder(...)`, devolve o parcial HTMX do transcript atualizado.
  - `assistente_nova(request, cenario_id)` — POST, arquiva a ativa e cria uma nova, redireciona/HTMX.
- **URLs** em `apps/simulacao/urls.py`: `cenarios/<int:cenario_id>/assistente/`,
  `.../assistente/enviar/`, `.../assistente/nova/`. Item na barra de abas do cenário.
- **Templates**: `simulacao/assistente.html` (aba completa) + `simulacao/_assistente_transcript.html`
  (parcial HTMX trocado a cada mensagem).
- **Testes** `apps/simulacao/tests/test_views_assistente.py`:
  - `@login_required` (302 sem login);
  - isolamento de tenant (usuário da cooperativa B recebe 404 no cenário da A; não vê `ConversaIA` da A);
  - round-trip de uma mensagem com o client do Gemini **mockado** (assert que a função certa de
    `services.py` foi chamada com `cooperativa_id`/`scenario_id` corretos, e que `ConversaIA.mensagens`
    cresceu com os dois turnos);
  - histórico persiste: nova request GET na aba mostra as mensagens anteriores;
  - "Nova conversa" arquiva a ativa (`ativa=False`) e cria outra.

### 4. Dois planos independentes

O passo do `mcp_server.py` não depende em nada da aba de IA. Esta fase vira **dois planos de
implementação separados**:

- **Plano 9a — `mcp_server.py` → cliente HTTP.** Não depende da Fase 7. Passos:
  1. `mcp_server.py` reescrito como cliente `httpx` de `/api/v1/` + `_get` helper + tratamento de erro.
  2. Testes com `httpx` mockado (URL/params/header por tool) + `ToolError` nos casos 401/404/4xx.
  3. Docstring de setup + seção `## MCP` no `README.md`; `httpx` em `requirements.txt`.
  4. ADR 0009.
- **Plano 9b — aba "Assistente de IA".** Depende da Fase 7 (login + `request.user.cooperativa_id`). Passos:
  1. Model `ConversaIA` + migration + testes de isolamento de tenant.
  2. `apps/simulacao/assistente.py` (loop Gemini portado, `services.py` in-process) + testes com Gemini mockado.
  3. Views + URLs + templates + aba na navegação do cenário + testes de view.

## Verificação

- **MCP**: com uma `ApiKey` real criada via `manage.py shell` e `runserver` no ar, configurar
  `TRANSBORDO_API_URL`/`TRANSBORDO_API_KEY` e chamar as 9 tools via um cliente MCP (ou
  `python mcp_server.py` + inspector) — cada resposta bate campo a campo com o `curl` equivalente da
  `/api/v1/` (a mesma verificação da Fase 6, agora pelo outro lado).
- **Aba IA**: manual — logar, abrir a aba "Assistente de IA" de um cenário, perguntar algo que dispare
  uma função de relatório ("quais fábricas estão com excedente de estoque?"), conferir a resposta;
  recarregar a página → histórico persiste; logar como usuário de outra cooperativa → não vê nenhuma
  `ConversaIA` da primeira.
- `python manage.py check` + `pytest` (Django + SQLAlchemy) verdes.
- Tag `v0.9.0` ao final.

## Decisões em aberto / riscos

- **Duplicação temporária do loop Gemini** entre `ai_assistant.py` (raiz, SQLAlchemy, usado pelo
  Streamlit) e `apps/simulacao/assistente.py` (ORM Django). Vive até o Cutover (Fase 11), quando o
  arquivo da raiz sai. Não vale extrair uma camada comum para dois consumidores com data de morte.
- **`mcp_server.py` passa a depender do Django estar no ar.** Antes conectava direto no Postgres; agora,
  se a API estiver fora, as tools falham. Trade-off aceito: a alternativa (Django + banco na máquina do
  analista) é pior. O erro 5xx/timeout vira uma `ToolError` legível.
- **Sem rate limiting na `/api/v1/`** (risco herdado da Fase 6) — agora com um consumidor real
  (`mcp_server.py`) vale reavaliar antes de expor a chave a analistas fora do time. Registrado também no
  spec da Fase 6.
- **Persistência do histórico cresce sem limite.** `ConversaIA.mensagens` é um JSONField que só cresce.
  Aceitável no volume atual (uso interno); uma política de retenção/truncamento entra no radar se
  conversas longas virarem problema de payload.
