# ADR 0010 — MCP consome /api/v1/ por HTTP; Assistente de IA roda in-process no Django

- Status: Aceito
- Data: 2026-08-29

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
- Duplicação temporária do loop Gemini entre `ai_assistant.py` (raiz, SQLAlchemy, Streamlit) e
  `apps/simulacao/assistente.py` (ORM Django) até o Cutover (Fase 11).
