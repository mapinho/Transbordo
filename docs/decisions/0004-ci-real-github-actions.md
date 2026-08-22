# ADR 0004 — CI real via GitHub Actions desde o commit zero

- Status: Aceito
- Data: 2026-08-22

## Contexto

O APP_Vector (projeto de referência) não tem pipeline de CI automatizado, só um gate manual documentado.
O Transbordo decide conscientemente não herdar essa lacuna.

## Decisão

- `.github/workflows/ci.yml` no repositório `Transbordo`, rodando a cada push/PR para `main`:
  `python manage.py check`, `python manage.py makemigrations --check --dry-run` e `pytest`.
- Job roda contra um container de serviço `postgres:16` (mesmo engine de produção), não SQLite — evita
  divergência de comportamento entre o banco de teste e o de produção.

## Consequências

- Todo PR/push para `main` tem sinal automático de "quebrou o quê" antes de qualquer revisão manual.
- O workflow precisa ser mantido conforme novas apps/migrações forem adicionadas nas próximas fases —
  não deveria exigir mudança estrutural, só tempo de execução crescente.
