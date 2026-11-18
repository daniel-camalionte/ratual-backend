"""Dispositivos (refrigeradores): estado atual, calibração da faixa e vínculo com empresa."""

from flask import current_app
from flask_openapi3 import APIBlueprint, Tag

from app.core.auth import current_user, master_required, require_login_for_blueprint
from app.schemas.common import ErrorResponse as ErrorSchema
from app.schemas.dispositivos import (
    AtualizarDispositivoBody,
    AtualizarDispositivoResponse,
    DeviceIdPath,
    DispositivosResponse,
    ListarQuery,
)
from app.services import dispositivos as service

bp = APIBlueprint(
    "dispositivos",
    __name__,
    url_prefix="/v1/dispositivos",
    abp_tags=[Tag(name="Dispositivos")],
)
require_login_for_blueprint(bp)


@bp.get(
    "",
    summary="Lista os refrigeradores com o último estado",
    responses={200: DispositivosResponse, 401: ErrorSchema},
)
def listar(query: ListarQuery):
    """Master vê todos (com `todos=1`, inclusive desativados); cliente só os da própria empresa."""
    settings = current_app.extensions["settings"]
    return service.listar(
        current_user(), settings.ewelink_coleta_intervalo_min, service.parse_flag(query.todos)
    )


@bp.put(
    "/<string:deviceid>",
    summary="Calibra a faixa e gerencia vínculo/ativação do refrigerador (master)",
    responses={
        200: AtualizarDispositivoResponse,
        400: ErrorSchema,
        401: ErrorSchema,
        403: ErrorSchema,
        404: ErrorSchema,
    },
)
@master_required
def atualizar(path: DeviceIdPath, body: AtualizarDispositivoBody):
    """Campos omitidos não mudam; `id_empresa: null` desvincula."""
    enviados = {k: getattr(body, k) for k in body.model_fields_set}
    return service.atualizar(current_user(), path.deviceid, enviados)
