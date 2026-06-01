"""AlertaAgent — detecção de anomalias em tempo real durante a contagem."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

_DIVERGENCIA_OPERADOR_PERC = 40   # alerta se operador tem >40% divergência (mínimo 5 contagens)
_DESVIO_ITEM_PERC = 100            # alerta se item tem >100% de desvio relativo
_MAX_RECONTAGENS = 3               # alerta se item foi contado mais de 3 vezes


class AlertaAgent:
    """
    Detecta anomalias durante a contagem (regras rápidas, sem IA).
    Chamado após cada registro para fornecer feedback em tempo real.
    """

    def analisar(
        self,
        codigo: str,
        quantidade_encontrada: int,
        quantidade_base: int,
        operador: str | None,
        contagens: list[dict],
    ) -> dict:
        alertas: list[dict] = []

        # 1. Desvio extremo no item atual
        if quantidade_base > 0:
            desvio_perc = abs(quantidade_encontrada - quantidade_base) / quantidade_base * 100
            if desvio_perc >= _DESVIO_ITEM_PERC:
                alertas.append({
                    "tipo": "desvio_extremo",
                    "severidade": "alto",
                    "mensagem": (
                        f"Desvio de {desvio_perc:.0f}% no item {codigo}. "
                        "Confirme a leitura e recontagem obrigatória."
                    ),
                })

        # 2. Item recontado muitas vezes na sessão
        recontagens = sum(1 for c in contagens if c.get("codigo") == codigo)
        if recontagens >= _MAX_RECONTAGENS:
            alertas.append({
                "tipo": "multiplas_recontagens",
                "severidade": "medio",
                "mensagem": (
                    f"Item {codigo} foi contado {recontagens} vezes. "
                    "Possível inconsistência — verifique o estoque físico."
                ),
            })

        # 3. Alta taxa de divergência do operador atual
        if operador:
            contagens_op = [c for c in contagens if c.get("operador") == operador]
            if len(contagens_op) >= 5:
                divs_op = sum(1 for c in contagens_op if c.get("divergencia"))
                taxa = divs_op / len(contagens_op) * 100
                if taxa >= _DIVERGENCIA_OPERADOR_PERC:
                    alertas.append({
                        "tipo": "operador_alta_divergencia",
                        "severidade": "medio",
                        "mensagem": (
                            f"Operador '{operador}' tem {taxa:.0f}% de divergência "
                            f"({divs_op}/{len(contagens_op)}). Verificar equipamento ou treinamento."
                        ),
                    })

        return {
            "alertas": alertas,
            "tem_alertas": len(alertas) > 0,
            "severidade_maxima": (
                "alto" if any(a["severidade"] == "alto" for a in alertas)
                else "medio" if alertas
                else "normal"
            ),
        }
