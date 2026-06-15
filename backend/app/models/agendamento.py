from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.database import Base


class AgendamentoSessao(Base):
    """
    Agenda criação automática de sessões de inventário.

    frequencia:
      - "unico"   → executa uma vez na data/hora especificada
      - "diario"  → executa todo dia no horário configurado
      - "semanal" → executa na dia_semana (0=segunda … 6=domingo) e horário
      - "mensal"  → executa no dia_mes (1–28) e horário
    """
    __tablename__ = "agendamentos_sessao"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    nome_template = Column(String, nullable=False)
    descricao = Column(Text, nullable=True)

    frequencia = Column(String, nullable=False, default="unico")  # unico|diario|semanal|mensal
    hora = Column(String, nullable=False, default="08:00")         # "HH:MM"
    dia_semana = Column(Integer, nullable=True)                    # 0=seg … 6=dom (semanal)
    dia_mes = Column(Integer, nullable=True)                       # 1–28 (mensal)

    # Sessão de referência para copiar os itens
    sessao_template_id = Column(String, nullable=True)

    ativo = Column(Boolean, default=True, nullable=False)
    proxima_execucao = Column(DateTime(timezone=True), nullable=True)
    ultima_execucao = Column(DateTime(timezone=True), nullable=True)
    ultima_sessao_criada_id = Column(String, nullable=True)

    # Quem criou / gerencia
    token_admin = Column(String, nullable=False, default=lambda: secrets.token_hex(8).upper())
    criado_em = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
