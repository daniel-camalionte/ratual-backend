"""Painel: séries de temperatura e de uso do compressor."""

from flask import current_app
from flask_openapi3 import APIBlueprint, Tag

from app.core.auth import current_user, require_login_for_blueprint
from app.schemas.common import ErrorResponse as ErrorSchema
from app.schemas.dashboard import GraficosQuery, GraficosResponse
from app.services import dashboard as service

bp = APIBlueprint(
    "dashboard",
    __name__,
    url_prefix="/v1/dashboard",
    abp_tags=[Tag(name="Dashboard")],
)
require_login_for_blueprint(bp)


@bp.get(
    "/graficos",
    summary="Séries do painel (temperatura média e compressor por dia)",
    responses={200: GraficosResponse, 400: ErrorSchema, 401: ErrorSchema},
)
def graficos(query: GraficosQuery):
    """Master considera todos os aparelhos; cliente, só os da própria empresa."""
    settings = current_app.extensions["settings"]
    return service.graficos(
        current_user(), settings.ewelink_coleta_intervalo_min, query.horas, query.dias
    )
