"""
SopCoachAgent — Agente de suporte operacional conversacional ao operador.
Guia operadores em campo sobre Procedimentos Operacionais Padrão (POPs) e regras de contagem.
"""
from __future__ import annotations

import logging
from app.agents.provider import provider

logger = logging.getLogger(__name__)

class SopCoachAgent:
    """Responde dúvidas de contagem dos operadores em tempo real com base nas regras do negócio."""

    def responder(self, mensagens: list[dict], contexto_extra: str | None = None) -> dict:
        """
        mensagens: lista de dicts com 'role' e 'content'
        contexto_extra: informações sobre o item atual ou status do scanner
        """
        # Sistema de prompts com as Regras de Negócio do INVIQ
        prompt_sistema = """Você é o Assistente do INVIQ, um robô de suporte operacional no depósito de inventário físico.
Seu objetivo é ajudar operadores e supervisores a executarem suas contagens corretamente e resolverem problemas operacionais em tempo real.

REGRAS DE OPERAÇÃO DO INVIQ:
1. O inventário é feito por rodadas:
   - Rodada 1: Todos os itens devem ser contados uma vez.
   - Rodada 2: Apenas itens que apresentaram divergência na Rodada 1 são recontados.
   - Rodada 3: Recontagem final de divergências que persistem.
   - 'Para Ajuste': Se na recontagem a quantidade der idêntica à anterior, o item é fechado como "Para Ajuste" (consenso).
2. Divergências críticas: Itens com diferença superior a 100% ou de alto valor (>= R$ 5.000) devem ter contagem física testemunhada por supervisor.
3. Se um código QR/etiqueta estiver danificado:
   - Tentar a busca fuzzy pelo nome do produto ou localização no modo manual.
   - Se não encontrar, registrar uma observação e notificar o supervisor.
4. Se o scanner mobile ficar offline:
   - O sistema salva na fila local do celular (localStorage) e sincroniza automaticamente quando a internet voltar. Não saia da página para não perder dados.
5. Se o item pertencer a outro setor:
   - O operador deve se mover para o setor correto ou pedir para o admin liberar o grupo dele.

Responda de forma curta, objetiva e muito amigável para operadores que estão em pé no depósito trabalhando com o celular."""

        messages_payload = [{"role": "system", "content": prompt_sistema}]
        if contexto_extra:
            messages_payload.append({"role": "system", "content": f"Contexto atual do scanner: {contexto_extra}"})

        # Adiciona histórico do usuário
        messages_payload.extend(mensagens)

        # Fallback local determinístico se IA não estiver disponível
        resposta_fallback = (
            "Desculpe, o suporte inteligente por IA está offline no momento. "
            "Por favor, procure seu supervisor de campo ou verifique se o QR code/código está legível."
        )

        ultima_msg = mensagens[-1]["content"].lower() if mensagens else ""
        if "offline" in ultima_msg or "internet" in ultima_msg:
            resposta_fallback = (
                "Se o sinal cair, continue contando normalmente! O INVIQ salva tudo no celular e sincroniza "
                "sozinho assim que a conexão retornar. Só não feche a aba do navegador."
            )
        elif "danificado" in ultima_msg or "rasgado" in ultima_msg or "qr" in ultima_msg or "ler" in ultima_msg:
            resposta_fallback = (
                "Se a etiqueta estiver rasgada, mude para a busca manual e digite o código SKU ou nome do produto. "
                "Se não der certo, chame o supervisor para colar uma nova etiqueta QR."
            )
        elif "supervisor" in ultima_msg:
            resposta_fallback = (
                "Para itens de alto valor ou divergências extremas (acima de 100%), o supervisor deve "
                "testemunhar a contagem. O token de supervisor permite que ele valide a área diretamente no painel."
            )

        resultado = {
            "resposta": resposta_fallback,
            "contexto_verificado": True,
            "fonte": "basico"
        }

        if not provider.disponivel:
            return resultado

        # Executa chat completion via Groq
        ia_resposta = provider.completar_chat(messages_payload, max_tokens=300)
        if ia_resposta:
            resultado.update({
                "resposta": ia_resposta,
                "fonte": "ia"
            })

        return resultado
