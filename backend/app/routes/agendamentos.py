"""
CRUD de agendamentos — criação automática de sessões de inventário.
"""
from __future__ import annotations

import hmac
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.agendamento import AgendamentoSessao

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agendamentos", tags=["Agendamentos"])

FrequenciaType = Literal["unico", "diario", "semanal", "mensal"]
DIAS_SEMANA = {"segunda": 0, "terca": 1, "quarta": 2, "quinta": 3, "sexta": 4, "sabado": 5, "domingo": 6}


# ── Schemas ───────────────────────────────────────────────────────────────────

class AgendamentoCreate(BaseModel):
    nome_template: str
    descricao: str | None = None
    frequencia: FrequenciaType = "semanal"
    hora: str = "08:00"
    dia_semana: int | None = None    # 0=segunda … 6=domingo (para semanal)
    dia_mes: int | None = None       # 1–28 (para mensal)
    sessao_template_id: str | None = None
    data_inicio: datetime | None = None   # Para frequência "unico"

    @field_validator("hora")
    @classmethod
    def validar_hora(cls, v: str) -> str:
        try:
            h, m = map(int, v.split(":"))
            assert 0 <= h <= 23 and 0 <= m <= 59
        except Exception:
            raise ValueError("hora deve estar no formato HH:MM (ex: 08:00)")
        return v

    @field_validator("dia_semana")
    @classmethod
    def validar_dia_semana(cls, v):
        if v is not None and not (0 <= v <= 6):
            raise ValueError("dia_semana deve ser 0 (segunda) a 6 (domingo)")
        return v

    @field_validator("dia_mes")
    @classmethod
    def validar_dia_mes(cls, v):
        if v is not None and not (1 <= v <= 28):
            raise ValueError("dia_mes deve ser 1 a 28")
        return v


class AgendamentoUpdate(BaseModel):
    nome_template: str | None = None
    descricao: str | None = None
    hora: str | None = None
    dia_semana: int | None = None
    dia_mes: int | None = None
    sessao_template_id: str | None = None
    ativo: bool | None = None


def _to_dict(a, include_token: bool = False) -> dict:
    d = {
        "id": a.id,
        "nome_template": a.nome_template,
        "descricao": a.descricao,
        "frequencia": a.frequencia,
        "hora": a.hora,
        "dia_semana": a.dia_semana,
        "dia_mes": a.dia_mes,
        "sessao_template_id": a.sessao_template_id,
        "ativo": a.ativo,
        "proxima_execucao": a.proxima_execucao.isoformat() if a.proxima_execucao else None,
        "ultima_execucao": a.ultima_execucao.isoformat() if a.ultima_execucao else None,
        "ultima_sessao_criada_id": a.ultima_sessao_criada_id,
        "criado_em": a.criado_em.isoformat() if a.criado_em else None,
    }
    if include_token:
        d["token_admin"] = a.token_admin
    return d


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/", status_code=201)
def criar_agendamento(payload: AgendamentoCreate, db: Session = Depends(get_db)) -> dict:
    """
    Cria um novo agendamento de sessão de inventário.

    Frequências disponíveis:
    - **unico**: executa uma vez na data/hora especificada (data_inicio obrigatório)
    - **diario**: todo dia no horário configurado
    - **semanal**: toda semana no dia_semana e horário (0=segunda, 6=domingo)
    - **mensal**: todo mês no dia_mes e horário (1–28)

    Opcionalmente, informe `sessao_template_id` para copiar automaticamente
    os itens de uma sessão anterior (reutiliza a planilha de estoque).
    """

    from app.services.scheduler import calcular_proxima_execucao_inicial

    if payload.frequencia == "unico" and not payload.data_inicio:
        raise HTTPException(
            status_code=422,
            detail="Para frequência 'unico', informe data_inicio (ex: '2026-07-15T08:00:00Z')."
        )
    if payload.frequencia == "semanal" and payload.dia_semana is None:
        raise HTTPException(status_code=422, detail="Para frequência 'semanal', informe dia_semana (0=segunda … 6=domingo).")
    if payload.frequencia == "mensal" and payload.dia_mes is None:
        raise HTTPException(status_code=422, detail="Para frequência 'mensal', informe dia_mes (1–28).")

    # Valida sessão template se fornecida
    if payload.sessao_template_id:
        from app.repositories import sessao_repo
        template = sessao_repo.buscar_sessao(db, payload.sessao_template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Sessão template não encontrada.")

    proxima = calcular_proxima_execucao_inicial(
        frequencia=payload.frequencia,
        hora=payload.hora,
        dia_semana=payload.dia_semana,
        dia_mes=payload.dia_mes,
        data_inicio=payload.data_inicio,
    )

    agendamento = AgendamentoSessao(
        nome_template=payload.nome_template,
        descricao=payload.descricao,
        frequencia=payload.frequencia,
        hora=payload.hora,
        dia_semana=payload.dia_semana,
        dia_mes=payload.dia_mes,
        sessao_template_id=payload.sessao_template_id,
        proxima_execucao=proxima,
    )
    db.add(agendamento)
    db.commit()
    db.refresh(agendamento)

    logger.info("Agendamento criado id=%s freq=%s proxima=%s", agendamento.id, payload.frequencia, proxima)
    return _to_dict(agendamento, include_token=True)


@router.get("/")
def listar_agendamentos(
    apenas_ativos: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> list[dict]:
    """Lista todos os agendamentos. Use apenas_ativos=true para filtrar apenas os ativos."""

    q = db.query(AgendamentoSessao)
    if apenas_ativos:
        q = q.filter(AgendamentoSessao.ativo == True)  # noqa: E712
    return [_to_dict(a) for a in q.order_by(AgendamentoSessao.criado_em.desc()).all()]


@router.get("/{agendamento_id}")
def buscar_agendamento(agendamento_id: str, db: Session = Depends(get_db)) -> dict:

    a = db.query(AgendamentoSessao).filter(AgendamentoSessao.id == agendamento_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    return _to_dict(a)


@router.patch("/{agendamento_id}")
def atualizar_agendamento(
    agendamento_id: str,
    payload: AgendamentoUpdate,
    token_admin: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    """Atualiza campos do agendamento. Requer token_admin do agendamento."""

    a = db.query(AgendamentoSessao).filter(AgendamentoSessao.id == agendamento_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    if not hmac.compare_digest(a.token_admin or "", token_admin or ""):
        raise HTTPException(status_code=403, detail="Token de administrador inválido.")

    if payload.nome_template is not None:
        a.nome_template = payload.nome_template
    if payload.descricao is not None:
        a.descricao = payload.descricao
    if payload.hora is not None:
        a.hora = payload.hora
    if payload.dia_semana is not None:
        a.dia_semana = payload.dia_semana
    if payload.dia_mes is not None:
        a.dia_mes = payload.dia_mes
    if payload.sessao_template_id is not None:
        a.sessao_template_id = payload.sessao_template_id
    if payload.ativo is not None:
        a.ativo = payload.ativo

    db.commit()
    db.refresh(a)
    return _to_dict(a)


@router.delete("/{agendamento_id}", status_code=204)
def deletar_agendamento(
    agendamento_id: str,
    token_admin: str = Query(...),
    db: Session = Depends(get_db),
):
    """Remove permanentemente um agendamento. Requer token_admin do agendamento."""

    a = db.query(AgendamentoSessao).filter(AgendamentoSessao.id == agendamento_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    if not hmac.compare_digest(a.token_admin or "", token_admin or ""):
        raise HTTPException(status_code=403, detail="Token de administrador inválido.")

    db.delete(a)
    db.commit()


@router.post("/{agendamento_id}/executar-agora")
def executar_agora(
    agendamento_id: str,
    token_admin: str = Query(...),
    db: Session = Depends(get_db),
) -> dict:
    """
    Executa o agendamento imediatamente, independente da data programada.
    Útil para testar o agendamento ou forçar criação manual.
    """

    from app.services.scheduler import _executar_agendamento

    a = db.query(AgendamentoSessao).filter(AgendamentoSessao.id == agendamento_id).first()
    if not a:
        raise HTTPException(status_code=404, detail="Agendamento não encontrado")
    if not hmac.compare_digest(a.token_admin or "", token_admin or ""):
        raise HTTPException(status_code=403, detail="Token de administrador inválido.")

    try:
        agora = datetime.now(timezone.utc)
        sessao_id = _executar_agendamento(db, a, agora)
        return {
            "mensagem": "Agendamento executado com sucesso.",
            "sessao_criada_id": sessao_id,
            "agendamento_id": agendamento_id,
        }
    except Exception as exc:
        logger.error("Execução manual agendamento %s falhou: %s", agendamento_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Falha ao executar agendamento: {exc}")
