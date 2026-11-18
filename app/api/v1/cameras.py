"""Câmeras EZVIZ: `bp` (/v1/cameras) e `bp_ezviz` (/v1/ezviz: conta, coleta, status)."""

import base64
import hmac
import os

from flask import current_app, request, send_file
from flask_openapi3 import APIBlueprint, Tag

from app.core.auth import current_user, master_required, require_login_for_blueprint
from app.core.errors import AppError
from app.schemas.cameras import (
    AlarmePath,
    AlarmesQuery,
    AlarmesResponse,
    AoVivoQuery,
    CameraCadastroBody,
    CameraEdicaoBody,
    CameraListResponse,
    CameraPath,
    CameraSalvaResponse,
    ColetaResponse,
    ContaResponse,
    GravacaoQuery,
    LinkVideoResponse,
    ListarQuery,
    StatusResponse,
)
from app.schemas.common import ErrorResponse as ErrorSchema
from app.services import cameras as service

_TAG = [Tag(name="Câmeras")]
bp = APIBlueprint("cameras", __name__, url_prefix="/v1/cameras", abp_tags=_TAG)
bp_ezviz = APIBlueprint("ezviz", __name__, url_prefix="/v1/ezviz", abp_tags=_TAG)
require_login_for_blueprint(bp)  # sessão em todas as rotas de /cameras (401 antes da validação)


def _settings():
    return current_app.extensions["settings"]


def _flag(valor) -> bool:
    return valor in ("1", "true")


def _check_scheduler_auth() -> None:
    """Valida o segredo do agendador: header X-Scheduler-Secret ou Basic (senha)."""
    esperado = os.environ.get("SCHEDULER_SECRET") or _settings().scheduler_secret.get_secret_value()
    nao_autorizado = AppError("Não autorizado", status_code=401, code="unauthenticated")
    if not esperado:
        raise nao_autorizado
    if hmac.compare_digest(request.headers.get("X-Scheduler-Secret", ""), esperado):
        return
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            _, senha = base64.b64decode(auth[6:]).decode("utf-8").split(":", 1)
        except Exception:
            raise nao_autorizado from None
        if hmac.compare_digest(senha, esperado):
            return
    raise nao_autorizado


@bp.get(
    "",
    summary="Câmeras visíveis (master: todas; cliente: as dos refrigeradores da empresa)",
    responses={200: CameraListResponse, 401: ErrorSchema},
)
def listar(query: ListarQuery):
    """Lista as câmeras do usuário; `todas=1` (master) inclui as inativas."""
    return service.listar(current_user(), _flag(query.todas))


@bp.post(
    "",
    summary="Cadastra uma câmera da conta EZVIZ (master)",
    responses={
        201: CameraSalvaResponse,
        400: ErrorSchema,
        401: ErrorSchema,
        403: ErrorSchema,
        409: ErrorSchema,
    },
)
@master_required
def cadastrar(body: CameraCadastroBody):
    """Confirma a câmera na conta EZVIZ, vincula ao refrigerador e guarda o código cifrado."""
    resp = service.cadastrar(_settings(), current_user(), body.model_dump())
    return resp, 201


@bp.put(
    "/<int:id_camera>",
    summary="Edita nome, vínculo, código ou ativo (master)",
    responses={
        200: CameraSalvaResponse,
        400: ErrorSchema,
        401: ErrorSchema,
        403: ErrorSchema,
        404: ErrorSchema,
    },
)
@master_required
def editar(path: CameraPath, body: CameraEdicaoBody):
    """Altera só os campos enviados."""
    return service.editar(current_user(), path.id_camera, body.model_dump(exclude_unset=True))


@bp.get(
    "/<int:id_camera>/ao-vivo",
    summary="Link temporário de vídeo ao vivo",
    responses={200: LinkVideoResponse, 401: ErrorSchema, 404: ErrorSchema, 409: ErrorSchema},
)
def ao_vivo(path: CameraPath, query: AoVivoQuery):
    """O token da EZVIZ fica no backend; devolve só o link da câmera, válido por poucos minutos."""
    return service.ao_vivo(
        _settings(), current_user(), path.id_camera, query.qualidade, _flag(query.h265)
    )


@bp.get(
    "/<int:id_camera>/gravacao",
    summary="Link temporário de gravação (nuvem ou cartão)",
    responses={200: LinkVideoResponse, 400: ErrorSchema, 401: ErrorSchema, 404: ErrorSchema},
)
def gravacao(path: CameraPath, query: GravacaoQuery):
    """Trecho de até 6 horas, `inicio`/`fim` no formato YYYY-MM-DD HH:MM:SS."""
    return service.gravacao(
        _settings(),
        current_user(),
        path.id_camera,
        query.inicio,
        query.fim,
        query.origem,
        _flag(query.h265),
    )


@bp.get(
    "/<int:id_camera>/alarmes",
    summary="Alarmes importados da câmera",
    responses={200: AlarmesResponse, 401: ErrorSchema, 404: ErrorSchema},
)
def alarmes(path: CameraPath, query: AlarmesQuery):
    """Mais recentes primeiro; `limite` até 200."""
    return service.alarmes(current_user(), path.id_camera, query.limite, query.inicio, query.fim)


@bp.get(
    "/alarmes/<int:id_alarme>/foto",
    summary="Foto do alarme (JPEG)",
    responses={200: None, 401: ErrorSchema, 404: ErrorSchema},
)
def foto(path: AlarmePath):
    """Imagem do alarme, só para quem enxerga a câmera."""
    caminho = service.foto(current_user(), path.id_alarme)
    resp = send_file(caminho, mimetype="image/jpeg")
    resp.headers["Cache-Control"] = "private, max-age=86400"
    return resp


@bp_ezviz.get(
    "/conta",
    summary="Câmeras da conta EZVIZ e se já estão cadastradas (master)",
    responses={200: ContaResponse, 401: ErrorSchema, 403: ErrorSchema},
)
@master_required
def conta():
    """Consulta a conta EZVIZ."""
    return service.conta(_settings())


@bp_ezviz.post(
    "/coletar",
    summary="Coleta de status e alarmes (cron; exige X-Scheduler-Secret)",
    responses={200: ColetaResponse, 401: ErrorSchema},
)
def coletar():
    """Atualiza o status das câmeras e importa os alarmes novos com foto."""
    _check_scheduler_auth()
    return service.coletar(_settings())


@bp_ezviz.get(
    "/status",
    summary="Estado do token e últimas coletas (master)",
    responses={200: StatusResponse, 401: ErrorSchema, 403: ErrorSchema},
)
@master_required
def status():
    """Nunca devolve o valor do token."""
    return service.status(_settings())
