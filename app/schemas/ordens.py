"""Ordens de serviço e disponibilidade da agenda."""

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.servicos import Dinheiro, Hora

STATUS_OS = Literal["solicitado", "confirmado", "em_atendimento", "concluido", "cancelado"]


class _Corpo(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="ignore")


class OsPath(BaseModel):
    id_os: int = Field(..., ge=1)


class DisponibilidadeQuery(BaseModel):
    inicio: Optional[date] = Field(None, description="AAAA-MM-DD (mínimo: amanhã)")
    dias: int = Field(21, description="Quantidade de dias (1 a 60)")


class JanelaLivre(BaseModel):
    hora_inicio: str
    hora_fim: str
    vagas_livres: int


class DiaLivre(BaseModel):
    data: date
    janelas: list[JanelaLivre]


class DisponibilidadeResponse(BaseModel):
    inicio: date
    fim: date
    dias: list[DiaLivre]


class OrdemListQuery(BaseModel):
    status: Optional[str] = Field(None, description="Lista separada por vírgula")
    inicio: Optional[date] = None
    fim: Optional[date] = None
    id_empresa: Optional[int] = Field(None, ge=1, description="Só master")
    id_tecnico: Optional[int] = Field(None, ge=1, description="Só master")


class OrdemCreate(_Corpo):
    """Cliente: pedido de visita. Master: agendamento direto (exige id_empresa e hora_fim)."""

    id_tipo_servico: int = Field(..., ge=1)
    descricao: Optional[str] = Field(None, max_length=1000)
    deviceid: Optional[str] = Field(None, max_length=100)
    data: date
    hora_inicio: Hora
    id_empresa: Optional[int] = Field(None, ge=1, description="Só master")
    hora_fim: Optional[Hora] = Field(None, description="Só master")
    id_tecnico: Optional[int] = Field(None, ge=1, description="Só master")
    valor_servico: Optional[Dinheiro] = Field(None, description="Só master")


class OrdemUpdate(_Corpo):
    status: STATUS_OS = None
    motivo_cancelamento: Optional[str] = Field(None, max_length=255)
    id_tecnico: Optional[int] = Field(None, ge=1)
    data: date = None
    hora_inicio: Hora = None
    hora_fim: Hora = None
    valor_servico: Dinheiro = None
    valor_pecas: Dinheiro = None
    descricao_pecas: Optional[str] = Field(None, max_length=500)
    observacao_tecnica: Optional[str] = Field(None, max_length=5000)


class CancelarBody(_Corpo):
    motivo: Optional[str] = Field(None, max_length=255)


class OrdemEmpresa(BaseModel):
    id_empresa: int
    nome: str


class OrdemDispositivo(BaseModel):
    deviceid: str
    nome: Optional[str] = None


class OrdemTipo(BaseModel):
    id_tipo_servico: int
    nome: str


class OrdemTecnico(BaseModel):
    id_tecnico: int
    nome: str
    telefone: Optional[str] = None


class OrdemValores(BaseModel):
    servico: Optional[float] = None
    desconto_percentual: Optional[float] = None
    desconto: Optional[float] = None
    pecas: Optional[float] = None
    total: Optional[float] = None


class OrdemOut(BaseModel):
    id_os: int
    status: str
    origem: Optional[str] = None
    data: date
    hora_inicio: Optional[str] = None
    hora_fim: Optional[str] = None
    empresa: OrdemEmpresa
    dispositivo: Optional[OrdemDispositivo] = None
    tipo_servico: OrdemTipo
    tecnico: Optional[OrdemTecnico] = None
    descricao: Optional[str] = None
    valores: OrdemValores
    descricao_pecas: Optional[str] = None
    observacao_tecnica: Optional[str] = None
    motivo_cancelamento: Optional[str] = None
    solicitante: Optional[str] = None
    criado_em: Optional[str] = None
    concluido_em: Optional[str] = None


class OrdemListResponse(BaseModel):
    total: int
    ordens: list[OrdemOut]


class OrdemResponse(BaseModel):
    msg: str
    ordem: Optional[OrdemOut] = None
    avisos: Optional[list[str]] = None


class MsgResponse(BaseModel):
    msg: str
