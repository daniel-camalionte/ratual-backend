from typing import Optional, Union

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt


class DeviceIdPath(BaseModel):
    deviceid: str = Field(..., min_length=1, max_length=100)


class ListarQuery(BaseModel):
    todos: Optional[str] = Field(None, description="1/true: master inclui desativados")


class AtualizarDispositivoBody(BaseModel):
    """Campos omitidos não mudam. `id_empresa: null` desvincula o refrigerador."""

    model_config = ConfigDict(extra="forbid")

    tipo: Optional[str] = Field(None, description="congelado | resfriado")
    temp_min: Optional[Union[StrictInt, StrictFloat]] = None
    temp_max: Optional[Union[StrictInt, StrictFloat]] = None
    tolerancia_min: Optional[StrictInt] = None
    id_empresa: Optional[StrictInt] = None
    ativo: Optional[StrictBool] = None


class FaixaOut(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    tolerancia_min: Optional[int] = None


class EmpresaRefOut(BaseModel):
    id_empresa: int
    nome: Optional[str] = None


class CameraRefOut(BaseModel):
    id_camera: int
    online: bool


class DispositivoOut(BaseModel):
    deviceid: str
    nome: str
    modelo: Optional[str] = None
    marca: Optional[str] = None
    tipo: Optional[str] = None
    faixa: FaixaOut
    online: bool
    temperatura: Optional[float] = None
    umidade: Optional[float] = None
    rele: Optional[bool] = None
    sinal: Optional[int] = None
    limite_min: Optional[float] = None
    limite_max: Optional[float] = None
    data_leitura: Optional[str] = Field(None, description="ISO 8601, horário de Brasília")
    empresa: Optional[EmpresaRefOut] = None
    ativo: bool
    camera: Optional[CameraRefOut] = None


class DispositivosResponse(BaseModel):
    total: int
    intervalo_coleta_min: int
    dispositivos: list[DispositivoOut]


class AtualizarDispositivoResponse(BaseModel):
    msg: str
    deviceid: str
    tipo: Optional[str] = None
    faixa: Optional[FaixaOut] = None
    id_empresa: Optional[int] = None
    ativo: Optional[int] = None
