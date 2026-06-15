"""add filiais table and segunda_aprovacao + filial_id columns to sessoes

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-14

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Usa SQL puro com IF NOT EXISTS para ser idempotente — seguro mesmo que create_all()
    # já tenha criado a tabela ou alguma coluna numa tentativa anterior de deploy.
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS filiais (
            id TEXT PRIMARY KEY,
            nome TEXT NOT NULL,
            codigo TEXT NOT NULL,
            empresa TEXT,
            cidade TEXT,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            criado_em TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_filiais_codigo UNIQUE (codigo)
        )
    """))

    conn.execute(sa.text(
        "ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS filial_id TEXT"
    ))
    conn.execute(sa.text(
        "ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS token_segunda_aprovacao TEXT"
    ))
    conn.execute(sa.text(
        "ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS segunda_aprovacao_em TIMESTAMP WITH TIME ZONE"
    ))
    conn.execute(sa.text(
        "ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS segunda_aprovacao_por TEXT"
    ))
    conn.execute(sa.text(
        "ALTER TABLE sessoes ADD COLUMN IF NOT EXISTS segunda_aprovacao_ok INTEGER DEFAULT 0"
    ))


def downgrade() -> None:
    op.drop_column('sessoes', 'segunda_aprovacao_ok')
    op.drop_column('sessoes', 'segunda_aprovacao_por')
    op.drop_column('sessoes', 'segunda_aprovacao_em')
    op.drop_column('sessoes', 'token_segunda_aprovacao')
    op.drop_column('sessoes', 'filial_id')
    op.drop_table('filiais')
