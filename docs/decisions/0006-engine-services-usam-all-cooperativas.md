# ADR 0006 — engine.py e services.py consultam via all_cooperativas, não objects

- Status: Aceito
- Data: 2026-08-22

## Contexto

`apps.simulacao.engine`/`apps.simulacao.services` são o porte 1:1 de `calculations.py`/
`logistics_services.py`: funções de domínio que recebem `cenario_id`/`scenario_id` como parâmetro
explícito. O código SQLAlchemy original nunca teve noção de "cooperativa da sessão corrente" —
o único limite de tenant sempre foi o `cenario_id` passado pelo chamador.

## Decisão

- Toda query em `engine.py`/`services.py` usa `Model.all_cooperativas` (manager sem escopo, ADR 0001/
  0003), nunca `Model.objects` (o `TenantManager` fail-closed, que depende de
  `CooperativaScopeMiddleware` ter rodado numa requisição HTTP).
- Justificativa: estas funções precisam funcionar corretamente quando chamadas fora de uma requisição
  HTTP — um worker Procrastinate (Fase 5, próxima etapa do roteiro), um management command, ou os
  próprios testes automatizados deste módulo. Depender do contexto implícito de middleware aqui faria
  qualquer uma dessas chamadas falhar silenciosamente (queryset vazio, não um erro) assim que alguém
  esquecesse de também chamar `definir_cooperativa_atual()` manualmente — pior que exigir o
  `cenario_id`/`scenario_id` explícito que o chamador já precisa fornecer de qualquer forma.
- O uso de `all_cooperativas` aqui é exatamente o caso de "consulta cross-tenant deliberada" que a
  ADR 0003 já previu como uso legítimo do escape hatch — a autorização (o usuário pode ver este
  `cenario_id`?) é responsabilidade de quem CHAMA `engine.py`/`services.py` (a próxima fase, quando
  views/Django Ninja existirem), não destas funções de domínio puro.

## Consequências

- `engine.py`/`services.py` não têm proteção própria contra um `cenario_id` de outra cooperativa sendo
  passado por engano — confiam inteiramente no chamador. Isso é aceitável para funções de domínio
  interno (não expostas diretamente a input de usuário sem uma camada de autorização na frente), mas
  a próxima fase (views/Django Ninja) precisa validar `cenario.cooperativa_id == request.user.cooperativa_id`
  antes de repassar um `cenario_id` vindo de fora para estas funções.
