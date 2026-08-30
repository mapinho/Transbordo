# Fase 11 — Cutover — Design

- Status: Aprovado (aguarda plano de implementação)
- Data: 2026-08-30
- Roteiro: `docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` §11

## Contexto e objetivo

As Fases 5–10 portaram o domínio para Django, expuseram a Face JSON, adicionaram auth e puseram o
stack Django em produção (`transbordo.vectorconsulting.com.br`). O stack Streamlit/SQLAlchemy original
ainda vive **neste repositório** como código morto: `app.py` e mais 9 módulos na raiz, a suíte
`tests/` (SQLAlchemy), e a ferramenta de espelhamento `apps/simulacao/legado.py` + comando
`espelhar_legado` (usada uma vez para trazer o dado do Comigo para o Transbordo local).

**Reenquadramento em relação ao roteiro §11:** o §11 previa "Streamlit desligado; cliente migrado;
`Comigo.git` congelado". Não é o que acontece. **Comigo e Transbordo são dois produtos em produção,
independentes e permanentes** (domínios, configurações e bancos de dados separados, sem interferência
mútua). O cliente atual usa os dois: **Comigo** (`comigo.vectorconsulting.com.br`, repo `Comigo.git`)
continua servindo, com **desenvolvimento congelado** mas **sem ser desligado**; a evolução do produto
acontece no **Transbordo**. Ver ADR 0011.

Portanto, "Cutover" aqui significa três coisas concretas:

1. **Este repositório larga o código legado** — remoção dos 10 módulos da raiz, da suíte `tests/`, e da
   ferramenta de espelhamento (código + testes; o spec de design do espelhamento fica como histórico).
2. **Migração de dados dev→prod** — o banco Transbordo de produção é resetado e recebe um espelho
   completo do banco de desenvolvimento (que já contém o dado real, vindo da base de produção do
   Comigo via o espelhamento da Fase 5), seguido de uma higienização de credenciais/estado de dev.
3. **`VERSION` → `1.0.0`**, tag `v1.0.0`.

## Escopo

**Dentro:**

- Remover da raiz: `app.py`, `app_logic.py`, `calculations.py`, `scenarios.py`, `data_loader.py`,
  `logistics_services.py`, `utils.py`, `models.py`, `ai_assistant.py`, `generate_templates.py`.
- Remover a suíte SQLAlchemy: diretório `tests/` inteiro (≈20 `test_*.py` + `conftest.py`).
- Remover o espelhamento (lado Django): `apps/simulacao/legado.py`,
  `apps/simulacao/management/commands/espelhar_legado.py`, e os testes
  `apps/simulacao/tests/test_{command_espelhar_legado,legado_escrita,legado_leitura}.py`.
- Podar `requirements.txt`: remover `streamlit`, `SQLAlchemy`, `psycopg2-binary`, `plotly`; adicionar
  `psycopg[binary]>=3.2,<4` explícito (hoje é dep transitiva do procrastinate).
- `pytest.ini`: `testpaths = tests apps` → `testpaths = apps`.
- `Dockerfile`: revisar `libpq5` à luz do `psycopg[binary]` (que já embute a libpq) — remover se
  redundante; nenhuma outra mudança.
- Remover `comigo.conf` e `comigo-le-ssl.conf` do repo.
- Comando `apps/core/management/commands/sanitizar_pos_restore.py` (novo) + testes (TDD).
- Runbook de migração de dados dev→prod em `docs/DEPLOY.md`.
- ADR `docs/decisions/0011-comigo-e-transbordo-produtos-permanentes.md`.
- Reescrita de `CLAUDE.md` (seções afetadas) e `README.md`.
- `CHANGELOG.md` `## [1.0.0]`, `VERSION` → `1.0.0`, tag `v1.0.0` (não pushed automaticamente).
- Remover os planos de fases já executadas de `docs/superpowers/plans/` (`fase8`, `fase9a`, `fase9b`,
  `fase10`). Specs e ADRs ficam.

**Fora:**

- Segunda cooperativa piloto / teste de carga concorrente sintético — não há segunda cooperativa; o
  cliente é único e o isolamento multi-tenant já é coberto pelos testes de `apps/`.
- Build step de Tailwind/daisyUI (substituir o CDN `@tailwindcss/browser@4`) — subprojeto próprio
  pós-`1.0.0` (toolchain de assets, integração Dockerfile/CI). Fica como está.
- Qualquer mudança no `Comigo.git` ou na sua infra (vhost, banco, container próprios).
- `Especificacao_Sistema_Transbordo_Atualizada.md` — permanece (spec funcional do domínio; descreve
  regras de negócio ainda válidas, ainda que com as telas/fluxos do Streamlit).

## Decisões

### 1. Comigo e Transbordo: dois produtos permanentes (ADR 0011)

Não há migração de cliente nem desligamento do Streamlit do cliente. O código legado neste repo é
peso morto — o Streamlit que o cliente usa é o `Comigo.git`, deploy separado. Remoção é segura para o
serviço Transbordo em produção: ele roda `gunicorn config.wsgi` + `procrastinate worker`, e nada em
`apps/` ou `config/` importa os módulos da raiz. A única ponte era `apps/simulacao/legado.py`
(`import models as legado` + `sqlalchemy`), que sai junto.

### 2. Migração de dados: espelho completo + higienização

Reset do banco de produção (`dropdb`/`createdb`) e restore de um `pg_dump -Fc` completo do banco de
desenvolvimento. Prod passa a ser idêntico ao local, **inclusive** o resíduo de dev (usuários de
teste, `ApiKey`s de dev, jobs do procrastinate, sessões). Um comando de gestão idempotente,
`sanitizar_pos_restore`, apaga esse resíduo logo após o restore. Identidade real (Admin Vector,
usuários, `ApiKey`s) é recriada em prod do zero pelo runbook.

Rejeitado: carga seletiva `--data-only` só das tabelas de domínio (menos passos de reset, mas colisão
de PK com o dado de teste que já está em prod e risco de esquecer uma tabela); `dumpdata`/`loaddata`
(frágil com as ~13k linhas de `movimentacoes_diarias` e FKs).

### 3. `sanitizar_pos_restore` — o que apaga e o que preserva

Só **uma** FK de domínio referencia `core.User`: `simulacao.ConversaIA.usuario` (CASCADE). Isso torna
o `delete()` de usuários seguro.

| Alvo | Ação | Porquê |
|---|---|---|
| `integracoes.ApiKey` | `delete()` (todas) | chave de dev não pode autenticar em prod |
| `core.User` | `delete()` (todos) | usuários de dev; cascateia `ConversaIA` e `django_admin_log` |
| `simulacao.ConversaIA` | `delete()` residual | caso sobre conversa sem `usuario` |
| `procrastinate_jobs`, `procrastinate_events` | `TRUNCATE ... RESTART IDENTITY` | job de dev pendente não pode executar em prod |
| `django_session` | `TRUNCATE` | sessões de dev |
| `django_site` (pk = `SITE_ID`) | `update(domain=ALLOWED_HOSTS[0], name=ALLOWED_HOSTS[0])` | allauth usa o Site para montar URLs de e-mail |

**Preserva:** `core.Cooperativa` (a cooperativa real) e todo o domínio `simulacao` (fábricas,
armazéns, rotas, previsões, safras, movimentações, resumos, cenários), `django_migrations`.

Tudo numa transação. Flag `--dry-run` imprime as contagens sem escrever. Idempotente: rodar duas vezes
não muda nada na segunda.

### 4. `requirements.txt` e `psycopg`

`psycopg` (v3) 3.x está instalado hoje apenas como dependência transitiva do `procrastinate` — não
está pinado. Ao remover `psycopg2-binary` (usado só pelo `data_loader.py`/`models.py` legados),
pina-se `psycopg[binary]` explícito. `psycopg[binary]` embute a libpq; o `Dockerfile` pode então
dispensar o `apt-get install libpq5` (decisão do plano — verificar que o build passa sem ele).

Deps que **ficam** (uso em `apps/`): `pandas` + `ortools` (`apps/simulacao/engine.py`), `openpyxl`
(`apps/simulacao/planilha.py`), `google-genai` (`apps/simulacao/assistente.py`), `httpx` + `fastmcp` +
`mcp[cli]` (`mcp_server.py`), `python-dotenv`.

### 5. Sequência de trabalho

Comigo e Transbordo já são produção independente; não há rollback a preservar. A ordem é indiferente
para segurança:

1. Branch de trabalho (worktree) → PR único: remoção do legado + poda de deps + `sanitizar_pos_restore`
   + docs + `VERSION`/`CHANGELOG` + ADR. Merge em `main`, tag `v1.0.0` (local).
2. Migração de dados em produção seguindo o runbook novo, quando o operador quiser. Independente do
   merge — o serviço Transbordo em produção não é afetado pela remoção do código.

## Componentes e interfaces

| Unidade | O que faz | Como se usa | Depende de |
|---|---|---|---|
| `sanitizar_pos_restore` (comando) | apaga resíduo de dev pós-restore, ajusta `django_site` | `python manage.py sanitizar_pos_restore [--dry-run]` | models `core`/`integracoes`/`simulacao`, `settings.ALLOWED_HOSTS`, conexão crua p/ as tabelas `procrastinate_*`/`django_session` |
| runbook "Migração de dados dev→prod" (`DEPLOY.md`) | procedimento manual `pg_dump`/reset/restore/sanitize/recriar identidade | operador no host | `docker compose`, `pg_dump`/`pg_restore`/`dropdb`/`createdb`, `sanitizar_pos_restore`, `criar_admin_vector` |
| ADR 0011 | registra Comigo/Transbordo como produtos permanentes separados | leitura | — |

## Tratamento de erro

- **`sanitizar_pos_restore` em banco já limpo:** idempotente — contagens zeradas, nenhuma exceção.
- **`sanitizar_pos_restore` sem as tabelas `procrastinate_*`:** não deve acontecer (migração
  `procrastinate` sempre aplicada), mas o `TRUNCATE` é `IF EXISTS`-guardado; ausência não é fatal.
- **`migrate` pós-restore acha migração a aplicar:** sinal de que o dump veio de um dev desatualizado
  — o runbook manda abortar e re-dumpar de um local com `makemigrations --check` limpo.
- **`pytest apps/` quebra após remover um módulo da raiz:** algum teste em `apps/` dependia
  implicitamente do legado. O plano remove em passos e roda `pytest apps/ -q` após cada um para
  localizar.
- **Restore em prod com `web`/`worker` no ar:** o runbook manda `docker compose stop web worker` antes
  do `dropdb`; sem isso o `dropdb` falha com "database is being accessed by other users".

## Estratégia de teste

- **`sanitizar_pos_restore`** — único código novo, TDD: cria `User`/`ApiKey`/`ConversaIA` de mentira +
  linhas em `procrastinate_jobs`/`django_session`, roda o comando, assere que `Cooperativa` + domínio
  `simulacao` sobrevivem, que `User`/`ApiKey`/`ConversaIA` e as tabelas de estado foram zeradas, e que
  o `django_site` ficou com o domínio de `ALLOWED_HOSTS[0]`. Roda de novo → assere idempotência.
  `--dry-run` não escreve.
- **Regressão da remoção:** `pytest apps/ -q` verde após cada passo; `python manage.py check` e
  `python manage.py makemigrations --check --dry-run` limpos ao final.
- **Infra:** `docker compose config` válido; `docker compose build web` OK (com `psycopg[binary]`, sem
  `libpq5` se o plano assim decidir); `check --deploy` limpo sob `config.settings.prod`.
- **Contagem de testes:** cai de ~406 para (~406 − suíte `tests/` − 3 testes de espelhamento) + os
  testes novos de `sanitizar_pos_restore`. Número exato registrado no plano.
- **Runbook de migração de dados:** não exercitável neste ambiente — rodado uma vez em produção pelo
  operador. A seção "Verificação" abaixo lista o esperado.

## Verificação (manual, produção — não faz parte das tasks do plano)

Após o merge e a execução do runbook no host:

1. `docker compose ps` → `web` healthy, `worker` up.
2. `curl https://transbordo.vectorconsulting.com.br/healthz/` → `{"version": "1.0.0", "db": "ok"}`.
3. Login com o Admin Vector recriado; abrir a cooperativa real; conferir que fábricas/armazéns/rotas/
   previsões/safras/cenários batem com o que havia no dev.
4. Rodar uma simulação e confirmar que o `worker` processa (`LogExecucao` conclui).
5. Aba "Assistente de IA" (com `GEMINI_API_KEY`) responde — `ConversaIA` nova é criada.
6. Uma `ApiKey` de dev antiga → `GET /api/v1/...` retorna `401`; a `ApiKey` nova → `200`.
7. `comigo.vectorconsulting.com.br` (Comigo.git) continua no ar, intacto.

## Self-Review

**Placeholder scan:** sem "TBD"/"TODO". "Número exato registrado no plano" e "decisão do plano"
(libpq5) são delegações deliberadas à fase de planejamento, não lacunas de design. A contagem de
linhas de `movimentacoes_diarias` (~13k) vem do CLAUDE.md (13299).

**Consistência interna:** o shape do `sanitizar_pos_restore` (o que apaga / o que preserva) é idêntico
na Decisão 3, em Componentes e em Estratégia de teste. A sequência (Decisão 5) casa com "Fora" (sem
rollback) e com o Contexto (produtos independentes).

**Escopo:** um subsistema (largar o legado + migrar dados + versionar). Sem múltiplos subsistemas
independentes; não precisa decompor. O build step de Tailwind foi explicitamente excluído por ter peso
próprio.

**Ambiguidade:** "espelho completo" = `pg_dump -Fc` do banco de dev inteiro, restaurado num banco de
prod recriado do zero — não um `--data-only` seletivo (Decisão 2, explícito). "Remover o legado" = a
lista fechada de arquivos em "Escopo", não uma varredura aberta.
