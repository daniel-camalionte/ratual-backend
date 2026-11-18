"""Modelos de eventos e alertas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventosQuery(BaseModel):
    # limite/offset são validados no serviço (400 com mensagem, como no Brain)
    tipo: Optional[str] = Field(None, description="Um ou mais tipos separados por vírgula")
    deviceid: Optional[str] = Field(None, max_length=50)
    ativos: Optional[str] = Field(None, description="1/true: só eventos em andamento")
    inicio: Optional[str] = None
    fim: Optional[str] = None
    limite: Optional[str] = Field(None, description="1 a 500 (padrão 100)")
    offset: Optional[str] = None


class AlertasQuery(BaseModel):
    deviceid: Optional[str] = Field(None, max_length=50)
    inicio: Optional[str] = None
    fim: Optional[str] = None
    limite: Optional[str] = Field(None, description="1 a 500 (padrão 100)")
    offset: Optional[str] = None


class DispositivoRef(BaseModel):
    deviceid: str
    nome: str


class EmpresaRef(BaseModel):
    id_empresa: int
    nome: Optional[str] = None


class EventoOut(BaseModel):
    id_evento: int
    tipo: str
    origem: str = Field(..., description="sistema | app | externo")
    ativo: bool
    inicio: datetime
    fim: Optional[datetime] = None
    duracao_min: Optional[int] = None
    valor: Optional[float] = None
    detalhe: dict[str, Any]
    descricao: str
    usuario: Optional[str] = None
    dispositivo: DispositivoRef
    empresa: Optional[EmpresaRef] = None


class EventosResponse(BaseModel):
    total: int
    limite: int
    offset: int
    eventos: list[EventoOut]


class ReprocessarResponse(BaseModel):
    msg: str
    leituras: int
    eventos: int
    por_tipo: dict[str, int]
    ativos: int
