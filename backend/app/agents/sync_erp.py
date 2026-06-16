"""SyncERPAgent — conciliação de divergências e sincronização com ERPs.

Traduz os ajustes de estoque confirmados em payloads estruturados para
Bling, Omie, TOTVS, SAP ou qualquer ERP com API REST.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)


class SyncERPAgent:
    """Mapeia dados do inventário e gera payloads de integração para ERPs."""

    def conciliar(self, sessao_id: str, erp_nome: str, db) -> dict:
        from app.models.contagem import Contagem
        from app.models.item_base import ItemBase
        from app.agents.provider import provider

        contagens_ajuste = (
            db.query(Contagem)
            .filter(Contagem.sessao_id == sessao_id, Contagem.para_ajuste == True)  # noqa: E712
            .all()
        )

        codigos = [c.codigo for c in contagens_ajuste]
        itens_base = {
            i.codigo: i
            for i in db.query(ItemBase).filter(
                ItemBase.sessao_id == sessao_id, ItemBase.codigo.in_(codigos)
            ).all()
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
                "valor_total_ajuste": round(diferenca * valor_unit, 2),
            })

        erp_nome = erp_nome.lower().strip()
        erros_validacao: list[str] = []
        valido = True

        for a in ajustes_lista:
            if " " in a["codigo"]:
                erros_validacao.append(
                    f"Código '{a['codigo']}' contém espaços. ERPs como Bling/Omie rejeitam SKUs com espaços."
                )
                valido = False
            if len(a["codigo"]) > 60:
                erros_validacao.append(
                    f"Código '{a['codigo']}' é longo demais (>60 caracteres) para integração padrão."
                )
                valido = False

        payload_modelo = self._montar_payload(erp_nome, sessao_id, ajustes_lista)

        resultado_basico = {
            "erp": erp_nome,
            "total_itens_ajustados": len(ajustes_lista),
            "itens": ajustes_lista,
            "payload_integracao": payload_modelo,
            "validacao": {"valido": valido, "alertas": erros_validacao},
            "fonte": "basico",
        }

        if not provider.disponivel:
            resultado_basico["mensagem_ia"] = "IA indisponível. Usando mapeamento estático básico."
            return resultado_basico

        prompt = f"""Você é um arquiteto de integrações e especialista em sistemas ERP.
Dado a lista de itens com divergências a serem ajustados na empresa e o ERP de destino '{erp_nome}', gere o payload de API JSON exato e as regras de mapeamento semântico.

DADOS DE AJUSTES:
{json.dumps(ajustes_lista[:10], ensure_ascii=False, indent=2)}

FORMATO DE DESTINO EXIGIDO: {erp_nome}

Gere o mapeamento e o payload de sincronização e responda EXCLUSIVAMENTE em JSON válido com o seguinte formato:
{{
  "payload_integracao": {{ }},
  "documentacao_mapeamento": "breve explicação das rotas, endpoints recomendados do ERP e método HTTP",
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
                "fonte": "ia",
            })

        return resultado_basico

    def _montar_payload(self, erp_nome: str, sessao_id: str, ajustes: list[dict]) -> dict:
        if erp_nome == "bling":
            return {
                "estoque": [
                    {
                        "codigo": a["codigo"],
                        "quantidade": a["quantidade_atual"],
                        "operacao": "B" if a["quantidade_ajuste"] >= 0 else "D",
                        "observacao": "Ajuste via INVIQ Inventário QR",
                    }
                    for a in ajustes
                ]
            }
        if erp_nome == "omie":
            return {
                "cabecalho": {
                    "codigo_integracao": f"INVIQ-{sessao_id[:8].upper()}",
                    "data_movimento": "",
                },
                "produtos": [
                    {
                        "codigo_produto": a["codigo"],
                        "quantidade": abs(a["quantidade_ajuste"]),
                        "tipo_movimento": "ENTRADA" if a["quantidade_ajuste"] >= 0 else "SAIDA",
                        "valor_unitario": a["valor_unitario"],
                    }
                    for a in ajustes
                ],
            }
        # Fallback genérico (TOTVS / SAP / outros)
        return {
            "inventario_id": sessao_id,
            "erp_destino": erp_nome,
            "itens": [
                {
                    "sku": a["codigo"],
                    "ajuste": a["quantidade_ajuste"],
                    "saldo_final": a["quantidade_atual"],
                    "custo_unitario": a["valor_unitario"],
                }
                for a in ajustes
            ],
        }
