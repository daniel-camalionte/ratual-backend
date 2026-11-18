from typing import Optional

from pydantic import BaseModel, Field, field_validator


class EmpresaOut(BaseModel):
    id_empresa: int
    nome: str
    tipo: str = Field(..., description="master | cliente")


class UsuarioOut(BaseModel):
    id_usuario: int
    nome: str
    login: str
    telefone: Optional[str] = None
    perfil: str = Field(..., description="admin | operador | visualizador")
    empresa: EmpresaOut


class UsuarioResponse(BaseModel):
    usuario: UsuarioOut


class SolicitarCodigoBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=150, examples=["voce@empresa.com.br"])

    @field_validator("email", mode="before")
    @classmethod
    def _normalize(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


class VerificarCodigoBody(BaseModel):
    email: str = Field(..., min_length=3, max_length=150)
    codigo: str = Field(..., pattern=r"^\d{6}$", examples=["123456"], description="6 dígitos")

    @field_validator("email", mode="before")
    @classmethod
    def _normalize(cls, v):
        return v.strip().lower() if isinstance(v, str) else v


class CodigoEnviadoResponse(BaseModel):
    email: str = Field(..., description="E-mail de destino, mascarado (m***@exemplo.com)")
    expira_em: int = Field(..., description="Validade do código, em segundos")
    reenvio_em: int = Field(..., description="Segundos até poder pedir outro código")
