"""
Integração com TOTVS Protheus — Módulo de Ajuste de Estoque.

Configuração via variáveis de ambiente:
  TOTVS_URL          = http://seu-servidor-totvs:8080
  TOTVS_EMPRESA      = T1             (código da empresa no Protheus)
  TOTVS_FILIAL       = 01             (código da filial)
  TOTVS_USER         = admin
  TOTVS_PASSWORD     = senha
  TOTVS_ARMAZEM      = 01             (armazém padrão para ajuste)
  TOTVS_DRY_RUN      = true           (true = não envia nada, só loga o payload)

Quando TOTVS_URL não estiver configurado, todas as operações rodam em modo
dry-run e retornam o payload que seria enviado — perfeito para testes/demo.

Fluxo Protheus REST:
  1. POST /rest/api/framework/v1/loginsession  → obtém Bearer token
  2. POST /rest/api/est/v1/inventoryadjustments → envia ajuste (MATA200)
  3. GET  /rest/api/est/v1/inventoryadjustments/{id} → consulta status
"""
from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from base64 import b64encode
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# ── Configuração ──────────────────────────────────────────────────────────────

_TOTVS_URL      = os.getenv("TOTVS_URL", "").rstrip("/")
_TOTVS_EMPRESA  = os.getenv("TOTVS_EMPRESA", "T1")
_TOTVS_FILIAL   = os.getenv("TOTVS_FILIAL", "01")
_TOTVS_USER     = os.getenv("TOTVS_USER", "")
_TOTVS_PASSWORD = os.getenv("TOTVS_PASSWORD", "")
_TOTVS_ARMAZEM  = os.getenv("TOTVS_ARMAZEM", "01")
_TOTVS_DRY_RUN  = os.getenv("TOTVS_DRY_RUN", "false").lower() == "true"

_TIMEOUT_SEGUNDOS = 15
_MAX_RETRIES      = 3
_RETRY_BACKOFF    = [1, 2, 4]  # segundos entre tentativas


def configurado() -> bool:
    """Retorna True se TOTVS_URL e credenciais estiverem configurados."""
    return bool(_TOTVS_URL and _TOTVS_USER and _TOTVS_PASSWORD)


def modo_dry_run() -> bool:
    """Dry-run: retorna True quando TOTVS não está configurado OU TOTVS_DRY_RUN=true."""
    return _TOTVS_DRY_RUN or not configurado()


# ── Autenticação ──────────────────────────────────────────────────────────────

def _obter_token_bearer() -> str:
    """
    Autentica no TOTVS Protheus REST via Basic Auth e retorna Bearer token.
    Endpoint padrão: POST /rest/api/framework/v1/loginsession
    """
    url = f"{_TOTVS_URL}/rest/api/framework/v1/loginsession"
    credentials = b64encode(f"{_TOTVS_USER}:{_TOTVS_PASSWORD}".encode()).decode()
    payload = json.dumps({
        "userName": _TOTVS_USER,
        "password": _TOTVS_PASSWORD,
        "empresa": _TOTVS_EMPRESA,
        "filial": _TOTVS_FILIAL,
    }).encode()

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", f"Basic {credentials}")

    with urllib.request.urlopen(req, timeout=_TIMEOUT_SEGUNDOS) as resp:
        data = json.loads(resp.read())
        token = data.get("access_token") or data.get("token") or data.get("Token")
        if not token:
            raise ValueError(f"TOTVS não retornou access_token. Resposta: {data}")
        return token


# ── Mapeamento Inventário → Protheus ─────────────────────────────────────────

def _montar_payload_ajuste(
    sessao_codigo: str,
    sessao_nome: str,
    itens_divergentes: list[dict],
    data_inventario: str | None = None,
) -> dict:
    """
    Monta payload no formato TOTVS Protheus REST para ajuste de estoque (MATA200).

    Estrutura baseada na API REST Protheus 12.1.x — módulo EST (Estoque).
    doc: https://api.totvs.com.br/apis/est/inventory
    """
    data_ref = data_inventario or datetime.now(timezone.utc).strftime("%Y%m%d")

    linhas = []
    for item in itens_divergentes:
        quantidade_ajuste = item.get("quantidade_encontrada")
        if quantidade_ajuste is None:
            continue
        linhas.append({
            "produto": str(item.get("codigo", "")),
            "descricao": str(item.get("produto", "")),
            "armazem": item.get("local_fisico") or _TOTVS_ARMAZEM,
            "quantidadeAnterior": float(item.get("quantidade_base", 0)),
            "quantidadeInventario": float(quantidade_ajuste),
            "diferenca": float(item.get("diferenca", 0)),
            "tipoMovimento": "A",   # A = Ajuste de Inventário no Protheus
            "observacao": f"Inventário INVIQ {sessao_codigo} — {sessao_nome}",
        })

    return {
        "empresa": _TOTVS_EMPRESA,
        "filial": _TOTVS_FILIAL,
        "documentoOrigem": sessao_codigo,
        "dataInventario": data_ref,
        "descricao": f"Ajuste automático — Inventário {sessao_nome}",
        "origem": "INVIQ",
        "itens": linhas,
    }


# ── Envio com retry ───────────────────────────────────────────────────────────

def _post_com_retry(url: str, payload: dict, token: str) -> dict:
    body = json.dumps(payload).encode()
    for tentativa, espera in enumerate(_RETRY_BACKOFF, 1):
        try:
            req = urllib.request.Request(url, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {token}")
            req.add_header("X-TOTVS-Origin", "INVIQ")
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEGUNDOS) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            body_err = exc.read().decode(errors="replace")
            logger.error("TOTVS HTTP %s tentativa %s/%s: %s", exc.code, tentativa, _MAX_RETRIES, body_err)
            if exc.code in (400, 401, 403, 422):  # erros não-recuperáveis
                raise
        except Exception as exc:
            logger.warning("TOTVS tentativa %s/%s falhou: %s", tentativa, _MAX_RETRIES, exc)
        if tentativa < _MAX_RETRIES:
            time.sleep(espera)
    raise RuntimeError(f"TOTVS: {_MAX_RETRIES} tentativas esgotadas para POST {url}")


# ── API pública ───────────────────────────────────────────────────────────────

def enviar_ajuste_estoque(
    sessao_codigo: str,
    sessao_nome: str,
    itens_divergentes: list[dict],
    data_inventario: str | None = None,
) -> dict[str, Any]:
    """
    Envia ajuste de estoque ao TOTVS Protheus.

    Se estiver em modo dry-run, retorna o payload sem enviar nada.
    Sempre retorna um dict com:
      - sucesso: bool
      - dry_run: bool
      - payload_enviado: dict (o que foi/seria enviado)
      - resposta_totvs: dict | None (só quando realmente enviado)
      - erro: str | None
      - timestamp: str
    """
    payload = _montar_payload_ajuste(
        sessao_codigo, sessao_nome, itens_divergentes, data_inventario
    )
    agora = datetime.now(timezone.utc).isoformat()

    if modo_dry_run():
        aviso = (
            "TOTVS não configurado — defina TOTVS_URL, TOTVS_USER e TOTVS_PASSWORD no .env."
            if not configurado() else
            "TOTVS_DRY_RUN=true — payload gerado mas não enviado."
        )
        logger.info("TOTVS dry-run sessao=%s itens=%d", sessao_codigo, len(payload["itens"]))
        return {
            "sucesso": True,
            "dry_run": True,
            "aviso": aviso,
            "payload_enviado": payload,
            "resposta_totvs": None,
            "erro": None,
            "timestamp": agora,
        }

    try:
        token = _obter_token_bearer()
        url = f"{_TOTVS_URL}/rest/api/est/v1/inventoryadjustments"
        resposta = _post_com_retry(url, payload, token)
        logger.info("TOTVS ajuste enviado sessao=%s protocolo=%s", sessao_codigo, resposta.get("id") or resposta.get("protocoloTotvs"))
        return {
            "sucesso": True,
            "dry_run": False,
            "payload_enviado": payload,
            "resposta_totvs": resposta,
            "erro": None,
            "timestamp": agora,
        }
    except Exception as exc:
        logger.error("TOTVS falhou sessao=%s erro=%s", sessao_codigo, exc, exc_info=True)
        return {
            "sucesso": False,
            "dry_run": False,
            "payload_enviado": payload,
            "resposta_totvs": None,
            "erro": str(exc),
            "timestamp": agora,
        }


def consultar_status_ajuste(protocolo_totvs: str) -> dict[str, Any]:
    """Consulta o status de um ajuste já enviado pelo protocolo retornado pelo TOTVS."""
    if modo_dry_run():
        return {"status": "dry_run", "protocolo": protocolo_totvs, "mensagem": "Modo dry-run ativo."}
    try:
        token = _obter_token_bearer()
        url = f"{_TOTVS_URL}/rest/api/est/v1/inventoryadjustments/{urllib.parse.quote(protocolo_totvs)}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SEGUNDOS) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.error("TOTVS consulta falhou protocolo=%s erro=%s", protocolo_totvs, exc)
        return {"status": "erro", "protocolo": protocolo_totvs, "erro": str(exc)}


def info_configuracao() -> dict:
    """Retorna informações da configuração atual (sem expor credenciais)."""
    return {
        "configurado": configurado(),
        "dry_run": modo_dry_run(),
        "totvs_url": _TOTVS_URL or None,
        "empresa": _TOTVS_EMPRESA,
        "filial": _TOTVS_FILIAL,
        "armazem_padrao": _TOTVS_ARMAZEM,
        "credenciais_presentes": bool(_TOTVS_USER and _TOTVS_PASSWORD),
    }
