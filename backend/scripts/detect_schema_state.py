"""Detecta o estado do schema para o entrypoint decidir se precisa 'alembic stamp'.

Cenários:
  1. Banco vazio (novo)                  -> exit 1 (deixa 'alembic upgrade head' criar tudo)
  2. Schema existe SEM alembic_version    -> exit 0 (precisa 'alembic stamp head' antes)
     (schema criado por create_all()/create_tables() em algum momento, nunca versionado)
  3. Schema existe COM alembic_version    -> exit 1 (já versionado; upgrade normal)

Uso no entrypoint:
    if python scripts/detect_schema_state.py; then alembic stamp head; fi
    alembic upgrade head
"""
from __future__ import annotations

import os
import sys

import sqlalchemy as sa


def main() -> int:
    url = os.environ.get("DATABASE_URL", "")
    if not url or url.startswith("sqlite"):
        return 1  # sqlite/dev: não mexe

    connect_args = {} if "sslmode" in url else {"sslmode": "require"}
    engine = sa.create_engine(url, connect_args=connect_args)
    insp = sa.inspect(engine)
    tables = set(insp.get_table_names())

    tem_alembic = "alembic_version" in tables
    # 'sessoes' é a tabela central — se existe, o schema já foi criado alguma vez
    tem_schema = "sessoes" in tables

    if tem_schema and not tem_alembic:
        print("[detect] Schema pré-existente sem alembic_version — precisa stamp.", file=sys.stderr)
        return 0
    print(
        f"[detect] Sem ação (schema={tem_schema}, alembic_version={tem_alembic}).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
