from sqlalchemy import Column, String, DateTime, Integer, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import enum
import uuid
import secrets

from app.database import Base


class StatusSessao(str, enum.Enum):
    ativa = "ativa"
    pausada = "pausada"
    concluida = "concluida"
    cancelada = "cancelada"


def _gerar_token() -> str:
    """Gera um token alfanumérico de 16 caracteres maiúsculos (8 bytes = 2^64 combinações)."""
    return secrets.token_hex(8).upper()


class Sessao(Base):
    __tablename__ = "sessoes"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    codigo = Column(String, unique=True, nullable=False)  # INV-2026-0001
    nome = Column(String, nullable=False)
    status = Column(SAEnum(StatusSessao), default=StatusSessao.ativa)
    data_inicio = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    data_fim = Column(DateTime(timezone=True), nullable=True)
    token_acesso = Column(String, nullable=True, default=_gerar_token)
    rodada_token = Column(Integer, nullable=True, default=1)
    token_admin = Column(String, nullable=True, default=lambda: secrets.token_hex(8).upper())  # token do criador do inventário
    token_supervisor = Column(String, nullable=True)  # token do supervisor (acesso somente-leitura)
    filial_id = Column(String, ForeignKey("filiais.id"), nullable=True)
    pausada_em = Column(DateTime(timezone=True), nullable=True)
    previsao_retomada = Column(String, nullable=True)  # ex: "14:00"
    webhook_url = Column(String, nullable=True)  # URL para POST ao concluir/cancelar

    # Segunda aprovação (4 olhos) — token separado do token_admin
    token_segunda_aprovacao = Column(String, nullable=True, default=lambda: secrets.token_hex(8).upper())
    segunda_aprovacao_em = Column(DateTime(timezone=True), nullable=True)
    segunda_aprovacao_por = Column(String, nullable=True)
    segunda_aprovacao_ok = Column(Integer, nullable=True, default=0)  # 0=pendente 1=aprovada 2=rejeitada

    itens = relationship("ItemBase", back_populates="sessao", cascade="all, delete-orphan")
    contagens = relationship("Contagem", back_populates="sessao", cascade="all, delete-orphan")
    grupos = relationship("GrupoOperador", back_populates="sessao", cascade="all, delete-orphan")
