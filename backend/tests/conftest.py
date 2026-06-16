"""
Fixtures compartilhadas para todos os testes.
Usa SQLite em memória com StaticPool — conexão única compartilhada,
garantindo que todas as sessions vejam as mesmas tabelas.
"""
from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db
from app.limiter import limiter

# SlowAPI lê RATELIMIT_ENABLED do env e armazena como string (truthy mesmo quando 'false').
# Forçamos o boolean False diretamente para desabilitar o rate limiter em testes.
limiter.enabled = False

engine_test = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,  # Conexão única — todas as sessions compartilham o mesmo DB
)
TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def reset_db():
    """Cria tabelas antes de cada teste e limpa depois."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


def _criar_admin_e_token(db_session) -> str:
    """Cria um admin de teste e retorna o JWT Bearer token."""
    import uuid
    from app.models.admin import Admin
    from app.auth import hash_senha, criar_token

    admin = Admin(
        id=str(uuid.uuid4()),
        nome="Admin Teste",
        email="teste@inviq.local",
        senha_hash=hash_senha("senha_teste_123"),
    )
    db_session.add(admin)
    db_session.commit()
    return criar_token({"sub": admin.email})


@pytest.fixture()
def client(reset_db):
    """TestClient com banco de teste e JWT de admin pré-configurado."""
    app.dependency_overrides[get_db] = override_get_db
    # Cria admin e obtém token antes de abrir o TestClient
    db = TestingSession()
    token = _criar_admin_e_token(db)
    db.close()
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def sessao(client):
    """Cria uma sessão ativa."""
    r = client.post("/api/sessoes/", json={"nome": "Sessão Teste"})
    assert r.status_code == 201, f"Falha ao criar sessão: {r.text}"
    return r.json()


@pytest.fixture()
def sessao_com_itens(client, sessao):
    """Sessão com 3 itens importados via Excel."""
    import io
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["codigo", "produto", "quantidade"])
    ws.append(["ABC-001", "Produto Alpha", 10])
    ws.append(["ABC-002", "Produto Beta",  5])
    ws.append(["ABC-003", "Produto Gamma", 20])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    tok = sessao["token_admin"]
    r = client.post(
        f"/api/sessoes/{sessao['id']}/upload?token_admin={tok}",
        files={"file": ("itens.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 201, f"Falha no upload: {r.text}"
    return sessao
