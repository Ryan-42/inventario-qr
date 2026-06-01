"""
Fixtures compartilhadas para todos os testes.
Usa SQLite em memória com StaticPool — conexão única compartilhada,
garantindo que todas as sessions vejam as mesmas tabelas.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base, get_db

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


@pytest.fixture()
def client(reset_db):
    """TestClient com banco de teste. Depende de reset_db para garantir tabelas já existentes."""
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
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

    r = client.post(
        f"/api/sessoes/{sessao['id']}/upload",
        files={"file": ("itens.xlsx", buf,
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert r.status_code == 201, f"Falha no upload: {r.text}"
    return sessao
