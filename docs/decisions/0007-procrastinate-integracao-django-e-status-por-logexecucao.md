# ADR 0007 — Procrastinate via contrib.django, LogExecucao como fonte de status, lock duplo

- Status: Aceito
- Data: 2026-08-26

## Contexto

A Fase 5.5 do roteiro (`docs/superpowers/specs/2026-08-26-fase5-simulacao-assincrona-design.md`) precisa
disparar `engine.simular_periodo` de forma assíncrona, com uma UI de acompanhamento de status via HTMX,
sem modificar a lógica de otimização em si e sem que duas execuções simultâneas do mesmo cenário corrompam
`MovimentacaoDiaria`/`ResumoMensal*` (apagados e reescritos por completo a cada execução).

## Decisão

- Integração via `procrastinate.contrib.django` (app Django oficial) — reaproveita a conexão já
  configurada em `DJANGO_DB_*`, entra no `manage.py migrate` normal, e expõe fixtures de teste prontas
  (`procrastinate.testing.InMemoryConnector` via `procrastinate_app.current_app.replace_connector(...)`).
  Um `procrastinate.App` avulso não traria vantagem nenhuma e duplicaria configuração que o Django já
  tem.
- `LogExecucao` (já existente, tabela de auditoria de execuções) é a única fonte de verdade do status de
  uma execução em andamento — nenhuma view introspecta o schema interno do Procrastinate
  (`procrastinate_jobs`). A view que dispara cria um `LogExecucao(status='em_andamento')` como marcador
  *antes* de enfileirar a task; a task, ao terminar, apaga esse marcador em caso de sucesso (porque
  `engine.simular_periodo` já cria seu próprio `LogExecucao(status='sucesso')` de forma autônoma ao
  final — não modificado por esta fase) ou o atualiza para `status='erro'` em caso de falha (porque
  `simular_periodo` não grava nada no caminho de exceção).
- Concorrência: dois cadeados com propósitos diferentes. A view rejeita um novo disparo na hora,
  sem enfileirar, se já existe um `LogExecucao(status='em_andamento')` para aquele cenário — a menos que
  seja "órfão" (mais velho que 30 minutos, o que indica um worker morto no meio da execução; nesse caso
  o antigo é marcado `erro` e o disparo é permitido). Como defesa em profundidade contra a corrida entre
  dois POSTs quase simultâneos, `.configure(lock=f"simulacao-cenario-{id}",
  queueing_lock=f"simulacao-cenario-{id}").defer(...)` serializa tanto o enfileiramento quanto a
  execução por cenário no próprio Procrastinate.
- A task usa `Model.all_cooperativas` (nunca `Model.objects`) para toda query, incluindo a atualização do
  próprio `LogExecucao` marcador — consistente com a ADR 0006: um worker Procrastinate roda fora do
  ciclo de request HTTP, sem o contextvar de cooperativa que o `TenantManager` exige.

## Consequências

- Uma execução bem-sucedida deixa exatamente um `LogExecucao(status='sucesso')` na auditoria (o marcador
  é descartado) — o histórico de execuções não duplica linhas por causa do disparo assíncrono.
- O timeout de staleness (30 min) é um valor fixo, não configurável por variável de ambiente ainda —
  reavaliar se cenários de produção mostrarem execuções legitimamente mais longas (ver "Decisões em
  aberto" da spec).
- Rodar a aba "Simulação" localmente exige dois processos: `python manage.py runserver` e
  `python manage.py procrastinate worker` — nenhum dos dois sozinho é suficiente.
