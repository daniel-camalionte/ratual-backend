from typing import Optional

from pydantic import BaseModel, Field, StrictBool, StrictInt


class CameraPath(BaseModel):
    id_camera: int


class AlarmePath(BaseModel):
    id_alarme: int


class ListarQuery(BaseModel):
    todas: Optional[str] = Field(None, description="1/true: master também vê as inativas")


class AoVivoQuery(BaseModel):
    qualidade: str = Field("hd", description="hd | sd")
    h265: Optional[str] = Field(None, description="1 se o player aceita H.265")


class GravacaoQuery(BaseModel):
    inicio: Optional[str] = Field(None, description="YYYY-MM-DD HH:MM:SS")
    fim: Optional[str] = Field(None, description="YYYY-MM-DD HH:MM:SS")
    origem: str = Field("nuvem", description="nuvem | sd")
    h265: Optional[str] = None


class AlarmesQuery(BaseModel):
    limite: int = Field(50, description="1 a 200")
    inicio: Optional[str] = None
    fim: Optional[str] = None


class CameraCadastroBody(BaseModel):
    deviceserial: str = Field(..., min_length=1, max_length=20)
    canal: StrictInt = Field(1, ge=1)
    nome: Optional[str] = Field(None, max_length=150)
    deviceid: Optional[str] = Field(None, description="refrigerador vigiado")
    codigo: Optional[str] = Field(None, description="6 letras da etiqueta da câmera")


class CameraEdicaoBody(BaseModel):
    """Só os campos enviados são alterados; `deviceid`/`codigo` null removem o vínculo/código."""

    nome: Optional[str] = Field(None, max_length=150)
    deviceid: Optional[str] = None
    codigo: Optional[str] = None
    ativo: Optional[StrictBool] = None


class RefrigeradorOut(BaseModel):
    deviceid: str
    nome: str


class EmpresaCameraOut(BaseModel):
    id_empresa: int
    nome: Optional[str] = None


class CameraOut(BaseModel):
    id_camera: int
    deviceserial: str
    canal: int
    nome: Optional[str] = None
    modelo: Optional[str] = None
    online: bool
    criptografada: bool
    codigo_cadastrado: bool
    ativo: bool
    data_status: Optional[str] = None
    ultimo_alarme_em: Optional[str] = None
    refrigerador: Optional[RefrigeradorOut] = None
    empresa: Optional[EmpresaCameraOut] = None


class CameraListResponse(BaseModel):
    total: int
    cameras: list[CameraOut]


class CameraSalvaResponse(BaseModel):
    msg: str
    id_camera: int


class LinkCameraOut(BaseModel):
    id_camera: int
    nome: Optional[str] = None


class LinkVideoResponse(BaseModel):
    url: Optional[str] = None
    protocolo: str
    expira_em: str
    camera: LinkCameraOut


class AlarmeOut(BaseModel):
    id_alarme: int
    tipo: Optional[int] = None
    data: Optional[str] = None
    tem_foto: bool
    foto_criptografada: bool


class AlarmesResponse(BaseModel):
    total: int
    alarmes: list[AlarmeOut]


class ContaCameraOut(BaseModel):
    deviceserial: str
    canal: int
    nome: Optional[str] = None
    online: bool
    criptografada: bool
    id_camera: Optional[int] = None


class ContaResponse(BaseModel):
    total: int
    cameras: list[ContaCameraOut]


class ColetaResponse(BaseModel):
    msg: str
    status: str
    cameras: Optional[int] = None
    online: Optional[int] = None
    alarmes_novos: Optional[int] = None
    chamadas_api: Optional[int] = None
    avisos: Optional[list[str]] = None


class ExecucaoOut(BaseModel):
    inicio: Optional[str] = None
    status: str
    cameras: int
    alarmes_novos: int
    chamadas_api: int
    duracao_ms: Optional[int] = None
    mensagem: Optional[str] = None


class StatusResponse(BaseModel):
    token: dict = Field(..., description="Estado do token (nunca o valor)")
    ultimas_execucoes: list[ExecucaoOut]
