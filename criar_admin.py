#!/usr/bin/env python3
"""Cria o primeiro administrador do INVIQ.

Uso:
    python criar_admin.py
    ADMIN_EMAIL=admin@empresa.com ADMIN_SENHA=senha123 python criar_admin.py
"""
import os
import sys
import uuid

# Garante que o backend está no path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from app.database import SessionLocal, create_tables
from app.models.admin import Admin
from app.auth import hash_senha


def main():
    create_tables()

    email = os.getenv("ADMIN_EMAIL") or input("Email do admin: ").strip()
    senha = os.getenv("ADMIN_SENHA") or input("Senha do admin: ").strip()
    nome  = os.getenv("ADMIN_NOME") or input("Nome do admin [Admin]: ").strip() or "Admin"

    if not email or not senha:
        print("Email e senha são obrigatórios.")
        sys.exit(1)

    db = SessionLocal()
    try:
        existente = db.query(Admin).filter(Admin.email == email).first()
        if existente:
            print(f"Admin '{email}' já existe. Atualizando senha...")
            existente.senha_hash = hash_senha(senha)
            existente.nome = nome
            db.commit()
            print("Senha atualizada com sucesso.")
            return

        admin = Admin(
            id=str(uuid.uuid4()),
            nome=nome,
            email=email,
            senha_hash=hash_senha(senha),
        )
        db.add(admin)
        db.commit()
        print(f"\nAdmin criado com sucesso!")
        print(f"  Email: {email}")
        print(f"  Nome:  {nome}")
        print(f"\nAcesse http://localhost:8000/login para entrar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
