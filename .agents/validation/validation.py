from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

_SAMPLE_SIZE = 30
_MAX_TOKENS = 512


class ValidationAgent:
    """
    Valida dados de planilha antes do import.

    Realiza sempre uma validação básica (sem IA).
    Se um provider de IA estiver configurado (Groq ou Anthropic),
    enriquece o resultado com análise adicional.
    """

    def validate(self, items: list[dict]) -> dict:
        from app.agents.provider import provider

        resultado = self._validacao_basica(items)

        if provider.disponivel and items:
            resultado = self._enriquecer_com_ia(provider, resultado, items)

        return resultado

    # ------------------------------------------------------------------
    # Validação básica (sem IA)
    # ------------------------------------------------------------------

    def _validacao_basica(self, items: list[dict]) -> dict:
        problemas: list[dict] = []
        avisos: list[dict] = []
        codigos_vistos: set[str] = set()

        for i, item in enumerate(items):
            linha = i + 2
            codigo = item.get("codigo")
            produto = item.get("produto")
            qty = item.get("quantidade", 0)

            if not codigo:
                problemas.append({"linha": linha, "tipo": "codigo_vazio", "descricao": "Código em branco"})
            else:
                if codigo in codigos_vistos:
                    avisos.append({"linha": linha, "tipo": "duplicata", "descricao": f"Código '{codigo}' duplicado"})
                codigos_vistos.add(codigo)

            if not produto:
                avisos.append({"linha": linha, "tipo": "produto_vazio", "descricao": "Nome do produto em branco"})

            try:
                qty_num = int(qty) if qty is not None else 0
            except (TypeError, ValueError):
                problemas.append({"linha": linha, "tipo": "quantidade_invalida", "descricao": f"Quantidade '{qty}' não é um número inteiro válido"})
                qty_num = None

            if qty_num is not None:
                if qty_num < 0:
                    problemas.append({"linha": linha, "tipo": "quantidade_negativa", "descricao": f"Quantidade {qty_num} inválida"})
                elif qty_num == 0:
                    avisos.append({"linha": linha, "tipo": "quantidade_zero", "descricao": "Quantidade zero pode ser erro"})

        total_invalidos = len(problemas)
        total_validos = len(items) - total_invalidos

        return {
            "valido": total_invalidos == 0,
            "pode_importar_com_avisos": total_invalidos == 0,
            "problemas": problemas,
            "avisos": avisos,
            "total_validos": total_validos,
            "total_invalidos": total_invalidos,
            "fonte": "basico",
            "confianca": 1.0,
        }

    # ------------------------------------------------------------------
    # Enriquecimento com IA
    # ------------------------------------------------------------------

    def _enriquecer_com_ia(self, provider, resultado_basico: dict, items: list[dict]) -> dict:
        sample = items[: _SAMPLE_SIZE]
        prompt = (
            f"Analise estes {len(items)} itens de inventário "
            f"(mostrando primeiros {len(sample)}):\n"
            f"{json.dumps(sample, ensure_ascii=False, indent=2)}\n\n"
            "Identifique problemas adicionais: códigos com formato inconsistente, "
            "nomes de produtos suspeitos, padrões anômalos, quantidades implausíveis.\n\n"
            "Responda SOMENTE em JSON válido (sem texto extra):\n"
            '{"insights": ["string"], "risco_geral": "baixo|medio|alto", "recomendacoes": ["string"]}'
        )

        ia_data = provider.completar_json(prompt, max_tokens=_MAX_TOKENS)
        if ia_data:
            resultado_basico.update({
                "fonte": "ia",
                "insights": ia_data.get("insights", []),
                "risco_geral": ia_data.get("risco_geral", "baixo"),
                "recomendacoes": ia_data.get("recomendacoes", []),
            })
        else:
            logger.warning("ValidationAgent: falha na análise IA — mantendo resultado básico")

        return resultado_basico
