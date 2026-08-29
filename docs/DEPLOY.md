# Deploy — Transbordo (stack Django)

O stack Django roda em `transbordo.vectorconsulting.com.br`, ao lado do Streamlit
(`comigo.vectorconsulting.com.br`), que continua no ar até o Cutover (Fase 11).
PostgreSQL é externo/bare-metal no host. Deploy é manual, em `/opt/comigo`.

## Primeira vez

1. **DNS** — registro A `transbordo.vectorconsulting.com.br` → IP do host (mesmo IP do `comigo`).
2. **Grupo `docker`** — o `deploy.sh` roda `docker compose` sem `sudo`. Garanta que o usuário de deploy
   está no grupo `docker`: `groups | grep -q docker || sudo usermod -aG docker $USER` (e faça logout/login
   para valer). Alternativa: rodar `./deploy.sh` com `sudo`.
3. **Container órfão `comigo_mcp`** — o serviço `mcp` saiu do `docker-compose.yml`, mas o container
   `comigo_mcp` que estava rodando continua publicando `0.0.0.0:8000`. Remover um serviço do compose
   **não** para o container dele. O `web` agora publica em `127.0.0.1:8060` (não `:8000`), então não há mais
   colisão de porta — mas o órfão continua sendo peso morto e expondo `0.0.0.0:8000`. Antes de qualquer
   `docker compose up`, rode uma vez: `docker compose down --remove-orphans` (para `comigo_mcp` e outros
   órfãos; o `comigo` é recriado pelo `up` adiante).
4. **`.env`** (em `/opt/comigo/.env`) — acrescentar as chaves do stack Django, **uma `KEY=VALUE` por linha**:
   ```
   DJANGO_SECRET_KEY=<gerar: python -c "import secrets; print(secrets.token_urlsafe(64))">
   DJANGO_ALLOWED_HOSTS=transbordo.vectorconsulting.com.br,localhost,127.0.0.1
   DJANGO_DB_HOST=host.docker.internal
   DJANGO_DB_NAME=transbordo
   DJANGO_DB_USER=transbordo
   DJANGO_DB_PASSWORD=<senha do role>
   DJANGO_DB_PORT=5432
   GEMINI_API_KEY=<opcional — aba Assistente de IA>
   GOOGLE_CLIENT_ID=
   GOOGLE_CLIENT_SECRET=
   MICROSOFT_CLIENT_ID=
   MICROSOFT_CLIENT_SECRET=
   MICROSOFT_TENANT=common
   DJANGO_EMAIL_HOST=
   DJANGO_EMAIL_PORT=587
   DJANGO_EMAIL_HOST_USER=
   DJANGO_EMAIL_HOST_PASSWORD=
   DJANGO_EMAIL_USE_TLS=true
   DJANGO_DEFAULT_FROM_EMAIL=nao-responda@transbordo.vectorconsulting.com.br
   ```
   > **Aviso:** as entradas `localhost,127.0.0.1` em `DJANGO_ALLOWED_HOSTS` são exigidas pelo healthcheck
   > de loopback do container (`Host: localhost`) e pelo poll do `deploy.sh` (`Host: 127.0.0.1`) → com
   > `DEBUG=False`, `CommonMiddleware` levanta `DisallowedHost`/HTTP 400 sem elas, e o `web` nunca fica
   > `healthy`. O `web` só publica em `127.0.0.1:8060` (o Apache é o único ingress externo), então essas
   > entradas **não** são alcançáveis de fora — nunca reduza esta linha só para o domínio.
   >
   > `GOOGLE_*`, `MICROSOFT_*` e `DJANGO_EMAIL_*` são opcionais (só quando o provedor/recurso é usado).
   > Deixe cada chave opcional não usada **vazia e em sua própria linha** — `python-dotenv` / `env_file`
   > leem uma chave por linha, e empacotar várias numa linha faz `DJANGO_EMAIL_HOST` virar lixo truthy
   > (o `prod.py` então liga um `EMAIL_BACKEND` SMTP quebrado).
   >
   > (`DJANGO_SETTINGS_MODULE` **não** vai no `.env` — está no `environment:` de cada serviço no compose.)
5. **PostgreSQL** — o container conecta pela rede bridge do Docker. No host:
   - `postgresql.conf`: `listen_addresses = '*'` (ou o IP da bridge `docker0`, tipicamente `172.17.0.1`).
   - `pg_hba.conf`: `host  transbordo  transbordo  172.16.0.0/12  scram-sha-256`.
   - `systemctl reload postgresql`.
   - Criar o banco/role se ainda não existir (ver `docs/decisions/0002-...`).
6. **Certificado** — `sudo certbot --apache -d transbordo.vectorconsulting.com.br`.
   (Isso cria `transbordo-le-ssl.conf` automaticamente; se o certbot gerar um arquivo próprio,
   substitua-o pelo `transbordo-le-ssl.conf` deste repo, mantendo as linhas `SSLCertificate*`.)
7. **Apache** — `sudo cp transbordo.conf transbordo-le-ssl.conf /etc/apache2/sites-available/` →
   `sudo a2ensite transbordo transbordo-le-ssl` → `sudo apache2ctl configtest` → `sudo systemctl reload apache2`.
8. **Primeira migração** — `docker compose run --rm migrate`.
9. **Admin Vector** — `docker compose run --rm web python manage.py criar_admin_vector <user> --email <email>`.
10. **Subir** — `docker compose up -d web worker` e conferir `docker compose ps` (web = healthy).

## Deploy recorrente

```
cd /opt/comigo && ./deploy.sh
```
O script faz: `git pull` (só quando o HEAD está num branch) → `build web worker` → `migrate` →
`check --deploy` → `up -d web worker` → poll de `/healthz/` (falha com exit ≠ 0 se `db:"ok"` não vier em 60s).

## Rollback

```
cd /opt/comigo
git checkout <tag-anterior>   # ex.: v0.9.0
./deploy.sh
```
Em HEAD destacado (tag), o `deploy.sh` **pula o `git pull`** — a tag conferida fica no lugar (sem o guard,
o `git pull origin main` faria fast-forward de volta pro `main` e desfaria o rollback).

As migrações da fase são aditivas (forward-only). Um rollback que precise reverter schema é manual e
raro — reverter a migração específica com `docker compose run --rm web python manage.py migrate <app> <migração-anterior>` antes do `git checkout`.

## Streamlit (legado)

Sem mudança. Continua em `comigo.vectorconsulting.com.br` via o serviço `comigo` e as confs
`comigo*.conf`. Reinício isolado: `docker compose up -d --build comigo`. Sai na Fase 11.

`comigo-le-ssl.conf` ainda faz proxy de `/sse` e `/messages` para `127.0.0.1:8000` — nada escuta nessa
porta (o `web` está em `:8060`), então essas rotas em `comigo.vectorconsulting.com.br` respondem 502 até a
Fase 11 remover `comigo*.conf` (o MCP server virou cliente stdio local — ADR 0010).
