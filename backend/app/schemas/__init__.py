import ipaddress
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from pydantic import BaseModel, field_validator, Field

from app.models.sessao import StatusSessao


# ── Sessão ──────────────────────────────────────────────────────────────────

class SessaoCreate(BaseModel):
    nome: str = Field(..., max_length=120)
    webhook_url: Optional[str] = Field(default=None, max_length=500)
    filial_id: Optional[str] = Field(default=None, description="ID da filial à qual esta sessão pertence")

    @field_validator("nome")
    @classmethod
    def nome_nao_vazio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Nome da sessão não pode ser vazio")
        return v

    @field_validator("webhook_url")
    @classmethod
    def webhook_url_valida(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError("webhook_url deve começar com http:// ou https://")
        try:
            parsed = urlparse(v)
            host = (parsed.hostname or "").lower()
            if not host:
                raise ValueError("webhook_url inválida: host ausente")
            if host in ("localhost", "localhost.localdomain"):
                raise ValueError("webhook_url não pode apontar para endereços locais")
            try:
                ip = ipaddress.ip_address(host)
                if (ip.is_private or ip.is_loopback or ip.is_link_local
                        or ip.is_multicast or ip.is_reserved or ip.is_unspecified):
                    raise ValueError("webhook_url não pode apontar para endereços privados ou reservados")
            except ValueError as exc:
                if "webhook_url" in str(exc):
                    raise
                # host is a domain name, not an IP — that's acceptable
        except ValueError:
            raise
        except Exception:
            raise ValueError("webhook_url inválida")
        return v


class SessaoResponse(BaseModel):
    id: str
    codigo: str
    nome: str
    status: StatusSessao
    data_inicio: datetime
    data_fim: Optional[datetime] = None
    total_itens: int = 0
    itens_contados: int = 0
    total_divergencias: int = 0
    webhook_url: Optional[str] = None
    filial_id: Optional[str] = None

    model_config = {"from_attributes": True}


class SessaoCreateResponse(SessaoResponse):
    """Resposta da criação de sessão — inclui token_admin (retornado apenas uma vez)."""
    token_admin: str


class SessaoStats(BaseModel):
    total: int
    conferidos: int
    pendentes: int
    divergencias: int
    percentual: float


# ── Item Base ────────────────────────────────────────────────────────────────

class ItemBaseResponse(BaseModel):
    id: str
    codigo: str
    produto: str
    quantidade_base: int

    model_config = {"from_attributes": True}


class ItemListaOperador(BaseModel):
    """Item visível ao operador durante contagem — sem quantidade_base (contagem cega)."""
    codigo: str
    produto: str
    local_fisico: Optional[str] = None
    ja_contado: bool

    model_config = {"from_attributes": True}


class ItemComStatus(BaseModel):
    codigo: str
    produto: str
    quantidade_base: int
    quantidade_encontrada: Optional[int] = None
    diferenca: Optional[int] = None
    status: str  # "OK" | "Divergente" | "Pendente"
    operador: Optional[str] = None
    observacao: Optional[str] = None
    timestamp: Optional[datetime] = None
    rodada: Optional[int] = None


# ── Contagem ─────────────────────────────────────────────────────────────────

class ContagemCreate(BaseModel):
    codigo: str = Field(..., max_length=100)
    quantidade_encontrada: int = Field(..., ge=0, le=999_999)
    operador: Optional[str] = Field(default=None, max_length=100)
    observacao: Optional[str] = Field(default=None, max_length=500)

    @field_validator("quantidade_encontrada")
    @classmethod
    def quantidade_nao_negativa(cls, v: int) -> int:
        if v < 0:
            raise ValueError("Quantidade encontrada não pode ser negativa")
        return v

    @field_validator("codigo")
    @classmethod
    def codigo_nao_vazio(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Código não pode ser vazio")
        return v


class ContagemResponse(BaseModel):
    id: str
    sessao_id: str
    codigo: str
    quantidade_encontrada: int
    divergencia: bool
    para_ajuste: bool = False
    operador: Optional[str]
    observacao: Optional[str] = None
    timestamp: datetime
    rodada: int = 1
    produto: Optional[str] = None
    quantidade_base: Optional[int] = None
    diferenca: Optional[int] = None

    model_config = {"from_attributes": True}


class HistoricoContagemResponse(BaseModel):
    id: str
    sessao_id: str
    codigo: str
    quantidade_encontrada: int
    quantidade_base: int
    divergencia: bool
    para_ajuste: bool = False
    operador: Optional[str]
    observacao: Optional[str] = None
    rodada: int
    timestamp: datetime

    model_config = {"from_attributes": True}


class BuscaItemResponse(BaseModel):
    codigo: str
    produto: str
    quantidade_base: int
    ja_contado: bool
    rodada_atual: int = 0
    para_ajuste: bool = False
    contagem_anterior: Optional[ContagemResponse] = None


# ── Rodadas ──────────────────────────────────────────────────────────────────

class RodadaResumo(BaseModel):
    numero: int
    total: int
    divergencias: int
    concluida: bool


class ItemParaContagem(BaseModel):
    codigo: str
    produto: str
    quantidade_base: int
    rodada: int


class RodadasInfo(BaseModel):
    rodada_maxima: int
    rodadas: list[RodadaResumo]
    itens_segunda: list[ItemParaContagem]
    itens_terceira: list[ItemParaContagem]


# ── Progresso de Rodada ───────────────────────────────────────────────────────

class ValorEstoqueStats(BaseModel):
    valor_inicial: float
    valor_final: float
    diferenca: float
    percentual_variacao: float
    itens_com_valor: int
    itens_sem_valor: int
    maiores_perdas: list[dict] = []
    maiores_ganhos: list[dict] = []
    tem_dados_financeiros: bool


class ProgressoRodada(BaseModel):
    rodada_atual: int
    total_rodada: int
    contados_rodada: int
    faltando: int
    completa: bool
    tem_itens: bool = True
    divergencias: int
    proxima_rodada_necessaria: bool
    faltando_r1: int = 0
    faltando_r2: int = 0
    faltando_r3: int = 0
    divergencias_r1: int = 0
    divergencias_r2: int = 0
    divergencias_r3: int = 0
