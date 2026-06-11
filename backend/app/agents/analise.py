"""
AnaliseAgent — análise de inventário pós-sessão via IA.

Recebe os dados de uma sessão concluída/ativa e retorna insights acionáveis:
padrões de divergência, itens críticos, recomendações e resumo executivo.
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_MAX_TOKENS = 1500
_MAX_DIVERGENCIAS_PROMPT = 50  # limita payload para não estourar contexto


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
        """
        Analisa a sessão e retorna um dict com insights.

        Retorna resultado básico (sem IA) se nenhum provider estiver configurado.
        """
        from app.agents.provider import provider

        basico = self._analise_basica(stats, divergencias, valor_estoque, metricas)

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
    # Análise básica (sem IA)
    # ------------------------------------------------------------------

    def _analise_basica(self, stats: dict, divergencias: list[dict], valor_estoque: dict | None = None, metricas: dict | None = None) -> dict:
        total = stats.get("total", 0)
        conferidos = stats.get("conferidos", 0)
        divs = stats.get("divergencias", 0)
        percentual = stats.get("percentual", 0.0)

        taxa_divergencia = round(divs / conferidos * 100, 1) if conferidos > 0 else 0.0

        # Detecta itens com maior desvio absoluto
        itens_criticos = sorted(
            [d for d in divergencias if d.get("diferenca") is not None],
            key=lambda x: abs(x.get("diferenca", 0)),
            reverse=True,
        )[:5]

        nivel_risco = "baixo"
        if taxa_divergencia > 30:
            nivel_risco = "alto"
        elif taxa_divergencia > 10:
            nivel_risco = "medio"

        # Padrões por local físico
        padroes = []
        locais: dict[str, int] = {}
        for d in divergencias:
            loc = d.get("local_fisico") or "Sem localização"
            locais[loc] = locais.get(loc, 0) + 1
        if locais and len(locais) > 1:
            top_local, top_count = max(locais.items(), key=lambda x: x[1])
            pct_local = round(top_count / divs * 100, 0) if divs > 0 else 0
            if pct_local >= 30:
                padroes.append(f"{top_local} concentra {pct_local:.0f}% das divergências ({top_count} itens)")

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
                padroes.append(f"Retrabalho elevado: {metricas['taxa_retrabalho_pct']:.1f}% dos itens foram recontados.")
            if metricas.get("pct_rastreabilidade", 100) < 90:
                padroes.append(f"Rastreabilidade baixa: {metricas['pct_rastreabilidade']:.1f}% das contagens têm operador identificado.")

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
            "recomendacoes": [
                "Recontar os itens com maior divergência para confirmar os valores.",
                "Verificar se a planilha base está atualizada com o estoque real.",
            ] if divs > 0 else ["Nenhuma divergência detectada — inventário dentro do esperado."],
            "risco_geral": nivel_risco,
            "taxa_divergencia": taxa_divergencia,
            "valor_estoque": valor_estoque,
        }

    # ------------------------------------------------------------------
    # Análise com IA
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

        # Monta bloco financeiro somente se disponível
        bloco_financeiro = ""
        if valor_estoque and valor_estoque.get("tem_dados_financeiros"):
            vi = valor_estoque["valor_inicial"]
            vf = valor_estoque["valor_final"]
            delta = valor_estoque["diferenca"]
            pct = valor_estoque["percentual_variacao"]
            perdas = valor_estoque.get("maiores_perdas", [])[:3]
            ganhos = valor_estoque.get("maiores_ganhos", [])[:3]
            bloco_financeiro = f"""
ANÁLISE FINANCEIRA:
- Valor inicial do estoque: R$ {vi:,.2f}
- Valor final apurado: R$ {vf:,.2f}
- Diferença: R$ {delta:,.2f} ({pct:+.2f}%)
- Maiores perdas: {json.dumps(perdas, ensure_ascii=False)}
- Maiores ganhos: {json.dumps(ganhos, ensure_ascii=False)}
"""

        # Monta bloco de locais físicos
        locais: dict[str, int] = {}
        for d in divs_limitadas:
            loc = d.get("local_fisico") or "Sem localização"
            locais[loc] = locais.get(loc, 0) + 1
        bloco_locais = ""
        if locais:
            top_locais = sorted(locais.items(), key=lambda x: x[1], reverse=True)[:5]
            bloco_locais = f"\nDIVERGÊNCIAS POR LOCAL FÍSICO: {json.dumps(dict(top_locais), ensure_ascii=False)}"

        def _serializable(obj):
            from datetime import datetime, date
            if isinstance(obj, (datetime, date)):
                return obj.isoformat()
            raise TypeError(f"Not serializable: {type(obj)}")

        # Bloco de métricas de produtividade (novo)
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
- Operadores: {ops_str or 'nenhum'}
"""

        prompt = f"""Você é um especialista em gestão de inventário e controle de estoque.
Analise os dados desta sessão de inventário e forneça insights acionáveis em português.

DADOS DA SESSÃO:
- Nome: {getattr(sessao, 'nome', 'N/A')}
- Código: {getattr(sessao, 'codigo', 'N/A')}
- Total de itens: {stats.get('total', 0)}
- Itens conferidos: {stats.get('conferidos', 0)}
- Itens pendentes: {stats.get('pendentes', 0)}
- Divergências: {stats.get('divergencias', 0)}
- Progresso: {stats.get('percentual', 0):.1f}%
{bloco_metricas}{bloco_financeiro}{bloco_locais}

ITENS COM DIVERGÊNCIA ({len(divergencias)} total, mostrando {len(divs_limitadas)}):
{json.dumps(divs_limitadas, ensure_ascii=False, indent=2, default=_serializable)}

AMOSTRA DE TODOS OS ITENS ({len(itens_sample)} itens):
{json.dumps(itens_sample[:20], ensure_ascii=False, default=_serializable)}

Analise e identifique:
1. Padrões nos itens divergentes por local físico, categoria ou faixa de valor
2. Impacto financeiro das divergências (se dados disponíveis)
3. Itens que precisam de atenção imediata com justificativa financeira
4. Recomendações práticas para o gestor incluindo ações de ajuste de estoque

Responda SOMENTE em JSON válido:
{{
  "resumo": "parágrafo executivo de 2-3 frases com impacto financeiro se disponível",
  "padroes": ["padrão por local", "padrão por valor", "padrão por operador"],
  "itens_criticos": [
    {{"codigo": "...", "produto": "...", "diferenca": 0, "diferenca_valor": 0.0, "motivo": "..."}}
  ],
  "recomendacoes": ["ação concreta com impacto financeiro se disponível"],
  "risco_geral": "baixo|medio|alto",
  "taxa_divergencia": 0.0,
  "relatorio_executivo": "texto narrativo de 3-5 frases para apresentação gerencial"
}}"""

        result = provider.completar_json(prompt, max_tokens=_MAX_TOKENS)
        if result:
            result["valor_estoque"] = valor_estoque
        return result
