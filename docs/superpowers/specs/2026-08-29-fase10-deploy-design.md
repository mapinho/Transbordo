# Fase 10 — Deploy — Design

- Status: Aprovado (aguarda plano de implementação)
- Data: 2026-08-29
- Roteiro: `docs/superpowers/specs/2026-08-22-fase5-arquitetura-saas-django.md` §10

## Contexto e objetivo

O stack Django (Fases 5–9) roda hoje só em dev (`runserver` + `procrastinate worker`). A Fase 10
coloca-o em produção **ao lado** do Streamlit, que continua servindo `comigo.vectorconsulting.com.br`
até o Cutover (Fase 11). A infra existente (`Dockerfile`, `docker-compose.yml`, `deploy.sh`,
`comigo.conf`, `comigo-le-ssl.conf`) é toda orientada a Streamlit.

Objetivo: servir o Django por `gunicorn` num container, com um serviço `worker` para o Procrastinate,
atrás do Apache num **subdomínio novo** (`transbordo.vectorconsulting.com.br`), com `/healthz/` fazendo
`SELECT 1` real e um runbook de deploy manual. PostgreSQL continua externo/bare-metal no host.

## Escopo

**Dentro:**
- `Dockerfile` bumped para `python:3.13-slim`, `gunicorn` + `whitenoise` adicionados, `collectstatic` no
  build.
- Três serviços novos no `docker-compose.yml` (`web`, `worker`, `migrate`), a partir de uma única
  imagem; sem volume de código (código assado na imagem).
- `apps/core/views.py:healthz` faz `SELECT 1` real; `200 {"version", "db":"ok"}` / `503 {..., "db":"erro"}`.
- `config/settings/prod.py`: WhiteNoise, HSTS, garantir `check --deploy` limpo.
- `transbordo.conf` + `transbordo-le-ssl.conf` (par de vhosts Apache, subdomínio novo).
- `deploy.sh` reescrito como runbook script; `docs/DEPLOY.md` com o procedimento manual completo
  (primeira vez + recorrente + rollback).
- `VERSION` → `0.10.0`, `CHANGELOG.md`, tag `v0.10.0` (não pushed automaticamente).

**Fora:**
- Remover o stack Streamlit (`comigo`/`mcp` services, `comigo*.conf`, `app.py` etc.) — é a Fase 11.
  Os serviços `comigo` e as confs `comigo*.conf` ficam **intocados**; o serviço `mcp` (SSE) é
  **removido** agora porque nada mais o usa desde a Fase 9a (ADR 0010).
- Servidor MCP hospedado — analistas rodam `mcp_server.py` (stdio) na própria máquina contra
  `https://transbordo.vectorconsulting.com.br/api/v1/` com uma `ApiKey` (modelo da Fase 9a).
- CI/CD automatizado, blue-green, orquestração — deploy é manual (`./deploy.sh` no host), mesmo padrão
  do APP_Vector.
- Mudar as tags `<script>`/`<link>` de CDN em `templates/base.html` para assets locais.
- Containerizar o PostgreSQL.

## Decisões de arquitetura

### 1. Subdomínio novo para o Django

`transbordo.vectorconsulting.com.br` → Django (`gunicorn` em `127.0.0.1:8000`).
`comigo.vectorconsulting.com.br` → Streamlit (`8501`), inalterado.

Separação limpa: os dois apps totalmente usáveis em paralelo, sem reescrita de path, sem
`FORCE_SCRIPT_NAME`. Custo: um vhost Apache novo e um certificado Let's Encrypt novo.
Rejeitado: trocar o domínio principal para o Django agora (quebra bookmarks dos usuários do Streamlit
antes da hora) e split por path no mesmo vhost (Django sob prefixo é frágil).

### 2. Uma imagem, três comandos, um compose

O `Dockerfile` produz uma imagem que serve os dois stacks; o `CMD` continua `streamlit run` e os
serviços Django sobrescrevem `command` no compose.

Serviços novos no **mesmo** `docker-compose.yml` (não um arquivo separado): o `deploy.sh` já faz
`docker compose down && up -d --build` do stack inteiro; um arquivo só casa com esse fluxo, e a Fase 11
apenas apaga os serviços `comigo` legados.

| serviço | command | portas | restart | notas |
|---|---|---|---|---|
| `web` | `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60 --access-logfile - --error-logfile -` | `127.0.0.1:8000:8000` | `unless-stopped` | `healthcheck` via `curl -f localhost:8000/healthz/` |
| `worker` | `python manage.py procrastinate worker` | — | `unless-stopped` | `depends_on: [web]` só p/ ordem |
| `migrate` | `python manage.py migrate --noinput` | — | `"no"` | `profiles: ["tools"]` — nunca sobe com `up`; roda via `docker compose run --rm migrate` |

Todos: `build: .`, **sem** volume `.:/app`, `env_file: [.env]`,
`environment: [TZ=America/Sao_Paulo, DJANGO_SETTINGS_MODULE=config.settings.prod]`,
`extra_hosts: ["host.docker.internal:host-gateway"]`.

Migração continua passo manual deliberado (convenção do projeto — ver CLAUDE.md, o histórico da
`core.0004`). O entrypoint **não** roda `migrate`.

### 3. Config e banco

O container Django usa o **mesmo** `/opt/comigo/.env` (via `env_file`). As chaves `DB_*` (Streamlit) e
`DJANGO_DB_*` (Django) já são distintas. `DJANGO_SETTINGS_MODULE=config.settings.prod` vai no
`environment:` de cada serviço Django no compose (não no `.env`, que é compartilhado). Chaves a
acrescentar no `.env` do servidor:

```
DJANGO_SECRET_KEY=<forte, gerado>
DJANGO_ALLOWED_HOSTS=transbordo.vectorconsulting.com.br
DJANGO_DB_HOST=host.docker.internal            # container → Postgres bare-metal do host
DJANGO_DB_NAME / DJANGO_DB_USER / DJANGO_DB_PASSWORD / DJANGO_DB_PORT
GEMINI_API_KEY=<opcional — aba Assistente de IA>
GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET / MICROSOFT_CLIENT_ID / MICROSOFT_CLIENT_SECRET / MICROSOFT_TENANT
DJANGO_EMAIL_* / DJANGO_DEFAULT_FROM_EMAIL     # opcional
```

`extra_hosts: host.docker.internal:host-gateway` dá ao container uma rota para o Postgres do host sem
`network_mode: host` (mantém o mapeamento de porta e o isolamento).

### 4. Estáticos com WhiteNoise

`gunicorn` serve os estáticos (comprimidos, hasheados) via `WhiteNoiseMiddleware` — sem `Alias` no
Apache, sem volume compartilhado. `collectstatic --noinput` roda **no build do Docker** (não toca
banco), sob `DJANGO_SETTINGS_MODULE=config.settings.base` + `DJANGO_SECRET_KEY` descartável, escrevendo
em `STATIC_ROOT` dentro da imagem.

`config/settings/prod.py`:
- `WhiteNoiseMiddleware` logo após `SecurityMiddleware` no `MIDDLEWARE`.
- `STORAGES["staticfiles"]["BACKEND"] = "whitenoise.storage.CompressedManifestStaticFilesStorage"`.

O tráfego atual de estáticos é leve (Tailwind/daisyUI/htmx/tabulator vêm de CDN em `base.html`; só
`grid_editor.js`/`modal.js` e os assets do admin são locais). Suficiente nesse volume.

### 5. `/healthz/` com `SELECT 1`

`apps/core/views.py:healthz`:
```python
def healthz(request):
    from django.db import connection
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
            c.fetchone()
        db_ok = True
    except OperationalError:
        db_ok = False
    status = 200 if db_ok else 503
    return JsonResponse({"version": settings.APP_VERSION, "db": "ok" if db_ok else "erro"}, status=status)
```
Sem auth, sem dependência de `ALLOWED_HOSTS` (é path puro). Usado pelo `healthcheck` do container `web`
e pelo poll do `deploy.sh`.

### 6. Apache: `transbordo.conf` / `transbordo-le-ssl.conf`

Espelham o par `comigo`:
- **:80** — `ServerName transbordo.vectorconsulting.com.br`, redireciona tudo p/ HTTPS.
- **:443** — `ProxyPreserveHost On`, `RequestHeader set X-Forwarded-Proto "https"` (alimenta
  `SECURE_PROXY_SSL_HEADER` do Django), `ProxyPass / http://127.0.0.1:8000/` + `ProxyPassReverse`.
  **Sem** blocos `/sse`, `/messages` ou WebSocket (HTMX é HTTP puro). `SSLCertificate*` apontando p/ um
  path Let's Encrypt novo — `certbot --apache -d transbordo.vectorconsulting.com.br` no primeiro deploy.

### 7. `deploy.sh` + `docs/DEPLOY.md`

`deploy.sh` (em `/opt/comigo`, recorrente):
```
git pull
docker compose build web worker
docker compose run --rm migrate
docker compose run --rm web python manage.py check --deploy
docker compose up -d web worker
# poll: curl -fsS http://127.0.0.1:8000/healthz/ até "db":"ok" (timeout ~60s, exit≠0 em falha)
docker compose ps
```
As linhas do Streamlit (`comigo`) ficam num bloco marcado `# legado — Fase 11 remove`.

`docs/DEPLOY.md`:
- **Primeira vez:** registro A no DNS (`transbordo` → IP do host), chaves `DJANGO_*` no `.env`,
  `certbot --apache -d transbordo.vectorconsulting.com.br`, `a2ensite transbordo transbordo-le-ssl`,
  `systemctl reload apache2`, primeiro `docker compose run --rm migrate`.
- **Recorrente:** `./deploy.sh`.
- **Rollback:** `git checkout <tag-anterior> && ./deploy.sh` (as migrações da Fase são forward-only;
  rollback de schema é manual e raro — anotado).

## Componentes e interfaces

| Unidade | O que faz | Como se usa | Depende de |
|---|---|---|---|
| imagem Docker | empacota deps + código + estáticos coletados | `docker compose build` | `requirements.txt`, `python:3.13-slim` |
| `web` (compose) | serve o Django via gunicorn | `docker compose up -d web` | imagem, `.env`, Postgres do host |
| `worker` (compose) | roda a fila Procrastinate | `docker compose up -d worker` | imagem, `.env`, Postgres do host |
| `migrate` (compose) | aplica migrações (manual) | `docker compose run --rm migrate` | imagem, `.env`, Postgres do host |
| `healthz` view | version + `SELECT 1` | `GET /healthz/` | `django.db.connection`, `settings.APP_VERSION` |
| `transbordo*.conf` | TLS + reverse proxy | `a2ensite` + reload | cert Let's Encrypt, `web` em `:8000` |
| `deploy.sh` | orquestra o deploy no host | `./deploy.sh` | docker compose, `curl` |

## Tratamento de erro

- **Banco fora no boot:** `web` sobe, `/healthz/` responde `503 db:"erro"`, `healthcheck` marca
  `unhealthy`, `deploy.sh` falha no poll e sai com código ≠ 0 (deploy abortado, versão anterior segue
  no ar porque `up -d` não derrubou nada em falha de build/migrate anteriores).
- **`migrate` falha:** `docker compose run --rm migrate` sai ≠ 0, `deploy.sh` para antes do `up -d`.
- **`check --deploy` acha problema:** `deploy.sh` para. Esperado 0 issues; o único resíduo possível
  (`SECRET_KEY`) é coberto pela chave forte no `.env`.
- **Cert ausente/expirado:** Apache não recarrega; `apache2ctl configtest` no runbook antes do reload.

## Estratégia de teste

- **pytest:** só `apps/core/tests/test_healthz.py` muda — `db:"ok"` no 200, `503` + `db:"erro"` quando
  o cursor levanta `OperationalError` (mock). `pytest` completo (Django + SQLAlchemy) verde.
- **`check --deploy`:** sob `config.settings.prod` com env representativo → 0 issues.
- **End-to-end local (gate de hand-off):** Docker Desktop + Postgres `transbordo` local:
  1. `docker compose build web` OK (collectstatic rodou no build).
  2. `docker compose run --rm migrate` → "No migrations to apply".
  3. `docker compose up -d web worker` → `web` health = `healthy`.
  4. `curl 127.0.0.1:8000/healthz/` → `200 {"version":"0.10.0","db":"ok"}`.
  5. `curl -H "Host: transbordo.vectorconsulting.com.br" 127.0.0.1:8000/accounts/login/` → `200`; asset
     hasheado do admin resolve `200`.
  6. log do `worker` mostra conexão com o Procrastinate e polling.
  7. `docker compose down`.
- **Apache:** validado só por raciocínio de sintaxe (`apache2ctl configtest` não roda aqui) — a
  verificação real é server-side, anotada no runbook.

## Verificação (server-side, manual, pós-merge)

- Deploy real no host: `docs/DEPLOY.md` primeira-vez, depois `./deploy.sh`, `/healthz/` externo
  responde `db:"ok"` por HTTPS, login e uma aba de cenário abrem, a aba Assistente responde (com
  `GEMINI_API_KEY`), o `worker` processa uma simulação.
- Streamlit em `comigo.vectorconsulting.com.br` continua no ar, intacto.

## Riscos / decisões em aberto

- **`host.docker.internal:host-gateway`** funciona em Docker ≥ 20.10 no Linux; se o host for antigo, o
  fallback é `network_mode: host` + `DJANGO_DB_HOST=localhost` (anotado no runbook).
- **`pg_hba.conf` do Postgres** precisa aceitar conexão da rede bridge do Docker (faixa
  `172.16.0.0/12`) para o usuário `DJANGO_DB_USER` — passo de primeira-vez no runbook.
- **Sem rate limiting na `/api/v1/`** (herdado das Fases 6/9) — com a API exposta por HTTPS a analistas,
  reavaliar antes de distribuir `ApiKey` fora do time.
- **`collectstatic` no build** infla a imagem levemente e re-roda a cada mudança de código (camada após
  `COPY . .`). Aceitável; alternativa (entrypoint) atrasaria todo boot.
- **Rollback de migração** é forward-only por convenção — um rollback que precise reverter schema é
  manual e deve ser raro (as migrações da Fase são aditivas).
