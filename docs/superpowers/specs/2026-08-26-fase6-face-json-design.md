# Fase 6 — Face JSON (Django Ninja sobre services.py)

## Contexto e objetivo

O roteiro (`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md`, seção 7) lista a Fase 6
como "Face JSON — Django Ninja para MCP server e Assistente de IA": `apps/integracoes/` deve expor
Django Ninja sobre `apps/simulacao/services.py`, "substituindo o acesso direto ao ORM que
`mcp_server.py`/`ai_assistant.py` fazem hoje". Fundação, Port do Domínio, UI, Carga de Dados e Simulação
Assíncrona já estão em `main`.

Hoje `mcp_server.py` (FastMCP, transporte stdio) e `ai_assistant.py` (Gemini function calling) rodam
sobre o stack legado, consultando `logistics_services.py` (SQLAlchemy) diretamente em processo — nenhum
dos dois faz uma chamada HTTP para lugar nenhum. `apps/simulacao/services.py` já é um port fiel dessa
mesma camada de relatórios para o ORM Django, usado hoje só internamente por `views.py`/`engine.py`, com
isolamento de tenant via `TenantManager` (ADR 0001/0003) quando chamado a partir de uma view, e via
`all_cooperativas` explícito quando chamado de fora do ciclo de request (ADR 0006).

Esta etapa constrói a "face JSON" em cima desse `services.py` já existente — a primeira vez que algo
externo ao processo Django vai falar com ele por HTTP.

## Escopo

**Dentro:**
- `apps/integracoes/models.py::ApiKey` — chave de API por cooperativa.
- `apps/integracoes/auth.py` — autenticação Django Ninja via header `X-API-Key`, que também define a
  cooperativa corrente do request (mesmo mecanismo do `CooperativaScopeMiddleware`).
- `apps/integracoes/api.py` — 9 endpoints `NinjaAPI` espelhando 1:1 os 9 tools que `mcp_server.py` já
  expõe, com respostas tipadas (`ninja.Schema`).
- Testes cobrindo sucesso, autenticação, autorização cross-tenant e validação de entrada de cada
  endpoint.

**Fora:**
- Migrar `mcp_server.py`/`ai_assistant.py` para consumir a API nova — decisão explícita desta etapa:
  construir e provar a API isoladamente primeiro, sem misturar com a troca de quem a consome (duas
  mudanças arriscadas na mesma entrega). A migração dos dois consumidores fica para uma etapa seguinte.
- `clone_scenario` (escrita) — os 9 endpoints são todos de leitura, o mesmo conjunto que os tools MCP já
  cobrem hoje. Nenhum consumidor atual precisa de escrita via API.
- Autenticação de usuário final (OAuth/allauth) — isso é a Fase 7 do roteiro. A chave de API desta etapa
  é processo-a-processo (um serviço automatizado por cooperativa), não login de pessoa.

## Levantamento

Os 9 endpoints espelham exatamente os 9 `@mcp.tool()` de `mcp_server.py`, que por sua vez espelham as 9
funções de `logistics_services.py` (legado) — `apps/simulacao/services.py` já é o port 1:1 dessas
mesmas 9 funções para o ORM Django. Formato de resposta de cada uma, extraído do código-fonte de
`services.py`:

- `list_scenarios(cooperativa_id)` → `list[{id, nome, is_oficial, data_criacao}]`
- `get_daily_movements(scenario_id, start_date?, end_date?, origin_id?, destination_id?, limit=150)` →
  `list[{id, data, origem_id, origem, destino_id, destino, quantidade_ton, quantidade_sc, custo_total_r$}]`
- `get_monthly_summary(scenario_id, start_date?, end_date?)` → `{resumo_mensal: [...], detalhe_rotas: [...]}`
- `get_factories_summary(scenario_id)` →
  `list[{mes, fabrica_id, fabrica, recebimento_produtor_ton, recebimento_transbordo_ton, esmagado_ton, saldo_estoque_ton, capacidade_estatica_ton, excedente_estoque_ton}]`
- `get_warehouses_summary(scenario_id)` → mesmo formato, campos `armazem_id`/`armazem`/`envio_transbordo_ton` no lugar de fábrica/esmagamento
- `compare_factories(scenario_id)` →
  `list[{fabrica_id, fabrica, recebimento_produtor_total_ton, recebimento_transbordo_total_ton, esmagado_total_ton, pico_estoque_mensal_ton, excedente_total_acumulado_ton}]`
- `compare_warehouses(scenario_id)` → mesmo formato, lado armazém
- `get_stock_excesses_report(scenario_id)` →
  `list[{mes, entidade_tipo, entidade_id, entidade_nome, estoque_final_ton, capacidade_estatica_ton, excedente_estouro_ton}]`
- `get_stock_ruptures_report(scenario_id)` → mesmo formato, campo `deficit_ton` no lugar de `excedente_estouro_ton`

**Achado:** `get_monthly_summary` retorna chaves diferentes conforme o resultado — `{"meses": [],
"rotas": []}` quando não há movimentações, `{"resumo_mensal": [...], "detalhe_rotas": [...]}` quando há.
Confirmado que é um bug pré-existente no `logistics_services.py` legado (não introduzido pelo port
Django) — `services.py` o preservou fielmente como "porte 1:1". Decisão: **não tocar em `services.py`**
(módulo compartilhado por `views.py`/`engine.py`, fora do escopo desta etapa); o endpoint Ninja
normaliza a resposta vazia para o formato `{resumo_mensal: [], detalhe_rotas: []}` antes de aplicar o
schema tipado, para que o contrato da API nova seja consistente independentemente dessa inconsistência
legada.

## Decisões de arquitetura

### 1. Chave de API por cooperativa, guardada em `ApiKey` (model), não em variável de ambiente

Um model simples (`cooperativa` FK, `chave`, `ativo`, `created_at`, sem rotação nem escopos) é
revogável sem redeploy e escala para múltiplas cooperativas sem crescer o `.env` — consistente com o
resto do schema multi-tenant do projeto. Uma variável de ambiente por cooperativa não escalaria e
exigiria redeploy para revogar uma chave comprometida.

### 2. Autenticação reaproveita o mecanismo de tenancy existente, não inventa um novo

`ApiKeyAuth` (uma classe de auth do Django Ninja) resolve o header `X-API-Key` para uma `ApiKey` ativa e
chama `definir_cooperativa_atual(api_key.cooperativa_id)` (mesma função de `apps/core/tenancy.py` que
`CooperativaScopeMiddleware` já usa para requests HTMX) pela duração do request. Consequência direta: os
endpoints podem autorizar um `scenario_id` recebido do chamador com o mesmo `get_object_or_404(Cenario,
id=scenario_id)` tenant-scoped (`.objects`) que as views HTMX já usam — nenhum mecanismo de autorização
novo, nenhuma duplicação da lógica de isolamento de tenant. `services.py` continua recebendo
`cooperativa_id`/`scenario_id` explícitos e usando `all_cooperativas` internamente (ADR 0006,
inalterado) — a autorização acontece inteiramente na camada Ninja, antes de chamar `services.py`, nunca
dentro dele.

### 3. Respostas tipadas com `ninja.Schema`, uma por formato de dict já existente

Django Ninja gera OpenAPI/Swagger automaticamente a partir de schemas tipados — é o que torna a API
autodescritiva o suficiente para um consumidor externo (MCP futuro, ou qualquer outro serviço) confiar
nela sem ler o código-fonte Python. O esforço é mecânico: os 9 formatos de resposta já são conhecidos
(ver "Levantamento" acima), só é preciso declará-los. Alternativa descartada: devolver os dicts soltos
(`response=list[dict]`) — mais rápido de escrever agora, mas deixa o contrato implícito e não detecta
drift entre o dict retornado e o formato documentado.

### 4. Endpoints somente leitura, prefixo `/api/v1/`

```
GET /api/v1/cenarios/
GET /api/v1/cenarios/{scenario_id}/movimentacoes/          ?start_date&end_date&origin_id&destination_id&limit
GET /api/v1/cenarios/{scenario_id}/resumo-mensal/          ?start_date&end_date
GET /api/v1/cenarios/{scenario_id}/fabricas/resumo/
GET /api/v1/cenarios/{scenario_id}/armazens/resumo/
GET /api/v1/cenarios/{scenario_id}/fabricas/comparacao/
GET /api/v1/cenarios/{scenario_id}/armazens/comparacao/
GET /api/v1/cenarios/{scenario_id}/alertas/excedentes/
GET /api/v1/cenarios/{scenario_id}/alertas/rupturas/
```

`/cenarios/` não tem parâmetro na URL — a cooperativa vem da API key, não é passada pelo chamador
(impossível pedir a lista de outra cooperativa por engano ou má-fé). Os 8 endpoints restantes recebem
`scenario_id` na URL e o autorizam contra a cooperativa da API key antes de chamar `services.py`
(decisão 2).

### 5. Tratamento de erros

- **401** — header `X-API-Key` ausente ou sem `ApiKey` ativa correspondente.
- **404** — `scenario_id` inexistente ou de outra cooperativa (mesmo `get_object_or_404` das views
  HTMX).
- **400** — datas malformadas: `services._parse_date` já levanta `ValueError`; um exception handler do
  Ninja (`@api.exception_handler(ValueError)`) converte isso numa resposta 400 com a mensagem do erro,
  em vez de vazar um 500.
- **422** — validação automática do Ninja/Pydantic para parâmetros de query mal-formados (`limit`
  não-numérico, etc.) — sem código adicional.

## Testes

Mesma infraestrutura `TestCase` já usada no resto do projeto — nenhuma task assíncrona envolvida aqui,
então sem a pegadinha de `TransactionTestCase` da Fase 5.5. Casos por endpoint:
- sucesso com dados reais, resposta no formato tipado esperado;
- 401 sem header `X-API-Key` e com uma chave inexistente/inativa;
- 404 para `scenario_id` pertencente a outra cooperativa;
- 400 para `start_date`/`end_date` malformados, nos dois endpoints que aceitam datas.

Mais um teste de isolamento cross-cooperativa dedicado em `list_scenarios`: a cooperativa A nunca vê um
cenário da cooperativa B na resposta, mesmo que ambas tenham cenários com o mesmo nome.

## Verificação

- `python manage.py check` e a suíte `pytest` (SQLAlchemy + Django) verdes.
- Documentação OpenAPI acessível em `/api/v1/docs` (gerada automaticamente pelo Django Ninja) —
  conferir manualmente que os 9 endpoints aparecem com os schemas de resposta corretos.
- Verificação manual: com uma `ApiKey` real criada via `manage.py shell`, chamar os 9 endpoints via
  `curl` contra o cenário oficial espelhado do banco legado
  (`docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md`) e comparar as respostas com
  as dos tools MCP equivalentes rodando sobre o mesmo cenário — devem bater campo a campo (exceto pela
  normalização do achado de `get_monthly_summary`, documentada acima).

## Decisões em aberto / riscos

- **Chave de API em texto plano no banco.** O model `ApiKey` guarda a chave diretamente, sem hash — mais
  simples para esta etapa (poucas chaves, ambiente de coexistência interna), mas significa que um vazamento
  do banco expõe as chaves diretamente. Vale reavaliar (hash + comparação constante-tempo) antes de haver
  mais de uma cooperativa piloto usando isto em produção, ou quando a Fase 7 (Auth) tratar de segurança de
  credenciais de forma mais ampla.
- **Sem rate limiting.** Um consumidor mal-comportado (ou uma chave vazada) pode gerar carga sem limite.
  Aceitável para um único consumidor interno conhecido nesta fase; entra no radar antes de expor a API a
  qualquer processo fora do controle direto do time.
- **`clone_scenario` fora do escopo.** Se o MCP server ou o Assistente de IA precisarem de uma ação de
  escrita no futuro (hoje nenhum dos dois usa `clone_scenario`), esta API precisará de um endpoint POST
  novo — não coberto por este desenho, que é deliberadamente só-leitura.
