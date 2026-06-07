"""adiciona valor 'pausada' ao enum statussessao no PostgreSQL

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-07

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL não suporta remover valores de enum — IF NOT EXISTS evita erro em re-run
    op.execute("ALTER TYPE statussessao ADD VALUE IF NOT EXISTS 'pausada'")


def downgrade() -> None:
    # Não é possível remover valores de um enum no PostgreSQL sem recriar o tipo.
    # Para rollback, seria necessário: criar novo enum, migrar coluna, dropar o antigo.
    # Por segurança, esta migration não tem downgrade automático.
    pass
