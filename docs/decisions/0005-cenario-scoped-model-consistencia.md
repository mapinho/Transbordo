# ADR 0005 — CenarioScopedModel: consistência cooperativa/cenario via clean()

- Status: Aceito
- Data: 2026-08-22

## Contexto

`cooperativa_id` é propagado como coluna direta a `Cenario` e a todos os seus descendentes (ADR 0001),
em vez de ser derivado por JOIN via `cenario.cooperativa_id` a cada leitura. Nada no `TenantManager`
(que só filtra leituras — ver ADR 0001/0003) impede que um `cooperativa_id` divergente seja gravado
numa `Fabrica`/`Armazem`/`Rota` cujo `cenario` pertence a outra cooperativa.

## Decisão

- `apps.simulacao.models.CenarioScopedModel` (abstrata, estende `CooperativaScopedModel`) adiciona um
  FK `cenario` obrigatório e um `clean()` que levanta `ValidationError` se
  `self.cenario.cooperativa_id != self.cooperativa_id`.
- Usada por `Fabrica`, `Armazem`, `Rota` (Task 1), `SafraUnidade`, `MovimentacaoDiaria` (Task 2),
  `ResumoMensalFabrica`, `ResumoMensalArmazem` (Task 3) — os 7 models cujo vínculo primário com o
  cenário é um FK direto `cenario`.
- `PrevisaoFabrica`/`PrevisaoArmazem` (Task 2) não têm FK direto a `Cenario` (nunca tiveram, no
  SQLAlchemy original — o vínculo é via `fabrica`/`armazem`), então cada um implementa seu próprio
  `clean()` mais estreito (`self.fabrica.cooperativa_id`/`self.armazem.cooperativa_id`), sem herdar
  este mixin.
- `LogExecucao` (Task 3) não herda este mixin: seu `cenario` é nullable por design (ver o próprio
  comentário no `models.py` original — representa execução contra o cenário oficial), incompatível
  com a obrigatoriedade que `CenarioScopedModel` assume. Declara seu próprio FK nullable e seu próprio
  `clean()` que só valida a consistência quando `cenario` não é `None`.
- `clean()` não é chamado automaticamente por `save()` (convenção já usada por `apps.core.models.User`,
  Fase 5 Fundação) — é responsabilidade do código de escrita (a próxima fase, quando views/forms
  existirem) chamar `full_clean()` antes de `save()`, ou usar `Model.objects.create()` sempre com o
  `cooperativa` derivado do `cenario` já validado.

## Consequências

- Nenhuma proteção em nível de banco (`CheckConstraint`) ainda — `clean()` só pega o erro se o código
  de escrita chamar `full_clean()`. Uma futura fase (quando este código for exercitado por views reais)
  deve avaliar se vale a pena promover para `CheckConstraint`, como já foi feito para
  `User.papel`/`cooperativa` na Fase 5 Fundação (revisão final, finding Important #2).
- `clean()` acessa `self.cenario` (dispara uma query se ainda não estiver em cache) — aceitável, pois
  não é chamado no caminho quente de leitura (`engine.py`/`services.py` nunca chamam `clean()`).
