"""grupos_operador, para_ajuste, token_admin, token_supervisor, rodada_token

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-04

Adiciona:
- tabela grupos_operador
- coluna para_ajuste em contagens e historico_contagens
- colunas token_admin, token_supervisor, rodada_token, pausada_em, previsao_retomada em sessoes
- colunas local_fisico, valor_estoque em itens_base
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_column_if_missing(table: str, column: sa.Column) -> None:
    """Tenta adicionar coluna; ignora se já existir (idempotente)."""
    try:
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(column)
    except Exception:
        pass  # coluna já existe — ignorar


def upgrade() -> None:
    # ── grupos_operador ───────────────────────────────────────────────
    op.create_table(
        'grupos_operador',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('sessao_id', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('filtro', sa.String(), nullable=False, server_default='*'),
        sa.Column('tipo_filtro', sa.String(), nullable=False, server_default='prefixo'),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('cor', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['sessao_id'], ['sessoes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        if_not_exists=True,
    )
    op.create_index(
        'ix_grupos_sessao', 'grupos_operador', ['sessao_id'], if_not_exists=True
    )

    # ── contagens: para_ajuste ─────────────────────────────────────────
    _add_column_if_missing(
        'contagens',
        sa.Column('para_ajuste', sa.Boolean(), nullable=False, server_default='0'),
    )

    # ── historico_contagens: para_ajuste ───────────────────────────────
    _add_column_if_missing(
        'historico_contagens',
        sa.Column('para_ajuste', sa.Boolean(), nullable=False, server_default='0'),
    )

    # ── itens_base: local_fisico, valor_estoque ────────────────────────
    _add_column_if_missing(
        'itens_base',
        sa.Column('local_fisico', sa.String(), nullable=True),
    )
    _add_column_if_missing(
        'itens_base',
        sa.Column('valor_estoque', sa.Float(), nullable=True),
    )

    # ── sessoes: colunas novas ─────────────────────────────────────────
    for col in [
        sa.Column('token_acesso', sa.String(), nullable=True),
        sa.Column('rodada_token', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('token_admin', sa.String(), nullable=True),
        sa.Column('token_supervisor', sa.String(), nullable=True),
        sa.Column('pausada_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('previsao_retomada', sa.String(), nullable=True),
    ]:
        _add_column_if_missing('sessoes', col)

    # ── índices de performance ─────────────────────────────────────────
    for idx_name, table, cols in [
        ('ix_contagens_sessao_divergencia', 'contagens', ['sessao_id', 'divergencia']),
        ('ix_contagens_sessao_rodada', 'contagens', ['sessao_id', 'rodada']),
        ('ix_itens_base_sessao_codigo', 'itens_base', ['sessao_id', 'codigo']),
        ('ix_historico_sessao_codigo2', 'historico_contagens', ['sessao_id', 'codigo']),
    ]:
        try:
            op.create_index(idx_name, table, cols)
        except Exception:
            pass


def downgrade() -> None:
    # Remover na ordem inversa
    for idx in ['ix_historico_sessao_codigo2', 'ix_itens_base_sessao_codigo',
                'ix_contagens_sessao_rodada', 'ix_contagens_sessao_divergencia']:
        try:
            op.drop_index(idx)
        except Exception:
            pass

    op.drop_index('ix_grupos_sessao', table_name='grupos_operador')
    op.drop_table('grupos_operador')
