from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import logging
import os

logger = logging.getLogger(__name__)

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./inventario.db")

# SQLite precisa de check_same_thread=False para funcionar com FastAPI.
# PostgreSQL em produção requer SSL; se a DATABASE_URL já inclui sslmode não duplicamos.
_is_postgres = not DATABASE_URL.startswith("sqlite")
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
elif "sslmode" not in DATABASE_URL:
    connect_args = {"sslmode": "require"}
else:
    connect_args = {}
engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    # Em produção com PostgreSQL: pool dimensionado para suportar múltiplos workers Gunicorn.
    # pool_size: conexões permanentes mantidas abertas.
    # max_overflow: conexões extras permitidas sob carga pico.
    # pool_recycle: fecha conexões ociosas após 1h para evitar idle timeout do PG.
    **({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 3600,
    } if _is_postgres else {}),
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    from app.models import sessao, item_base, contagem, grupo_operador, agendamento, filial, admin  # noqa — registra todos os modelos
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite()


def _migrate_sqlite():
    """Migrações incrementais para SQLite (sem Alembic runtime)."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    from sqlalchemy import text
    with engine.connect() as conn:
        _add_col_if_missing(conn, "contagens", "rodada", "INTEGER NOT NULL DEFAULT 1")
        _add_col_if_missing(conn, "contagens", "observacao", "TEXT")
        _add_col_if_missing(conn, "contagens", "para_ajuste", "INTEGER NOT NULL DEFAULT 0")
        _add_col_if_missing(conn, "itens_base", "local_fisico", "TEXT")
        _add_col_if_missing(conn, "itens_base", "valor_estoque", "REAL")
        _add_col_if_missing(conn, "sessoes", "token_acesso", "TEXT")
        _add_col_if_missing(conn, "sessoes", "rodada_token", "INTEGER DEFAULT 1")
        _add_col_if_missing(conn, "sessoes", "token_supervisor", "TEXT")
        _add_col_if_missing(conn, "sessoes", "pausada_em", "TIMESTAMP")
        _add_col_if_missing(conn, "sessoes", "previsao_retomada", "TEXT")
        _add_col_if_missing(conn, "sessoes", "token_admin", "TEXT")
        _add_col_if_missing(conn, "sessoes", "webhook_url", "TEXT")
        _add_col_if_missing(conn, "sessoes", "filial_id", "TEXT")
        _add_col_if_missing(conn, "sessoes", "token_segunda_aprovacao", "TEXT")
        _add_col_if_missing(conn, "sessoes", "segunda_aprovacao_em", "TIMESTAMP")
        _add_col_if_missing(conn, "sessoes", "segunda_aprovacao_por", "TEXT")
        _add_col_if_missing(conn, "sessoes", "segunda_aprovacao_ok", "INTEGER NOT NULL DEFAULT 0")
        _add_col_if_missing(conn, "historico_contagens", "para_ajuste", "INTEGER NOT NULL DEFAULT 0")
        # Cria tabela grupos_operador se não existir
        try:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS grupos_operador (
                    id TEXT PRIMARY KEY,
                    sessao_id TEXT NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
                    nome TEXT NOT NULL,
                    filtro TEXT NOT NULL DEFAULT '*',
                    tipo_filtro TEXT NOT NULL DEFAULT 'prefixo',
                    token TEXT NOT NULL,
                    cor TEXT
                )
            """))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_grupos_sessao ON grupos_operador (sessao_id)"
            ))
            conn.commit()
        except Exception as exc:
            logger.error("Criação da tabela grupos_operador falhou: %s", exc)
        # Gera tokens para sessões que não têm (criadas antes desta feature)
        try:
            import secrets
            rows = conn.execute(text("SELECT id FROM sessoes WHERE token_acesso IS NULL")).fetchall()
            for row in rows:
                tok = secrets.token_hex(8).upper()
                conn.execute(text("UPDATE sessoes SET token_acesso = :tok, rodada_token = 1 WHERE id = :id"), {"tok": tok, "id": row[0]})
            if rows:
                conn.commit()
        except Exception:
            pass
        # Gera token_admin para sessões que não têm
        try:
            import secrets as _sec
            rows_adm = conn.execute(text("SELECT id FROM sessoes WHERE token_admin IS NULL")).fetchall()
            for row in rows_adm:
                tok = _sec.token_hex(8).upper()
                conn.execute(text("UPDATE sessoes SET token_admin = :tok WHERE id = :id"), {"tok": tok, "id": row[0]})
            if rows_adm:
                conn.commit()
        except Exception:
            pass
        # Índices compostos para queries de divergência e rodada
        _indices = [
            ("ix_historico_sessao_codigo", "historico_contagens", "(sessao_id, codigo)"),
            ("ix_itens_base_sessao_codigo", "itens_base", "(sessao_id, codigo)"),
            ("ix_contagens_sessao_divergencia", "contagens", "(sessao_id, divergencia)"),
            ("ix_contagens_sessao_rodada", "contagens", "(sessao_id, rodada)"),
        ]
        for idx_name, tbl, cols in _indices:
            try:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {tbl} {cols}"))
                conn.commit()
            except Exception as exc:
                logger.warning("Índice %s não criado (provavelmente já existe): %s", idx_name, exc)


def _add_col_if_missing(conn, table: str, col: str, col_def: str) -> None:
    from sqlalchemy import text
    try:
        rows = conn.execute(text(f"PRAGMA table_info(`{table}`)")).fetchall()
        if col not in [r[1] for r in rows]:
            conn.execute(text(f"ALTER TABLE `{table}` ADD COLUMN `{col}` {col_def}"))
            conn.commit()
            logger.info("Migração SQLite: adicionada coluna '%s' em '%s'", col, table)
    except Exception as exc:
        logger.error(
            "migration_failed table=%s col=%s error=%s — verifique o banco antes de continuar.",
            table, col, exc,
        )
