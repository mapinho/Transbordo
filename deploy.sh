#!/bin/bash
# Deploy recorrente do stack Transbordo (Django) em /opt/comigo.
# Primeira vez / DNS / certbot / Apache: ver docs/DEPLOY.md.
set -euo pipefail
cd /opt/comigo

if git symbolic-ref -q HEAD >/dev/null; then
  echo "--- git pull ---"
  git pull origin main
else
  echo "--- HEAD destacado (rollback) — pulando git pull ---"
fi

echo "--- build (web, worker) ---"
docker compose build web worker

echo "--- migrate (explícito) ---"
docker compose run --rm migrate

echo "--- check --deploy ---"
docker compose run --rm web python manage.py check --deploy

echo "--- up -d (web, worker) ---"
docker compose up -d web worker

echo "--- poll /healthz/ ---"
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8000/healthz/ | grep -q '"db": *"ok"'; then
    echo "healthz OK"
    docker compose ps
    exit 0
  fi
  sleep 3
done
echo "ERRO: /healthz/ não respondeu db:ok em 60s" >&2
docker compose logs --tail=50 web >&2
exit 1

# --- legado (Streamlit) — Fase 11 remove ---
# O serviço `comigo` continua no docker-compose.yml e é reiniciado à parte:
#   docker compose up -d --build comigo
