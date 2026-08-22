# ADR 0001 — Multi-tenancy: schema compartilhado + cooperativa_id

- Status: Aceito
- Data: 2026-08-22

## Contexto

O Transbordo evolui de um app de cooperativa única para um SaaS multi-cooperativa. É preciso isolar os
dados de cada cooperativa (tenant) sem reescrever o motor de otimização (`calculations.py`) nem adotar
uma solução operacionalmente pesada demais para o estágio atual do produto.

## Decisão

- Schema compartilhado: uma única base de dados, um único conjunto de tabelas, com `cooperativa_id`
  (FK, `on_delete=PROTECT`) propagado a `Cenario` e a todos os seus descendentes — mesmo tipo de
  migração aditiva que a correção A11 da Fase 1 já fez para `cenario_id` no stack SQLAlchemy.
- Isolamento automático via `TenantManager`/`CooperativaScopeMiddleware` (ver
  `docs/decisions/0003-tenant-isolation-fail-closed.md`): toda query em um model derivado de
  `CooperativaScopedModel` fica implicitamente escopada pela cooperativa do usuário autenticado.
- **Alternativa rejeitada**: `django-tenants` (schema-per-tenant) — isolamento mais forte, mas migrations
  por schema e integração menos comum com Procrastinate/HTMX; mais complexidade operacional do que o
  estágio atual do produto justifica.

## Consequências

- Toda tabela tenant-scoped precisa herdar `CooperativaScopedModel` (ou repetir o padrão manualmente) —
  esquecer isso é um vazamento de isolamento silencioso, por isso o teste de isolamento é obrigatório
  (ADR 0003).
- Uma cooperativa com volume desproporcional de dados compartilha a mesma tabela/índices das demais —
  aceitável no estágio atual; reavaliar se o volume por cooperativa crescer muito antes de uma eventual
  migração para schema-per-tenant.
