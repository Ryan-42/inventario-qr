"""
Scheduler de agendamentos — verifica sessões pendentes e cria automaticamente.
Roda como background task assíncrona no startup do FastAPI.
Intervalo: a cada 60 segundos (< 1 minuto de atraso máximo).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_INTERVALO_SEGUNDOS = 60


async def loop_agendamentos():
    """Executa em background — não bloqueia o event loop do FastAPI."""
    logger.info("Scheduler de agendamentos iniciado (intervalo: %ds)", _INTERVALO_SEGUNDOS)
    while True:
        try:
            await _processar_agendamentos_pendentes()
        except Exception as exc:
            logger.error("Scheduler erro inesperado: %s", exc, exc_info=True)
        await asyncio.sleep(_INTERVALO_SEGUNDOS)


async def _processar_agendamentos_pendentes():
    from app.database import SessionLocal
    agora = datetime.now(timezone.utc)

    with SessionLocal() as db:
        from app.models.agendamento import AgendamentoSessao
        from sqlalchemy import and_

        pendentes = (
            db.query(AgendamentoSessao)
            .filter(
                AgendamentoSessao.ativo == True,  # noqa: E712
                AgendamentoSessao.proxima_execucao <= agora,
            )
            .all()
        )

        for agendamento in pendentes:
            try:
                sessao_id = await asyncio.to_thread(_executar_agendamento, db, agendamento, agora)
                logger.info(
                    "Agendamento executado id=%s nome='%s' sessao_criada=%s",
                    agendamento.id, agendamento.nome_template, sessao_id,
                )
            except Exception as exc:
                logger.error("Agendamento %s falhou: %s", agendamento.id, exc, exc_info=True)
                try:
                    from app.services.email_service import notificar_agendamento_falhou
                    notificar_agendamento_falhou(agendamento.nome_template, str(exc))
                except Exception:
                    pass


def _executar_agendamento(db, agendamento, agora: datetime) -> str | None:
    """
    Cria uma nova sessão baseada no template do agendamento.
    Copia os itens da sessão de referência se configurado.
    Atualiza próxima execução conforme a frequência.
    """
    from app.models.sessao import Sessao
    from app.repositories import sessao_repo, item_repo
    import secrets

    # Cria a nova sessão
    nome = f"{agendamento.nome_template} — {agora.strftime('%d/%m/%Y %H:%M')}"
    nova_sessao = sessao_repo.criar_sessao(db, nome)
    agendamento.ultima_sessao_criada_id = nova_sessao.id

    # Copia itens da sessão template se configurado
    if agendamento.sessao_template_id:
        itens_template = item_repo.listar_itens(db, agendamento.sessao_template_id)
        if itens_template:
            itens_dict = [
                {
                    "codigo": i.codigo,
                    "produto": i.produto,
                    "quantidade_base": i.quantidade_base,
                    "local_fisico": i.local_fisico,
                    "valor_estoque": float(i.valor_estoque) if i.valor_estoque else None,
                }
                for i in itens_template
            ]
            item_repo.criar_itens_bulk(db, nova_sessao.id, itens_dict)
            logger.info(
                "Agendamento %s: copiados %d itens da sessão template %s",
                agendamento.id, len(itens_dict), agendamento.sessao_template_id,
            )

    # Atualiza campos do agendamento
    agendamento.ultima_execucao = agora
    agendamento.proxima_execucao = _calcular_proxima_execucao(agendamento, agora)

    # Desativa agendamentos únicos após execução
    if agendamento.frequencia == "unico":
        agendamento.ativo = False

    db.commit()
    return nova_sessao.id


def _calcular_proxima_execucao(agendamento, referencia: datetime) -> datetime | None:
    """Calcula a próxima data/hora de execução conforme a frequência."""
    hora_str = agendamento.hora or "08:00"
    try:
        hora, minuto = map(int, hora_str.split(":"))
    except ValueError:
        hora, minuto = 8, 0

    if agendamento.frequencia == "unico":
        return None

    if agendamento.frequencia == "diario":
        proxima = (referencia + timedelta(days=1)).replace(
            hour=hora, minute=minuto, second=0, microsecond=0
        )
        return proxima

    if agendamento.frequencia == "semanal":
        dia_alvo = agendamento.dia_semana or 0
        dias_faltando = (dia_alvo - referencia.weekday()) % 7
        if dias_faltando == 0:
            dias_faltando = 7
        proxima = (referencia + timedelta(days=dias_faltando)).replace(
            hour=hora, minute=minuto, second=0, microsecond=0
        )
        return proxima

    if agendamento.frequencia == "mensal":
        dia_alvo = agendamento.dia_mes or 1
        # Avança para o próximo mês
        mes_seguinte = referencia.month + 1
        ano_seguinte = referencia.year
        if mes_seguinte > 12:
            mes_seguinte = 1
            ano_seguinte += 1
        # Garante que o dia existe no mês (ex: dia 31 em fevereiro → dia 28)
        import calendar
        ultimo_dia = calendar.monthrange(ano_seguinte, mes_seguinte)[1]
        dia_final = min(dia_alvo, ultimo_dia)
        proxima = referencia.replace(
            year=ano_seguinte, month=mes_seguinte, day=dia_final,
            hour=hora, minute=minuto, second=0, microsecond=0
        )
        return proxima

    return None


def calcular_proxima_execucao_inicial(
    frequencia: str,
    hora: str,
    dia_semana: int | None,
    dia_mes: int | None,
    data_inicio: datetime | None = None,
) -> datetime:
    """Calcula a primeira execução ao criar um novo agendamento."""
    agora = data_inicio or datetime.now(timezone.utc)
    try:
        h, m = map(int, hora.split(":"))
    except ValueError:
        h, m = 8, 0

    if frequencia == "unico":
        # Para único, data_inicio deve ser fornecida pelo usuário
        return data_inicio or agora

    if frequencia == "diario":
        proxima = agora.replace(hour=h, minute=m, second=0, microsecond=0)
        if proxima <= agora:
            proxima += timedelta(days=1)
        return proxima

    if frequencia == "semanal":
        dia_alvo = dia_semana or 0
        dias_faltando = (dia_alvo - agora.weekday()) % 7
        if dias_faltando == 0:
            proxima = agora.replace(hour=h, minute=m, second=0, microsecond=0)
            if proxima <= agora:
                dias_faltando = 7
            else:
                return proxima
        proxima = (agora + timedelta(days=dias_faltando)).replace(
            hour=h, minute=m, second=0, microsecond=0
        )
        return proxima

    if frequencia == "mensal":
        dia_alvo = dia_mes or 1
        import calendar
        ultimo_dia = calendar.monthrange(agora.year, agora.month)[1]
        dia_final = min(dia_alvo, ultimo_dia)
        proxima = agora.replace(day=dia_final, hour=h, minute=m, second=0, microsecond=0)
        if proxima <= agora:
            mes_seguinte = agora.month + 1
            ano_seguinte = agora.year
            if mes_seguinte > 12:
                mes_seguinte = 1
                ano_seguinte += 1
            ultimo_dia = calendar.monthrange(ano_seguinte, mes_seguinte)[1]
            dia_final = min(dia_alvo, ultimo_dia)
            proxima = proxima.replace(year=ano_seguinte, month=mes_seguinte, day=dia_final)
        return proxima

    return agora + timedelta(hours=1)
