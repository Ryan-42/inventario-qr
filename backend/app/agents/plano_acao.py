"""
PlanoAcaoAgent — Agente de melhoria contínua e planos de ação.
Gera planos estruturados 5W2H para correção de processos logísticos baseados em divergências.
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session
from app.models.sessao import Sessao
from app.repositories import sessao_repo
from app.services.sessao_service import montar_divergencias
from app.agents.provider import provider

logger = logging.getLogger(__name__)

class PlanoAcaoAgent:
    """Gera um plano de ação estratégico 5W2H pós-inventário para corrigir gargalos no armazém."""

    def gerar_plano(self, sessao_id: str, db: Session) -> dict:
        sessao = db.query(Sessao).filter(Sessao.id == sessao_id).first()
        if not sessao:
            return {"erro": "Sessão não encontrada"}

        stats = sessao_repo.stats_sessao(db, sessao_id)
        valor_estoque = sessao_repo.calcular_valor_estoque(db, sessao_id)
        divergencias = montar_divergencias(db, sessao_id)
        metricas = sessao_repo.calcular_metricas_sessao(db, sessao_id)

        # Montar resumo das principais perdas e setores
        top_perdas = valor_estoque.get("maiores_perdas", [])[:3]
        total_divergencias = len(divergencias)
        perda_financeira = valor_estoque.get("diferenca", 0.0)

        # 1. Fallback / Plano determinístico local
        plano_local = [
            {
                "o_que": "Auditoria de divergências críticas de alto valor",
                "por_que": "Evitar prejuízos fiscais e garantir acurácia financeira.",
                "onde": "Depósito Central / Almoxarifado",
                "quem": "Supervisor de Inventário + Auditores Externos",
                "quando": "Imediatamente (nas próximas 48 horas)",
                "como": "Realizar contagem cega testemunhada dos itens com desvio absoluto superior a R$ 5.000.",
                "quanto": "Custo operacional interno existente (R$ 0,00)"
            },
            {
                "o_que": "Revisão física das prateleiras de maior divergência",
                "por_que": "Identificar erros sistêmicos de alocação ou possível desvio físico.",
                "onde": "Zonas e corredores de alta divergência",
                "quem": "Operador Líder do Turno",
                "quando": "Próximos 7 dias",
                "como": "Validar se os produtos estão alocados nas prateleiras descritas na planilha ou se há trocas de local.",
                "quanto": "R$ 0,00"
            }
        ]

        if total_divergencias > 5:
            plano_local.append({
                "o_que": "Treinamento prático de acurácia de leitura",
                "por_que": "Reduzir a alta taxa de retrabalho e scans duplicados identificados.",
                "onde": "Sala de Treinamentos / Área de Logística",
                "quem": "Líder de TI / Equipe de Qualidade",
                "quando": "Próximo mês",
                "como": "Treinar operadores sobre o uso adequado da câmera do celular, estabilidade física e verificação de quantidade.",
                "quanto": "Custo de 2 horas de treinamento interno"
            })

        resultado_basico = {
            "sessao_codigo": sessao.codigo,
            "sessao_nome": sessao.nome,
            "resumo_problemas": {
                "total_divergencias": total_divergencias,
                "impacto_financeiro": perda_financeira,
                "taxa_retrabalho_pct": metricas.get("taxa_retrabalho_pct", 0.0)
            },
            "plano_5w2h": plano_local,
            "conclusao_gestao": "Recomenda-se a imediata homologação deste plano junto aos líderes logísticos para evitar perdas fiscais recorrentes.",
            "fonte": "basico"
        }

        # 2. Chamar Groq/Llama se disponível
        if not provider.disponivel:
            resultado_basico["mensagem_ia"] = "IA indisponível. Usando plano de ação padrão estruturado localmente."
            return resultado_basico

        prompt = f"""Você é um Gerente Geral de Operações e Supply Chain.
Com base nas estatísticas de erros e perdas financeiras do inventário abaixo, gere um plano de ação estratégico estruturado no formato 5W2H (O que, Por que, Onde, Quem, Quando, Como, Quanto) para otimizar os processos do depósito e sanar os problemas relatados.

MÉTRICAS DO INVENTÁRIO:
- Código: {sessao.codigo}
- Total de Divergências: {total_divergencias}
- Impacto Financeiro Total: R$ {perda_financeira:,.2f}
- Taxa de Retrabalho: {metricas.get('taxa_retrabalho_pct', 0.0)}%
- Maiores Perdas: {top_perdas}

Gere o plano de melhoria contínua e responda EXCLUSIVAMENTE em JSON válido com o seguinte formato:
{{
  "plano_5w2h": [
    {{
      "o_que": "Ação concreta (O que fazer)",
      "por_que": "Justificativa lógica (Por que fazer)",
      "onde": "Local físico ou setor (Onde fazer)",
      "quem": "Responsável pela ação (Quem fará)",
      "quando": "Prazo estimado (Quando fará)",
      "como": "Método de execução (Como fará)",
      "quanto": "Custo estimado (Quanto custará)"
    }}
  ],
  "conclusao_gestao": "parágrafo executivo sintetizando os principais focos de atenção operacional no depósito."
}}
"""
        ia_data = provider.completar_json(prompt, max_tokens=1024)
        if ia_data:
            resultado_basico.update({
                "plano_5w2h": ia_data.get("plano_5w2h", plano_local),
                "conclusao_gestao": ia_data.get("conclusao_gestao"),
                "fonte": "ia"
            })

        return resultado_basico
