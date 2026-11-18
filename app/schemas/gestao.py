"""Modelos da gestão. Os campos de entrada são `Any` de propósito: regras e mensagens de validação
ficam no service (400 com mensagem em português, como no Brain). Campo ausente != campo null."""

from typing import Any, Optional

from pydantic import BaseModel, Field


class _Corpo(BaseModel):
    def enviados(self) -> dict:
        """Só os campos que vieram no JSON."""
        return {k: getattr(self, k) for k in self.model_fields_set}


class EmpresaCriarBody(_Corpo):
    nome: Any = Field(None, description="Obrigatório (até 150 caracteres)")
    documento: Any = Field(None, description="CNPJ/CPF (opcional, único)")


class EmpresaEditarBody(_Corpo):
    nome: Any = None
    documento: Any = None
    ativo: Any = Field(None, description="true | false")
    id_plano: Any = Field(None, description="id do plano ou null")


class UsuarioCriarBody(_Corpo):
    nome: Any = None
    login: Any = Field(None, description="E-mail")
    telefone: Any = Field(None, description="Opcional; guarda só os dígitos (10 a 13)")
    perfil: Any = Field(None, description="admin | operador | visualizador (padrão visualizador)")
    id_empresa: Any = Field(
        None, description="Obrigatório para a master; ignorado para admin de cliente"
    )


class UsuarioEditarBody(_Corpo):
    nome: Any = None
    login: Any = None
    telefone: Any = None
    perfil: Any = None
    ativo: Any = None
    id_empresa: Any = Field(None, description="Somente a master move usuários de empresa")


class UsuariosQuery(BaseModel):
    id_empresa: Optional[int] = Field(None, description="Filtro (só vale para a master)")


class AuditoriaQuery(BaseModel):
    limite: Any = Field(100, description="1 a 500 (padrão 100)")


class UsuarioPath(BaseModel):
    id_usuario: int


class EmpresaPath(BaseModel):
    id_empresa: int


class MensagemOut(BaseModel):
    msg: str


class EmpresaIdOut(MensagemOut):
    id_empresa: int


class PlanoOut(BaseModel):
    id_plano: int
    nome: str
    desconto_servico: float


class EmpresaItemOut(BaseModel):
    id_empresa: int
    nome: str
    documento: Optional[str] = None
    tipo: str
    ativo: bool
    usuarios: int
    dispositivos: int
    plano: Optional[PlanoOut] = None
    criado_em: Optional[str] = None


class EmpresasResponse(BaseModel):
    total: int
    empresas: list[EmpresaItemOut]


class EmpresaRefOut(BaseModel):
    id_empresa: int
    nome: str
    tipo: str


class UsuarioItemOut(BaseModel):
    id_usuario: int
    nome: str
    login: str
    telefone: Optional[str] = None
    perfil: str
    ativo: bool
    ultimo_login: Optional[str] = None
    criado_em: Optional[str] = None
    empresa: EmpresaRefOut
    eu: bool


class UsuariosResponse(BaseModel):
    total: int
    usuarios: list[UsuarioItemOut]


class UsuarioIdOut(MensagemOut):
    id_usuario: int


class AuditoriaUsuarioOut(BaseModel):
    nome: str
    login: str


class AuditoriaItemOut(BaseModel):
    id_auditoria: int
    acao: str
    entidade: str
    id_entidade: Optional[str] = None
    detalhe: dict
    quando: Optional[str] = None
    usuario: AuditoriaUsuarioOut


class AuditoriaResponse(BaseModel):
    total: int
    registros: list[AuditoriaItemOut]
