"""
AnaliseAgent — análise de inventário pós-sessão via IA.

Recebe os dados de uma sessão concluída/ativa e retorna insights acionáveis:
padrões de divergência, itens críticos, recomendações, resumo executivo e análise de operadores.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TOKENS = 2000
_MAX_DIVERGENCIAS_PROMPT = 50


class AnaliseAgent:
    """Analisa dados de inventário e gera insights com IA."""

    def analisar(
        self,
        sessao: Any,
        stats: dict,
        divergencias: list[dict],
        itens_sample: list[dict],
        valor_estoque: dict | None = None,
        metricas: dict | None = None,
    ) -> dict:
        from app.agents.provider import provider

        basico = self._analise_basica(stats, divergencias, itens_sample, valor_estoque, metricas)

        if not provider.disponivel:
            basico["fonte"] = "basico"
            basico["mensagem_ia"] = (
                "Configure GROQ_API_KEY no .env para obter análise detalhada com IA. "
                "Chave gratuita em: https://console.groq.com"
            )
            return basico

        ia_data = self._analisar_com_ia(provider, sessao, stats, divergencias, itens_sample, valor_estoque, metricas)
        if ia_data:
            basico.update(ia_data)
            basico["fonte"] = "ia"
        else:
            basico["fonte"] = "basico"

        return basico

    # ------------------------------------------------------------------
    # Análise básica (sem IA) — mais rica que antes
    # ------------------------------------------------------------------

    def _analise_basica(
        self,
        stats: dict,
        divergencias: list[dict],
        itens_sample: list[dict],
        valor_estoque: dict | None = None,
        metricas: dict | None = None,
    ) -> dict:
        total = stats.get("total", 0)
        conferidos = stats.get("conferidos", 0)
        divs = stats.get("divergencias", 0)
        percentual = stats.get("percentual", 0.0)

        taxa_divergencia = round(divs / conferidos * 100, 1) if conferidos > 0 else 0.0

        # Itens com maior desvio absoluto
        itens_criticos = sorted(
            [d for d in divergencias if d.get("diferenca") is not None],
            key=lambda x: abs(x.get("diferenca", 0)),
            reverse=True,
        )[:5]

        # Nível de risco
        if taxa_divergencia > 30:
            nivel_risco = "alto"
        elif taxa_divergencia > 10:
            nivel_risco = "medio"
        else:
            nivel_risco = "baixo"

        padroes: list[str] = []

        # Padrão: concentração por local físico
        locais: Counter = Counter()
        for d in divergencias:
            loc = d.get("local_fisico") or "Sem localização"
            locais[loc] += 1
        if locais and divs > 0:
            top_local, top_count = locais.most_common(1)[0]
            pct_local = round(top_count / divs * 100, 0)
            if pct_local >= 30:
                padroes.append(f"{top_local} concentra {pct_local:.0f}% das divergências ({top_count} itens)")

        # Padrão: itens com diferença positiva vs negativa
        positivos = sum(1 for d in divergencias if (d.get("diferenca") or 0) > 0)
        negativos = sum(1 for d in divergencias if (d.get("diferenca") or 0) < 0)
        if positivos > 0 and negativos > 0:
            padroes.append(
                f"{positivos} iten(s) com excesso e {negativos} com falta — possível erro de localização ou troca entre itens"
            )
        elif negativos > positivos and divs > 2:
            padroes.append(f"Predominância de faltas ({negativos}/{divs}) — verificar possível desvio ou furto")
        elif positivos > negativos and divs > 2:
            padroes.append(f"Predominância de excessos ({positivos}/{divs}) — verificar itens duplicados ou alocação errada")

        # Padrão: operadores com divergência alta
        ops_div: Counter = Counter()
        for d in divergencias:
            op = d.get("operador") or "Sem operador"
            ops_div[op] += 1
        if ops_div and divs > 3:
            op_top, op_count = ops_div.most_common(1)[0]
            op_pct = round(op_count / divs * 100, 0)
            if op_pct >= 40:
                padroes.append(f"Operador '{op_top}' registrou {op_pct:.0f}% das divergências — revisar treinamento")

        # Resumo financeiro básico
        resumo_financeiro = ""
        if valor_estoque and valor_estoque.get("tem_dados_financeiros"):
            vi = valor_estoque["valor_inicial"]
            vf = valor_estoque["valor_final"]
            pct_var = valor_estoque["percentual_variacao"]
            sinal = "+" if pct_var >= 0 else ""
            resumo_financeiro = (
                f" Impacto financeiro: de R$ {vi:,.2f} para R$ {vf:,.2f} ({sinal}{pct_var:.1f}%)."
            )

        # Métricas de produtividade
        metricas_resumo: dict = {}
        if metricas:
            dur = metricas.get("duracao_minutos", 0)
            dur_str = f"{int(dur // 60)}h {int(dur % 60)}min" if dur >= 60 else f"{int(dur)}min"
            metricas_resumo = {
                "duracao": dur_str,
                "itens_por_minuto": metricas.get("itens_por_minuto"),
                "taxa_retrabalho_pct": metricas.get("taxa_retrabalho_pct"),
                "rastreabilidade_pct": metricas.get("pct_rastreabilidade"),
            }
            if metricas.get("taxa_retrabalho_pct", 0) > 10:
                padroes.append(
                    f"Retrabalho elevado: {metricas['taxa_retrabalho_pct']:.1f}% dos itens precisaram de recontagem"
                )
            if metricas.get("pct_rastreabilidade", 100) < 90:
                padroes.append(
                    f"Rastreabilidade baixa: {metricas['pct_rastreabilidade']:.1f}% das contagens têm operador identificado"
                )

        # Recomendações baseadas nos dados
        recomendacoes: list[str] = []
        if divs > 0:
            recomendacoes.append(
                f"Recontar os {len(itens_criticos)} itens com maior desvio para confirmar valores antes de fechar o estoque."
            )
            if negativos > positivos:
                recomendacoes.append(
                    "Investigar possível desvio: a maioria das divergências é por falta. Verifique registros de saída recentes."
                )
            if locais and divs > 0:
                top_l = locais.most_common(1)[0][0]
                recomendacoes.append(f"Priorizar revisão do local '{top_l}' que concentra a maior parte das divergências.")
        else:
            recomendacoes.append("Inventário sem divergências — estoque alinhado com a planilha base.")

        if total > 0 and conferidos < total:
            recomendacoes.append(
                f"Há {total - conferidos} iten(s) ainda não contados. Complete a contagem antes de concluir a sessão."
            )

        return {
            "resumo": (
                f"{conferidos}/{total} itens conferidos ({percentual:.1f}% de progresso). "
                f"{divs} divergência(s) encontrada(s) ({taxa_divergencia:.1f}% dos itens conferidos)."
                f"{resumo_financeiro}"
            ),
            "metricas_produtividade": metricas_resumo,
            "padroes": padroes,
            "itens_criticos": [
                {
                    "codigo": item.get("codigo", ""),
                    "produto": item.get("produto", ""),
                    "diferenca": item.get("diferenca", 0),
                    "motivo": "Maior desvio absoluto entre base e encontrado",
                }
                for item in itens_criticos
            ],
            "recomendacoes": recomendacoes,
            "risco_geral": nivel_risco,
            "taxa_divergencia": taxa_divergencia,
            "valor_estoque": valor_estoque,
            "analise_operadores": self._analise_operadores(divergencias, itens_sample),
        }

    def _analise_operadores(self, divergencias: list[dict], itens: list[dict]) -> list[dict]:
        """Retorna ranking de operadores por taxa de divergência."""
        total_por_op: Counter = Counter()
        div_por_op: Counter = Counter()

        for item in itens:
            op = item.get("operador") or "Sem operador"
            total_por_op[op] += 1

        for d in divergencias:
            op = d.get("operador") or "Sem operador"
            div_por_op[op] += 1

        resultado = []
        for op, total in total_por_op.most_common():
            divs_op = div_por_op.get(op, 0)
            taxa = round(divs_op / total * 100, 1) if total > 0 else 0.0
            resultado.append({
                "operador": op,
                "total_itens": total,
                "divergencias": divs_op,
                "taxa_divergencia_pct": taxa,
            })
        return sorted(resultado, key=lambda x: x["taxa_divergencia_pct"], reverse=True)

    # ------------------------------------------------------------------
    # Análise com IA — prompt enriquecido
    # ------------------------------------------------------------------

    def _analisar_com_ia(
        self,
        provider,
        sessao: Any,
        stats: dict,
        divergencias: list[dict],
        itens_sample: list[dict],
        valor_estoque: dict | None = None,
        metricas: dict | None = None,
    ) -> dict | None:
        divs_limitadas = divergencias[:_MAX_DIVERGENCIAS_PROMPT]

        def _serializable(obj):
            from datetime import datetime, date
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            raise TypeError(f"Not serializable: {type(obj)}")

        # Bloco financeiro
        bloco_financeiro = ""
        if valor_estoque and valor_estoque.get("tem_dados_financeiros"):
            vi = valor_estoque["valor_inicial"]
            vf = valor_estoque["valor_final"]
            delta = valor_estoque["diferenca"]
            pct = valor_estoque["percentual_variacao"]
            perdas = valor_estoque.get("maiores_perdas", [])[:3]
            ganhos = valor_estoque.get("maiores_ganhos", [])[:3]
            bloco_financeiro = f"""
IMPACTO FINANCEIRO:
- Valor inicial do estoque: R$ {vi:,.2f}
- Valor final apurado: R$ {vf:,.2f}
- Diferença total: R$ {delta:,.2f} ({pct:+.2f}%)
- Maiores perdas (top 3): {json.dumps(perdas, ensure_ascii=False)}
- Maiores ganhos (top 3): {json.dumps(ganhos, ensure_ascii=False)}
"""

        # Bloco de locais físicos
        locais: Counter = Counter()
        for d in divs_limitadas:
            loc = d.get("local_fisico") or "Sem localização"
            locais[loc] += 1
        bloco_locais = ""
        if locais:
            top_locais = locais.most_common(5)
            bloco_locais = f"\nDIVERGÊNCIAS POR LOCAL: {json.dumps(dict(top_locais), ensure_ascii=False)}"

        # Bloco de operadores
        ops_div: Counter = Counter()
        for d in divs_limitadas:
            op = d.get("operador") or "Sem operador"
            ops_div[op] += 1
        bloco_ops = ""
        if ops_div:
            bloco_ops = f"\nDIVERGÊNCIAS POR OPERADOR: {json.dumps(dict(ops_div.most_common(5)), ensure_ascii=False)}"

        # Bloco de métricas
        bloco_metricas = ""
        if metricas:
            dur = metricas.get("duracao_minutos", 0)
            dur_str = f"{int(dur // 60)}h {int(dur % 60)}min" if dur >= 60 else f"{int(dur)}min"
            por_op = metricas.get("por_operador", [])[:5]
            ops_str = "; ".join(
                f"{o['operador']} ({o['contagens']} itens, {o.get('itens_por_minuto') or 0:.1f}/min)"
                for o in por_op
            )
            bloco_metricas = f"""
MÉTRICAS DE PRODUTIVIDADE:
- Duração total: {dur_str}
- Ritmo médio: {metricas.get('itens_por_minuto', 0):.2f} itens/min
- Taxa de retrabalho: {metricas.get('taxa_retrabalho_pct', 0):.1f}% ({metricas.get('retrabalho_absoluto', 0)} recontagens extras)
- Rastreabilidade: {metricas.get('pct_rastreabilidade', 0):.1f}% das contagens com operador identificado
- Performance por operador: {ops_str or 'nenhum'}
"""

        # Análise de positivos vs negativos
        positivos = sum(1 for d in divs_limitadas if (d.get("diferenca") or 0) > 0)
        negativos = sum(1 for d in divs_limitadas if (d.get("diferenca") or 0) < 0)

        prompt = f"""Você é um especialista sênior em gestão de inventário, controle de estoque e auditoria fiscal.
Analise os dados desta sessão de inventário e forneça insights profundos e acionáveis em português para apresentação ao gestor da TI e liderança da empresa.

DADOS DA SESSÃO:
- Nome: {getattr(sessao, 'nome', 'N/A')}
- Código: {getattr(sessao, 'codigo', 'N/A')}
- Total de itens: {stats.get('total', 0)}
- Itens conferidos: {stats.get('conferidos', 0)}
- Itens pendentes: {stats.get('pendentes', 0)}
- Divergências totais: {stats.get('divergencias', 0)}
- Progresso: {stats.get('percentual', 0):.1f}%
- Divergências com FALTA: {negativos}
- Divergências com EXCESSO: {positivos}
{bloco_metricas}{bloco_financeiro}{bloco_locais}{bloco_ops}

ITENS COM DIVERGÊNCIA ({len(divergencias)} total, mostrando {len(divs_limitadas)}):
{json.dumps(divs_limitadas, ensure_ascii=False, indent=2, default=_serializable)}

AMOSTRA DE TODOS OS ITENS (primeiros {min(20, len(itens_sample))}):
{json.dumps(itens_sample[:20], ensure_ascii=False, default=_serializable)}

Analise e identifique (seja específico e use os dados reais fornecidos):
1. Padrões por local físico, por operador e por tipo de divergência (falta vs excesso)
2. Impacto financeiro detalhado se dados disponíveis
3. Causas prováveis das divergências (erro de contagem, desvio, itens trocados, planilha desatualizada)
4. Itens que precisam de atenção imediata com justificativa financeira ou operacional
5. Recomendações práticas e específicas para corrigir o estoque e prevenir recorrência
6. Avaliação da qualidade do processo de inventário (completude, rastreabilidade, retrabalho)

Responda SOMENTE em JSON válido com esta estrutura exata:
{{
  "resumo": "parágrafo executivo de 3-4 frases com impacto financeiro e principais achados",
  "relatorio_executivo": "texto narrativo de 4-6 frases para apresentação gerencial — inclua contexto, achados e próximos passos",
  "padroes": [
    "padrão específico identificado nos dados com números concretos",
    "outro padrão — seja específico, não genérico"
  ],
  "causas_provaveis": [
    "causa provável baseada nos dados — ex: 'Concentração no Depósito A sugere...'"
  ],
  "itens_criticos": [
    {{"codigo": "...", "produto": "...", "diferenca": 0, "diferenca_valor": 0.0, "motivo": "justificativa específica", "prioridade": "alta|media|baixa"}}
  ],
  "recomendacoes": [
    "ação concreta e específica — com prazo sugerido e responsável quando possível"
  ],
  "avaliacao_processo": {{
    "nota": "1-10",
    "pontos_fortes": ["ponto forte específico"],
    "pontos_melhoria": ["área de melhoria específica"]
  }},
  "risco_geral": "baixo|medio|alto",
  "taxa_divergencia": 0.0
}}"""

        result = provider.completar_json(prompt, max_tokens=_MAX_TOKENS)
        if result:
            result["valor_estoque"] = valor_estoque
        return result
