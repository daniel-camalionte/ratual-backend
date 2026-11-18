"""Central de serviços: planos, tipos, técnicos, grade e bloqueios de agenda, catálogo."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Optional

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

HORA_RE = r"^([01]\d|2[0-3]):[0-5]\d$"


def _dinheiro(v: Any) -> Any:
    if isinstance(v, bool):
        raise ValueError("deve ser um número")
    if isinstance(v, (int, float, str)):
        try:
            return Decimal(str(v).replace(",", ".")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        except Exception as exc:  # noqa: BLE001
            raise ValueError("deve ser um número") from exc
    return v


Dinheiro = Annotated[Decimal, BeforeValidator(_dinheiro), Field(ge=0, le=99999999)]
Percentual = Annotated[Decimal, BeforeValidator(_dinheiro), Field(ge=0, le=100)]
Hora = Annotated[str, Field(pattern=HORA_RE, examples=["08:30"])]


class _Corpo(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


class IdPath(BaseModel):
    id_item: int = Field(..., ge=1)


class BloqueioPath(BaseModel):
    id_bloqueio: int = Field(..., ge=1)


# ── planos ───────────────────────────────────────────────────────────────


class PlanoCreate(_Corpo):
    nome: str = Field(..., min_length=1, max_length=60)
    descricao: Optional[str] = Field(None, max_length=255)
    preco_mensal: Optional[Dinheiro] = None
    desconto_servico: Percentual
    visitas_preventivas_ano: Optional[int] = Field(None, ge=0, le=52)
    pontos_inclusos: Optional[int] = Field(None, ge=0)
    ativo: Optional[bool] = None


class PlanoUpdate(_Corpo):
    nome: str = Field(None, min_length=1, max_length=60)
    descricao: Optional[str] = Field(None, max_length=255)
    preco_mensal: Optional[Dinheiro] = None
    desconto_servico: Percentual = None
    visitas_preventivas_ano: int = Field(None, ge=0, le=52)
    pontos_inclusos: Optional[int] = Field(None, ge=0)
    ativo: bool = None


class PlanoOut(BaseModel):
    id_plano: int
    nome: str
    descricao: Optional[str] = None
    preco_mensal: Optional[float] = None
    desconto_servico: Optional[float] = None
    visitas_preventivas_ano: Optional[int] = None
    pontos_inclusos: Optional[int] = None
    ativo: bool
    clientes: int


class PlanoListResponse(BaseModel):
    total: int
    planos: list[PlanoOut]


# ── tipos de serviço ─────────────────────────────────────────────────────


class TipoServicoCreate(_Corpo):
    nome: str = Field(..., min_length=1, max_length=100)
    descricao: Optional[str] = Field(None, max_length=255)
    valor: Dinheiro
    cliente_pode_solicitar: Optional[bool] = None
    ativo: Optional[bool] = None


class TipoServicoUpdate(_Corpo):
    nome: str = Field(None, min_length=1, max_length=100)
    descricao: Optional[str] = Field(None, max_length=255)
    valor: Dinheiro = None
    cliente_pode_solicitar: bool = None
    ativo: bool = None


class TipoServicoOut(BaseModel):
    id_tipo_servico: int
    nome: str
    descricao: Optional[str] = None
    valor: Optional[float] = None
    cliente_pode_solicitar: bool
    ativo: bool


class TipoServicoListResponse(BaseModel):
    total: int
    tipos: list[TipoServicoOut]


# ── técnicos ─────────────────────────────────────────────────────────────


class TecnicoCreate(_Corpo):
    nome: str = Field(..., min_length=1, max_length=120)
    telefone: Optional[str] = Field(None, max_length=30)
    ativo: Optional[bool] = None


class TecnicoUpdate(_Corpo):
    nome: str = Field(None, min_length=1, max_length=120)
    telefone: Optional[str] = Field(None, max_length=30)
    ativo: bool = None


class TecnicoOut(BaseModel):
    id_tecnico: int
    nome: str
    telefone: Optional[str] = None
    ativo: bool


class TecnicoListResponse(BaseModel):
    total: int
    tecnicos: list[TecnicoOut]


# ── grade (janelas) ──────────────────────────────────────────────────────


class JanelaCreate(_Corpo):
    dia_semana: int = Field(..., ge=0, le=6, description="0 = domingo ... 6 = sábado")
    hora_inicio: Hora
    hora_fim: Hora
    vagas: int = Field(..., ge=1, le=50)
    ativo: Optional[bool] = None


class JanelaUpdate(_Corpo):
    dia_semana: int = Field(None, ge=0, le=6)
    hora_inicio: Hora = None
    hora_fim: Hora = None
    vagas: int = Field(None, ge=1, le=50)
    ativo: bool = None


class JanelaOut(BaseModel):
    id_janela: int
    dia_semana: int
    dia: str
    hora_inicio: str
    hora_fim: str
    vagas: int
    ativo: bool


class JanelaListResponse(BaseModel):
    total: int
    janelas: list[JanelaOut]


# ── bloqueios ────────────────────────────────────────────────────────────


class BloqueioCreate(_Corpo):
    data: date
    motivo: Optional[str] = Field(None, max_length=120)


class BloqueioOut(BaseModel):
    id_bloqueio: int
    data: date
    motivo: Optional[str] = None


class BloqueioListResponse(BaseModel):
    total: int
    bloqueios: list[BloqueioOut]


# ── respostas comuns e catálogo ──────────────────────────────────────────


class MsgIdResponse(BaseModel):
    msg: str
    id: Optional[int] = None


class CatalogoQuery(BaseModel):
    id_empresa: Optional[int] = Field(
        None, ge=1, description="Só master: simula o catálogo de uma empresa"
    )


class CatalogoPlano(BaseModel):
    id_plano: int
    nome: str
    desconto_servico: float


class CatalogoTipo(TipoServicoOut):
    valor_com_desconto: float


class CatalogoResponse(BaseModel):
    plano: Optional[CatalogoPlano] = None
    tipos: list[CatalogoTipo]
