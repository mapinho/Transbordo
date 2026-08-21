# Relatório de Revisão de Código — Fase 1

**Data:** 20/08/2026
**Escopo:** 12 módulos Python de produção (~2.500 linhas), revisados em 4 lotes independentes via agentes especializados em Python.
**Método:** leitura completa dos arquivos-alvo de cada lote + cross-reference com módulos relacionados; sem alterações de código nesta fase — apenas achados.

## Resumo

| Severidade | Qtde | Ação recomendada |
|---|---|---|
| **Crítico** | 5 | Corrigir antes de qualquer trabalho de arquitetura (Fase 5) — são bugs de perda/corrupção silenciosa de dados em produção hoje |
| **Alto** | 11 | Corrigir na Fase 3/4, priorizados pelo impacto listado abaixo |
| **Médio** | 14 | Backlog de dívida técnica — boa parte já é o achado de performance N+1 documentado no roteiro, mais duplicação e lacunas de validação |
| **Baixo** | 8 | Faxina — código morto, imports, constantes mágicas |

Os achados dos dois itens já registrados no roteiro original (credencial hardcoded em `data_loader.py:61`, `except:` nu em `utils.py:171,174`) foram confirmados como únicos no seu tipo — nenhuma outra instância do mesmo padrão apareceu nos 12 arquivos.

---

## 🔴 Críticos

> **Status (20/08/2026): os 5 Críticos foram corrigidos e têm teste de regressão.** Infra de testes criada em `tests/` (pytest + SQLite em memória via `tests/conftest.py`; `pytest.ini`; `pytest` adicionado em `requirements-dev.txt`). Lógica pura extraída de `app.py` para `app_logic.py` (sem import de `streamlit`) para permitir teste unitário de C2/C3. Suíte completa: `.venv/Scripts/python.exe -m pytest tests/ -v` → 6 passed. Altos/Médios/Baixos permanecem em aberto.

### C1 — Simulação apaga o histórico antes de recalculá-lo, sem transação
**Arquivo:** `calculations.py:158-161, 276` · também `app.py:387-393`
`simular_periodo` deleta e **comita** todas as `MovimentacaoDiaria`/`ResumoMensal*` do cenário logo no início (linha 161), antes do laço de até 730 dias rodar. O resultado novo só é salvo no commit final (linha 276). `app.py` captura a exceção mas nunca chama `session.rollback()` — e não adiantaria, o delete já está commitado.
**Cenário de falha:** qualquer exceção no meio do laço (dado de safra/previsão faltando, timeout do OR-Tools, queda de conexão) deixa o cenário **permanentemente sem movimentações nem resumos** no banco. O assistente de IA e o MCP passam a reportar "sem dados" para um cenário que antes tinha um plano válido, sem nenhum rastro do que aconteceu.

### C2 — Edições em campos inteiros de Fábricas/Armazéns nunca são salvas
**Arquivo:** `app.py:282-297` (Fábricas), `app.py:302-316` (Armazéns)
O handler de salvar Fábricas grava só 3 dos 6 campos editáveis — `limite_caminhoes`, `carga_media_caminhao` e `estoque_inicial` nunca chegam ao banco. O handler de Armazéns não atualiza `estoque_inicial` em linhas existentes (só grava esse campo ao *criar* uma linha nova). Em ambos, o toast "Salvo com sucesso!" aparece de qualquer forma.
**Cenário de falha:** planejador edita "Limite de Caminhões" de uma fábrica, salva, vê sucesso, roda a simulação — o otimizador usa o valor antigo silenciosamente. Não há como o usuário perceber.

### C3 — Vazamento de conexão de banco em qualquer exceção não tratada
**Arquivo:** `app.py:55, 607` · `data_loader.py:82-97`
`session.close()` é a última linha de `main()`, sem `try/finally`. O engine é compartilhado entre todos os usuários (`st.cache_resource`) com pool padrão (5 + 10 overflow). Qualquer exceção não tratada em qualquer parte do fluxo (ver A5/A6 abaixo) pula o close.
**Cenário de falha:** depois de ~15 ocorrências de qualquer exceção não tratada (ex. limpar a célula "Distância (km)" em Rotas e salvar), o pool inteiro se esgota — **todos os usuários** passam a travar/errar em `init_db()`, exigindo restart do processo. É uma saída de ar da aplicação inteira, não um bug isolado de um usuário.

### C4 — Clonagem de cenário pode desviar ou perder janelas de safra de fábricas
**Arquivo:** `scenarios.py:91`
Único ponto do código que faz `entidade_tipo == 'Fábrica'` (comparação estrita); todo o resto do sistema usa "se `== 'Armazém'`, senão assume Fábrica". Se o valor persistido não for exatamente a string `'Fábrica'`, cai no `else` e busca em `armazem_map` — e como os IDs de `Fabrica` e `Armazem` são sequências independentes que comumente colidem (1, 2, 3...), a janela de safra da fábrica pode ser silenciosamente descartada ou **anexada a um armazém errado** no cenário clonado.

### C5 — Clonagem de cenário não é transacional
**Arquivo:** `scenarios.py:11-101` · `app.py:208-217`
O novo `Cenario` é commitado na linha 14; as seis fases seguintes (fábricas, armazéns, rotas, previsões, safras) não têm `try/except`/rollback. `app.py` captura a exceção mas nunca chama `session.rollback()`.
**Cenário de falha:** falha em qualquer fase intermediária deixa um `Cenario` vazio e órfão no banco (visível na lista mas sem dados), **e** deixa a sessão do Postgres em estado de transação abortada pelo resto da renderização da página — toda query seguinte nessa página falha com um erro sem relação aparente com a causa real.

---

## 🟠 Altos

> **Status (20/08/2026): os 11 Altos foram corrigidos e têm teste de regressão.** Suíte completa: 35 testes, todos verdes (`.venv/Scripts/python.exe -m pytest tests/ -v`). Destaques do que mudou: `logistics_services.py` ganhou `get_stock_ruptures_report` (espelhado em `ai_assistant.py`/`mcp_server.py`), lookups em lote no lugar de N+1, `MAX_LIMIT=1000` e mensagens de data inválida claras (A2-A4); `data_loader.py` agora valida campos obrigatórios antes de tocar a sessão, trata célula vazia igual a coluna ausente no fallback, e isola erro por linha nos 4 importadores (A8-A10); `app.py`/`app_logic.py` ganharam builders de DataFrame compartilhados entre upload e edição, validação nos 5 handlers de salvar, e refresh do `session_state` pós-commit (A5-A7); `models.py` teve `cenario_id` marcado `nullable=False` nas 7 tabelas escopadas por cenário (A11 — **ver ressalva de migração abaixo**); `calculations.py` agora levanta exceção se nenhum solver OR-Tools estiver disponível e loga warning em status não-ótimo (A1). **Achado extra descoberto durante a correção:** os handlers de Rotas e Previsões em `app.py` usavam atribuição de dicionário (`r['campo'] = ...`) em objetos ORM, o que sempre lançava `TypeError` — ou seja, salvar Rotas ou Previsões estava **100% quebrado** antes desta correção, não apenas "sem validação".
>
> **Ressalva operacional (A11):** a mudança em `models.py` só é garantida em bancos criados do zero (testes, novo deploy). Um Postgres de produção já existente precisa de uma migração manual: confirmar que não há linhas com `cenario_id IS NULL` nas 7 tabelas e só então rodar `ALTER TABLE ... ALTER COLUMN cenario_id SET NOT NULL` — isso não foi (e não deveria ser) automatizado por um agente sem acesso ao banco real.

| # | Achado | Local |
|---|---|---|
| A1 | Falha do solver (indisponível ou não-ótimo) é tratada como "nenhum movimento necessário" — `None` e `[]` são ambos falsy, sem log de status não-ótimo | `calculations.py:38-40,152,212-214` |
| A2 | Estoque negativo ("ruptura") é permitido sem clamp e nunca alertado — `get_stock_excesses_report` só verifica excesso positivo; contradiz a missão declarada do assistente de IA de evitar rupturas | `calculations.py:199,207,246,249`; `logistics_services.py:290-310`; `ai_assistant.py:9` |
| A3 | N+1 em toda ferramenta de IA/MCP, sem limite superior real (`limit=150` não é hard cap) | `logistics_services.py:62-321` (7 ocorrências) |
| A4 | `mcp_server.py` não tem nenhum tratamento de exceção — data string malformada crasha com traceback bruto exposto ao cliente MCP | `mcp_server.py:19-39` |
| A5 | Upload de planilha deixa `session_state` com colunas de banco em vez de colunas rotuladas — próxima edição crasha com `KeyError` | `app.py:498-501,510-513` vs `280-297/300-316` |
| A6 | Validação inconsistente nos handlers de salvar — commit parcial em Fábricas, zero validação em Armazéns/Rotas/Previsões/Safra; `float("")` crasha sem tratamento | `app.py:284-296,303-374` |
| A7 | Linhas salvas/adicionadas não voltam para o `session_state` — save bem-sucedido parece ter falhado | `app.py:223-274,302-316` |
| A8 | Células vazias de Excel viram `NaN`, que satisfaz `NOT NULL` no Postgres sem erro — corrompe capacidades usadas pelo otimizador silenciosamente | `data_loader.py:240-245,273-275` |
| A9 | `.get()` com fallback só cobre coluna ausente, não célula vazia — contradiz o fallback documentado (`custo_frete_entressafra` → `custo_frete_ton`) | `data_loader.py:309,343-358` |
| A10 | Zero tratamento de exceção nos laços de import — uma linha ruim crasha o lote inteiro com traceback bruto, sem indicar qual linha/coluna | `data_loader.py:229-361`; `app.py:495,507,520,527` |
| A11 | `cenario_id` é `nullable=True` em toda tabela escopada por cenário — inserção futura sem esse campo vira dado órfão invisível para todas as queries filtradas | `models.py:20,36,49,85,95,114,128` |

---

## 🟡 Médios

> **Status (20/08/2026): 11 dos 14 Médios corrigidos e testados; 3 conscientemente adiados.** Suíte completa: 66 testes, todos verdes. Corrigidos: M1 (cache de cenários com `st.cache_data(ttl=30)` + invalidação explícita nas mutações), M2 (lookups em lote em `app_logic.py`), M4 (`get_movement_totals` via `func.sum`), M5 (safra consolidada num único helper `obter_janela_safra`, dead code removido), M6 (resolvido como efeito colateral do A3), M7 (crash no `format_dataframe` para célula já formatada), M8 (previsões em lote na clonagem), M12/M13/M14 (scripts órfãos `analise_mineiros.py`, `temp_aggregate.py`, `generate_templates.py` deletados — nada no projeto os importava). **Adiados conscientemente:** M3 (já substancialmente mitigado pelo C3 — a sessão sempre fecha corretamente agora, então a conexão volta ao pool a cada rerun; reescrever o ciclo de vida da sessão do Streamlit para reuso teria risco desproporcional ao ganho); M9 (validação de ownership de `scenario_id` — não há conceito de tenant/auth hoje, forçar uma validação agora seria simular algo que só faz sentido pós-Fase 5); M10 (deduplicar `ai_assistant.py`/`mcp_server.py` — a forma correta provavelmente é superada pela migração para Django Ninja/DRF da Fase 5, investir agora arrisca retrabalho).
>
> **Achado extra corrigido, sem ID formal:** a credencial de banco hardcoded em `data_loader.py:61` (`"Comigo36908!"`), sinalizada logo no início da Fase 1 mas nunca incluída no catálogo C/A/M/L — removida; `get_engine()` agora falha explicitamente pedindo `.env` em vez de usar um fallback com senha em texto plano.

| # | Achado | Local |
|---|---|---|
| M1 | Lista de cenários requery a cada rerun do Streamlit, sem `st.cache_data` | `app.py:58` |
| M2 | N+1 / lookups duplicados por linha em vez de join | `app.py:172,188,242-264` |
| M3 | Sessão de banco criada/destruída a cada rerun em vez de escopada | `app.py:55/607` |
| M4 | Totais de comparação agregados em Python em vez de SQL (`func.sum`) | `app.py:133-139` |
| M5 | `esta_na_safra` é código morto; a mesma lógica de janela de safra é duplicada em 2 outros pontos independentes — risco de drift | `calculations.py:13-28,104-111,139-143` |
| M6 | `session.get()` duplicado (2x por linha) em vez de cachear, inconsistente com o padrão usado no resto do arquivo | `logistics_services.py:106-107,207,251` |
| M7 | Coerção de coluna objeto em `format_dataframe` pode crashar o render se a célula já vier formatada em pt-BR (ex. reimportação de export) | `utils.py:118-128` |
| M8 | N+1 / flush por linha em `clone_scenario` em vez de query em lote | `scenarios.py:36,50,69,79` |
| M9 | Nenhuma ferramenta de IA/MCP valida ownership de `scenario_id` — sem risco hoje (single-tenant), mas é exatamente o buraco que a Fase 5 (SaaS) precisa fechar antes de multi-tenant | `ai_assistant.py:38-126`; `mcp_server.py:18-105` |
| M10 | Lógica dos wrappers de ferramenta 100% duplicada entre `ai_assistant.py` e `mcp_server.py`, sem fonte única — qualquer correção de validação precisa ser aplicada 2x | `ai_assistant.py:30-126` vs `mcp_server.py:10-105` |
| M11 | Parâmetros opcionais tipados como `str`/`int` em vez de `Optional[...]` nos dois arquivos | `ai_assistant.py:39-64`; `mcp_server.py:20-45` |
| M12 | `analise_mineiros.py` é código morto (nada importa) com nomes de entidade hardcoded — crasha em qualquer dataset sem um armazém chamado "MINEIROS" | `analise_mineiros.py:13-21` |
| M13 | `temp_aggregate.py` é código morto que consulta SQLite bruto, mas o banco real é PostgreSQL — silenciosamente não faz nada, ou pior, lê um `.db` local não relacionado se existir um no diretório | `temp_aggregate.py:11-32` |
| M14 | `generate_templates.py` está dessincronizado do exportador real (`app.py:399-480`) — falta a coluna `custo_frete_entressafra`, causando preço de entressafra errado se alguém ainda usar esse script | `generate_templates.py:23-26` vs `app.py:445` |

---

## ⚪ Baixos

> **Status (20/08/2026): 7 dos 8 Baixos corrigidos.** L1 (atribuições redundantes removidas), L2 (import movido para o topo), L3 (resolvido como efeito colateral do A4), L4 (cascade duplo `delete-orphan` removido — teste revelou que a suíte SQLite não valida `ondelete='CASCADE'` do FK sem `PRAGMA foreign_keys=ON`, ficando como sugestão de melhoria futura da suíte), L5 (heurística de detecção de nuvem simplificada junto da remoção da credencial hardcoded), L6/L7 (resolvidos pela deleção de `generate_templates.py`), L8 (números mágicos ton→saca nomeados). **Não aplicável:** nenhum Baixo ficou pendente por decisão — todos os 8 foram endereçados (diretamente ou como efeito colateral de outro fix).

| # | Achado | Local |
|---|---|---|
| L1 | Atribuições redundantes que duplicam saída de `build_df_from_model` | `app.py:229,235,266` |
| L2 | Import no meio de função em vez do topo do módulo | `app.py:545` |
| L3 | Parsing de data sem try/except nas tools expostas à IA/MCP (menos grave que A4 porque `ai_assistant.py` tem um catch-all externo) | `logistics_services.py:48,51,94,97` |
| L4 | Dupla ownership `delete-orphan` em `Rota` (via `Fabrica.rotas` e `Armazem.rotas`) — inofensivo hoje porque `Rota` sempre é criada via construtor direto, mas é um risco latente se um refactor futuro passar a usar `.append()` | `models.py:29-30,42-43` |
| L5 | Detecção de ambiente cloud/local frágil (`STREAMLIT_SERVER_PORT` no `os.environ`) pode mascarar a proteção contra fallback de credencial hardcoded | `data_loader.py:54` |
| L6 | Coluna `eh_safra` do template de previsões nunca é lida no import — usuário preenche, é descartada silenciosamente | `generate_templates.py:29-31`; `data_loader.py:318-366` |
| L7 | `generate_templates.py` inteiro está órfão (nada no app o chama) — segunda fonte de verdade do schema de import, desincronizada | `generate_templates.py:1-37` |
| L8 | Números mágicos de conversão ton↔saca (`1000`, `60`) duplicados em vez de constante nomeada | `logistics_services.py:73,109` |

---

## Não-achados confirmados
- Sem risco de SQL injection em nenhum dos 12 arquivos — todo SQL construído por f-string usa apenas nomes de tabela fixos, nunca entrada de usuário.
- `GEMINI_API_KEY` nunca é logada, ecoada ou exposta em mensagem de erro.
- `clone_scenario` duplica corretamente todas as categorias de dado exigidas pela regra de negócio documentada (fábricas, armazéns, rotas, previsões, safras), omitindo corretamente dados computados (`MovimentacaoDiaria`, `ResumoMensal*`).

## Recomendação de sequenciamento
Os 5 Críticos (C1–C5) envolvem perda/corrupção silenciosa de dados **em produção hoje**, não são dívida técnica que pode esperar a Fase 5 — recomenda-se corrigi-los antes de iniciar a migração de arquitetura, já que qualquer um deles seria re-descoberto (e mais caro de depurar) dentro de um Django novo. C1, C3 e C5 compartilham a mesma causa raiz (falta de `try/finally`/transação ao redor de operações multi-passo) e podem ser corrigidos numa única leva.
