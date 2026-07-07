"""RelatorioExecutivoAgent — consolida todos os dados em um único relatório pronto para apresentação."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TOKENS = 2000


class RelatorioExecutivoAgent:
    """
    Gera relatório executivo consolidado combinando métricas de produtividade,
    impacto financeiro, ranking de operadores e divergências críticas.

    Elimina a necessidade de consultar 4 endpoints separados para montar uma apresentação.
    Com IA: gera narrativa executiva profissional.
    Sem IA: gera relatório estruturado com todos os dados.
    """

    def gerar(
        self,
        sessao: Any,
        stats: dict,
        metricas: dict,
        valor_estoque: dict | None,
        divergencias: list[dict],
    ) -> dict:
        from app.agents.provider import provider

        basico = self._relatorio_basico(sessao, stats, metricas, valor_estoque, divergencias)

        if not provider.disponivel:
            basico["fonte"] = "basico"
            return basico

        enriquecido = self._enriquecer_com_ia(provider, sessao, stats, metricas, valor_estoque, divergencias)
        if enriquecido:
            basico.update(enriquecido)
            basico["fonte"] = "ia"
        else:
            basico["fonte"] = "basico"

        return basico

    def _dur_str(self, dur_min: float) -> str:
        if dur_min >= 60:
            return f"{int(dur_min // 60)}h {int(dur_min % 60)}min"
        return f"{int(dur_min)}min"

    def _relatorio_basico(self, sessao, stats, metricas, valor_estoque, divergencias) -> dict:
        dur_str = self._dur_str(metricas.get("duracao_minutos", 0))

        impacto_financeiro = None
        if valor_estoque and valor_estoque.get("tem_dados_financeiros"):
            delta = valor_estoque["diferenca"]
            pct = valor_estoque["percentual_variacao"]
            impacto_financeiro = f"R$ {delta:+,.2f} ({pct:+.1f}%)"

        por_op = metricas.get("por_operador", [])
        ranking_ops = [
            {
                "operador": op["operador"],
                "contagens": op["contagens"],
                "itens_unicos": op["itens_unicos"],
                "itens_por_minuto": op.get("itens_por_minuto"),
                "duracao_minutos": op.get("duracao_minutos"),
            }
            for op in sorted(por_op, key=lambda x: x.get("contagens", 0), reverse=True)[:10]
        ]

        top_divs = sorted(
            [d for d in divergencias if d.get("diferenca") is not None],
            key=lambda x: abs(x.get("diferenca", 0)),
            reverse=True,
        )[:10]

        total = stats.get("total", 0)
        conferidos = stats.get("conferidos", 0)
        divs = stats.get("divergencias", 0)
        taxa_div = round(divs / conferidos * 100, 1) if conferidos > 0 else 0.0

        nivel_risco = "baixo"
        if taxa_div > 30:
            nivel_risco = "alto"
        elif taxa_div > 10:
            nivel_risco = "medio"

        recomendacoes = []
        if divs > 0:
            recomendacoes.append(f"Revisar os {divs} itens divergentes antes do fechamento do inventário.")
        if metricas.get("taxa_retrabalho_pct", 0) > 10:
            recomendacoes.append(
                f"Taxa de retrabalho de {metricas['taxa_retrabalho_pct']:.1f}% está elevada — "
                "considerar treinamento dos operadores ou revisão dos processos de contagem."
            )
        if metricas.get("pct_rastreabilidade", 100) < 90:
            recomendacoes.append(
                f"Rastreabilidade de {metricas['pct_rastreabilidade']:.1f}% abaixo do ideal — "
                "garantir que todos os operadores se identifiquem antes de contar."
            )
        if valor_estoque and valor_estoque.get("tem_dados_financeiros"):
            perdas = valor_estoque.get("maiores_perdas", [])
            if perdas:
                top_perda = perdas[0]
                recomendacoes.append(
                    f"Investigar item '{top_perda.get('produto', top_perda.get('codigo'))}' "
                    f"— maior perda financeira: R$ {top_perda.get('diferenca_valor', 0):,.2f}."
                )
        if not recomendacoes:
            recomendacoes.append("Inventário dentro dos parâmetros — nenhuma ação crítica necessária.")

        sumario = (
            f"Inventário '{getattr(sessao, 'nome', '')}' ({getattr(sessao, 'codigo', '')}) "
            f"concluído em {dur_str} com {conferidos}/{total} itens conferidos. "
            f"Taxa de divergência: {taxa_div:.1f}%."
        )
        if impacto_financeiro:
            sumario += f" Impacto financeiro: {impacto_financeiro}."

        return {
            "titulo": f"Relatório Executivo — {getattr(sessao, 'codigo', '')} — {getattr(sessao, 'nome', '')}",
            "sumario_executivo": sumario,
            "kpis_destaque": {
                "duracao": dur_str,
                "itens_por_minuto": metricas.get("itens_por_minuto"),
                "taxa_divergencia_pct": taxa_div,
                "taxa_retrabalho_pct": metricas.get("taxa_retrabalho_pct"),
                "rastreabilidade_pct": metricas.get("pct_rastreabilidade"),
                "total_itens": total,
                "itens_conferidos": conferidos,
                "divergencias_absolutas": divs,
                "total_tentativas": metricas.get("total_tentativas_historico"),
                "impacto_financeiro": impacto_financeiro,
            },
            "ranking_operadores": ranking_ops,
            "itens_criticos": [
                {
                    "codigo": d.get("codigo"),
                    "produto": d.get("produto"),
                    "local": d.get("local_fisico"),
                    "base": d.get("quantidade_base"),
                    "encontrado": d.get("quantidade_encontrada"),
                    "diferenca": d.get("diferenca"),
                    "diferenca_valor": d.get("diferenca_valor"),
                }
                for d in top_divs
            ],
            "recomendacoes": recomendacoes,
            "risco_geral": nivel_risco,
            "conclusao_executiva": sumario,
        }

    def _enriquecer_com_ia(self, provider, sessao, stats, metricas, valor_estoque, divergencias) -> dict | None:
        por_op = metricas.get("por_operador", [])[:5]
        top_divs = sorted(
            [d for d in divergencias if d.get("diferenca") is not None],
            key=lambda x: abs(x.get("diferenca", 0)),
            reverse=True,
        )[:15]

        dur_str = self._dur_str(metricas.get("duracao_minutos", 0))

        bloco_financeiro = ""
        if valor_estoque and valor_estoque.get("tem_dados_financeiros"):
            vi = valor_estoque["valor_inicial"]
            vf = valor_estoque["valor_final"]
            delta = valor_estoque["diferenca"]
            pct = valor_estoque["percentual_variacao"]
            perdas = valor_estoque.get("maiores_perdas", [])[:3]
            bloco_financeiro = f"""
IMPACTO FINANCEIRO:
- Valor inicial: R$ {vi:,.2f} → Valor apurado: R$ {vf:,.2f}
- Variação: R$ {delta:+,.2f} ({pct:+.2f}%)
- Maiores perdas: {json.dumps(perdas, ensure_ascii=False)}"""

        prompt = f"""Você é um analista sênior de inventário. Gere um relatório executivo em português para apresentação gerencial.

SESSÃO: {getattr(sessao, 'nome', 'N/A')} ({getattr(sessao, 'codigo', 'N/A')})

MÉTRICAS DE PRODUTIVIDADE:
- Duração: {dur_str}
- Itens/min (ritmo médio): {metricas.get('itens_por_minuto', 0):.2f}
- Total de tentativas: {metricas.get('total_tentativas_historico', 0)}
- Taxa divergência: {metricas.get('taxa_divergencia_pct', 0):.1f}%
- Taxa retrabalho: {metricas.get('taxa_retrabalho_pct', 0):.1f}%
- Rastreabilidade: {metricas.get('pct_rastreabilidade', 0):.1f}%
{bloco_financeiro}

OPERADORES:
{json.dumps(por_op, ensure_ascii=False, indent=2)}

TOP DIVERGÊNCIAS:
{json.dumps(top_divs, ensure_ascii=False, indent=2)}

Gere SOMENTE o JSON abaixo (sem texto adicional):
{{
  "sumario_executivo": "3-4 frases executivas: resultado geral, produtividade, impacto financeiro se houver",
  "padroes_identificados": ["padrão por local ou operador ou categoria"],
  "recomendacoes": ["ação concreta e mensurável para o gestor"],
  "risco_geral": "baixo|medio|alto",
  "conclusao_executiva": "2-3 frases impactantes para o slide final da apresentação"
}}"""

        return provider.completar_json(prompt, max_tokens=_MAX_TOKENS)
