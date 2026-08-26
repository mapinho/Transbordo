# Fase 5.5 — Simulação assíncrona (Procrastinate + polling HTMX)

## Contexto e objetivo

O roteiro da Fase 5 (`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md`) lista como
etapa 5 a fila de jobs assíncrona: "task assíncrona de simulação + polling HTMX de progresso". As
etapas anteriores já estão em `main` — Fundação, Port do Domínio, UI (grades Tabulator) e Carga de
Dados. O motor de otimização em si (`apps/simulacao/engine.py::simular_periodo`) já é um port fiel de
`calculations.py::simular_periodo`; falta apenas o disparo assíncrono e o acompanhamento de progresso
na UI — nenhuma mudança na lógica de otimização é necessária ou desejada aqui.

Hoje, no Streamlit, `simular_periodo` roda de forma síncrona e bloqueante dentro de um `st.spinner`
(`app.py:503-509`): o usuário escolhe intervalo de datas e estratégia, clica em um botão, e a
requisição HTTP fica presa até o fim da simulação. Não há progresso granular — só "Calculando..." e,
no final, sucesso ou erro. No Django/HTMX, uma requisição-resposta bloqueada por uma simulação longa
não é aceitável (timeout de proxy, worker do servidor ocupado); o disparo precisa ser assíncrono.

## Escopo

**Dentro:**
- Integração do Procrastinate ao projeto Django via `procrastinate.contrib.django`.
- `apps/simulacao/tasks.py`: task `executar_simulacao` que envolve `engine.simular_periodo` sem alterar
  sua lógica.
- Nova 6ª aba "Simulação" na subnav do cenário: formulário de disparo (datas + estratégia) e
  acompanhamento de status via polling HTMX, usando `LogExecucao` como fonte de verdade do estado.
- Guarda de concorrência: um cenário não pode ter duas execuções simultâneas.
- ADR documentando as decisões de integração (Procrastinate via `contrib.django`, `LogExecucao` como
  fonte de status, lock duplo).

**Fora:**
- Qualquer mudança em `engine.py`/`calculations.py`/`otimizar_dia`. O motor não é tocado.
- Progresso granular por dia simulado (percentual real) — decisão explícita, ver seção seguinte.
- Tela de resultado detalhado das movimentações geradas (dashboard de `MovimentacaoDiaria`/
  `ResumoMensal*`) — fica para uma fase futura; esta etapa mostra só o resumo que já existe em
  `LogExecucao` (dias simulados, duração, status).
- Deploy do worker em produção (supervisord/systemd/container) — fase "Deploy" do roteiro (etapa 8).
  Aqui o worker roda como processo de desenvolvimento local, documentado no CLAUDE.md.

## Decisões de arquitetura

### 1. Integração via `procrastinate.contrib.django`, não um `procrastinate.App` avulso

A integração oficial para Django reaproveita a conexão já configurada em `DJANGO_DB_*`, registra as
migrations do Procrastinate no `manage.py migrate` normal, e expõe `python manage.py procrastinate
worker` / fixtures de teste prontas (`InMemoryConnector` via `app.with_connector(...)`). Um `App`
avulso, gerenciando sua própria pool de conexão, não traria nenhuma vantagem e duplicaria configuração
que o Django já tem — não há trade-off real a explorar aqui, é a integração recomendada pela biblioteca
para projetos Django.

### 2. Progresso indeterminado, não percentual por dia

`simular_periodo` roda todos os dias do período dentro de uma única `transaction.atomic()` e só grava
o `LogExecucao` de sucesso no final (comentário do próprio `engine.py`: "commit separado, estritamente
posterior ao principal", preservando a garantia do original). Expor progresso por dia exigiria
instrumentar o motor para reportar fora dessa transação — risco de comprometer a garantia de
atomicidade existente, para um ganho pequeno (execuções tendem a durar segundos a poucos minutos).
A aba de Simulação mostra um spinner indeterminado enquanto `LogExecucao.status == 'em_andamento'`, e o
resultado final quando o status muda para `concluido` ou `erro`.

### 3. `LogExecucao` como única fonte de verdade do status

Em vez de a view de polling introspectar as tabelas internas do Procrastinate (`procrastinate_jobs`), a
task escreve o ciclo de vida diretamente no `LogExecucao` que o domínio já usa como trilha de auditoria:

1. Ao iniciar, a **view** (não a task) cria o `LogExecucao(status='em_andamento')` — isso precisa
   acontecer de forma síncrona no request, antes do `.defer()`, para que a checagem de concorrência do
   próximo disparo (seção 4) sempre encontre um registro consistente.
2. A task recebe o `id` desse `LogExecucao` já criado, roda `engine.simular_periodo`, e ao final
   atualiza a mesma linha para `concluido` (com `dias_simulados`, `duracao_segundos`) ou `erro` (com
   `mensagem`).

A view de polling só faz `LogExecucao.objects.filter(cenario_id=...).latest('data_execucao')` e
renderiza o fragmento correspondente ao `status` — nenhum acoplamento ao schema interno do Procrastinate.

### 4. Concorrência: dois cadeados com propósitos diferentes

`simular_periodo` apaga e reescreve `MovimentacaoDiaria`/`ResumoMensal*` do cenário inteiro; duas
execuções simultâneas no mesmo cenário corromperiam dados uma da outra.

- **Guarda de UX (rápida, na view)**: o POST de disparo rejeita na hora, sem enfileirar nada, se já
  existe um `LogExecucao(status='em_andamento')` para aquele cenário — a menos que esse registro seja
  "órfão" (mais velho que um timeout de staleness de 30 minutos), caso em que é marcado como
  `erro` ("execução interrompida — worker inativo") e o novo disparo é permitido. Sem esse timeout, um
  worker que morre no meio da execução travaria aquele cenário para sempre.
- **Guarda de correção (na task, via Procrastinate)**: `lock=f"simulacao-cenario-{cenario_id}"` no
  `.defer()` serializa a *execução* de jobs com essa chave — cobre a corrida entre dois POSTs quase
  simultâneos que passariam pela guarda de UX antes do primeiro `LogExecucao` comitar.

### 5. Tratamento de erros

A task envolve a chamada a `engine.simular_periodo` num `try/except` amplo: qualquer exceção atualiza o
`LogExecucao` para `erro` com `mensagem=str(e)[:500]` (mesmo limite de `CharField` já usado hoje) e
**relança** a exceção, para que o próprio Procrastinate também registre a falha no seu log interno —
observabilidade dupla sem custo adicional.

Nenhuma validação nova de intervalo de datas além do que `engine.py`/`calculations.py` já fazem —
mantém paridade com o comportamento atual do Streamlit.

## Fluxo e URLs

Três URLs novas em `apps/simulacao/urls.py`, seguindo o padrão das grades existentes:

- `cenarios/<id>/simulacao/` (GET) — a aba: formulário com datas pré-preenchidas via
  `engine.obter_range_previsoes` e select de estratégia (`Econômico` / `Expedição` / `Segurança`), mais
  o status da última execução conhecida.
- `cenarios/<id>/simulacao/executar/` (POST) — aplica a guarda de concorrência (seção 4), cria o
  `LogExecucao`, enfileira a task, devolve o fragmento de polling.
- `cenarios/<id>/simulacao/status/` (GET) — fragmento HTMX (`hx-trigger="every 2s"`) que lê o
  `LogExecucao` mais recente do cenário e renderiza: spinner (`em_andamento`), resumo de sucesso
  (`concluido`) ou mensagem de erro (`erro`). Nos dois estados terminais, o fragmento devolvido **não**
  inclui `hx-trigger`, o que naturalmente encerra o polling.

`templates/simulacao/_subnav.html` ganha o link da 6ª aba.

## Testes

TDD, como o resto do projeto. Os testes usam o `InMemoryConnector` do Procrastinate
(`app.with_connector(...)`) para rodar a task de forma síncrona e determinística nos testes, sem exigir
um worker real.

Casos a cobrir:
- POST enfileira a task e cria `LogExecucao(status='em_andamento')`.
- POST é bloqueado quando já existe um `em_andamento` recente (dentro do timeout de staleness).
- POST é permitido quando o `em_andamento` existente é órfão (mais velho que o timeout), e o antigo é
  marcado como `erro`.
- Task de sucesso atualiza `LogExecucao` com `status='concluido'`, `dias_simulados`,
  `duracao_segundos`.
- Task com exceção atualiza `LogExecucao` para `erro` com a mensagem truncada, e relança.
- View de polling renderiza o fragmento certo para cada `status`, e omite `hx-trigger` nos estados
  terminais.
- Isolamento de tenant: uma cooperativa não vê nem consegue disparar simulação para cenário de outra
  (mesmo padrão de teste já usado nas grades existentes).

## Verificação

- `python manage.py check` e a suíte `pytest` (SQLAlchemy + Django) verdes.
- Verificação manual: subir `python manage.py procrastinate worker` e `python manage.py runserver` em
  paralelo, disparar uma simulação real pela aba nova contra o cenário oficial espelhado do banco
  legado (`docs/superpowers/specs/2026-08-24-espelhamento-dados-legado-design.md`), confirmar que
  `MovimentacaoDiaria`/`ResumoMensal*` são gerados e que o polling chega ao estado `concluido` sem
  reload manual da página.

## Emenda ao roteiro

CLAUDE.md deve passar a documentar `python manage.py procrastinate worker` como comando de
desenvolvimento, ao lado de `runserver`, já que a partir desta etapa os dois processos precisam rodar
juntos para a simulação funcionar localmente.

## Decisões em aberto / riscos

- **Timeout de staleness fixo em 30 minutos.** É um valor razoável dado que execuções reais duram
  segundos a poucos minutos, mas não foi medido contra dados de produção reais em escala — vale
  reavaliar se cenários maiores (mais fábricas/armazéns/período mais longo) aparecerem no espelhamento
  legado.
- **Worker de desenvolvimento não tem restart automático.** Se o worker cair, novas simulações ficam
  enfileiradas sem rodar até alguém subir o processo de novo — aceitável para desenvolvimento local,
  mas é exatamente o tipo de risco operacional que a fase "Deploy" (etapa 8 do roteiro) precisa resolver
  com supervisão de processo antes do cutover.
- **Sem tela de resultado detalhado nesta etapa.** O usuário só vê o resumo (`dias_simulados`,
  `duracao_segundos`, status) — para conferir as movimentações geradas, ainda é preciso consultar o
  banco diretamente ou esperar uma fase de Dashboard. Fica registrado como próximo passo natural, não
  como parte desta etapa.
