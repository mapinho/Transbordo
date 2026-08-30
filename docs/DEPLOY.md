# Deploy — Transbordo

Transbordo roda em `transbordo.vectorconsulting.com.br`. O produto separado Comigo
(`comigo.vectorconsulting.com.br`, repo `Comigo.git`) roda com infra própria e independente,
desenvolvimento congelado (ver ADR 0011). PostgreSQL é externo/bare-metal no host. Deploy é manual,
em `/opt/comigo`.

## Primeira vez

1. **DNS** — registro A `transbordo.vectorconsulting.com.br` → IP do host (mesmo IP do `comigo`).
2. **Grupo `docker`** — o `deploy.sh` roda `docker compose` sem `sudo`. Garanta que o usuário de deploy
   está no grupo `docker`: `groups | grep -q docker || sudo usermod -aG docker $USER` (e faça logout/login
   para valer). Alternativa: rodar `./deploy.sh` com `sudo`.
3. **Containers órfãos** — se o host ainda tiver containers de um compose antigo (`comigo_mcp`,
   `comigo_app`), eles não param sozinhos ao sair do `docker-compose.yml`. Antes de qualquer
   `docker compose up`, rode uma vez para limpar: `docker compose down --remove-orphans`. (O produto
   Comigo roda com infra própria, do repo `Comigo.git`, e não é afetado.)
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
9. **Admin Vector** — `docker compose run --rm web python manage.py criar_admin_vector <username> --email <email>`.
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

2. **No host de prod** — backup do banco atual, parar os serviços que escrevem e recriar o banco:
   ```
   cd /opt/comigo
   pg_dump -Fc -h localhost -U transbordo -d transbordo -f prod_pre_restore_$(date +%F).dump   # guarde até o passo 6 passar
   docker compose stop web worker
   dropdb -h localhost -U transbordo transbordo
   createdb -h localhost -U transbordo -O transbordo transbordo
   pg_restore -h localhost -U transbordo --no-owner --no-privileges --exit-on-error -d transbordo transbordo_dev.dump
   ```
   (`dropdb` falha com "being accessed by other users" se `web`/`worker` ainda estiverem de pé — ou
   uma sessão `psql`/GUI aberta contra o banco — daí o `stop` antes.)
   (o role `transbordo` precisa de `CREATEDB`; senão rode `createdb` como `postgres -O transbordo`.)

3. **Conferir schema:**
   ```
   docker compose run --rm migrate
   ```
   Esperado: `No migrations to apply` (o dump já carrega `django_migrations`). Se aparecer migração a
   aplicar, o dump veio de um dev desatualizado. Como o banco de prod já foi recriado neste ponto,
   "abortar" aqui é: restaurar `prod_pre_restore_*.dump` de volta, corrigir o dump de dev
   (`makemigrations --check` no dev, re-dumpar) e repetir.

4. **Higienizar o resíduo de dev:**
   ```
   docker compose run --rm web python manage.py sanitizar_pos_restore --dry-run   # confere as contagens
   docker compose run --rm web python manage.py sanitizar_pos_restore --noinput
   ```
   Apaga `User`/`ApiKey`/`ConversaIA` de dev, zera `procrastinate_*`, `django_session` e
   `socialaccount_socialapp`, ajusta o `django_site` para `DJANGO_ALLOWED_HOSTS[0]`. **Não** toca a
   cooperativa nem o domínio de simulação. Sem `--noinput` (e num TTY), pede confirmação (`sim`).

5. **Recriar identidade real:**
   ```
   docker compose run --rm web python manage.py criar_admin_vector <username> --email <email>
   ```
   Depois, pela tela Gestão → Usuários, criar os usuários reais; pelo admin (`/admin/integracoes/apikey/`),
   emitir as `ApiKey`(s) reais.

6. **Subir e conferir:**
   ```
   docker compose up -d web worker
   curl -s http://127.0.0.1:8060/healthz/          # {"version": "1.0.0", "db": "ok"}
   docker compose run --rm web python manage.py shell -c "from apps.simulacao.models import MovimentacaoDiaria; print(MovimentacaoDiaria.all_cooperativas.count())"
   ```
   O `count()` de `MovimentacaoDiaria` deve bater com o mesmo `count()` no dev (~13k esperado);
   confira também fábricas/armazéns/rotas/previsões/safras/cenários por amostragem.
   Login com o Admin Vector; abrir a cooperativa; rodar uma simulação e ver o `worker` concluir.
   Passando tudo, pode descartar o `prod_pre_restore_*.dump`.

## Comigo (produto separado)

`comigo.vectorconsulting.com.br` roda a partir do repo **Comigo.git**, com vhost, banco e container
próprios — fora do escopo deste deploy e deste repositório. Ver ADR 0011.
