#!/bin/sh
# Entrypoint de produção — aplica migrations antes de iniciar o servidor.
# Garante que o schema PostgreSQL está sempre atualizado sem exigir deploy manual.
set -e

if [ -z "${DATABASE_URL:-}" ]; then
  echo "[entrypoint] ERRO FATAL: DATABASE_URL não definida."
  echo "[entrypoint] No Render, isso indica que o banco (free tier) foi removido/expirou"
  echo "[entrypoint] ou o link 'fromDatabase' não está mais válido. Recrie o banco e reconecte."
  exit 1
fi

echo "[entrypoint] Aguardando banco de dados..."
# Tenta conectar por até 60s (banco free do Render pode demorar a acordar/religar)
MAX=60
i=0
until python -c "
import os, sqlalchemy as sa
try:
    e = sa.create_engine(os.environ['DATABASE_URL'])
    e.connect().close()
    exit(0)
except Exception as exc:
    import sys
    print(f'  conexão falhou: {type(exc).__name__}: {exc}', file=sys.stderr)
    exit(1)
"; do
  i=$((i+1))
  if [ $i -ge $MAX ]; then
    echo "[entrypoint] ERRO FATAL: banco não disponível após ${MAX}s. Abortando."
    echo "[entrypoint] Causa provável: banco free do Render expirou (90 dias) e foi deletado,"
    echo "[entrypoint] ou as credenciais em DATABASE_URL mudaram. Verifique o painel do Render."
    exit 1
  fi
  echo "[entrypoint] Banco não disponível. Tentativa $i/${MAX}..."
  sleep 1
done
echo "[entrypoint] Banco disponível."

# Adota schema pré-existente (ex.: banco criado por create_all() antes do Alembic).
# Sem isto, 'alembic upgrade head' tentaria recriar tabelas existentes e falharia.
if python scripts/detect_schema_state.py; then
  echo "[entrypoint] Schema pré-existente detectado — adotando com 'alembic stamp head'..."
  if ! alembic stamp head; then
    echo "[entrypoint] ERRO FATAL: 'alembic stamp head' falhou."
    exit 1
  fi
fi

echo "[entrypoint] Aplicando migrations Alembic..."
if ! alembic upgrade head; then
  echo "[entrypoint] ERRO FATAL: 'alembic upgrade head' falhou (veja o traceback acima)."
  echo "[entrypoint] O servidor NÃO será iniciado para evitar rodar com schema inconsistente."
  exit 1
fi
echo "[entrypoint] Migrations aplicadas."

echo "[entrypoint] Iniciando servidor..."
exec gunicorn app.main:app \
  --worker-class uvicorn.workers.UvicornWorker \
  --workers "${GUNICORN_WORKERS:-2}" \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 120 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile - \
  --log-level "${LOG_LEVEL:-info}"
