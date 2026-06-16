"""
Serviço de notificações por e-mail via SMTP.

Configuração via variáveis de ambiente:
  SMTP_HOST        = smtp.empresa.com.br
  SMTP_PORT        = 587              (465 para SSL, 587 para STARTTLS)
  SMTP_USER        = inventario@empresa.com.br
  SMTP_PASSWORD    = senha
  SMTP_FROM        = INVIQ <inventario@empresa.com.br>
  SMTP_USE_TLS     = true             (true = STARTTLS; false = SSL direto na porta 465)
  NOTIF_EMAIL      = ti@empresa.com.br,gestor@empresa.com.br  (destinatários padrão)
  NOTIF_DIVERGENCIA_THRESHOLD = 10   (% de divergência que dispara alerta)

Se SMTP_HOST não estiver configurado, os e-mails são logados no console (dry-run).
"""
from __future__ import annotations

import logging
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Sequence

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

_SMTP_HOST    = os.getenv("SMTP_HOST", "")
_SMTP_PORT    = int(os.getenv("SMTP_PORT", "587"))
_SMTP_USER    = os.getenv("SMTP_USER", "")
_SMTP_PASS    = os.getenv("SMTP_PASSWORD", "")
_SMTP_FROM    = os.getenv("SMTP_FROM", f"INVIQ <{_SMTP_USER}>") if _SMTP_USER else "INVIQ <noreply@localhost>"
_SMTP_TLS     = os.getenv("SMTP_USE_TLS", "true").lower() != "false"
_NOTIF_EMAIL  = [e.strip() for e in os.getenv("NOTIF_EMAIL", "").split(",") if e.strip()]
_DIV_THRESH   = float(os.getenv("NOTIF_DIVERGENCIA_THRESHOLD", "10"))


def _he(s: object) -> str:
    """Escapa caracteres HTML em strings controladas pelo usuário."""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def configurado() -> bool:
    return bool(_SMTP_HOST and _SMTP_USER and _SMTP_PASS and _NOTIF_EMAIL)


# ── Core de envio ─────────────────────────────────────────────────────────────

def _enviar(
    assunto: str,
    html: str,
    destinatarios: list[str],
) -> None:
    """Monta e envia o e-mail. Lança exceção em caso de falha."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = assunto
    msg["From"]    = _SMTP_FROM
    msg["To"]      = ", ".join(destinatarios)
    msg.attach(MIMEText(html, "html", "utf-8"))

    if not configurado():
        logger.info(
            "EMAIL dry-run (SMTP não configurado) | para=%s | assunto=%s",
            destinatarios, assunto,
        )
        return

    try:
        if _SMTP_TLS:
            with smtplib.SMTP(_SMTP_HOST, _SMTP_PORT, timeout=15) as s:
                s.ehlo()
                s.starttls()
                s.login(_SMTP_USER, _SMTP_PASS)
                s.sendmail(_SMTP_FROM, destinatarios, msg.as_bytes())
        else:
            with smtplib.SMTP_SSL(_SMTP_HOST, _SMTP_PORT, timeout=15) as s:
                s.login(_SMTP_USER, _SMTP_PASS)
                s.sendmail(_SMTP_FROM, destinatarios, msg.as_bytes())
        logger.info("EMAIL enviado para=%s assunto=%s", destinatarios, assunto)
    except Exception as exc:
        logger.error("EMAIL falhou para=%s erro=%s", destinatarios, exc, exc_info=True)
        raise


def _enviar_async(assunto: str, html: str, destinatarios: list[str]) -> None:
    """Envia em thread separada para não bloquear a requisição."""
    t = threading.Thread(target=_enviar, args=(assunto, html, destinatarios), daemon=True)
    t.start()


# ── Templates HTML ─────────────────────────────────────────────────────────────

def _base_html(titulo: str, conteudo: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="utf-8"><style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
         background: #f0f4f8; margin: 0; padding: 24px; color: #1a2b42; }}
  .card {{ background: #fff; border-radius: 12px; padding: 32px; max-width: 600px;
           margin: 0 auto; box-shadow: 0 4px 24px rgba(0,0,0,0.08); }}
  .header {{ text-align: center; margin-bottom: 28px; }}
  .logo {{ font-size: 28px; font-weight: 900; color: #005f8f; letter-spacing: -1px; }}
  .subtitle {{ font-size: 12px; color: #64748b; letter-spacing: 0.1em; text-transform: uppercase; }}
  h2 {{ font-size: 20px; font-weight: 700; margin: 0 0 16px; color: #1a2b42; }}
  p {{ font-size: 14px; line-height: 1.6; color: #475569; margin: 0 0 12px; }}
  .stat {{ background: #f0f9ff; border-left: 4px solid #0ea5e9; border-radius: 6px;
           padding: 12px 16px; margin: 16px 0; }}
  .stat .label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #64748b; }}
  .stat .value {{ font-size: 24px; font-weight: 700; color: #005f8f; margin-top: 2px; }}
  .badge-ok   {{ background: #dcfce7; color: #166534; padding: 3px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }}
  .badge-warn {{ background: #fef9c3; color: #854d0e; padding: 3px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }}
  .badge-err  {{ background: #fee2e2; color: #991b1b; padding: 3px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }}
  .btn {{ display: inline-block; background: #005f8f; color: #fff; padding: 12px 28px;
          border-radius: 8px; text-decoration: none; font-weight: 600; font-size: 14px; margin-top: 20px; }}
  .footer {{ text-align: center; margin-top: 28px; font-size: 11px; color: #94a3b8; }}
  table {{ width: 100%; border-collapse: collapse; margin: 16px 0; font-size: 13px; }}
  th {{ background: #f0f4f8; padding: 8px 12px; text-align: left; font-size: 11px;
        text-transform: uppercase; letter-spacing: 0.06em; color: #64748b; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #e2e8f0; }}
</style></head>
<body>
<div class="card">
  <div class="header">
    <div class="logo">INVIQ</div>
    <div class="subtitle">Sistema de Inventário por QR Code</div>
  </div>
  <h2>{titulo}</h2>
  {conteudo}
  <div class="footer">
    Esta mensagem foi gerada automaticamente pelo INVIQ.<br>
    Não responda este e-mail.
  </div>
</div>
</body></html>"""


# ── Notificações específicas ──────────────────────────────────────────────────

def notificar_sessao_concluida(
    sessao_id: str,
    sessao_nome: str,
    sessao_codigo: str,
    total_itens: int,
    divergencias: int,
    taxa_acerto: float,
    operadores: list[str],
    destinatarios: list[str] | None = None,
) -> None:
    """Dispara e-mail quando uma sessão de inventário é concluída."""
    dests = destinatarios or _NOTIF_EMAIL
    if not dests:
        logger.debug("EMAIL sessao_concluida: sem destinatários configurados, pulando.")
        return

    badge_taxa = (
        '<span class="badge-ok">Excelente</span>' if taxa_acerto >= 95 else
        '<span class="badge-warn">Atenção</span>' if taxa_acerto >= 80 else
        '<span class="badge-err">Crítico</span>'
    )

    ops_html = (
        "<p>Operadores: <strong>" + ", ".join(_he(o) for o in operadores) + "</strong></p>"
        if operadores else ""
    )

    base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")

    conteudo = f"""
    <p>O inventário <strong>{_he(sessao_nome)}</strong> (<code>{_he(sessao_codigo)}</code>) foi concluído.</p>
    <div class="stat"><div class="label">Taxa de Acerto</div><div class="value">{taxa_acerto:.1f}% {badge_taxa}</div></div>
    <table>
      <tr><th>Itens na base</th><th>Divergências</th><th>Conformes</th></tr>
      <tr>
        <td><strong>{total_itens}</strong></td>
        <td><strong style="color:#991b1b">{divergencias}</strong></td>
        <td><strong style="color:#166534">{total_itens - divergencias}</strong></td>
      </tr>
    </table>
    {ops_html}
    <a class="btn" href="{base_url}/sessao/{sessao_id}">Ver Relatório Completo</a>
    """
    html = _base_html(f"Inventário Concluído — {_he(sessao_nome)}", conteudo)
    _enviar_async(f"[INVIQ] Inventário concluído: {sessao_nome}", html, dests)


def notificar_alta_divergencia(
    sessao_id: str,
    sessao_nome: str,
    sessao_codigo: str,
    taxa_divergencia: float,
    itens_divergentes: list[dict],
    destinatarios: list[str] | None = None,
) -> None:
    """Alerta quando a taxa de divergência ultrapassa o threshold configurado."""
    if taxa_divergencia < _DIV_THRESH:
        return
    dests = destinatarios or _NOTIF_EMAIL
    if not dests:
        return

    top_itens = itens_divergentes[:5]
    linhas_html = "".join(
        f"<tr><td><code>{_he(it.get('codigo',''))}</code></td>"
        f"<td>{_he(it.get('produto',''))}</td>"
        f"<td>{_he(it.get('quantidade_base',''))}</td>"
        f"<td><strong style='color:#991b1b'>{_he(it.get('quantidade_encontrada',''))}</strong></td></tr>"
        for it in top_itens
    )

    base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")
    conteudo = f"""
    <p>O inventário <strong>{_he(sessao_nome)}</strong> (<code>{_he(sessao_codigo)}</code>)
    atingiu uma taxa de divergência de <strong style="color:#991b1b">{taxa_divergencia:.1f}%</strong>,
    acima do limite configurado de {_DIV_THRESH:.0f}%.</p>
    <div class="stat" style="border-color:#ef4444;background:#fef2f2">
      <div class="label">Taxa de Divergência</div>
      <div class="value" style="color:#991b1b">{taxa_divergencia:.1f}%</div>
    </div>
    <p>Top itens divergentes:</p>
    <table>
      <tr><th>Código</th><th>Produto</th><th>Base</th><th>Encontrado</th></tr>
      {linhas_html}
    </table>
    <a class="btn" style="background:#991b1b" href="{base_url}/sessao/{sessao_id}">Revisar Inventário</a>
    """
    html = _base_html(f"Alerta de Divergência — {_he(sessao_nome)}", conteudo)
    _enviar_async(
        f"[INVIQ] ALERTA: Divergência alta em {sessao_nome} ({taxa_divergencia:.1f}%)",
        html, dests,
    )


def notificar_agendamento_falhou(
    agendamento_nome: str,
    erro: str,
    destinatarios: list[str] | None = None,
) -> None:
    """Alerta quando um agendamento automático falha."""
    dests = destinatarios or _NOTIF_EMAIL
    if not dests:
        return

    conteudo = f"""
    <p>O agendamento <strong>{_he(agendamento_nome)}</strong> falhou durante a execução automática.</p>
    <div class="stat" style="border-color:#ef4444;background:#fef2f2">
      <div class="label">Erro</div>
      <div class="value" style="font-size:14px;color:#991b1b">{_he(erro)}</div>
    </div>
    <p>Verifique os logs do servidor e, se necessário, execute o agendamento manualmente
    pela interface de administração.</p>
    """
    html = _base_html(f"Falha no Agendamento — {_he(agendamento_nome)}", conteudo)
    _enviar_async(f"[INVIQ] Falha no agendamento: {agendamento_nome}", html, dests)


def notificar_segunda_aprovacao_pendente(
    sessao_id: str,
    sessao_nome: str,
    aprovador_primario: str,
    destinatarios: list[str] | None = None,
) -> None:
    """Notifica o segundo aprovador que há uma sessão aguardando aprovação final."""
    dests = destinatarios or _NOTIF_EMAIL
    if not dests:
        return

    base_url = os.getenv("APP_BASE_URL", "http://localhost:8000")
    conteudo = f"""
    <p>O inventário <strong>{_he(sessao_nome)}</strong> foi concluído por <strong>{_he(aprovador_primario)}</strong>
    e aguarda a <strong>segunda aprovação</strong> antes do envio ao ERP.</p>
    <p>Acesse o painel de supervisão para revisar os dados e confirmar o ajuste de estoque.</p>
    <a class="btn" href="{base_url}/sessao/{sessao_id}">Revisar e Aprovar</a>
    """
    html = _base_html(f"Segunda Aprovação Pendente — {_he(sessao_nome)}", conteudo)
    _enviar_async(f"[INVIQ] Aprovação pendente: {sessao_nome}", html, dests)


def info_configuracao() -> dict:
    return {
        "configurado": configurado(),
        "smtp_host": _SMTP_HOST or None,
        "smtp_port": _SMTP_PORT,
        "smtp_user": _SMTP_USER or None,
        "tls": _SMTP_TLS,
        "destinatarios_padrao": _NOTIF_EMAIL,
        "threshold_divergencia_pct": _DIV_THRESH,
    }
