"""índices em historico_contagens e tabela admins

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-16

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name  # 'postgresql' ou 'sqlite'

    # ── Tabela admins (criada pelo create_all, mas garantimos via migration) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id VARCHAR PRIMARY KEY,
            nome VARCHAR NOT NULL,
            email VARCHAR NOT NULL UNIQUE,
            senha_hash VARCHAR NOT NULL,
            criado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """ if dialect == "postgresql" else """
        CREATE TABLE IF NOT EXISTS admins (
            id VARCHAR PRIMARY KEY,
            nome VARCHAR NOT NULL,
            email VARCHAR NOT NULL UNIQUE,
            senha_hash VARCHAR NOT NULL,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # ── Índices em historico_contagens ────────────────────────────────────────
    # Estes índices aceleram: relatorio_operadores, auditoria, comparar_sessoes
    if dialect == "postgresql":
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_historico_sessao_id
            ON historico_contagens(sessao_id)
        """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_historico_sessao_codigo
            ON historico_contagens(sessao_id, codigo)
        """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_historico_sessao_divergencia
            ON historico_contagens(sessao_id, divergencia)
        """)
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_historico_sessao_operador
            ON historico_contagens(sessao_id, operador)
        """)
        # Índice em para_ajuste para queries de contagens
        op.execute("""
            CREATE INDEX IF NOT EXISTS ix_contagens_sessao_para_ajuste
            ON contagens(sessao_id, para_ajuste)
        """)
    else:
        # SQLite: CREATE INDEX IF NOT EXISTS é suportado desde 3.3.0
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_historico_sessao_id "
            "ON historico_contagens(sessao_id)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_historico_sessao_codigo "
            "ON historico_contagens(sessao_id, codigo)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_historico_sessao_divergencia "
            "ON historico_contagens(sessao_id, divergencia)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_historico_sessao_operador "
            "ON historico_contagens(sessao_id, operador)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_contagens_sessao_para_ajuste "
            "ON contagens(sessao_id, para_ajuste)"
        )


def downgrade() -> None:
    for idx in [
        "ix_historico_sessao_id",
        "ix_historico_sessao_codigo",
        "ix_historico_sessao_divergencia",
        "ix_historico_sessao_operador",
        "ix_contagens_sessao_para_ajuste",
    ]:
        try:
            op.drop_index(idx)
        except Exception:
            pass
