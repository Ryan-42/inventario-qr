"""
Scheduler de agendamentos — verifica sessões pendentes e cria automaticamente.
Roda como background task assíncrona no startup do FastAPI.
Intervalo: a cada 60 segundos (< 1 minuto de atraso máximo).

MULTI-WORKER (Gunicorn): com N workers, N schedulers sobem simultaneamente.
Para evitar execução duplicada, usamos pg_try_advisory_lock em PostgreSQL —
apenas o worker que adquire o lock processa o ciclo; os demais ignoram.
Em SQLite (dev/teste), assumimos worker único e pulamos o lock.

NOTA: os testes rodam em SQLite e NÃO validam concorrência real de PostgreSQL.
A lógica do advisory lock só pode ser verificada em ambiente PostgreSQL real.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

_INTERVALO_SEGUNDOS = 60

# Advisory lock key (valor arbitrário estável — identifica o scheduler desta app)
_ADVISORY_LOCK_KEY = 1_234_567_890


def _tentar_adquirir_lock_pg(db) -> bool:
    """
    Tenta adquirir um PostgreSQL advisory lock transacional.
    Retorna True se adquirido (este worker processa), False se outro worker já tem o lock.
    Em SQLite, retorna sempre True (lock não necessário com worker único).
    """
    from sqlalchemy import text
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    if dialect != "postgresql":
        return True
    try:
        result = db.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": _ADVISORY_LOCK_KEY})
        acquired = result.scalar()
        return bool(acquired)
    except Exception as exc:
        logger.warning("scheduler: falha ao tentar advisory lock — %s (processando sem lock)", exc)
        return True


def _liberar_lock_pg(db) -> None:
    """Libera o advisory lock PostgreSQL. Em SQLite, no-op."""
    from sqlalchemy import text
    dialect = db.bind.dialect.name if db.bind else "sqlite"
    if dialect != "postgresql":
        return
    try:
        db.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": _ADVISORY_LOCK_KEY})
    except Exception as exc:
        logger.warning("scheduler: falha ao liberar advisory lock — %s", exc)


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
        # Advisory lock: garante que só um worker por vez processa agendamentos
        if not _tentar_adquirir_lock_pg(db):
            logger.debug("scheduler: outro worker está processando — pulando ciclo")
            return

        try:
            from app.models.agendamento import AgendamentoSessao

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
                    # Passa apenas o ID para evitar compartilhar a Session entre threads
                    agendamento_id = agendamento.id
                    sessao_id = await asyncio.to_thread(_executar_agendamento_por_id, agendamento_id, agora)
                    logger.info(
                        "Agendamento executado id=%s sessao_criada=%s",
                        agendamento_id, sessao_id,
                    )
                except Exception as exc:
                    logger.error("Agendamento %s falhou: %s", agendamento.id, exc, exc_info=True)
                    try:
                        from app.services.email_service import notificar_agendamento_falhou
                        notificar_agendamento_falhou(agendamento.nome_template, str(exc))
                    except Exception:
                        pass
        finally:
            _liberar_lock_pg(db)


def _executar_agendamento_com_db(db, agendamento, agora: datetime) -> str | None:
    """Versão síncrona para uso no route executar-agora — reutiliza a Session existente."""
    from app.repositories import sessao_repo, item_repo

    nome = f"{agendamento.nome_template} — {agora.strftime('%d/%m/%Y %H:%M')}"
    nova_sessao = sessao_repo.criar_sessao(db, nome)
    agendamento.ultima_sessao_criada_id = nova_sessao.id

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

    agendamento.ultima_execucao = agora
    agendamento.proxima_execucao = _calcular_proxima_execucao(agendamento, agora)

    if agendamento.frequencia == "unico":
        agendamento.ativo = False

    db.commit()
    return nova_sessao.id


def _executar_agendamento_por_id(agendamento_id: str, agora: datetime) -> str | None:
    """
    Cria uma nova sessão baseada no template do agendamento.
    Abre sua própria Session — não recebe db como parâmetro para evitar uso
    cross-thread de SQLAlchemy Session (não thread-safe).
    """
    from app.database import SessionLocal
    from app.models.agendamento import AgendamentoSessao
    from app.repositories import sessao_repo, item_repo

    with SessionLocal() as db:
        agendamento = db.query(AgendamentoSessao).filter(AgendamentoSessao.id == agendamento_id).first()
        if not agendamento:
            return None

        nome = f"{agendamento.nome_template} — {agora.strftime('%d/%m/%Y %H:%M')}"
        nova_sessao = sessao_repo.criar_sessao(db, nome)
        agendamento.ultima_sessao_criada_id = nova_sessao.id

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

        agendamento.ultima_execucao = agora
        agendamento.proxima_execucao = _calcular_proxima_execucao(agendamento, agora)

        if agendamento.frequencia == "unico":
            agendamento.ativo = False

        db.commit()
        return nova_sessao.id


def _tz_agendamentos():
    """Fuso em que o campo `hora` é interpretado (SCHEDULER_TZ, default America/Sao_Paulo).
    Sem isso, "08:00" seria UTC — a sessão nasceria às 05:00 no horário de Brasília."""
    from zoneinfo import ZoneInfo
    from app.config import SCHEDULER_TZ
    try:
        return ZoneInfo(SCHEDULER_TZ)
    except Exception:
        logger.warning("SCHEDULER_TZ inválido (%r) — usando UTC", SCHEDULER_TZ)
        return timezone.utc


def _calcular_proxima_execucao(agendamento, referencia: datetime) -> datetime | None:
    """Calcula a próxima data/hora de execução conforme a frequência.
    O cálculo é feito no fuso SCHEDULER_TZ; o resultado é armazenado em UTC."""
    hora_str = agendamento.hora or "08:00"
    try:
        hora, minuto = map(int, hora_str.split(":"))
    except ValueError:
        hora, minuto = 8, 0

    tz = _tz_agendamentos()
    if referencia.tzinfo is None:
        referencia = referencia.replace(tzinfo=timezone.utc)
    referencia = referencia.astimezone(tz)

    if agendamento.frequencia == "unico":
        return None

    if agendamento.frequencia == "diario":
        proxima = (referencia + timedelta(days=1)).replace(
            hour=hora, minute=minuto, second=0, microsecond=0
        )
        return proxima.astimezone(timezone.utc)

    if agendamento.frequencia == "semanal":
        dia_alvo = agendamento.dia_semana or 0
        dias_faltando = (dia_alvo - referencia.weekday()) % 7
        if dias_faltando == 0:
            dias_faltando = 7
        proxima = (referencia + timedelta(days=dias_faltando)).replace(
            hour=hora, minute=minuto, second=0, microsecond=0
        )
        return proxima.astimezone(timezone.utc)

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
        return proxima.astimezone(timezone.utc)

    return None


def calcular_proxima_execucao_inicial(
    frequencia: str,
    hora: str,
    dia_semana: int | None,
    dia_mes: int | None,
    data_inicio: datetime | None = None,
) -> datetime:
    """Calcula a primeira execução ao criar um novo agendamento.
    `hora` é interpretada no fuso SCHEDULER_TZ; o resultado é armazenado em UTC."""
    tz = _tz_agendamentos()
    agora = data_inicio or datetime.now(timezone.utc)
    if agora.tzinfo is None:
        # datetime sem fuso vindo do payload: interpreta no fuso dos agendamentos
        agora = agora.replace(tzinfo=tz)
    agora = agora.astimezone(tz)

    try:
        h, m = map(int, hora.split(":"))
    except ValueError:
        h, m = 8, 0

    if frequencia == "unico":
        # Para único, data_inicio deve ser fornecida pelo usuário
        return (data_inicio or agora) if (data_inicio is None or data_inicio.tzinfo) else data_inicio.replace(tzinfo=tz)

    if frequencia == "diario":
        proxima = agora.replace(hour=h, minute=m, second=0, microsecond=0)
        if proxima <= agora:
            proxima += timedelta(days=1)
        return proxima.astimezone(timezone.utc)

    if frequencia == "semanal":
        dia_alvo = dia_semana or 0
        dias_faltando = (dia_alvo - agora.weekday()) % 7
        if dias_faltando == 0:
            proxima = agora.replace(hour=h, minute=m, second=0, microsecond=0)
            if proxima <= agora:
                dias_faltando = 7
            else:
                return proxima.astimezone(timezone.utc)
        proxima = (agora + timedelta(days=dias_faltando)).replace(
            hour=h, minute=m, second=0, microsecond=0
        )
        return proxima.astimezone(timezone.utc)

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
        return proxima.astimezone(timezone.utc)

    return (agora + timedelta(hours=1)).astimezone(timezone.utc)
