# ── Stage 1: dependências ─────────────────────────────────────────────────────
FROM python:3.12-slim AS deps

WORKDIR /app

# Instala apenas o necessário para compilar pacotes Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# ── Stage 2: imagem final ──────────────────────────────────────────────────────
FROM python:3.12-slim AS final

WORKDIR /app

# Copia apenas pacotes instalados (não o compilador)
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Instala libpq (runtime apenas — sem gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copia código da aplicação
COPY . .

# Usuário não-root para segurança
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser /app \
    && chmod +x /app/entrypoint.sh
USER appuser

EXPOSE 8000

# Prod: entrypoint roda alembic upgrade head antes do gunicorn
# Dev: sobrescrever com CMD ["uvicorn", ...] no docker-compose.yml
CMD ["/app/entrypoint.sh"]

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
