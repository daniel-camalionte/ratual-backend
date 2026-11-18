"""Eventos (linha do tempo) e alertas ativos dos refrigeradores."""

from flask import current_app
from flask_openapi3 import APIBlueprint, Tag

from app.core.auth import current_user, master_required, require_login_for_blueprint
from app.schemas.common import ErrorResponse as ErrorSchema
from app.schemas.eventos import (
    AlertasQuery,
    EventosQuery,
    EventosResponse,
    ReprocessarResponse,
)
from app.services import eventos as service

# tags/prefixo: as rotas ficam em /v1/eventos, /v1/eventos/reprocessar e /v1/alertas
bp = APIBlueprint("eventos", __name__, url_prefix="/v1", abp_tags=[Tag(name="Eventos")])
require_login_for_blueprint(bp)


@bp.get(
    "/eventos",
    summary="Linha do tempo de eventos (master: todos; cliente: só a própria empresa)",
    responses={200: EventosResponse, 400: ErrorSchema, 401: ErrorSchema},
)
def listar(query: EventosQuery):
    return service.listar(
        current_user(), query.tipo, query.deviceid, query.ativos, query.inicio, query.fim,
        query.limite, query.offset,
    )  # fmt: skip


@bp.get(
    "/alertas",
    summary="Alertas ativos: offline e fora da faixa em andamento",
    responses={200: EventosResponse, 400: ErrorSchema, 401: ErrorSchema},
)
def alertas(query: AlertasQuery):
    return service.listar(
        current_user(), None, query.deviceid, None, query.inicio, query.fim,
        query.limite, query.offset, somente_alertas=True,
    )  # fmt: skip


@bp.post(
    "/eventos/reprocessar",
    summary="Recria os eventos de sistema a partir das leituras (só master)",
    responses={200: ReprocessarResponse, 401: ErrorSchema, 403: ErrorSchema, 409: ErrorSchema},
)
@master_required
def reprocessar():
    """Útil após calibrar as faixas. Preserva comandos do app e eventos de câmera."""
    return service.reprocessar_historico(current_app.extensions["settings"])
