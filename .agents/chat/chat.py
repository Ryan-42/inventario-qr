"""InventarioChatAgent — chat interativo sobre sessão de inventário."""
from __future__ import annotations
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_HISTORY = 10
_MAX_TOKENS = 800
_CHARS_PER_MSG = 600


class InventarioChatAgent:
    """
    Chat em linguagem natural sobre uma sessão de inventário.
    Padrão: constrói contexto rico com dados reais e responde
    perguntas como "quais itens faltam?", "quem teve mais divergências?".
    """

    def responder(
        self,
        sessao: Any,
        stats: dict,
        divergencias: list[dict],
        itens: list[dict],
        contagens: list[dict],
        mensagem: str,
        historico: list[dict],
        rodadas_info: dict = None,
    ) -> dict:
        from app.agents.provider import provider

        if not provider.disponivel:
            return {
                "resposta": (
                    "IA não configurada. Configure GROQ_API_KEY no arquivo .env "
                    "para usar o chat. Chave gratuita em: https://console.groq.com"
                ),
                "fonte": "sistema",
            }

        contexto = self._construir_contexto(sessao, stats, divergencias, itens, contagens, rodadas_info or {})
        messages: list[dict] = [
            {
                "role": "system",
                "content": (
                    "Você é um assistente especializado em análise de inventário industrial. "
                    "Responda SEMPRE em português, de forma objetiva e direta. "
                    "Use os dados concretos fornecidos. Seja preciso com números.\n\n"
                    f"DADOS DA SESSÃO:\n{contexto}"
                ),
            }
        ]

        _ROLES_PERMITIDOS = {"user", "assistant"}
        for msg in historico[-_MAX_HISTORY:]:
            role = msg.get("role", "user")
            if role not in _ROLES_PERMITIDOS:
                role = "user"  # whitelist: impede injeção de role "system" via histórico
            messages.append({
                "role": role,
                "content": str(msg.get("content", ""))[:_CHARS_PER_MSG],
            })
        messages.append({"role": "user", "content": mensagem[:1000]})

        resposta = provider.completar_chat(messages, max_tokens=_MAX_TOKENS)
        return {
            "resposta": resposta or "Não consegui processar sua pergunta. Tente reformular.",
            "fonte": "ia",
        }

    def _construir_contexto(
        self,
        sessao: Any,
        stats: dict,
        divergencias: list[dict],
        itens: list[dict],
        contagens: list[dict],
        rodadas_info: dict = None,
    ) -> str:
        op_map: dict[str, dict] = {}
        for c in contagens:
            op = c.get("operador") or "(sem nome)"
            d = op_map.setdefault(op, {"total": 0, "divs": 0})
            d["total"] += 1
            if c.get("divergencia"):
                d["divs"] += 1

        ops_str = "; ".join(
            f"{op}: {d['total']} leituras, {d['divs']} div."
            for op, d in sorted(op_map.items(), key=lambda x: -x[1]["total"])[:5]
        ) or "nenhum operador ainda"

        top_div = sorted(
            [d for d in divergencias if d.get("diferenca") is not None],
            key=lambda x: abs(x.get("diferenca", 0)),
            reverse=True,
        )[:5]
        div_str = "; ".join(
            f"{d.get('codigo')} ({str(d.get('produto','?'))[:25]}): "
            f"base={d.get('quantidade_base')}, encontrado={d.get('quantidade_encontrada')}"
            for d in top_div
        ) or "nenhuma divergência"

        pendentes = [i for i in itens if i.get("status") == "Pendente"]
        pendentes_str = ", ".join(i.get("codigo", "") for i in pendentes[:8])
        if len(pendentes) > 8:
            pendentes_str += f" e mais {len(pendentes) - 8}"

        rodadas_info = rodadas_info or {}
        rodadas_linha = (
            f"Rodadas de contagem: rodada máxima={rodadas_info.get('rodada_maxima', 0)}, "
            f"aguardando 2ª contagem: {len(rodadas_info.get('itens_segunda', []))} itens, "
            f"aguardando 3ª contagem: {len(rodadas_info.get('itens_terceira', []))} itens"
        )
        return (
            f"Sessão: '{getattr(sessao, 'nome', 'N/A')}' | Status: {getattr(sessao, 'status', 'N/A')}\n"
            f"Progresso: {stats.get('conferidos', 0)}/{stats.get('total', 0)} "
            f"({stats.get('percentual', 0.0):.1f}%)\n"
            f"Pendentes: {stats.get('pendentes', 0)} | "
            f"Divergências: {stats.get('divergencias', 0)}\n"
            f"Operadores: {ops_str}\n"
            f"Top divergências: {div_str}\n"
            f"Itens pendentes (amostra): {pendentes_str or 'nenhum'}\n"
            f"{rodadas_linha}"
        )
