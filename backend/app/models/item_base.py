from sqlalchemy import Column, String, Integer, Float, ForeignKey, UniqueConstraint, Index
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class ItemBase(Base):
    __tablename__ = "itens_base"
    __table_args__ = (
        UniqueConstraint("sessao_id", "codigo", name="uq_itens_base_sessao_codigo"),
        Index("ix_itens_base_sessao_codigo", "sessao_id", "codigo"),
    )

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sessao_id = Column(String, ForeignKey("sessoes.id"), nullable=False)
    codigo = Column(String, nullable=False)
    produto = Column(String, nullable=False)
    quantidade_base = Column(Integer, nullable=False)
    local_fisico = Column(String, nullable=True)
    valor_estoque = Column(Float, nullable=True)

    sessao = relationship("Sessao", back_populates="itens")
