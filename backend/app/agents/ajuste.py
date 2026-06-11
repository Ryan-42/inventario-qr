"""RecomendacaoAjusteAgent — recomendação inteligente de Para Ajuste para supervisores."""
from __future__ import annotations

import logging
from collections import Counter

logger = logging.getLogger(__name__)

_VALOR_ALTO_THRESHOLD = 5_000.0  # R$ — exige consenso mais rigoroso
_CONSENSO_MINIMO = 2              # operadores distintos em consenso para recomendar ajuste


class RecomendacaoAjusteAgent:
    """
    Analisa o histórico de contagem de itens divergentes e recomenda a ação correta.

    Para cada item retorna:
      "ajustar"     — consenso suficiente, pode fechar como Para Ajuste
      "recontar"    — poucas leituras ou sem consenso, recontagem independente
      "investigar"  — leituras muito inconsistentes ou item de alto valor — presença do supervisor
    """

    def recomendar(self, itens_historico: list[dict]) -> list[dict]:
        """
        itens_historico: lista de dicts com:
          {
            "codigo": str,
            "produto": str,
            "quantidade_base": int,
            "valor_estoque": float | None,
            "historico": [
              {"quantidade": int, "operador": str | None, "rodada": int, "timestamp": str | None}
            ],
            "rodada_atual": int,
          }
        """
        return [self._analisar_item(item) for item in itens_historico]

    def _analisar_item(self, item: dict) -> dict:
        codigo = item["codigo"]
        produto = item.get("produto", "")
        qtd_base = item.get("quantidade_base", 0)
        valor = float(item.get("valor_estoque") or 0.0)
        historico = item.get("historico", [])
        rodada = item.get("rodada_atual", 1)

        if not historico:
            return {
                "codigo": codigo,
                "produto": produto,
                "recomendacao": "recontar",
                "confianca": "baixa",
                "justificativa": "Nenhuma contagem registrada ainda.",
                "quantidade_sugerida": None,
                "historico_resumido": {"total_registros": 0},
            }

        quantidades = [h["quantidade"] for h in historico if h.get("quantidade") is not None]
        operadores = [h.get("operador") or "(sem operador)" for h in historico]
        qtd_op = list(zip(operadores, quantidades))

        contagem_qtds = Counter(quantidades)
        qtd_mais_votada, votos = contagem_qtds.most_common(1)[0]
        ops_em_consenso = len({op for op, qtd in qtd_op if qtd == qtd_mais_votada})
        total_ops = len(set(operadores))
        alto_valor = valor >= _VALOR_ALTO_THRESHOLD

        if qtd_base > 0:
            desvio = abs(qtd_mais_votada - qtd_base) / qtd_base * 100
        else:
            desvio = 0.0 if qtd_mais_votada == 0 else 100.0

        # --- Regras de decisão ---
        if len(set(quantidades)) == 1 and total_ops >= _CONSENSO_MINIMO:
            recomendacao, confianca = "ajustar", "alta"
            justificativa = (
                f"Consenso total: todos os {len(historico)} registros de {total_ops} operador(es) "
                f"apontam {qtd_mais_votada} unidades."
            )
        elif ops_em_consenso >= _CONSENSO_MINIMO and desvio <= 15:
            recomendacao, confianca = "ajustar", "media"
            justificativa = (
                f"{ops_em_consenso}/{total_ops} operador(es) concordam em {qtd_mais_votada} "
                f"(desvio de {desvio:.1f}% vs. base). Ajuste recomendado com revisão."
            )
        elif alto_valor and desvio > 20:
            recomendacao, confianca = "investigar", "alta"
            justificativa = (
                f"Item de alto valor (R$ {valor:,.2f}) com desvio de {desvio:.1f}% e leituras "
                f"divergentes: {sorted(set(quantidades))}. Contagem presencial obrigatória."
            )
        elif len(set(quantidades)) > 2 or (rodada >= 3 and len(set(quantidades)) > 1):
            recomendacao, confianca = "investigar", "media"
            justificativa = (
                f"Leituras inconsistentes após {rodada} rodada(s): {sorted(set(quantidades))} unid. "
                "Verificação física com supervisor recomendada."
            )
        else:
            recomendacao, confianca = "recontar", "media"
            justificativa = (
                f"Apenas {total_ops} operador(es), sem consenso claro "
                f"(leituras: {sorted(set(quantidades))}). Nova contagem independente recomendada."
            )

        if alto_valor and recomendacao == "ajustar":
            justificativa += f" ⚠ Item de alto valor (R$ {valor:,.2f}) — confirmar com supervisor."

        return {
            "codigo": codigo,
            "produto": produto,
            "quantidade_base": qtd_base,
            "quantidade_sugerida": qtd_mais_votada if recomendacao == "ajustar" else None,
            "recomendacao": recomendacao,
            "confianca": confianca,
            "justificativa": justificativa,
            "rodada_atual": rodada,
            "historico_resumido": {
                "total_registros": len(historico),
                "operadores_distintos": total_ops,
                "quantidades_registradas": sorted(set(quantidades)),
                "quantidade_mais_votada": qtd_mais_votada,
                "votos_por_quantidade": dict(contagem_qtds.most_common()),
            },
            "alto_valor": alto_valor,
            "valor_estoque": valor if valor > 0 else None,
        }
