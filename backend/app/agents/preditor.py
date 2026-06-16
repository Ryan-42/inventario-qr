"""
PredictionAgent — Agente preditivo de riscos e planejamento de inventário.
Analisa histórico de contagens anteriores e prevê comportamento de SKUs e setores.
"""
from __future__ import annotations

import logging
from typing import Any
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.sessao import Sessao
from app.models.item_base import ItemBase
from app.models.contagem import Contagem, HistoricoContagem
from app.agents.provider import provider

logger = logging.getLogger(__name__)

class PredictionAgent:
    """Analisa histórico de contagens e prevê itens críticos e tempos estimados."""

    def prever(self, sessao_id: str, db: Session) -> dict:
        sessao_atual = db.query(Sessao).filter(Sessao.id == sessao_id).first()
        if not sessao_atual:
            return {"erro": "Sessão não encontrada"}

        # 1. Coletar histórico do banco
        itens_atuais = db.query(ItemBase).filter(ItemBase.sessao_id == sessao_id).all()
        total_itens_novos = len(itens_atuais)

        # Buscar outras sessões concluintes
        sessoes_anteriores = (
            db.query(Sessao)
            .filter(Sessao.id != sessao_id, Sessao.status == "concluida")
            .order_by(Sessao.data_inicio.desc())
            .limit(5)
            .all()
        )

        hist_stats = []
        codigos_historico_problemas = {}

        for s in sessoes_anteriores:
            # Stats de divergência por item
            contagens_s = db.query(Contagem).filter(Contagem.sessao_id == s.id).all()
            total_s = len(contagens_s)
            divs_s = sum(1 for c in contagens_s if c.divergencia)
            taxa_div = round(divs_s / total_s * 100, 1) if total_s > 0 else 0.0

            hist_stats.append({
                "codigo": s.codigo,
                "nome": s.nome,
                "total_itens": total_s,
                "taxa_divergencia_pct": taxa_div
            })

            # Mapeia SKUs que divergiram nessa sessão
            for c in contagens_s:
                if c.divergencia:
                    codigos_historico_problemas[c.codigo] = codigos_historico_problemas.get(c.codigo, 0) + 1

        # 2. Heurística Local (Fallback)
        itens_alto_risco_local = []
        for item in itens_atuais:
            cod = item.codigo
            fator_risco = codigos_historico_problemas.get(cod, 0)
            valor = float(item.valor_estoque or 0.0)
            
            # Se já divergiu em inventários anteriores ou tem valor muito alto (> 5000) com algum histórico
            if fator_risco > 0 or (valor > 5000.0 and len(sessoes_anteriores) > 0):
                prob = min(30 + (fator_risco * 20), 95)
                itens_alto_risco_local.append({
                    "codigo": cod,
                    "produto": item.produto,
                    "local": item.local_fisico,
                    "valor": valor,
                    "probabilidade_divergencia_pct": prob,
                    "motivo": f"Divergiu em {fator_risco} inventário(s) anterior(es)." if fator_risco > 0 else "Item de alto valor com histórico pendente."
                })

        itens_alto_risco_local = sorted(itens_alto_risco_local, key=lambda x: x["probabilidade_divergencia_pct"], reverse=True)[:15]

        # Estimar tempo e operadores
        est_tempo_minutos = max(30, int(total_itens_novos * 1.2)) # ~1.2 min por item
        operadores_sugeridos = max(1, int(total_itens_novos / 150) + 1)

        resultado_basico = {
            "sessao_codigo": sessao_atual.codigo,
            "total_itens_sessao": total_itens_novos,
            "historico_analisado": hist_stats,
            "itens_alto_risco": itens_alto_risco_local,
            "estimativas": {
                "duracao_estimada_minutos": est_tempo_minutos,
                "operadores_sugeridos": operadores_sugeridos,
                "tempo_por_item_segundos": 72,
            },
            "recomendacoes": [
                "Revisar o cadastro de itens recorrentemente divergentes antes do início.",
                f"Alocar pelo menos {operadores_sugeridos} operadores para cobrir a área estimada.",
                "Iniciar contagem com dupla verificação nos corredores de alto valor."
            ],
            "fonte": "basico"
        }

        # 3. Chamar Groq/Llama se disponível
        if not provider.disponivel:
            resultado_basico["mensagem_ia"] = "IA indisponível. Usando predição básica local."
            return resultado_basico

        prompt = f"""Você é um especialista em controle de estoque e auditoria.
Analise os dados da sessão atual de inventário e o histórico das sessões anteriores para fazer previsões preventivas e recomendações operacionais.

SESSÃO ATUAL:
- Código: {sessao_atual.codigo}
- Nome: {sessao_atual.nome}
- Total de Itens: {total_itens_novos}

HISTÓRICO DE SESSÕES ANTERIORES:
{hist_stats}

ITENS DA SESSÃO ATUAL COM MAIOR QUANTIDADE DE ERROS NO HISTÓRICO:
{itens_alto_risco_local[:10]}

Gere previsões preventivas e responda EXCLUSIVAMENTE em JSON válido com o seguinte formato:
{{
  "itens_alto_risco": [
    {{
      "codigo": "código do item",
      "produto": "nome do produto",
      "probabilidade_divergencia_pct": 85,
      "motivo": "justificativa baseada no histórico ou valor financeiro"
    }}
  ],
  "estimativas": {{
    "duracao_estimada_minutos": 120,
    "operadores_sugeridos": 3,
    "perda_financeira_esperada_reais": 450.00
  }},
  "recomendacoes": [
    "recomedação operacional específica para prevenir divergências"
  ]
}}
"""
        ia_data = provider.completar_json(prompt, max_tokens=1024)
        if ia_data:
            resultado_basico.update({
                "itens_alto_risco": ia_data.get("itens_alto_risco", itens_alto_risco_local),
                "estimativas": ia_data.get("estimativas", resultado_basico["estimativas"]),
                "recomendacoes": ia_data.get("recomendacoes", resultado_basico["recomendacoes"]),
                "fonte": "ia"
            })

        return resultado_basico
