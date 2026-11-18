"""Integração eWeLink: OAuth da conta, coleta periódica (cron), gráfico e relé dos refrigeradores."""  # noqa: E501

import base64
import hmac
from typing import Optional

from flask import current_app, request
from flask_openapi3 import APIBlueprint, Tag

from app.core.auth import current_user, login_required, master_required
from app.core.errors import AppError
from app.schemas.common import ErrorResponse as ErrorSchema
from app.schemas.ewelink import (
    AuthResponse,
    CallbackQuery,
    CallbackResponse,
    ColetaResponse,
    ColetaStatusResponse,
    DispositivosEwelinkResponse,
    GraficoPath,
    GraficoQuery,
    GraficoResponse,
    ReleBody,
    ReleResponse,
)
from app.services import ewelink as service

bp = APIBlueprint("ewelink", __name__, url_prefix="/v1/ewelink", abp_tags=[Tag(name="eWeLink")])

# sem sessão: o callback é chamado pela eWeLink (protegido pelo state) e a coleta, pela cron (secret)  # noqa: E501
_PUBLICAS = {"ewelink.callback", "ewelink.coletar"}


@bp.before_request
def _exigir_sessao():
    """Sessão em todas as rotas (exceto as públicas) ANTES da validação do corpo: 401, não 422."""
    if request.method == "OPTIONS" or request.endpoint in _PUBLICAS:
        return None
    login_required(lambda: None)()
    return None


def _scheduler_autorizado(segredo: str) -> bool:
    """Valida o SCHEDULER_SECRET via X-Scheduler-Secret ou HTTP Basic (a senha)."""
    if not segredo:
        return False
    esperado = segredo.encode()
    enviado = request.headers.get("X-Scheduler-Secret")
    if enviado is not None and hmac.compare_digest(enviado.encode(), esperado):
        return True
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Basic "):
        try:
            _, senha = base64.b64decode(auth[6:]).decode("utf-8").split(":", 1)
        except Exception:  # noqa: BLE001 - cabeçalho malformado = não autorizado
            return False
        return hmac.compare_digest(senha.encode(), esperado)
    return False


def _settings():
    return current_app.extensions["settings"]


@bp.get(
    "/auth",
    summary="Gera a URL de login da conta eWeLink (só master)",
    responses={200: AuthResponse, 401: ErrorSchema, 403: ErrorSchema},
)
@master_required
def auth():
    """Abra a URL devolvida no navegador e faça login na eWeLink; ela volta para /ewelink/callback."""  # noqa: E501
    return service.auth(_settings())


@bp.get(
    "/callback",
    summary="Retorno do OAuth (chamado pela eWeLink; protegido pelo state)",
    responses={200: CallbackResponse, 400: ErrorSchema},
)
def callback(query: CallbackQuery):
    """Troca o code por tokens e guarda-os criptografados. Sem sessão: vale o state de /ewelink/auth."""  # noqa: E501
    return service.callback(_settings(), query.code, query.region, query.state)


@bp.get(
    "/dispositivos",
    summary="Diagnóstico: dispositivos direto da eWeLink (só master)",
    responses={
        200: DispositivosEwelinkResponse,
        401: ErrorSchema,
        403: ErrorSchema,
        503: ErrorSchema,
    },
)
@master_required
def dispositivos():
    """O app usa GET /v1/dispositivos (lê do banco); esta rota consulta a eWeLink ao vivo."""
    return service.dispositivos(_settings(), current_user())


@bp.post(
    "/coletar",
    summary="Coleta uma leitura de cada dispositivo (cron; exige SCHEDULER_SECRET)",
    responses={200: ColetaResponse, 401: ErrorSchema, 503: ErrorSchema},
)
def coletar():
    """Chamada pela cron com o header X-Scheduler-Secret (ou Basic com o segredo como senha)."""
    if not _scheduler_autorizado(_settings().scheduler_secret.get_secret_value()):
        raise AppError("Não autorizado", status_code=401, code="unauthenticated")
    return service.coletar(_settings())


@bp.get(
    "/coleta/status",
    summary="Saúde da coleta: última execução, atraso e sessão eWeLink (só master)",
    responses={200: ColetaStatusResponse, 401: ErrorSchema, 403: ErrorSchema},
)
@master_required
def coleta_status():
    return service.status_coleta(_settings())


@bp.get(
    "/dispositivo/<deviceid>/grafico",
    summary="Série de leituras de um refrigerador para o gráfico",
    responses={200: GraficoResponse, 400: ErrorSchema, 401: ErrorSchema, 404: ErrorSchema},
)
@login_required
def grafico(path: GraficoPath, query: GraficoQuery):
    """Master vê qualquer refrigerador; cliente, só os da própria empresa (outro = 404)."""
    return service.grafico(current_user(), path.deviceid, query.horas, query.inicio, query.fim)


@bp.post(
    "/dispositivo/<deviceid>/rele",
    summary="Liga ou desliga o compressor (só admin; fica na auditoria de comandos)",
    responses={
        200: ReleResponse, 400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema,
        404: ErrorSchema, 409: ErrorSchema, 502: ErrorSchema,
    },
)  # fmt: skip
@login_required
def rele(path: GraficoPath, body: ReleBody):
    ligado: Optional[object] = body.ligado
    return service.alterar_rele(_settings(), current_user(), path.deviceid, ligado)
