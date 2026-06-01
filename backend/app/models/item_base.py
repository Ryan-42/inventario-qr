from sqlalchemy import Column, String, Integer, Float, ForeignKey
from sqlalchemy.orm import relationship
import uuid

from app.database import Base


class ItemBase(Base):
    __tablename__ = "itens_base"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sessao_id = Column(String, ForeignKey("sessoes.id"), nullable=False)
    codigo = Column(String, nullable=False)
    produto = Column(String, nullable=False)
    quantidade_base = Column(Integer, nullable=False)
    local_fisico = Column(String, nullable=True)   # setor, prateleira, corredor, etc.
    valor_estoque = Column(Float, nullable=True)   # valor total do item (qtd × preço unitário)

    sessao = relationship("Sessao", back_populates="itens")
