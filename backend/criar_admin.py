#!/usr/bin/env python3
"""Cria (ou atualiza a senha do) primeiro administrador do INVIQ.

Rode a partir da pasta backend/. Usa a DATABASE_URL do ambiente:
  - Local (sem DATABASE_URL): grava no SQLite backend/inventario.db
  - Produção (Render Shell): grava no banco de produção (Neon/Postgres)

Uso interativo:
    python criar_admin.py

Uso não-interativo (útil no Render Shell):
    ADMIN_EMAIL=admin@empresa.com ADMIN_SENHA='SenhaForte123' ADMIN_NOME='Admin' python criar_admin.py
"""
from __future__ import annotations

import os
import sys
import uuid

from app.database import SessionLocal, create_tables
from app.models.admin import Admin
from app.auth import hash_senha


def main() -> None:
    # Garante que a tabela admins existe (idempotente).
    create_tables()

    email = os.getenv("ADMIN_EMAIL") or input("Email do admin: ").strip()
    senha = os.getenv("ADMIN_SENHA") or input("Senha do admin: ").strip()
    nome = os.getenv("ADMIN_NOME") or (input("Nome do admin [Admin]: ").strip() or "Admin")

    if not email or not senha:
        print("ERRO: email e senha são obrigatórios.")
        sys.exit(1)
    if len(senha) < 8:
        print("ERRO: a senha deve ter pelo menos 8 caracteres.")
        sys.exit(1)

    db = SessionLocal()
    try:
        existente = db.query(Admin).filter(Admin.email == email).first()
        if existente:
            existente.senha_hash = hash_senha(senha)
            existente.nome = nome
            db.commit()
            print(f"Admin '{email}' já existia — senha e nome atualizados.")
            return

        admin = Admin(
            id=str(uuid.uuid4()),
            nome=nome,
            email=email,
            senha_hash=hash_senha(senha),
        )
        db.add(admin)
        db.commit()
        print("Admin criado com sucesso!")
        print(f"  Email: {email}")
        print(f"  Nome:  {nome}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
