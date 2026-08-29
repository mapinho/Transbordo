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

# Estáticos coletados no build (não toca o banco). Settings `base` + uma
# SECRET_KEY descartável só para este passo; o runtime usa `config.settings.prod`.
RUN DJANGO_SETTINGS_MODULE=config.settings.base DJANGO_SECRET_KEY=build-only \
    python manage.py collectstatic --noinput

EXPOSE 8501

# CMD default continua Streamlit (serviço `comigo`); os serviços Django
# (`web`/`worker`/`migrate`) sobrescrevem `command` no docker-compose.yml.
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.enableCORS=false", \
     "--server.enableXSRF=false"]
