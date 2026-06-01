"""
Provider de IA — abstrai Groq (gratuito) e Anthropic.
Prioridade: GROQ_API_KEY → ANTHROPIC_API_KEY → None (sem IA).

Para obter uma chave gratuita do Groq: https://console.groq.com
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

# Modelos por provider
_GROQ_MODEL = "llama-3.3-70b-versatile"
_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"


class AIProvider:
    """
    Wrapper unificado para chamadas de IA.
    Suporta Groq (OpenAI-compatible) e Anthropic.
    """

    def __init__(self) -> None:
        self._client: Any = None
        self._provider_type: str | None = None
        self._model: str | None = None
        self._init()

    def _init(self) -> None:
        groq_key = os.getenv("GROQ_API_KEY", "").strip()
        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

        if groq_key:
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=groq_key,
                    base_url="https://api.groq.com/openai/v1",
                    timeout=30.0,
                )
                self._provider_type = "groq"
                self._model = _GROQ_MODEL
                logger.info("AIProvider: usando Groq (%s)", _GROQ_MODEL)
                return
            except ImportError:
                logger.warning("AIProvider: pacote 'openai' não encontrado — instale com pip install openai")
            except Exception as exc:
                logger.warning("AIProvider: falha ao inicializar Groq — %s", exc)

        if anthropic_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=anthropic_key, timeout=30.0)
                self._provider_type = "anthropic"
                self._model = _ANTHROPIC_MODEL
                logger.info("AIProvider: usando Anthropic (%s)", _ANTHROPIC_MODEL)
                return
            except ImportError:
                logger.warning("AIProvider: pacote 'anthropic' não encontrado")
            except Exception as exc:
                logger.warning("AIProvider: falha ao inicializar Anthropic — %s", exc)

        logger.info("AIProvider: nenhuma chave configurada — modo sem IA")

    @property
    def disponivel(self) -> bool:
        return self._client is not None

    @property
    def provider_nome(self) -> str:
        return self._provider_type or "nenhum"

    def completar(self, prompt: str, max_tokens: int = 1024) -> str | None:
        """
        Envia o prompt e retorna o texto da resposta.
        Retorna None se o provider não estiver configurado ou em caso de erro.
        """
        if not self._client:
            return None
        try:
            if self._provider_type in ("groq", "openai"):
                resp = self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                    response_format={"type": "json_object"},
                )
                return resp.choices[0].message.content

            if self._provider_type == "anthropic":
                resp = self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                return resp.content[0].text

        except Exception as exc:
            logger.warning("AIProvider.completar: falha — %s", exc)

        return None

    def completar_chat(self, messages: list[dict], max_tokens: int = 800) -> str | None:
        """
        Chat completion com histórico de mensagens.
        `messages` é uma lista de dicts com 'role' e 'content'.
        Para Anthropic, separa system automaticamente.
        """
        if not self._client:
            return None
        try:
            if self._provider_type in ("groq", "openai"):
                resp = self._client.chat.completions.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    messages=messages,
                    temperature=0.7,
                )
                return resp.choices[0].message.content

            if self._provider_type == "anthropic":
                system = next((m["content"] for m in messages if m["role"] == "system"), "")
                user_msgs = [m for m in messages if m["role"] != "system"]
                resp = self._client.messages.create(
                    model=self._model,
                    system=system,
                    messages=user_msgs,
                    max_tokens=max_tokens,
                )
                return resp.content[0].text

        except Exception as exc:
            logger.warning("AIProvider.completar_chat: %s", exc)
        return None

    def completar_json(self, prompt: str, max_tokens: int = 1024) -> dict | None:
        """
        Chama `completar` e faz parse do JSON.
        Remove code fences caso o modelo as inclua.
        """
        raw = self.completar(prompt, max_tokens=max_tokens)
        if raw is None:
            return None

        raw = raw.strip()
        # Remove code fences (```json ... ```)
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning("AIProvider: resposta não é JSON válido — %s | raw: %.200s", exc, raw)
            return None


# Singleton global
provider = AIProvider()
