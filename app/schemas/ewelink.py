"""Modelos da integração eWeLink (OAuth, coleta, gráfico e relé)."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class AuthResponse(BaseModel):
    url: str = Field(..., description="URL de login da eWeLink (abrir no navegador)")
    msg: str


class CallbackQuery(BaseModel):
    code: Optional[str] = Field(None, description="Código devolvido pela eWeLink")
    region: Optional[str] = None
    state: Optional[str] = Field(None, description="State gerado em /ewelink/auth")


class CallbackResponse(BaseModel):
    msg: str
    region: str


class DispositivoEwelink(BaseModel):
    deviceid: Optional[str] = None
    nome: Optional[str] = None
    online: Optional[bool] = None
    modelo: Optional[str] = None
    marca: Optional[str] = None
    params: Optional[dict[str, Any]] = None


class DispositivosEwelinkResponse(BaseModel):
    msg: str
    total: int
    dispositivos: list[DispositivoEwelink]


class ColetaResponse(BaseModel):
    msg: str
    status: str = Field(..., description="ok | ignorada")
    total: Optional[int] = None
    chamadas_api: Optional[int] = None
    data_leitura: Optional[datetime] = None
    eventos: Optional[str] = None


class ExecucaoColeta(BaseModel):
    inicio: datetime
    status: str
    dispositivos: int
    leituras: int
    chamadas_api: int
    duracao_ms: Optional[int] = None
    mensagem: Optional[str] = None


class SessaoEwelink(BaseModel):
    token_salvo: bool
    acesso_expira: Optional[datetime] = None
    sessao_expira: Optional[datetime] = None


class ColetaStatusResponse(BaseModel):
    intervalo_min: int
    ultima_coleta_ok: Optional[datetime] = None
    minutos_desde_ultima_ok: Optional[int] = None
    atrasada: bool
    pausada_ate: Optional[datetime] = None
    ultimas_24h: dict[str, int]
    eWeLink: SessaoEwelink
    ultimas_execucoes: list[ExecucaoColeta]


class GraficoPath(BaseModel):
    deviceid: str = Field(..., max_length=50)


class GraficoQuery(BaseModel):
    horas: Optional[str] = Field(None, description="Últimas N horas (padrão 24)")
    inicio: Optional[str] = Field(None, description="YYYY-MM-DD ou YYYY-MM-DD HH:MM")
    fim: Optional[str] = Field(None, description="YYYY-MM-DD ou YYYY-MM-DD HH:MM")


class Periodo(BaseModel):
    inicio: datetime
    fim: datetime


class Faixa(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None


class ResumoGrafico(BaseModel):
    temperatura_atual: Optional[float] = None
    ultima_leitura: Optional[datetime] = None
    minima: Optional[float] = None
    maxima: Optional[float] = None
    media: Optional[float] = None
    compressor_ligado_pct: Optional[float] = None
    leituras: int
    leituras_offline: int


class PontoGrafico(BaseModel):
    data: datetime
    temperatura: Optional[float] = None
    rele: Optional[bool] = None
    online: bool
    min: Optional[float] = None
    max: Optional[float] = None


class GraficoResponse(BaseModel):
    deviceid: str
    nome: Optional[str] = None
    modelo: Optional[str] = None
    online: bool
    periodo: Periodo
    faixa: Faixa
    agrupamento_min: int
    resumo: ResumoGrafico
    total_pontos: int
    pontos: list[PontoGrafico]


class ReleBody(BaseModel):
    # validado no serviço (só bool de verdade vale; devolve 400 como no Brain)
    ligado: Optional[Any] = Field(None, description="true liga o compressor, false desliga")


class ReleResponse(BaseModel):
    msg: str
    deviceid: str
    ligado: bool
