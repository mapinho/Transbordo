FROM python:3.13-slim

WORKDIR /app

# curl: usado pelo HEALTHCHECK do serviço `web` (docker-compose.yml).
# libpq5: runtime do psycopg 3 (procrastinate) — importado já no `django.setup()`,
# então precisa existir inclusive para o `collectstatic` do build.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Dependências numa camada separada — o cache de build só reinstala quando
# requirements.txt muda, não a cada alteração de código.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV TZ=America/Sao_Paulo

# Estáticos coletados no build (não toca o banco). Roda sob `config.settings.prod`
# — o mesmo settings do runtime — para o storage WhiteNoise
# (CompressedManifestStaticFilesStorage) gerar o manifesto `staticfiles.json` e
# as variantes comprimidas dentro da imagem. `prod` lê SECRET_KEY e ALLOWED_HOSTS
# no import; valores descartáveis só para este passo (não vão para o runtime).
RUN DJANGO_SETTINGS_MODULE=config.settings.prod \
    DJANGO_SECRET_KEY=build-only-not-a-real-secret-key-000000000000 \
    DJANGO_ALLOWED_HOSTS=localhost \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Esta imagem serve só o stack Django. O Streamlit (`comigo.vectorconsulting.com.br`)
# roda num container próprio a partir do repo Comigo.git. `worker` e `migrate`
# sobrescrevem `command` no docker-compose.yml; `web` herda este CMD.
CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60", \
     "--access-logfile", "-", "--error-logfile", "-"]
