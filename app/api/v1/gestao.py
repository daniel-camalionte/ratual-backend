"""Gestão: empresas e auditoria (master) e usuários (admin)."""

from flask_openapi3 import APIBlueprint, Tag

from app.core.auth import (
    admin_required,
    current_user,
    master_required,
    require_login_for_blueprint,
)
from app.schemas.common import ErrorResponse as ErrorSchema
from app.schemas.gestao import (
    AuditoriaQuery,
    AuditoriaResponse,
    EmpresaCriarBody,
    EmpresaEditarBody,
    EmpresaIdOut,
    EmpresaPath,
    EmpresasResponse,
    UsuarioCriarBody,
    UsuarioEditarBody,
    UsuarioIdOut,
    UsuarioPath,
    UsuariosQuery,
    UsuariosResponse,
)
from app.services import gestao as service

_ERROS = {400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema}

bp_empresas = APIBlueprint(
    "gestao_empresas",
    __name__,
    url_prefix="/v1/empresas",
    abp_tags=[Tag(name="Empresas")],
)
bp_usuarios = APIBlueprint(
    "gestao_usuarios",
    __name__,
    url_prefix="/v1/usuarios",
    abp_tags=[Tag(name="Usuários")],
)
bp_auditoria = APIBlueprint(
    "gestao_auditoria",
    __name__,
    url_prefix="/v1/auditoria",
    abp_tags=[Tag(name="Auditoria")],
)
for _bp in (bp_empresas, bp_usuarios, bp_auditoria):
    require_login_for_blueprint(_bp)

bps = [bp_empresas, bp_usuarios, bp_auditoria]


# ── empresas (master) ────────────────────────────────────────────────────


@bp_empresas.get(
    "", summary="Lista as empresas (master)", responses={200: EmpresasResponse, **_ERROS}
)
@master_required
def listar_empresas():
    """Empresas com plano, usuários e refrigeradores ativos."""
    return service.listar_empresas()


@bp_empresas.post(
    "",
    summary="Cria uma empresa cliente (master)",
    responses={201: EmpresaIdOut, 409: ErrorSchema, **_ERROS},
)
@master_required
def criar_empresa(body: EmpresaCriarBody):
    """Cria a empresa cliente; o documento, se enviado, é único."""
    return service.criar_empresa(current_user(), body.enviados()), 201


@bp_empresas.put(
    "/<int:id_empresa>",
    summary="Edita uma empresa (master)",
    responses={200: EmpresaIdOut, 404: ErrorSchema, 409: ErrorSchema, **_ERROS},
)
@master_required
def editar_empresa(path: EmpresaPath, body: EmpresaEditarBody):
    """Altera nome, documento, ativo e/ou plano. A master não pode ser desativada."""
    return service.editar_empresa(current_user(), path.id_empresa, body.enviados())


# ── usuários (admin) ─────────────────────────────────────────────────────


@bp_usuarios.get("", summary="Lista usuários (admin)", responses={200: UsuariosResponse, **_ERROS})
@admin_required
def listar_usuarios(query: UsuariosQuery):
    """Admin da master vê todas as empresas (filtro opcional); admin do cliente, só a própria."""
    return service.listar_usuarios(current_user(), query.id_empresa)


@bp_usuarios.post(
    "",
    summary="Cria um usuário (admin); ele entra por e-mail + código",
    responses={201: UsuarioIdOut, 409: ErrorSchema, **_ERROS},
)
@admin_required
def criar_usuario(body: UsuarioCriarBody):
    """Sem senha: o acesso é por código enviado ao e-mail (login) do usuário."""
    return service.criar_usuario(current_user(), body.enviados()), 201


@bp_usuarios.put(
    "/<int:id_usuario>",
    summary="Edita um usuário (admin)",
    responses={200: UsuarioIdOut, 404: ErrorSchema, 409: ErrorSchema, **_ERROS},
)
@admin_required
def editar_usuario(path: UsuarioPath, body: UsuarioEditarBody):
    """Altera nome, login, telefone, perfil, ativo e (só master) empresa."""
    return service.editar_usuario(current_user(), path.id_usuario, body.enviados())


# ── auditoria (master) ───────────────────────────────────────────────────


@bp_auditoria.get(
    "", summary="Lista a trilha de auditoria (master)", responses={200: AuditoriaResponse, **_ERROS}
)
@master_required
def listar_auditoria(query: AuditoriaQuery):
    """Últimos registros (limite 1 a 500, padrão 100)."""
    return service.listar_auditoria(query.limite)
