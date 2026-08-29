# Deploy — Transbordo (stack Django)

O stack Django roda em `transbordo.vectorconsulting.com.br`, ao lado do Streamlit
(`comigo.vectorconsulting.com.br`), que continua no ar até o Cutover (Fase 11).
PostgreSQL é externo/bare-metal no host. Deploy é manual, em `/opt/comigo`.

## Primeira vez

1. **DNS** — registro A `transbordo.vectorconsulting.com.br` → IP do host (mesmo IP do `comigo`).
2. **`.env`** (em `/opt/comigo/.env`) — acrescentar as chaves do stack Django:
   ```
   DJANGO_SECRET_KEY=<gerar: python -c "import secrets; print(secrets.token_urlsafe(64))">
   DJANGO_ALLOWED_HOSTS=transbordo.vectorconsulting.com.br
   DJANGO_DB_HOST=host.docker.internal
   DJANGO_DB_NAME=transbordo
   DJANGO_DB_USER=transbordo
   DJANGO_DB_PASSWORD=<senha do role>
   DJANGO_DB_PORT=5432
   GEMINI_API_KEY=<opcional — aba Assistente de IA>
   GOOGLE_CLIENT_ID=      GOOGLE_CLIENT_SECRET=
   MICROSOFT_CLIENT_ID=   MICROSOFT_CLIENT_SECRET=   MICROSOFT_TENANT=common
   DJANGO_EMAIL_HOST=     DJANGO_EMAIL_PORT=587      # opcional
   DJANGO_EMAIL_HOST_USER=  DJANGO_EMAIL_HOST_PASSWORD=  DJANGO_EMAIL_USE_TLS=true
   DJANGO_DEFAULT_FROM_EMAIL=nao-responda@transbordo.vectorconsulting.com.br
   ```
   (`DJANGO_SETTINGS_MODULE` **não** vai no `.env` — está no `environment:` de cada serviço no compose.)
3. **PostgreSQL** — o container conecta pela rede bridge do Docker. No host:
   - `postgresql.conf`: `listen_addresses = '*'` (ou o IP da bridge `docker0`, tipicamente `172.17.0.1`).
   - `pg_hba.conf`: `host  transbordo  transbordo  172.16.0.0/12  scram-sha-256`.
   - `systemctl reload postgresql`.
   - Criar o banco/role se ainda não existir (ver `docs/decisions/0002-...`).
4. **Certificado** — `sudo certbot --apache -d transbordo.vectorconsulting.com.br`.
   (Isso cria `transbordo-le-ssl.conf` automaticamente; se o certbot gerar um arquivo próprio,
   substitua-o pelo `transbordo-le-ssl.conf` deste repo, mantendo as linhas `SSLCertificate*`.)
5. **Apache** — `sudo cp transbordo.conf transbordo-le-ssl.conf /etc/apache2/sites-available/` →
   `sudo a2ensite transbordo transbordo-le-ssl` → `sudo apache2ctl configtest` → `sudo systemctl reload apache2`.
6. **Primeira migração** — `docker compose run --rm migrate`.
7. **Admin Vector** — `docker compose run --rm web python manage.py criar_admin_vector <user> --email <email>`.
8. **Subir** — `docker compose up -d web worker` e conferir `docker compose ps` (web = healthy).

## Deploy recorrente

```
cd /opt/comigo && ./deploy.sh
```
O script faz: `git pull` → `build web worker` → `migrate` → `check --deploy` → `up -d web worker` →
poll de `/healthz/` (falha com exit ≠ 0 se `db:"ok"` não vier em 60s).

## Rollback

```
cd /opt/comigo
git checkout <tag-anterior>   # ex.: v0.9.0
./deploy.sh
```
As migrações da fase são aditivas (forward-only). Um rollback que precise reverter schema é manual e
raro — reverter a migração específica com `docker compose run --rm web python manage.py migrate <app> <migração-anterior>` antes do `git checkout`.

## Streamlit (legado)

Sem mudança. Continua em `comigo.vectorconsulting.com.br` via o serviço `comigo` e as confs
`comigo*.conf`. Reinício isolado: `docker compose up -d --build comigo`. Sai na Fase 11.
