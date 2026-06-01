"""historico_contagens, observacao, unique constraint, indices

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-28

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- contagens: coluna rodada (pode já existir via _migrate_sqlite) ---
    with op.batch_alter_table('contagens') as batch_op:
        batch_op.add_column(sa.Column('rodada', sa.Integer(), nullable=False, server_default='1'))
        batch_op.add_column(sa.Column('observacao', sa.String(), nullable=True))
        batch_op.create_unique_constraint('uq_contagens_sessao_codigo', ['sessao_id', 'codigo'])
        batch_op.create_index('ix_contagens_sessao_codigo', ['sessao_id', 'codigo'])

    # --- historico_contagens (append-only, imutável) ---
    op.create_table(
        'historico_contagens',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('sessao_id', sa.String(), nullable=False),
        sa.Column('codigo', sa.String(), nullable=False),
        sa.Column('quantidade_encontrada', sa.Integer(), nullable=False),
        sa.Column('quantidade_base', sa.Integer(), nullable=False),
        sa.Column('divergencia', sa.Boolean(), nullable=True),
        sa.Column('operador', sa.String(), nullable=True),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('rodada', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['sessao_id'], ['sessoes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_historico_sessao_codigo', 'historico_contagens', ['sessao_id', 'codigo'])
    op.create_index('ix_historico_sessao_timestamp', 'historico_contagens', ['sessao_id', 'timestamp'])

    # --- itens_base: unique constraint ---
    with op.batch_alter_table('itens_base') as batch_op:
        batch_op.create_unique_constraint('uq_itens_base_sessao_codigo', ['sessao_id', 'codigo'])

    # --- sessoes: índice para ordenação frequente ---
    op.create_index('ix_sessoes_data_inicio', 'sessoes', ['data_inicio'])


def downgrade() -> None:
    op.drop_index('ix_sessoes_data_inicio', table_name='sessoes')
    with op.batch_alter_table('itens_base') as batch_op:
        batch_op.drop_constraint('uq_itens_base_sessao_codigo', type_='unique')
    op.drop_index('ix_historico_sessao_timestamp', table_name='historico_contagens')
    op.drop_index('ix_historico_sessao_codigo', table_name='historico_contagens')
    op.drop_table('historico_contagens')
    with op.batch_alter_table('contagens') as batch_op:
        batch_op.drop_index('ix_contagens_sessao_codigo')
        batch_op.drop_constraint('uq_contagens_sessao_codigo', type_='unique')
        batch_op.drop_column('observacao')
        batch_op.drop_column('rodada')
