from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Admin(Base):
    __tablename__ = "admins"

    id        = Column(String, primary_key=True, index=True)
    nome      = Column(String, nullable=False)
    email     = Column(String, unique=True, nullable=False, index=True)
    senha_hash = Column(String, nullable=False)
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
