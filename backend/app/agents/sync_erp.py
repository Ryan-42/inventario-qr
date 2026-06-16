"""
SyncERPAgent — Agente de conciliação de divergências e sincronização com ERPs.
Traduz os ajustes de estoque confirmados em payloads estruturados para Bling, Omie, TOTVS, SAP, etc.
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session
from app.models.contagem import Contagem
from app.models.item_base import ItemBase
from app.agents.provider import provider

logger = logging.getLogger(__name__)

class SyncERPAgent:
    """Mapeia os dados do inventário e gera payloads de integração e validações semânticas para ERPs."""

    def conciliar(self, sessao_id: str, erp_nome: str, db: Session) -> dict:
        # 1. Carregar contagens marcadas para ajuste
        contagens_ajuste = (
            db.query(Contagem)
            .filter(Contagem.sessao_id == sessao_id, Contagem.para_ajuste == True)
            .all()
        )

        codigos = [c.codigo for c in contagens_ajuste]
        itens_base = {
            i.codigo: i
            for i in db.query(ItemBase).filter(ItemBase.sessao_id == sessao_id, ItemBase.codigo.in_(codigos)).all()
        }

        ajustes_lista = []
        for c in contagens_ajuste:
            item = itens_base.get(c.codigo)
            if not item:
                continue

            qtd_base = item.quantidade_base
            qtd_enc = c.quantidade_encontrada
            diferenca = qtd_enc - qtd_base
            valor_unit = float(item.valor_estoque or 0.0) / qtd_base if qtd_base > 0 else 0.0

            ajustes_lista.append({
                "codigo": c.codigo,
                "produto": item.produto,
                "local_fisico": item.local_fisico,
                "quantidade_anterior": qtd_base,
                "quantidade_atual": qtd_enc,
                "quantidade_ajuste": diferenca,
                "valor_unitario": round(valor_unit, 2),
                "valor_total_ajuste": round(diferenca * valor_unit, 2)
            })

        # Mapeamento local básico
        erp_nome = erp_nome.lower().strip()
        payload_modelo = {}
        valido = True
        erros_validacao = []

        # Validações semânticas básicas
        for a in ajustes_lista:
            # ERPs geralmente não aceitam espaços ou caracteres especiais nos códigos
            if " " in a["codigo"]:
                erros_validacao.append(f"Código '{a['codigo']}' contém espaços. ERPs como Bling/Omie rejeitam SKUs com espaços.")
                valido = False
            if len(a["codigo"]) > 60:
                erros_validacao.append(f"Código '{a['codigo']}' é longo demais (>60 caracteres) para integração padrão.")
                valido = False

        if erp_nome == "bling":
            payload_modelo = {
                "estoque": [
                    {
                        "codigo": a["codigo"],
                        "quantidade": a["quantidade_atual"],
                        "operacao": "B" if a["quantidade_ajuste"] >= 0 else "D", # Balanço/Acerto
                        "observacao": "Ajuste via INVIQ Inventário QR"
                    }
                    for a in ajustes_lista
                ]
            }
        elif erp_nome == "omie":
            payload_modelo = {
                "cabecalho": {
                    "codigo_integracao": f"INVIQ-{sessao_id[:8].upper()}",
                    "data_movimento": "" # A ser preenchida
                },
                "produtos": [
                    {
                        "codigo_produto": a["codigo"],
                        "quantidade": abs(a["quantidade_ajuste"]),
                        "tipo_movimento": "ENTRADA" if a["quantidade_ajuste"] >= 0 else "SAIDA",
                        "valor_unitario": a["valor_unitario"]
                    }
                    for a in ajustes_lista
                ]
            }
        else: # Fallback genérico / TOTVS / SAP
            payload_modelo = {
                "inventario_id": sessao_id,
                "erp_destino": erp_nome,
                "itens": [
                    {
                        "sku": a["codigo"],
                        "ajuste": a["quantidade_ajuste"],
                        "saldo_final": a["quantidade_atual"],
                        "custo_unitario": a["valor_unitario"]
                    }
                    for a in ajustes_lista
                ]
            }

        resultado_basico = {
            "erp": erp_nome,
            "total_itens_ajustados": len(ajustes_lista),
            "itens": ajustes_lista,
            "payload_integracao": payload_modelo,
            "validacao": {
                "valido": valido,
                "alertas": erros_validacao
            },
            "fonte": "basico"
        }

        # 3. Chamar Groq/Llama se disponível
        if not provider.disponivel:
            resultado_basico["mensagem_ia"] = "IA indisponível. Usando mapeamento estático básico."
            return resultado_basico

        prompt = f"""Você é um arquiteto de integrações e especialista em sistemas ERP.
Dado a lista de itens com divergências a serem ajustados na empresa e o ERP de destino '{erp_nome}', gere o payload de API JSON exato e as regras de mapeamento semântico.

DADOS DE AJUSTES:
{ajustes_lista[:10]}

FORMATO DE DESTINO EXIGIDO: {erp_nome}

Gere o mapeamento e o payload de sincronização e responda EXCLUSIVAMENTE em JSON válido com o seguinte formato:
{{
  "payload_integracao": {{ ... payload JSON específico de API do ERP configurado ... }},
  "documentacao_mapeamento": "breve explicação das rotas, endpoints recomendados do ERP e método HTTP (ex: POST /estoque/balanco)",
  "validacao": {{
    "valido": true,
    "alertas": [
      "possível problema com códigos de barras, unidades de medida ou limite de taxa do ERP destino"
    ]
  }}
}}
"""
        ia_data = provider.completar_json(prompt, max_tokens=1024)
        if ia_data:
            resultado_basico.update({
                "payload_integracao": ia_data.get("payload_integracao", payload_modelo),
                "documentacao_mapeamento": ia_data.get("documentacao_mapeamento"),
                "validacao": ia_data.get("validacao", resultado_basico["validacao"]),
                "fonte": "ia"
            })

        return resultado_basico
