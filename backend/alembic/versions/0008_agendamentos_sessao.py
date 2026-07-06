"""tabela agendamentos_sessao

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-06

Motivo: o model AgendamentoSessao existia apenas via create_all() (dev).
Em produção com APP_ENV=production o create_tables() não roda, então a
tabela precisava de uma migration própria — sem ela o scheduler quebra.
"""
from typing import Sequence, Union
from alembic import op

revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    dialect = conn.dialect.name  # 'postgresql' ou 'sqlite'

    op.execute("""
        CREATE TABLE IF NOT EXISTS agendamentos_sessao (
            id VARCHAR PRIMARY KEY,
            nome_template VARCHAR NOT NULL,
            descricao TEXT,
            frequencia VARCHAR NOT NULL DEFAULT 'unico',
            hora VARCHAR NOT NULL DEFAULT '08:00',
            dia_semana INTEGER,
            dia_mes INTEGER,
            sessao_template_id VARCHAR,
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            proxima_execucao TIMESTAMP WITH TIME ZONE,
            ultima_execucao TIMESTAMP WITH TIME ZONE,
            ultima_sessao_criada_id VARCHAR,
            token_admin VARCHAR NOT NULL,
            criado_em TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """ if dialect == "postgresql" else """
        CREATE TABLE IF NOT EXISTS agendamentos_sessao (
            id VARCHAR PRIMARY KEY,
            nome_template VARCHAR NOT NULL,
            descricao TEXT,
            frequencia VARCHAR NOT NULL DEFAULT 'unico',
            hora VARCHAR NOT NULL DEFAULT '08:00',
            dia_semana INTEGER,
            dia_mes INTEGER,
            sessao_template_id VARCHAR,
            ativo BOOLEAN NOT NULL DEFAULT 1,
            proxima_execucao DATETIME,
            ultima_execucao DATETIME,
            ultima_sessao_criada_id VARCHAR,
            token_admin VARCHAR NOT NULL,
            criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Índice para o scheduler: busca agendamentos ativos por proxima_execucao
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agendamentos_ativo_proxima "
        "ON agendamentos_sessao(ativo, proxima_execucao)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_agendamentos_ativo_proxima")
    op.execute("DROP TABLE IF EXISTS agendamentos_sessao")
