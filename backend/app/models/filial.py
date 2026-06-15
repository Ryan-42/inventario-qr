from sqlalchemy import Column, String, Boolean, DateTime
from datetime import datetime, timezone
import uuid

from app.database import Base


class Filial(Base):
    __tablename__ = "filiais"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nome = Column(String, nullable=False)
    codigo = Column(String, nullable=False, unique=True)  # código curto (ex: SP01, RJ02)
    empresa = Column(String, nullable=True)               # razão social ou nome fantasia
    cidade = Column(String, nullable=True)
    ativo = Column(Boolean, default=True, nullable=False)
    criado_em = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
