"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sessoes',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('codigo', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('status', sa.Enum('ativa', 'concluida', 'cancelada', name='statussessao'), nullable=True),
        sa.Column('data_inicio', sa.DateTime(timezone=True), nullable=True),
        sa.Column('data_fim', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('codigo'),
    )

    op.create_table(
        'itens_base',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('sessao_id', sa.String(), nullable=False),
        sa.Column('codigo', sa.String(), nullable=False),
        sa.Column('produto', sa.String(), nullable=False),
        sa.Column('quantidade_base', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['sessao_id'], ['sessoes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'contagens',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('sessao_id', sa.String(), nullable=False),
        sa.Column('codigo', sa.String(), nullable=False),
        sa.Column('quantidade_encontrada', sa.Integer(), nullable=False),
        sa.Column('divergencia', sa.Boolean(), nullable=True),
        sa.Column('operador', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sessao_id'], ['sessoes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # Índices para performance
    op.create_index('ix_itens_base_sessao_id', 'itens_base', ['sessao_id'])
    op.create_index('ix_itens_base_codigo', 'itens_base', ['sessao_id', 'codigo'])
    op.create_index('ix_contagens_sessao_id', 'contagens', ['sessao_id'])
    op.create_index('ix_contagens_timestamp', 'contagens', ['sessao_id', 'timestamp'])


def downgrade() -> None:
    op.drop_index('ix_contagens_timestamp', table_name='contagens')
    op.drop_index('ix_contagens_sessao_id', table_name='contagens')
    op.drop_index('ix_itens_base_codigo', table_name='itens_base')
    op.drop_index('ix_itens_base_sessao_id', table_name='itens_base')
    op.drop_table('contagens')
    op.drop_table('itens_base')
    op.drop_table('sessoes')
    # Remove o enum type (necessário no PostgreSQL)
    sa.Enum(name='statussessao').drop(op.get_bind(), checkfirst=True)
