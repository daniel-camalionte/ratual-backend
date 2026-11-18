"""Ordens de serviço (pedidos do cliente e gestão da equipe) e disponibilidade da agenda."""

from flask import current_app
from flask_openapi3 import APIBlueprint, Tag

from app.core.auth import current_user, master_required, require_login_for_blueprint
from app.core.background import em_segundo_plano
from app.schemas.common import ErrorResponse as ErrorSchema
from app.schemas.ordens import (
    CancelarBody,
    DisponibilidadeQuery,
    DisponibilidadeResponse,
    MsgResponse,
    OrdemCreate,
    OrdemListQuery,
    OrdemListResponse,
    OrdemResponse,
    OrdemUpdate,
    OsPath,
)
from app.services import ordens as service

bp = APIBlueprint("ordens", __name__, url_prefix="/v1", abp_tags=[Tag(name="Ordens de serviço")])
require_login_for_blueprint(bp)


@bp.get(
    "/agenda/disponibilidade",
    summary="Janelas livres da grade, dia a dia, a partir de amanhã",
    responses={200: DisponibilidadeResponse, 401: ErrorSchema},
)
def disponibilidade(query: DisponibilidadeQuery):
    """Considera vagas já ocupadas por ordens abertas e as datas bloqueadas."""
    return service.disponibilidade(query.inicio, query.dias)


@bp.get(
    "/ordens",
    summary="Lista ordens de serviço",
    responses={200: OrdemListResponse, 401: ErrorSchema},
)
def listar(query: OrdemListQuery):
    """Master: todas (com filtros). Cliente: só as da própria empresa."""
    return service.listar(current_user(), query.model_dump())


@bp.post(
    "/ordens",
    summary="Pede uma visita (cliente) ou agenda direto (master)",
    responses={
        201: OrdemResponse,
        400: ErrorSchema,
        401: ErrorSchema,
        403: ErrorSchema,
        409: ErrorSchema,
    },
)
def criar(body: OrdemCreate):
    """Cliente (admin/operador): escolhe uma janela livre; nasce 'solicitado' e a equipe é
    avisada por e-mail. Master: cria já 'confirmado', para qualquer cliente ativo."""
    resposta = service.criar(current_user(), body.model_dump())
    ordem = resposta["ordem"]
    if ordem.get("origem") == "cliente":
        em_segundo_plano(service.avisar_pedido, ordem, current_app.extensions["settings"].os_emails)
    return resposta, 201


@bp.put(
    "/ordens/<int:id_os>",
    summary="Confirma, atribui, remarca, lança valores ou conclui (master)",
    responses={
        200: OrdemResponse,
        400: ErrorSchema,
        401: ErrorSchema,
        403: ErrorSchema,
        404: ErrorSchema,
    },
)
@master_required
def editar(path: OsPath, body: OrdemUpdate):
    """Altera só os campos enviados; o status segue o fluxo permitido."""
    return service.editar(current_user(), path.id_os, body.model_dump(exclude_unset=True))


@bp.post(
    "/ordens/<int:id_os>/cancelar",
    summary="Cancela uma ordem",
    responses={
        200: MsgResponse,
        400: ErrorSchema,
        401: ErrorSchema,
        403: ErrorSchema,
        404: ErrorSchema,
    },
)
def cancelar(path: OsPath, body: CancelarBody):
    """Cliente: só da própria empresa e ainda 'solicitado'/'confirmado'. Master: qualquer aberta."""
    return service.cancelar(current_user(), path.id_os, body.motivo)
