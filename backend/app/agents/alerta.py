"""AlertaAgent — detecção de anomalias em tempo real durante a contagem."""
from __future__ import annotations
import logging

logger = logging.getLogger(__name__)

_DIVERGENCIA_OPERADOR_PERC = 40   # alerta se operador tem >40% divergência (mínimo 5 contagens)
_DESVIO_ITEM_PERC = 100            # alerta se item tem >100% de desvio relativo
_MAX_RECONTAGENS = 3               # alerta se item foi contado mais de 3 vezes
_LOCAL_DIVERGENCIA_PERC = 50       # alerta se local físico tem >50% divergência (mínimo 5 itens)
_VALOR_ALTO_THRESHOLD = 5_000.0    # R$5.000 — escalada para "critico" se item alto valor diverge muito


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
        valor_estoque_item: float | None = None,
        local_fisico_item: str | None = None,
    ) -> dict:
        alertas: list[dict] = []

        # 1. Item com quantidade_base == 0 na base de dados
        if quantidade_base == 0:
            alertas.append({
                "tipo": "quantidade_base_zero",
                "severidade": "medio",
                "mensagem": (
                    f"Item {codigo} tem quantidade base igual a zero na planilha. "
                    "Verifique se o item deveria constar no inventário."
                ),
            })

        # 2. Desvio extremo no item atual
        if quantidade_base > 0:
            desvio_perc = abs(quantidade_encontrada - quantidade_base) / quantidade_base * 100
            if desvio_perc >= _DESVIO_ITEM_PERC:
                # Escalada: item de alto valor com desvio extremo = crítico
                if valor_estoque_item and valor_estoque_item >= _VALOR_ALTO_THRESHOLD:
                    alertas.append({
                        "tipo": "item_alto_valor_divergente",
                        "severidade": "critico",
                        "mensagem": (
                            f"CRÍTICO: item {codigo} (R$ {valor_estoque_item:,.2f}) com desvio de "
                            f"{desvio_perc:.0f}%. Parar e recontar com supervisor presente."
                        ),
                    })
                else:
                    alertas.append({
                        "tipo": "desvio_extremo",
                        "severidade": "alto",
                        "mensagem": (
                            f"Desvio de {desvio_perc:.0f}% no item {codigo}. "
                            "Confirme a leitura e recontagem obrigatória."
                        ),
                    })

        # 3. Item recontado muitas vezes na sessão
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

        # 4. Alta taxa de divergência do operador atual
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

        # 5. Local físico com alta concentração de divergências
        if local_fisico_item:
            contagens_local = [c for c in contagens if c.get("local_fisico") == local_fisico_item]
            if len(contagens_local) >= 5:
                divs_local = sum(1 for c in contagens_local if c.get("divergencia"))
                taxa_local = divs_local / len(contagens_local) * 100
                if taxa_local >= _LOCAL_DIVERGENCIA_PERC:
                    alertas.append({
                        "tipo": "local_critico",
                        "severidade": "alto",
                        "mensagem": (
                            f"Local '{local_fisico_item}' tem {taxa_local:.0f}% de divergência "
                            f"({divs_local}/{len(contagens_local)} itens). "
                            "Possível problema sistêmico — revisar toda a área."
                        ),
                    })

        severidades = {a["severidade"] for a in alertas}
        severidade_maxima = (
            "critico" if "critico" in severidades
            else "alto" if "alto" in severidades
            else "medio" if "medio" in severidades
            else "normal"
        )

        return {
            "alertas": alertas,
            "tem_alertas": len(alertas) > 0,
            "severidade_maxima": severidade_maxima,
        }
