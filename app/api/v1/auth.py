"""Autenticação sem senha: e-mail + código de 6 dígitos; sessão em cookie httpOnly."""

from flask import current_app, request
from flask_openapi3 import APIBlueprint, Tag

from app.core.auth import (
    clear_session_cookie,
    current_token,
    current_user,
    login_required,
    set_session_cookie,
)
from app.core.errors import AppError
from app.repositories import auth as repo
from app.schemas.auth import (
    CodigoEnviadoResponse,
    SolicitarCodigoBody,
    UsuarioResponse,
    VerificarCodigoBody,
)
from app.schemas.common import ErrorResponse as ErrorSchema
from app.services import auth as service

bp = APIBlueprint("auth", __name__, url_prefix="/v1/auth", abp_tags=[Tag(name="Autenticação")])


@bp.post(
    "/solicitar-codigo",
    summary="Etapa 1: envia um código de 6 dígitos para o e-mail",
    responses={200: CodigoEnviadoResponse, 429: ErrorSchema, 503: ErrorSchema},
)
def solicitar_codigo(body: SolicitarCodigoBody):
    """Responde 200 mesmo para e-mail desconhecido (não revela quem tem cadastro); só envia se existir."""
    res = service.solicitar_codigo(
        current_app.extensions["settings"], body.email, request.remote_addr
    )
    return CodigoEnviadoResponse(**res).model_dump()


@bp.post(
    "/verificar-codigo",
    summary="Etapa 2: confere o código e abre a sessão (cookie httpOnly)",
    responses={200: UsuarioResponse, 400: ErrorSchema, 429: ErrorSchema},
)
def verificar_codigo(body: VerificarCodigoBody):
    usuario, token = service.verificar_codigo(
        current_app.extensions["settings"],
        body.email,
        body.codigo,
        request.remote_addr,
        request.headers.get("User-Agent"),
    )
    response = current_app.json.response({"usuario": usuario})
    set_session_cookie(response, token)
    return response


@bp.get(
    "/me", summary="Usuário da sessão atual", responses={200: UsuarioResponse, 401: ErrorSchema}
)
@login_required
def me():
    atual = repo.buscar_por_id(current_user()["id_usuario"])
    if not atual:
        raise AppError("Usuário não encontrado", status_code=404, code="not_found")
    return {"usuario": service.usuario_publico(atual)}


@bp.post("/logout", summary="Encerra a sessão", responses={204: None})
def logout():
    token = current_token()
    if token:
        service.logout(token)
    response = current_app.response_class(status=204)
    clear_session_cookie(response)
    return response
