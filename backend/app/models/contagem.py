from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
import uuid

from app.database import Base


class Contagem(Base):
    """Estado atual de cada item (upsert — uma linha por sessao+codigo)."""
    __tablename__ = "contagens"
    __table_args__ = (
        UniqueConstraint("sessao_id", "codigo", name="uq_contagens_sessao_codigo"),
        Index("ix_contagens_sessao_divergencia", "sessao_id", "divergencia"),
        Index("ix_contagens_sessao_rodada", "sessao_id", "rodada"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sessao_id = Column(String, ForeignKey("sessoes.id"), nullable=False)
    codigo = Column(String, nullable=False)
    quantidade_encontrada = Column(Integer, nullable=False)
    divergencia = Column(Boolean, default=False)
    operador = Column(String, nullable=True)
    observacao = Column(String, nullable=True)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    rodada = Column(Integer, default=1, nullable=False, server_default="1")
    # True quando a divergência foi confirmada e não avança mais rodada:
    # - operador registrou a mesma quantidade divergente novamente (confirmação)
    # - item chegou à rodada 3 e ainda diverge (sem mais rodadas disponíveis)
    para_ajuste = Column(Boolean, default=False, nullable=False, server_default="0")

    sessao = relationship("Sessao", back_populates="contagens")


class HistoricoContagem(Base):
    """Registro imutável de cada contagem individual (append-only, auditoria)."""
    __tablename__ = "historico_contagens"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sessao_id = Column(String, ForeignKey("sessoes.id"), nullable=False)
    codigo = Column(String, nullable=False)
    quantidade_encontrada = Column(Integer, nullable=False)
    quantidade_base = Column(Integer, nullable=False)
    divergencia = Column(Boolean, default=False)
    para_ajuste = Column(Boolean, default=False, nullable=False, server_default="0")
    operador = Column(String, nullable=True)
    observacao = Column(String, nullable=True)
    rodada = Column(Integer, default=1, nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    sessao = relationship("Sessao")
