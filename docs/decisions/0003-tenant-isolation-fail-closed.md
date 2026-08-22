# ADR 0003 — TenantManager falha fechado (sem cooperativa corrente = queryset vazio)

- Status: Aceito
- Data: 2026-08-22

## Contexto

O isolamento de tenant (ADR 0001) depende de um manager de queryset que escopa automaticamente por
cooperativa. É preciso decidir o comportamento quando nenhuma cooperativa corrente está definida (ex.:
requisição anônima, contexto de management command, bug de middleware).

## Decisão

- `apps.core.tenancy.TenantManager` (usado por `CooperativaScopedModel.objects`) resolve a cooperativa
  corrente de um `ContextVar`, populado por `CooperativaScopeMiddleware` a partir de
  `request.user.cooperativa_id`.
- **Falha fechada**: se a cooperativa corrente não estiver definida, o manager retorna `queryset.none()`
  — nunca todos os registros de todas as cooperativas.
- Consultas cross-tenant deliberadas (ex.: ferramentas do Admin Vector) usam explicitamente o manager
  `all_cooperativas` (sem escopo), nunca `objects`.
- Coberto por teste automatizado formal (`apps/core/tests/test_tenancy.py`): duas cooperativas, prova de
  que uma nunca enxerga dado da outra via `objects`, e que `all_cooperativas` intencionalmente enxerga
  ambas.

## Consequências

- Qualquer código que precise de acesso cross-tenant tem que optar explicitamente por
  `all_cooperativas` — fica óbvio na revisão de código quando isso acontece.
- Um bug que apague a cooperativa corrente do contexto (middleware não executado, contexto vazado entre
  requests) se manifesta como "página vazia" (visível, fácil de notar) em vez de "vazamento de dados de
  outra cooperativa" (silencioso, muito pior).
