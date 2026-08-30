# Fase 11 — Cutover — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Este repositório larga o stack Streamlit/SQLAlchemy legado (código morto), ganha um comando de higienização pós-restore para a migração de dados dev→prod, e é versionado `1.0.0`.

**Architecture:** Remoção em passos verificados (`pytest apps/` verde após cada um), porque o único acoplamento do legado dentro de `apps/` é `apps/simulacao/legado.py` — some primeiro, e o resto da raiz sai depois sem tocar o serviço Django em produção (`gunicorn config.wsgi` + `procrastinate worker`). A migração de dados é `pg_dump`/reset/restore manual (runbook) + um comando de gestão idempotente `sanitizar_pos_restore` que apaga o resíduo de dev.

**Tech Stack:** Django 6, `pytest`/`pytest-django`, PostgreSQL, procrastinate, Docker Compose, Apache.

**Spec:** `docs/superpowers/specs/2026-08-30-fase11-cutover-design.md`

## Global Constraints

- **Nada em `apps/` ou `config/` importa os módulos da raiz** (`app.py`, `models.py`, etc.) exceto `apps/simulacao/legado.py` (Task 1, que sai). Confirmar com `pytest apps/ -q` após cada remoção.
- **Não tocar o `Comigo.git` nem a infra dele** (vhost, banco, container próprios).
- **`Especificacao_Sistema_Transbordo_Atualizada.md` permanece** — é a spec funcional do domínio.
- Deps que **ficam** (uso real em `apps/`): `pandas` + `ortools` (`apps/simulacao/engine.py`), `openpyxl` (`apps/simulacao/planilha.py`), `google-genai` (`apps/simulacao/assistente.py`), `httpx` + `fastmcp` + `mcp[cli]` (`mcp_server.py`), `python-dotenv`.
- Deps que **saem**: `streamlit`, `SQLAlchemy`, `psycopg2-binary`, `plotly`. Entra: `psycopg[binary]>=3.2,<4`.
- Testes rodam sob `config.settings.dev` (`pytest.ini`); precisam do PostgreSQL local (`DJANGO_DB_*`).
- `sanitizar_pos_restore` é o único código novo → TDD estrito (teste falha primeiro).
- Commit style: `feat(cutover):` / `chore(cutover):` / `docs:` / `test(cutover):`, sumário pt-BR. Terminar toda mensagem de commit com:
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
- `VERSION` é a fonte de verdade da versão (`config/settings/base.py:15` lê o arquivo). Bump só na Task 7.
- Tag `v1.0.0` criada localmente na Task 7, **não** pushed automaticamente.

---

## File Structure

**Arquivos novos:**
- `apps/core/management/commands/sanitizar_pos_restore.py` — comando de higienização pós-restore.
- `apps/core/tests/test_command_sanitizar_pos_restore.py` — testes do comando.
- `docs/decisions/0011-comigo-e-transbordo-produtos-permanentes.md` — ADR.

**Arquivos apagados:**
- Raiz: `app.py`, `app_logic.py`, `calculations.py`, `scenarios.py`, `data_loader.py`, `logistics_services.py`, `utils.py`, `models.py`, `ai_assistant.py`, `generate_templates.py`.
- `tests/` — diretório inteiro (19 `test_*.py` + `conftest.py` + `__pycache__`).
- `apps/simulacao/legado.py`, `apps/simulacao/management/commands/espelhar_legado.py`.
- `apps/simulacao/tests/test_command_espelhar_legado.py`, `apps/simulacao/tests/test_legado_escrita.py`, `apps/simulacao/tests/test_legado_leitura.py`.
- `comigo.conf`, `comigo-le-ssl.conf`.
- `docs/superpowers/plans/2026-08-28-fase8-versionamento-limpeza.md`, `docs/superpowers/plans/2026-08-28-fase9a-mcp-http.md`, `docs/superpowers/plans/2026-08-28-fase9b-assistente-ia.md`, `docs/superpowers/plans/2026-08-29-fase10-deploy.md`.

**Arquivos modificados:**
- `requirements.txt` — poda de deps.
- `pytest.ini` — `testpaths = apps`.
- `Dockerfile` — avaliar remoção do `libpq5`.
- `.env.example` — remover bloco legado (`DB_*`, `DATABASE_URL`), consertar `GEMINI_API_KEY`.
- `apps/simulacao/CLAUDE.md` — remover a entrada de `legado.py`.
- `docs/DEPLOY.md` — runbook de migração de dados; encolher a seção "Streamlit (legado)".
- `CLAUDE.md` — reescrita das seções afetadas.
- `README.md` — reescrita como README de projeto Django.
- `CHANGELOG.md` — `## [1.0.0]`.
- `VERSION` — `1.0.0`.

---

## Task 1: Remover a ferramenta de espelhamento (lado Django)

**Files:**
- Delete: `apps/simulacao/legado.py`
- Delete: `apps/simulacao/management/commands/espelhar_legado.py`
- Delete: `apps/simulacao/tests/test_command_espelhar_legado.py`
- Delete: `apps/simulacao/tests/test_legado_escrita.py`
- Delete: `apps/simulacao/tests/test_legado_leitura.py`
- Modify: `apps/simulacao/CLAUDE.md`
- Modify: `.env.example`

**Interfaces:**
- Consumes: nada.
- Produces: `apps/` sem nenhuma referência a `sqlalchemy` nem a `import models`. Prova de que `apps/` é auto-suficiente antes de mexer na raiz.

- [ ] **Step 1: Confirmar que nada em `apps/` (fora dos testes de espelhamento) usa `legado`/`espelhar_legado`**

Run: `grep -rn "legado\|espelhar_legado\|ler_legado\|abrir_sessao_legado" apps/ --include="*.py" | grep -v "apps/simulacao/legado.py\|management/commands/espelhar_legado.py\|/tests/test_command_espelhar_legado\|/tests/test_legado_"`
Expected: só linhas de **comentário** em `apps/simulacao/planilha.py` (linhas ~46, ~219, ~662, que citam `data_loader.py`), nada mais. Se aparecer um `import` ou chamada real fora disso, PARAR e reportar.

- [ ] **Step 2: Apagar os cinco arquivos**

```bash
git rm apps/simulacao/legado.py \
       apps/simulacao/management/commands/espelhar_legado.py \
       apps/simulacao/tests/test_command_espelhar_legado.py \
       apps/simulacao/tests/test_legado_escrita.py \
       apps/simulacao/tests/test_legado_leitura.py
```

- [ ] **Step 3: Remover a entrada de `legado.py` do `apps/simulacao/CLAUDE.md`**

Apagar o bullet inteiro que começa com ``- `apps/simulacao/legado.py` — development-only tool that mirrors the seven input tables`` (uma linha longa; termina em ``requires `DATABASE_URL` (the legacy connection string) in the environment.``).

- [ ] **Step 4: Limpar o `.env.example`**

Remover o bloco de topo inteiro:
```
# Stack Streamlit/SQLAlchemy (legado) — ver .env real (não versionado) para valores.
# DB_USER=
# DB_PASSWORD=
# DB_HOST=localhost
# DB_PORT=5432
# DB_NAME=comigo
# GEMINI_API_KEY=
# DATABASE_URL=postgresql://user:pass@localhost:5432/comigo
# ^ exigida pelo management command Django `espelhar_legado` (apps/simulacao/legado.py):
#   é a conexão SQLAlchemy para o banco legado que ele lê.
```
Na seção "Fase 9", a linha `# GEMINI_API_KEY já existe acima (aba Assistente de IA)` fica órfã — **substituir** por uma chave real:
```
GEMINI_API_KEY=
```
(colocada logo após `TRANSBORDO_API_KEY=`).

- [ ] **Step 5: Rodar a suíte Django**

Run: `pytest apps/ -q`
Expected: PASS. A contagem cai pelos 3 testes de espelhamento removidos (`test_command_espelhar_legado`, `test_legado_escrita`, `test_legado_leitura`). Nenhuma falha nova de import.

- [ ] **Step 6: `check` do Django**

Run: `python manage.py check`
Expected: `System check identified no issues`.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore(cutover): remove a ferramenta de espelhamento (legado.py + espelhar_legado)

Trabalho concluído — o dado do Comigo já está no Transbordo local. Era o único
acoplamento do stack legado dentro de apps/. Spec de design fica como histórico.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: Remover o stack legado da raiz + a suíte `tests/`

**Files:**
- Delete: `app.py`, `app_logic.py`, `calculations.py`, `scenarios.py`, `data_loader.py`, `logistics_services.py`, `utils.py`, `models.py`, `ai_assistant.py`, `generate_templates.py`
- Delete: `tests/` (diretório inteiro)
- Modify: `pytest.ini`

**Interfaces:**
- Consumes: Task 1 (nada em `apps/` importa mais o legado).
- Produces: raiz só com `manage.py` e `mcp_server.py` em `.py`. `pytest.ini` com `testpaths = apps`.

- [ ] **Step 1: Confirmar zero import dos módulos da raiz fora da própria raiz e de `tests/`**

Run: `grep -rn "^\(import\|from\) \(app_logic\|calculations\|scenarios\|data_loader\|logistics_services\|utils\|models\|ai_assistant\)\b\|^import app$" --include="*.py" apps/ config/ mcp_server.py manage.py`
Expected: **nenhuma saída**. Se algo aparecer, PARAR e reportar (o design assume zero).

- [ ] **Step 2: Apagar os dez módulos da raiz e o diretório `tests/`**

```bash
git rm app.py app_logic.py calculations.py scenarios.py data_loader.py \
       logistics_services.py utils.py models.py ai_assistant.py generate_templates.py
git rm -r tests/
```

- [ ] **Step 3: Ajustar o `pytest.ini`**

De:
```
testpaths = tests apps
```
Para:
```
testpaths = apps
```
(o resto do arquivo — `DJANGO_SETTINGS_MODULE`, `python_files`, `pythonpath = .` — fica intacto; `pythonpath = .` continua servindo o `mcp_server.py` na raiz.)

- [ ] **Step 4: Rodar a suíte inteira**

Run: `pytest -q`
Expected: PASS. Agora `pytest` (sem args) == `pytest apps/`. Zero erro de coleta / import.

- [ ] **Step 5: Verificar migrações e check**

Run: `python manage.py check && python manage.py makemigrations --check --dry-run`
Expected: `System check identified no issues` e `No changes detected`.

- [ ] **Step 6: `py_compile` do que sobrou na raiz**

Run: `python -m py_compile manage.py mcp_server.py`
Expected: sem saída (sucesso).

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore(cutover): remove o stack Streamlit/SQLAlchemy da raiz + suite tests/

app.py e os 9 módulos irmãos + a suite SQLAlchemy (SQLite in-memory). O Streamlit
que o cliente usa é o Comigo.git, deploy separado (ver ADR 0011). pytest.ini passa
a testpaths = apps.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: Podar `requirements.txt` e revisar o `Dockerfile`

**Files:**
- Modify: `requirements.txt`
- Modify: `Dockerfile`

**Interfaces:**
- Consumes: Task 2 (nenhum código importa mais streamlit/sqlalchemy/psycopg2/plotly).
- Produces: `requirements.txt` só com deps do stack Django + MCP; `psycopg[binary]` explícito.

- [ ] **Step 1: Confirmar que `apps/` não usa as deps que vão sair**

Run: `grep -rn "import streamlit\|import sqlalchemy\|from sqlalchemy\|import plotly\|from plotly\|psycopg2" apps/ config/ mcp_server.py --include="*.py"`
Expected: **nenhuma saída**.

- [ ] **Step 2: Editar `requirements.txt`**

Remover estas 4 linhas:
```
streamlit==1.55.0
SQLAlchemy==2.0.48
psycopg2-binary==2.9.11
plotly==6.6.0
```
Adicionar (logo após `procrastinate>=3.9,<4.0`):
```
psycopg[binary]>=3.2,<4
```
Manter `pandas`, `openpyxl`, `ortools`, `google-genai`, `httpx`, `fastmcp`, `mcp[cli]`, `python-dotenv` e todas as `django*`/`gunicorn`/`whitenoise`.

- [ ] **Step 3: Reinstalar e rodar a suíte**

Run: `python -m pip install -r requirements.txt && pytest -q`
Expected: `psycopg[binary]` instala; `streamlit`/`SQLAlchemy`/`plotly`/`psycopg2-binary` podem continuar no ambiente (pip não desinstala sozinho) — o que importa é a suíte **PASS** com o `requirements.txt` novo.

- [ ] **Step 4: Revisar o `libpq5` no `Dockerfile`**

O `Dockerfile` instala `libpq5` "runtime do psycopg 3". Com `psycopg[binary]` (que empacota a própria libpq), o `libpq5` do apt fica redundante. Editar o bloco `apt-get` para instalar só `curl`:
```dockerfile
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
```
E ajustar o comentário acima dele (remover a linha sobre `libpq5`).

- [ ] **Step 5: Build da imagem**

Run: `docker compose build web`
Expected: build **passa**; o passo `collectstatic` roda; `pip install` traz `psycopg[binary]`. Se o build falhar em runtime de psycopg (ex.: `libpq` ausente), reverter o Step 4 (voltar `libpq5`) e registrar isso na nota da task.

- [ ] **Step 6: Smoke-test do container**

Run: `docker run --rm transbordo:latest python -c "import psycopg; import django; import gunicorn; print('ok')"`
Expected: `ok`.

- [ ] **Step 7: Validar o compose**

Run: `docker compose config --quiet && echo OK`
Expected: `OK`.

- [ ] **Step 8: Commit**

```bash
git add requirements.txt Dockerfile
git commit -m "chore(cutover): poda requirements (sai streamlit/sqlalchemy/plotly/psycopg2), psycopg[binary] explicito

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Comando `sanitizar_pos_restore` (TDD)

**Files:**
- Create: `apps/core/management/commands/sanitizar_pos_restore.py`
- Create: `apps/core/tests/test_command_sanitizar_pos_restore.py`

**Interfaces:**
- Consumes: `apps.core.models.User`/`Cooperativa`, `apps.integracoes.models.ApiKey`, `apps.simulacao.models.Cenario`/`ConversaIA`, `django.contrib.sites.models.Site`, `settings.ALLOWED_HOSTS`/`SITE_ID`, conexão crua para as tabelas `procrastinate_jobs`/`procrastinate_events`/`procrastinate_periodic_defers`/`procrastinate_workers`/`django_session`.
- Produces: `python manage.py sanitizar_pos_restore [--dry-run]`. Sem `--dry-run`: apaga todas as linhas de `ApiKey`, `User`, `ConversaIA`; `TRUNCATE ... RESTART IDENTITY` nas 5 tabelas de estado; `Site` pk=`SITE_ID` recebe `domain`/`name` = `settings.ALLOWED_HOSTS[0]` (pulado se vazio ou `*`). Tudo numa transação. Idempotente. `--dry-run` imprime as contagens e retorna sem escrever. Exit 0 sempre (salvo erro de banco).

- [ ] **Step 1: Escrever os testes que falham**

Criar `apps/core/tests/test_command_sanitizar_pos_restore.py` com:

```python
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings

from apps.core.models import Cooperativa, User
from apps.integracoes.models import ApiKey
from apps.simulacao.models import Cenario, ConversaIA


def _count(tabela):
    with connection.cursor() as cur:
        cur.execute(f'SELECT count(*) FROM {tabela}')
        return cur.fetchone()[0]


class SanitizarPosRestoreTests(TestCase):
    def setUp(self):
        self.coop = Cooperativa.objects.create(nome='Coop Real', slug='coop-real')
        self.cenario = Cenario.all_cooperativas.create(cooperativa=self.coop, nome='Cenário Real')
        self.user = User.objects.create_user(
            username='dev', email='dev@x.test', password='x',
            papel=User.PAPEL_ADMIN_COOPERATIVA, cooperativa=self.coop,
        )
        ApiKey.objects.create(cooperativa=self.coop, nome='dev key')
        ConversaIA.all_cooperativas.create(
            cooperativa=self.coop, cenario=self.cenario, usuario=self.user,
        )
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO procrastinate_jobs (queue_name, task_name) "
                "VALUES ('default', 'dummy')"
            )
            cur.execute(
                "INSERT INTO django_session (session_key, session_data, expire_date) "
                "VALUES ('k', 'd', now())"
            )

    def test_apaga_identidade_e_estado_preserva_dominio(self):
        call_command('sanitizar_pos_restore')
        self.assertEqual(User.objects.count(), 0)
        self.assertEqual(ApiKey.objects.count(), 0)
        self.assertEqual(ConversaIA.all_cooperativas.count(), 0)
        self.assertEqual(_count('procrastinate_jobs'), 0)
        self.assertEqual(_count('django_session'), 0)
        self.assertEqual(Cooperativa.objects.count(), 1)
        self.assertEqual(Cenario.all_cooperativas.count(), 1)

    @override_settings(ALLOWED_HOSTS=['transbordo.example.com', 'localhost'])
    def test_ajusta_django_site(self):
        call_command('sanitizar_pos_restore')
        site = Site.objects.get(pk=settings.SITE_ID)
        self.assertEqual(site.domain, 'transbordo.example.com')
        self.assertEqual(site.name, 'transbordo.example.com')

    def test_idempotente(self):
        call_command('sanitizar_pos_restore')
        call_command('sanitizar_pos_restore')
        self.assertEqual(User.objects.count(), 0)

    def test_dry_run_nao_escreve(self):
        call_command('sanitizar_pos_restore', '--dry-run')
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(ApiKey.objects.count(), 1)
        self.assertEqual(_count('procrastinate_jobs'), 1)
```

- [ ] **Step 2: Rodar para ver falhar**

Run: `pytest apps/core/tests/test_command_sanitizar_pos_restore.py -q`
Expected: FAIL — `CommandError: Unknown command: 'sanitizar_pos_restore'` (comando não existe).

- [ ] **Step 3: Implementar o comando**

Criar `apps/core/management/commands/sanitizar_pos_restore.py`:

```python
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.management.base import BaseCommand
from django.db import connection, transaction

from apps.core.models import User
from apps.integracoes.models import ApiKey
from apps.simulacao.models import ConversaIA

TABELAS_ESTADO = (
    'procrastinate_jobs',
    'procrastinate_events',
    'procrastinate_periodic_defers',
    'procrastinate_workers',
    'django_session',
)


class Command(BaseCommand):
    help = (
        'Higieniza o banco logo apos restaurar um dump de desenvolvimento em '
        'producao: apaga usuarios/ApiKeys/conversas de dev, zera filas do '
        'procrastinate e sessoes, e ajusta o django_site a partir de '
        'ALLOWED_HOSTS. Idempotente. Nao toca a Cooperativa nem o dominio de '
        'simulacao.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run', action='store_true',
            help='So imprime o que seria apagado, sem escrever.',
        )

    def _contar(self, tabela):
        with connection.cursor() as cur:
            cur.execute(f'SELECT count(*) FROM {tabela}')
            return cur.fetchone()[0]

    def handle(self, *args, **options):
        contagens = {
            'ApiKey': ApiKey.objects.count(),
            'User': User.objects.count(),
            'ConversaIA': ConversaIA.all_cooperativas.count(),
        }
        for t in TABELAS_ESTADO:
            contagens[t] = self._contar(t)
        for nome, n in contagens.items():
            self.stdout.write(f'  {nome}: {n}')

        host = settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else ''
        if host in ('', '*'):
            self.stdout.write(self.style.WARNING(
                'ALLOWED_HOSTS[0] inutilizavel; django_site nao sera ajustado.'
            ))
            host = None

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('--dry-run: nada foi escrito.'))
            return

        with transaction.atomic():
            ApiKey.objects.all().delete()
            User.objects.all().delete()
            ConversaIA.all_cooperativas.all().delete()
            with connection.cursor() as cur:
                cur.execute(
                    'TRUNCATE TABLE '
                    + ', '.join(TABELAS_ESTADO)
                    + ' RESTART IDENTITY'
                )
            if host:
                Site.objects.filter(pk=settings.SITE_ID).update(domain=host, name=host)

        self.stdout.write(self.style.SUCCESS('Higienizacao concluida.'))
```

- [ ] **Step 4: Rodar para ver passar**

Run: `pytest apps/core/tests/test_command_sanitizar_pos_restore.py -q`
Expected: PASS (4 testes).

- [ ] **Step 5: Suíte inteira (regressão)**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add apps/core/management/commands/sanitizar_pos_restore.py \
        apps/core/tests/test_command_sanitizar_pos_restore.py
git commit -m "feat(cutover): comando sanitizar_pos_restore (higieniza dev-residual pos-restore)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: Runbook de migração de dados + remoção das confs `comigo*`

**Files:**
- Modify: `docs/DEPLOY.md`
- Delete: `comigo.conf`, `comigo-le-ssl.conf`

**Interfaces:**
- Consumes: `sanitizar_pos_restore` (Task 4), `criar_admin_vector` (já existe).
- Produces: seção "Migração de dados dev→prod (uma vez)" no `DEPLOY.md`; seção "Streamlit (legado)" reduzida; confs `comigo*` fora do repo.

- [ ] **Step 1: Apagar as confs `comigo*`**

```bash
git rm comigo.conf comigo-le-ssl.conf
```

- [ ] **Step 2: Substituir a seção "Streamlit (legado)" do `docs/DEPLOY.md`**

Trocar o bloco atual (o `## Streamlit (legado)` e os dois parágrafos abaixo dele) por:

```markdown
## Comigo (produto separado)

`comigo.vectorconsulting.com.br` roda a partir do repo **Comigo.git**, com vhost, banco e container
próprios — fora do escopo deste deploy e deste repositório. Ver ADR 0011.
```

- [ ] **Step 3: Adicionar a seção de migração de dados ao `docs/DEPLOY.md`**

Inserir, logo após a seção "## Rollback" e antes de "## Comigo (produto separado)":

```markdown
## Migração de dados dev→prod (uma vez)

Popular o banco de produção do Transbordo com o dado real, que hoje vive só no banco de
desenvolvimento (trazido do Comigo pelo espelhamento da Fase 5). Estratégia: **espelho completo** do
banco de dev, restaurado num banco de prod recriado do zero, seguido de higienização do resíduo de dev.

**Pré-requisito:** o stack Django já está no ar em prod (`docs/DEPLOY.md` "Primeira vez").

1. **No dev** — dump do banco local:
   ```
   pg_dump -Fc -d transbordo -f transbordo_dev.dump
   ```
   Transferir `transbordo_dev.dump` para o host de produção.

2. **No host de prod** — parar os serviços que escrevem e recriar o banco:
   ```
   cd /opt/comigo
   docker compose stop web worker
   dropdb -h localhost -U transbordo transbordo
   createdb -h localhost -U transbordo -O transbordo transbordo
   pg_restore -h localhost -U transbordo --no-owner --no-privileges -d transbordo transbordo_dev.dump
   ```
   (`dropdb` falha com "being accessed by other users" se `web`/`worker` ainda estiverem de pé — daí o `stop` antes.)

3. **Conferir schema:**
   ```
   docker compose run --rm migrate
   ```
   Esperado: `No migrations to apply` (o dump já carrega `django_migrations`). Se aparecer migração a
   aplicar, o dump veio de um dev desatualizado — abortar, rodar `makemigrations --check` no dev e
   re-dumpar.

4. **Higienizar o resíduo de dev:**
   ```
   docker compose run --rm web python manage.py sanitizar_pos_restore --dry-run   # confere as contagens
   docker compose run --rm web python manage.py sanitizar_pos_restore
   ```
   Apaga `User`/`ApiKey`/`ConversaIA` de dev, zera `procrastinate_*` e `django_session`, ajusta o
   `django_site` para `DJANGO_ALLOWED_HOSTS[0]`. **Não** toca a cooperativa nem o domínio de simulação.

5. **Recriar identidade real:**
   ```
   docker compose run --rm web python manage.py criar_admin_vector <user> --email <email>
   ```
   Depois, pela tela Gestão → Usuários, criar os usuários reais; pelo admin (`/admin/integracoes/apikey/`),
   emitir as `ApiKey`(s) reais.

6. **Subir e conferir:**
   ```
   docker compose up -d web worker
   curl -s http://127.0.0.1:8060/healthz/          # {"version": "1.0.0", "db": "ok"}
   ```
   Login com o Admin Vector; abrir a cooperativa; conferir fábricas/armazéns/rotas/previsões/safras/
   cenários; rodar uma simulação e ver o `worker` concluir.
```

- [ ] **Step 4: Conferir que o `DEPLOY.md` não referencia mais `comigo*.conf` como algo deste repo**

Run: `grep -n "comigo.conf\|comigo-le-ssl\|comigo\*" docs/DEPLOY.md`
Expected: no máximo menção histórica; nenhuma instrução de `cp`/`a2ensite` de `comigo*` neste repo. Ajustar o que sobrar.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs(cutover): runbook de migracao dev->prod no DEPLOY.md; remove comigo*.conf

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 6: ADR 0011 + reescrita de `CLAUDE.md` / `README.md` + limpeza de plans

**Files:**
- Create: `docs/decisions/0011-comigo-e-transbordo-produtos-permanentes.md`
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Delete: `docs/superpowers/plans/2026-08-28-fase8-versionamento-limpeza.md`, `docs/superpowers/plans/2026-08-28-fase9a-mcp-http.md`, `docs/superpowers/plans/2026-08-28-fase9b-assistente-ia.md`, `docs/superpowers/plans/2026-08-29-fase10-deploy.md`

**Interfaces:**
- Consumes: decisões da spec.
- Produces: docs sem o file-map do legado; ADR 0011 registrando os dois produtos permanentes.

- [ ] **Step 1: Escrever o ADR `docs/decisions/0011-comigo-e-transbordo-produtos-permanentes.md`**

```markdown
# 11. Comigo e Transbordo: dois produtos permanentes independentes

Data: 2026-08-30
Status: Aceito

## Contexto

O roteiro da migração Django (`docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` §11)
previa um "Cutover": desligar o Streamlit, migrar o cliente para o Django e **congelar** o `Comigo.git`.

Na prática isso não aconteceu. O `Comigo.git` está em produção em `comigo.vectorconsulting.com.br`
com vhost, configuração e banco próprios; o `Transbordo.git` está em produção em
`transbordo.vectorconsulting.com.br`, também com infra e banco próprios e independentes. Os dados de
desenvolvimento do Transbordo vieram da base de produção do Comigo (espelhamento da Fase 5).

## Decisão

Comigo e Transbordo são **dois produtos em produção, independentes e permanentes**. O cliente usa os
dois: o Comigo continua servindo, com **desenvolvimento congelado** (nenhuma alteração nova) mas **sem
ser desligado**; a evolução do produto acontece só no Transbordo. Os dois repositórios e as duas infra
não interferem entre si.

Consequência para a "Fase 11": ela deixa de ser "migração de cliente / desligar Streamlit" e passa a
ser apenas **higiene deste repositório** — remover o código do stack Streamlit/SQLAlchemy que aqui é
peso morto (o Streamlit real é o Comigo.git) — mais a carga do banco de produção do Transbordo (espelho
do dev) e o versionamento `1.0.0`.

## Consequências

- O `Especificacao_Sistema_Transbordo_Atualizada.md` permanece como spec funcional do domínio.
- `mcp_server.py` continua no repo (cliente stdio da Face JSON, ADR 0010).
- Nenhuma mudança é feita no `Comigo.git`.
- Não há janela de rollback a preservar no cutover: os dois produtos já são produção estável à parte.
```

- [ ] **Step 2: Apagar os planos de fases já executadas**

```bash
git rm docs/superpowers/plans/2026-08-28-fase8-versionamento-limpeza.md \
       docs/superpowers/plans/2026-08-28-fase9a-mcp-http.md \
       docs/superpowers/plans/2026-08-28-fase9b-assistente-ia.md \
       docs/superpowers/plans/2026-08-29-fase10-deploy.md
```
(Este plano — `2026-08-30-fase11-cutover.md` — **fica** até a Fase 11 ser concluída; um follow-up futuro o remove.)

- [ ] **Step 3: Reescrever o `CLAUDE.md` — seção "Project Overview"**

Trocar o parágrafo que começa `**Comigo** is a logistics planning...` por:

```markdown
**Transbordo** is a multi-cooperative SaaS for planning & optimizing soy "transbordo" (transshipment):
daily movement of soy between Armazéns (warehouses, origins) and Fábricas (crushing plants,
destinations) to minimize freight cost while guaranteeing plants never run out of raw material. It
supports "what-if" scenario simulation (deep-cloned from the official baseline) and exposes the same
data through an MCP server and an in-app Gemini-powered chat assistant.

It began as a single-cooperative Streamlit app (**Comigo**, still in production at
`comigo.vectorconsulting.com.br` from the separate `Comigo.git` repo, development frozen) and was
rebuilt on Django 6 + HTMX across Fases 5–11. See ADR 0011.
```

Apagar o parágrafo seguinte (`The long-term direction (see ...) is evolving this from a single-cooperative Streamlit app...`) — já não é "long-term direction", é o estado atual.

- [ ] **Step 4: `CLAUDE.md` — seção "Tech Stack"**

Remover as linhas:
```
- Streamlit — UI, re-runs the whole script on every interaction
- SQLAlchemy 2.0 — ORM, legacy `Column()` declarative style, retrofit-typed with `Mapped[...]` annotations (no `mapped_column()` migration done yet)
- Pandas / Plotly — data processing & charts
```
Ajustar a linha do PostgreSQL de:
```
- PostgreSQL — production database; SQLite in-memory — test database (`tests/conftest.py`)
```
Para:
```
- PostgreSQL — production and test database (tests use a real local PostgreSQL via `DJANGO_DB_*`)
```
Adicionar:
```
- Django 6 + HTMX + django-cotton — server-rendered UI
- pandas — usado pelo engine de otimização e pela camada de services
```

- [ ] **Step 5: `CLAUDE.md` — seção "Commands"**

Substituir o bloco inteiro por:

```bash
# Install
pip install -r requirements.txt
pip install -r requirements-dev.txt   # adds pytest, for local dev only

# Run the app (dev)
python manage.py runserver
python manage.py procrastinate worker   # em outro terminal — a aba Simulação depende dele (ADR 0007)

# Run the MCP server standalone (stdio) — cliente HTTP de /api/v1/ (Fase 9)
TRANSBORDO_API_URL=http://localhost:8000/api/v1 TRANSBORDO_API_KEY=<ApiKey> python mcp_server.py

# Tests (precisa de um PostgreSQL local alcançável via DJANGO_DB_*)
pytest

# Django sanity checks
python manage.py check
python manage.py makemigrations --check --dry-run
```

- [ ] **Step 6: `CLAUDE.md` — seção "Fase 5"**

Trocar o título `## Fase 5 — Fundação Django (em progresso)` por `## Fase 5 — Fundação Django (concluída)` e substituir o parágrafo de coexistência ("Durante a coexistência com o app Streamlit/SQLAlchemy existente, os dois stacks vivem no mesmo repositório:") e a lista abaixo dele por:

```markdown
Migração para Django 6 + HTMX (ver `docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md`).

- `python manage.py check` — sanity check do projeto.
- `pytest` — roda os testes de `apps/*/tests/`; precisa de um PostgreSQL local alcançável via
  `DJANGO_DB_*` (crie o banco/role antes de rodar pela primeira vez — ver `docs/decisions/0002-...`).
- O `.env` usa `DJANGO_DB_*` / `DJANGO_*` — ver `.env.example`.
- ADRs em `docs/decisions/`, de `0001` a `0011`.
- `python manage.py procrastinate worker` — worker assíncrono; precisa estar rodando junto com o
  `runserver` para a aba "Simulação" executar (ADR 0007).
```

- [ ] **Step 7: `CLAUDE.md` — seção "Environment"**

Substituir o bloco (`A .env file at the project root is required...` até `On Streamlit Cloud, credentials are read from st.secrets instead of .env.`) por:

```markdown
A `.env` file at the project root is **required** (ver `.env.example`):

```env
DJANGO_SECRET_KEY=...
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_DB_NAME=transbordo
DJANGO_DB_USER=transbordo
DJANGO_DB_PASSWORD=...
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5432
GEMINI_API_KEY=...   # opcional — só para a aba "Assistente de IA"
```
```
(A lista "Fase 7 (stack Django) adiciona..." logo abaixo fica — só trocar "stack Django" por "Auth".)

- [ ] **Step 8: `CLAUDE.md` — seção "Architecture / File Map"**

Remover os 10 bullets do legado (`app.py`, `app_logic.py`, `models.py`, `calculations.py`, `scenarios.py`, `data_loader.py`, `logistics_services.py`, `ai_assistant.py`, `utils.py`, e o bullet `templates/` — pre-generated Excel templates — que descreve o legado; **manter** um bullet novo de `templates/` sobre os templates Django). Remover o bullet ``- `tests/` — pytest suite; `conftest.py` provides an in-memory SQLite `session` fixture...``.

O topo da seção fica:
```markdown
- `manage.py` — Django entrypoint.
- `mcp_server.py` — servidor MCP (stdio); desde a Fase 9 é cliente HTTP de `/api/v1/` (ADR 0010), sem acesso a banco. Config `TRANSBORDO_API_URL`/`TRANSBORDO_API_KEY`.
- `config/` — projeto Django (settings por ambiente, `urls.py`, `wsgi.py`).
- `apps/core/` — identidade e tenancy: `models.py` (`Cooperativa`, `User` com `papel`), `tenancy.py`/`middleware.py`, `adapters.py` (allauth, sem signup), `permissions.py`, comandos `criar_admin_vector` e `sanitizar_pos_restore`.
- `apps/gestao/` — telas HTMX de gestão (Cooperativas, Usuários, Minha cooperativa, Conta). **Sem models**. Ver `apps/gestao/CLAUDE.md`.
- `apps/simulacao/` — Django port do domínio (models, engine, services), Carga de Dados (`planilha.py`), Assistente de IA (`assistente.py` + `ConversaIA`). Ver `apps/simulacao/CLAUDE.md`.
- `apps/integracoes/` — Face JSON (Fase 6): Django Ninja somente-leitura sobre `apps/simulacao/services.py`, `/api/v1/`, auth `X-API-Key` (`ApiKey`). Ver `apps/integracoes/CLAUDE.md`.
- `templates/` — templates Django (`base.html`, `cotton/`, telas de `account`/`registration`/`socialaccount`/`gestao`/`simulacao`).
```

- [ ] **Step 9: `CLAUDE.md` — seção "Key Business Rules"**

Na linha das sacas, trocar:
```
- 1 saca = 60 kg — always use `KG_PER_TON` / `KG_PER_SACA` from `logistics_services.py`, never a magic `1000/60`.
```
Por:
```
- 1 saca = 60 kg — always use `KG_PER_TON` / `KG_PER_SACA` from `apps/simulacao/services.py`, never a magic `1000/60`.
```
Na linha da formatação pt-BR, trocar `via `utils.format_dataframe`` por `via os helpers de formatação de `apps/simulacao/`` (o `utils.py` da raiz não existe mais).
Na primeira linha (Cenário oficial), trocar `(see the field's own comment in `models.py`)` por `(see the field's own comment in `apps/simulacao/models.py`)`.

- [ ] **Step 10: `CLAUDE.md` — "Testing / TDD", "Related Docs", "Roadmap Status"**

- "Testing / TDD": trocar `write a failing test in `tests/` first` por `write a failing test in `apps/*/tests/` first`.
- "Roadmap Status": substituir o parágrafo inteiro por:
  ```markdown
  Fases 1–11 concluídas. `VERSION` / `CHANGELOG.md` na `1.0.0`. O produto Streamlit original (Comigo)
  segue em produção à parte, congelado (ADR 0011). Próximas evoluções são do Transbordo — confirme o
  escopo com o dono do projeto antes de começar trabalho novo.
  ```
- Apagar o parágrafo inteiro `One outstanding **manual, production-only** task from Fase 1: ...` (era sobre o `models.py` legado — não se aplica mais).

- [ ] **Step 11: Reescrever o `README.md`**

Substituir o conteúdo inteiro por:

```markdown
# Transbordo

SaaS multi-cooperativa para planejamento e otimização de transbordo de soja: movimentação diária entre
armazéns e fábricas minimizando frete, garantindo que as fábricas não fiquem sem matéria-prima.
Simulação de cenários ("e se"), Face JSON (`/api/v1/`) e assistente de IA (Gemini).

Django 6 + HTMX. Reconstruído a partir do app Streamlit original (**Comigo**, em produção à parte,
congelado — ver `docs/decisions/0011-...`).

## Rodar (dev)

1. `.env` na raiz (ver `.env.example`) — `DJANGO_SECRET_KEY`, `DJANGO_DB_*`, etc. Precisa de um
   PostgreSQL local com o banco/role `transbordo` (ver `docs/decisions/0002-...`).
2. Instalar:
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt   # pytest, para dev
   ```
3. Migrar e subir:
   ```bash
   python manage.py migrate
   python manage.py runserver
   python manage.py procrastinate worker   # outro terminal — a aba Simulação depende dele
   ```
4. Primeiro Admin Vector: `python manage.py criar_admin_vector <user> --email <email>`.

## Testes

```bash
pytest
```

## Deploy

Ver `docs/DEPLOY.md` (Docker Compose + gunicorn + Apache; runbook de primeira vez, recorrente,
rollback e migração de dados dev→prod).

## MCP

`mcp_server.py` é um servidor MCP (stdio) que expõe os relatórios de logística como *tools* para
clientes LLM (Claude Desktop, Cursor, Gemini CLI). É um **cliente HTTP** da Face JSON — não acessa o
banco.

| var | valor |
|---|---|
| `TRANSBORDO_API_URL` | base da API, ex. `https://transbordo.vectorconsulting.com.br/api/v1` |
| `TRANSBORDO_API_KEY` | uma `ApiKey` ativa (admin) — carrega a cooperativa |

Bloco `mcp.json` do cliente:

    {
      "mcpServers": {
        "transbordo": {
          "command": "python",
          "args": ["/caminho/para/mcp_server.py"],
          "env": {
            "TRANSBORDO_API_URL": "https://transbordo.vectorconsulting.com.br/api/v1",
            "TRANSBORDO_API_KEY": "..."
          }
        }
      }
    }

## Guia completo

Arquitetura, regras de negócio e convenções: [`CLAUDE.md`](CLAUDE.md).
```

- [ ] **Step 12: Conferir referências mortas nos docs**

Run: `grep -rn "app\.py\|app_logic\|logistics_services\|calculations\.py\|scenarios\.py\|data_loader\|streamlit run\|SQLite\|st\.secrets" CLAUDE.md README.md apps/simulacao/CLAUDE.md`
Expected: nenhuma referência que trate esses arquivos como existentes/atuais. (Menção histórica em prosa, ex. "o app Streamlit original", é OK.) Ajustar o que sobrar.

- [ ] **Step 13: Commit**

```bash
git add -A
git commit -m "docs(cutover): ADR 0011; reescreve CLAUDE.md/README.md como projeto Django; limpa plans executados

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 7: `VERSION` 1.0.0 + CHANGELOG + verificação final + tag

**Files:**
- Modify: `VERSION`
- Modify: `CHANGELOG.md`

**Interfaces:** nenhuma (metadados de release + verificação).

- [ ] **Step 1: `VERSION` → `1.0.0`**

Conteúdo do arquivo, exatamente:
```
1.0.0
```

- [ ] **Step 2: `CHANGELOG.md`**

Na linha 4, trocar:
```
Versionamento: [SemVer](https://semver.org/lang/pt-BR/). `v1.0.0` marca o cutover (Streamlit desligado).
```
Por:
```
Versionamento: [SemVer](https://semver.org/lang/pt-BR/). `v1.0.0` = o repo larga o stack Streamlit legado (ADR 0011).
```

Trocar o cabeçalho `## [Não lançado]` por `## [1.0.0] - 2026-08-30` e, dentro dele, acrescentar antes do `### Changed` existente:

```markdown
### Removed
- Fase 11 — Cutover: stack Streamlit/SQLAlchemy legado deste repo — `app.py` + 9 módulos irmãos da raiz, suíte `tests/` (SQLAlchemy), ferramenta de espelhamento (`apps/simulacao/legado.py` + comando `espelhar_legado`). Deps `streamlit`, `SQLAlchemy`, `psycopg2-binary`, `plotly`. Confs Apache `comigo*.conf`. O Streamlit em produção é o `Comigo.git`, separado e congelado (ADR 0011).

### Added
- Comando `python manage.py sanitizar_pos_restore` (higieniza resíduo de dev após restaurar um dump de desenvolvimento em produção) + runbook "Migração de dados dev→prod" em `docs/DEPLOY.md`.
- Dependência `psycopg[binary]` explícita (era transitiva do procrastinate).
- ADR 0011 — Comigo e Transbordo como dois produtos permanentes independentes.
```
(As entradas `### Changed` / `### Removed` que já estavam sob `[Não lançado]` — porta 8060, remoção do serviço `comigo` do compose — permanecem sob `[1.0.0]`.)

- [ ] **Step 3: Suíte completa**

Run: `pytest -q`
Expected: PASS. Registrar a contagem final nas notas da task (era ~406; agora ~[406 − suíte `tests/` (dezenas) − 3 de espelhamento] + 4 de `sanitizar_pos_restore`).

- [ ] **Step 4: Checks do Django**

Run: `python manage.py check && python manage.py makemigrations --check --dry-run`
Expected: `System check identified no issues` e `No changes detected`.

- [ ] **Step 5: `check --deploy`**

Run:
```bash
DJANGO_SETTINGS_MODULE=config.settings.prod \
DJANGO_SECRET_KEY='x7k2-plan-check-only-not-a-real-secret-9f3q8w1e' \
DJANGO_ALLOWED_HOSTS=transbordo.vectorconsulting.com.br \
python manage.py check --deploy
```
Expected: `System check identified no issues (0 silenced).`

- [ ] **Step 6: Build + compose**

Run: `docker compose build web && docker compose config --quiet && echo OK`
Expected: build passa; `OK`.

- [ ] **Step 7: `py_compile` da raiz**

Run: `python -m py_compile manage.py mcp_server.py`
Expected: sem saída.

- [ ] **Step 8: Commit + tag**

```bash
git add VERSION CHANGELOG.md
git commit -m "docs: release 1.0.0 (Fase 11 — Cutover)

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
git tag -a v1.0.0 -m "Fase 11 — Cutover (repo Django-only)"
```

> **Não** dar push da tag automaticamente. Reportar ao operador: `v1.0.0` é local, aguarda
> `git push origin main && git push origin v1.0.0`; e a migração de dados em produção segue a nova
> seção "Migração de dados dev→prod (uma vez)" do `docs/DEPLOY.md`.

---

## Verificação server-side (manual, pós-merge — fora das tasks)

Ver a seção "Verificação" da spec (`docs/superpowers/specs/2026-08-30-fase11-cutover-design.md`). Após
`git push` e o runbook de migração de dados no host:
`curl https://transbordo.vectorconsulting.com.br/healthz/` → `{"version": "1.0.0", "db": "ok"}`;
login, dado da cooperativa confere, simulação roda, ApiKey de dev antiga dá 401, ApiKey nova dá 200;
`comigo.vectorconsulting.com.br` intacto.

---

## Self-Review

**Cobertura da spec:**

| Item da spec | Task |
|---|---|
| Remover 10 módulos da raiz | Task 2 |
| Remover `tests/` (SQLAlchemy) | Task 2 |
| Remover espelhamento (`legado.py` + comando + 3 testes) | Task 1 |
| Podar `requirements.txt` (streamlit/SQLAlchemy/psycopg2-binary/plotly) + `psycopg[binary]` | Task 3 |
| `pytest.ini` → `testpaths = apps` | Task 2 |
| `Dockerfile` — revisar `libpq5` | Task 3 |
| Remover `comigo.conf` / `comigo-le-ssl.conf` | Task 5 |
| `sanitizar_pos_restore` + testes (TDD) | Task 4 |
| Runbook de migração dev→prod no `DEPLOY.md` | Task 5 |
| ADR 0011 | Task 6 |
| Reescrita `CLAUDE.md` | Task 6 (Steps 3–10) |
| Reescrita `README.md` | Task 6 (Step 11) |
| `apps/simulacao/CLAUDE.md` — tirar `legado.py` | Task 1 (Step 3) |
| `.env.example` — tirar bloco legado, consertar `GEMINI_API_KEY` | Task 1 (Step 4) |
| Remover plans de fases executadas | Task 6 (Step 2) |
| `CHANGELOG.md` `## [1.0.0]` | Task 7 (Step 2) |
| `VERSION` → `1.0.0` | Task 7 (Step 1) |
| tag `v1.0.0` (não pushed) | Task 7 (Step 8) |
| `sanitizar_pos_restore`: apaga ApiKey/User/ConversaIA, TRUNCATE 5 tabelas de estado, ajusta `django_site`, preserva Cooperativa + domínio, idempotente, `--dry-run` | Task 4 (Steps 1, 3) |
| Testes verdes após cada remoção | Tasks 1/2/3 (steps de `pytest`) |
| `check --deploy` limpo | Task 7 (Step 5) |
| Verificação server-side manual | seção própria + spec |

**Placeholder scan:** sem "TBD"/"TODO"/"implementar depois". A contagem exata de testes é registrada
na Task 7 Step 3 (não dá pra saber antes de rodar). O literal `SECRET_KEY` do `check --deploy` é
descartável só para o comando. `<user>`/`<email>` no runbook são valores do operador.

**Consistência de tipos/nomes:** `sanitizar_pos_restore` — nome idêntico no comando (Task 4 Step 3),
nos testes (Task 4 Step 1), no runbook (Task 5 Step 3), no `CHANGELOG` (Task 7) e no `CLAUDE.md`
(Task 6 Step 8). `TABELAS_ESTADO` = as mesmas 5 tabelas na constante do comando e nas asserções do
teste (`procrastinate_jobs`, `django_session` checadas explicitamente; as outras 3 truncadas junto).
`Cenario.all_cooperativas` / `ConversaIA.all_cooperativas` — manager confirmado nos testes existentes
de `apps/integracoes/`. `VERSION` = `1.0.0` idêntico em Task 7 Step 1, no `healthz` esperado (Task 5
Step 3, "Verificação") e na tag.

**Escopo:** um subsistema (largar o legado + migração de dados + versão). Sete tasks, cada uma com
deliverable testável isolado. Sem decomposição adicional.
