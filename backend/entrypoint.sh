#!/bin/sh
# Entrypoint de produção — aplica migrations antes de iniciar o servidor.
# Garante que o schema PostgreSQL está sempre atualizado sem exigir deploy manual.
set -e

echo "[entrypoint] Aguardando banco de dados..."
# Tenta conectar por até 30s (útil quando postgres está subindo junto)
MAX=30
i=0
until python -c "
import os, sqlalchemy as sa
try:
    e = sa.create_engine(os.environ['DATABASE_URL'])
    e.connect().close()
    exit(0)
except Exception:
    exit(1)
" 2>/dev/null; do
  i=$((i+1))
  if [ $i -ge $MAX ]; then
    echo "[entrypoint] Banco não disponível após ${MAX}s. Abortando."
    exit 1
  fi
  echo "[entrypoint] Banco não disponível. Tentativa $i/${MAX}..."
  sleep 1
done
echo "[entrypoint] Banco disponível."

echo "[entrypoint] Aplicando migrations Alembic..."
alembic upgrade head
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
