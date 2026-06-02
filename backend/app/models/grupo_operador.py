from sqlalchemy import Column, String, ForeignKey
from sqlalchemy.orm import relationship
import uuid
import secrets

from app.database import Base


class GrupoOperador(Base):
    """
    Grupo de itens atribuído a um conjunto de operadores.
    Cada grupo tem seu próprio token de acesso e filtro de códigos.
    """
    __tablename__ = "grupos_operador"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    sessao_id = Column(String, ForeignKey("sessoes.id", ondelete="CASCADE"), nullable=False)
    nome = Column(String, nullable=False)                 # ex: "Grupo A", "Corredor 1-5"
    filtro = Column(String, nullable=False, default="*")  # ex: "A" | "A,B" | "*" (todos)
    tipo_filtro = Column(String, nullable=False, default="prefixo")  # prefixo | lista | todos
    token = Column(String, nullable=False, default=lambda: secrets.token_hex(4).upper())
    cor = Column(String, nullable=True)  # cor para identificação visual (#ff6b6b)

    sessao = relationship("Sessao", back_populates="grupos")

    def valida_codigo(self, codigo: str) -> bool:
        """Verifica se o código pertence a este grupo."""
        if self.tipo_filtro == "todos" or self.filtro == "*":
            return True
        codigo_upper = codigo.upper()
        prefixos = [p.strip().upper() for p in self.filtro.split(",") if p.strip()]
        if not prefixos:
            return False
        if self.tipo_filtro == "prefixo":
            return any(codigo_upper.startswith(p) for p in prefixos)
        if self.tipo_filtro == "lista":
            return codigo_upper in prefixos
        # tipo_filtro desconhecido → negar acesso por segurança
        return False
