"""AntiFraudeAgent — auditoria comportamental e detecção de fraudes no inventário.

Analisa intervalos de tempo e padrões de contagem dos operadores para identificar
ghost counting, velocidade impossível e transições geográficas inválidas.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


class AntiFraudeAgent:
    """Detecta anomalias de contagem, velocidade impossível e digitação em massa (ghost counting)."""

    def auditar(self, sessao_id: str, db) -> dict:
        from app.models.contagem import HistoricoContagem
        from app.models.item_base import ItemBase
        from app.agents.provider import provider

        historico = (
            db.query(HistoricoContagem)
            .filter(HistoricoContagem.sessao_id == sessao_id)
            .order_by(HistoricoContagem.operador, HistoricoContagem.timestamp)
            .all()
        )

        itens_map = {
            i.codigo: i
            for i in db.query(ItemBase).filter(ItemBase.sessao_id == sessao_id).all()
        }

        # Organizar por operador
        op_logs: dict[str, list] = {}
        for h in historico:
            op = h.operador or "Desconhecido"
            op_logs.setdefault(op, []).append(h)

        anomalias: list[dict] = []
        resumo_operadores: dict[str, dict] = {}

        for op, logs in op_logs.items():
            total_contagem = len(logs)
            if total_contagem < 3:
                continue

            copia_exata_base = 0
            intervalos_curtos = 0
            geografia_invalida = 0

            for idx in range(1, len(logs)):
                prev_log = logs[idx - 1]
                curr_log = logs[idx]

                # Cópia exata (quantidade encontrada == quantidade base)
                if curr_log.quantidade_encontrada == curr_log.quantidade_base:
                    copia_exata_base += 1

                if prev_log.timestamp and curr_log.timestamp:
                    diff_seg = (curr_log.timestamp - prev_log.timestamp).total_seconds()

                    # Intervalo < 4s: ritmo impossível para contagem real
                    if 0 < diff_seg < 4.0:
                        intervalos_curtos += 1

                    # Transição de setor em < 10s: fisicamente impossível
                    item_prev = itens_map.get(prev_log.codigo)
                    item_curr = itens_map.get(curr_log.codigo)
                    if (
                        item_prev and item_curr
                        and item_prev.local_fisico != item_curr.local_fisico
                        and diff_seg < 10.0
                        and item_prev.local_fisico and item_curr.local_fisico
                    ):
                        geografia_invalida += 1

            taxa_copia = round(copia_exata_base / total_contagem * 100, 1)
            taxa_velocidade_anormal = round(intervalos_curtos / total_contagem * 100, 1)

            resumo_operadores[op] = {
                "total_contagens": total_contagem,
                "taxa_acerto_exato_pct": taxa_copia,
                "scans_ultra_rapidos": intervalos_curtos,
                "mudancas_setor_impossiveis": geografia_invalida,
                "status_risco": "normal",
            }

            if taxa_copia > 90.0 and total_contagem >= 10 and taxa_velocidade_anormal > 30.0:
                resumo_operadores[op]["status_risco"] = "alto"
                anomalias.append({
                    "operador": op,
                    "tipo": "ghost_counting",
                    "descricao": (
                        f"Operador '{op}' apresenta 90%+ de acerto exato e tempo ultra-rápido. "
                        "Fortes indícios de clique em OK sem contagem física."
                    ),
                    "score_risco": 90,
                })
            elif intervalos_curtos > (total_contagem * 0.4):
                resumo_operadores[op]["status_risco"] = "medio"
                anomalias.append({
                    "operador": op,
                    "tipo": "velocidade_incompativel",
                    "descricao": (
                        f"Operador '{op}' registrou contagens consecutivas em velocidade "
                        "incompatível com movimentação humana."
                    ),
                    "score_risco": 65,
                })
            elif geografia_invalida > 0:
                resumo_operadores[op]["status_risco"] = "medio"
                anomalias.append({
                    "operador": op,
                    "tipo": "geografia_invalida",
                    "descricao": f"Mudanças físicas de setor em menos de 10s pelo operador '{op}'.",
                    "score_risco": 50,
                })

        resultado_basico = {
            "total_operadores_analisados": len(resumo_operadores),
            "resumo_operadores": resumo_operadores,
            "anomalias_detectadas": anomalias,
            "risco_geral": (
                "alto" if any(a["score_risco"] >= 80 for a in anomalias)
                else "medio" if anomalias
                else "baixo"
            ),
            "fonte": "basico",
        }

        if not provider.disponivel:
            resultado_basico["mensagem_ia"] = "IA indisponível. Usando auditoria comportamental por regras locais."
            return resultado_basico

        if not anomalias:
            return resultado_basico

        # Anonimiza nomes de operadores antes de enviar à IA (LGPD)
        op_map = {op: f"Operador {i+1}" for i, op in enumerate(resumo_operadores)}
        resumo_anonimizado = {op_map[k]: v for k, v in resumo_operadores.items()}
        anomalias_anonimizadas = [
            {**a, "operador": op_map.get(a.get("operador", ""), a.get("operador", ""))}
            for a in anomalias
        ]

        prompt = f"""Você é um auditor interno de prevenção de perdas de uma grande empresa de logística.
Analise a telemetria comportamental de contagem dos operadores abaixo e escreva um parecer detalhado sobre possíveis fraudes ou comportamentos inadequados.
Os nomes de operadores foram anonimizados (Operador 1, Operador 2, etc.) por privacidade.

DADOS DE TELEMETRIA POR OPERADOR:
{json.dumps(resumo_anonimizado, ensure_ascii=False, indent=2)}

ANOMALIAS DETECTADAS PELO SISTEMA:
{json.dumps(anomalias_anonimizadas, ensure_ascii=False, indent=2)}

Responda EXCLUSIVAMENTE em JSON válido com a seguinte estrutura:
{{
  "parecer_auditoria": "parágrafo formal descrevendo a situação geral dos operadores, riscos de fraude e integridade do inventário.",
  "operadores_investigar": [
    {{
      "operador": "nome do operador",
      "gravidade": "alta|media",
      "motivo": "resumo dos comportamentos suspeitos"
    }}
  ],
  "acoes_preventivas": [
    "medida de controle a ser tomada pelo supervisor de TI ou do depósito"
  ]
}}
"""
        ia_data = provider.completar_json(prompt, max_tokens=1024)
        if ia_data:
            resultado_basico.update({
                "parecer_auditoria": ia_data.get("parecer_auditoria"),
                "operadores_investigar": ia_data.get("operadores_investigar"),
                "acoes_preventivas": ia_data.get("acoes_preventivas"),
                "fonte": "ia",
            })

        return resultado_basico
