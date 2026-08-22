# ADR 0002 — Settings por ambiente e variáveis DJANGO_DB_* separadas do stack legado

- Status: Aceito
- Data: 2026-08-22

## Contexto

O projeto Django precisa de configuração parametrizada por ambiente (dev/prod), convivendo no mesmo
repositório e no mesmo `.env` com o stack Streamlit/SQLAlchemy existente durante toda a migração
(Fases 1-7 do roteiro).

## Decisão

- Settings organizados em `config/settings/base.py`, `config/settings/dev.py` e `config/settings/prod.py`,
  selecionados via `DJANGO_SETTINGS_MODULE` (padrão herdado do APP_Vector, ADR 0002 de lá).
- Valores sensíveis carregados do mesmo `.env` já usado pelo stack Streamlit, via `python-dotenv`.
- Variáveis de banco do stack Django usam o prefixo `DJANGO_DB_*` (`DJANGO_DB_NAME`, `DJANGO_DB_USER`,
  `DJANGO_DB_PASSWORD`, `DJANGO_DB_HOST`, `DJANGO_DB_PORT`), deliberadamente distintas de `DB_*` (usadas
  por `data_loader.get_engine()` no stack SQLAlchemy) — para que os dois stacks nunca apontem para o
  mesmo banco por acidente enquanto convivem no mesmo `.env`.

## Consequências

- Dois bancos PostgreSQL distintos (ou dois nomes de banco distintos no mesmo servidor) precisam existir
  durante a migração: um para o stack legado (`DB_NAME`, hoje `comigo`) e outro para o stack Django
  (`DJANGO_DB_NAME`, sugerido `transbordo`) — o desenvolvedor precisa criar esse segundo banco localmente
  antes de rodar `manage.py migrate` pela primeira vez.
- `.env.example` documenta as duas famílias de variáveis lado a lado.
