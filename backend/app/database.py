from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
import os

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./inventario.db")

# SQLite precisa de check_same_thread=False para funcionar com FastAPI
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
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
    from app.models import sessao, item_base, contagem  # noqa — registra todos os modelos
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
        # Gera tokens para sessões que não têm (criadas antes desta feature)
        try:
            import secrets
            rows = conn.execute(text("SELECT id FROM sessoes WHERE token_acesso IS NULL")).fetchall()
            for row in rows:
                tok = secrets.token_hex(4).upper()
                conn.execute(text("UPDATE sessoes SET token_acesso = :tok, rodada_token = 1 WHERE id = :id"), {"tok": tok, "id": row[0]})
            if rows:
                conn.commit()
        except Exception:
            pass
        # historico_contagens já é criado pelo create_all — só garante índice
        try:
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_historico_sessao_codigo "
                "ON historico_contagens (sessao_id, codigo)"
            ))
            conn.commit()
        except Exception:
            pass


def _add_col_if_missing(conn, table: str, col: str, col_def: str) -> None:
    from sqlalchemy import text
    try:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
        if col not in [r[1] for r in rows]:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {col_def}"))
            conn.commit()
    except Exception:
        pass
