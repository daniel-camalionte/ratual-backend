"""Central de serviços: planos, tipos, técnicos, grade e bloqueios (master) e catálogo."""

from flask_openapi3 import APIBlueprint, Tag

from app.core.auth import current_user, master_required, require_login_for_blueprint
from app.schemas.common import ErrorResponse as ErrorSchema
from app.schemas.servicos import (
    BloqueioCreate,
    BloqueioListResponse,
    BloqueioPath,
    CatalogoQuery,
    CatalogoResponse,
    IdPath,
    JanelaCreate,
    JanelaListResponse,
    JanelaUpdate,
    MsgIdResponse,
    PlanoCreate,
    PlanoListResponse,
    PlanoUpdate,
    TecnicoCreate,
    TecnicoListResponse,
    TecnicoUpdate,
    TipoServicoCreate,
    TipoServicoListResponse,
    TipoServicoUpdate,
)
from app.services import servicos as service

bp = APIBlueprint(
    "servicos", __name__, url_prefix="/v1", abp_tags=[Tag(name="Central de serviços")]
)
require_login_for_blueprint(bp)

_ERROS = {400: ErrorSchema, 401: ErrorSchema, 403: ErrorSchema}


def _dados(body) -> dict:
    return body.model_dump(exclude_unset=True)


# ── planos ───────────────────────────────────────────────────────────────


@bp.get("/planos", summary="Lista os planos (master)", responses={200: PlanoListResponse, **_ERROS})
@master_required
def listar_planos():
    """Planos com a quantidade de clientes ativos em cada um."""
    return service.listar("plano")


@bp.post(
    "/planos",
    summary="Cria um plano (master)",
    responses={201: MsgIdResponse, 409: ErrorSchema, **_ERROS},
)
@master_required
def criar_plano(body: PlanoCreate):
    """Nome único; desconto em serviços em percentual."""
    return service.criar(current_user(), "plano", _dados(body)), 201


@bp.put(
    "/planos/<int:id_item>",
    summary="Altera um plano (master)",
    responses={200: MsgIdResponse, 404: ErrorSchema, 409: ErrorSchema, **_ERROS},
)
@master_required
def editar_plano(path: IdPath, body: PlanoUpdate):
    """Altera só os campos enviados; para tirar de uso, envie ativo=false."""
    return service.editar(current_user(), "plano", path.id_item, _dados(body))


# ── tipos de serviço ─────────────────────────────────────────────────────


@bp.get(
    "/tipos-servico",
    summary="Lista os tipos de serviço (master)",
    responses={200: TipoServicoListResponse, **_ERROS},
)
@master_required
def listar_tipos():
    """Todos os tipos, ativos primeiro."""
    return service.listar("tipo_servico")


@bp.post(
    "/tipos-servico",
    summary="Cria um tipo de serviço (master)",
    responses={201: MsgIdResponse, **_ERROS},
)
@master_required
def criar_tipo(body: TipoServicoCreate):
    """Valor base em reais; `cliente_pode_solicitar` libera o pedido pelo app."""
    return service.criar(current_user(), "tipo_servico", _dados(body)), 201


@bp.put(
    "/tipos-servico/<int:id_item>",
    summary="Altera um tipo de serviço (master)",
    responses={200: MsgIdResponse, 404: ErrorSchema, **_ERROS},
)
@master_required
def editar_tipo(path: IdPath, body: TipoServicoUpdate):
    """Altera só os campos enviados; ordens já abertas mantêm o valor gravado."""
    return service.editar(current_user(), "tipo_servico", path.id_item, _dados(body))


# ── técnicos ─────────────────────────────────────────────────────────────


@bp.get(
    "/tecnicos",
    summary="Lista os técnicos (master)",
    responses={200: TecnicoListResponse, **_ERROS},
)
@master_required
def listar_tecnicos():
    """Todos os técnicos, ativos primeiro."""
    return service.listar("tecnico")


@bp.post("/tecnicos", summary="Cria um técnico (master)", responses={201: MsgIdResponse, **_ERROS})
@master_required
def criar_tecnico(body: TecnicoCreate):
    """Cadastra um técnico de campo."""
    return service.criar(current_user(), "tecnico", _dados(body)), 201


@bp.put(
    "/tecnicos/<int:id_item>",
    summary="Altera um técnico (master)",
    responses={200: MsgIdResponse, 404: ErrorSchema, **_ERROS},
)
@master_required
def editar_tecnico(path: IdPath, body: TecnicoUpdate):
    """Altera só os campos enviados; para afastar, envie ativo=false."""
    return service.editar(current_user(), "tecnico", path.id_item, _dados(body))


# ── grade da agenda ──────────────────────────────────────────────────────


@bp.get(
    "/agenda/grade",
    summary="Lista as janelas da grade (master)",
    responses={200: JanelaListResponse, **_ERROS},
)
@master_required
def listar_janelas():
    """Janelas semanais de atendimento (0 = domingo)."""
    return service.listar("janela")


@bp.post(
    "/agenda/grade",
    summary="Cria uma janela da grade (master)",
    responses={201: MsgIdResponse, 409: ErrorSchema, **_ERROS},
)
@master_required
def criar_janela(body: JanelaCreate):
    """Janelas ativas do mesmo dia não podem se sobrepor."""
    return service.criar(current_user(), "janela", _dados(body)), 201


@bp.put(
    "/agenda/grade/<int:id_item>",
    summary="Altera uma janela da grade (master)",
    responses={200: MsgIdResponse, 404: ErrorSchema, 409: ErrorSchema, **_ERROS},
)
@master_required
def editar_janela(path: IdPath, body: JanelaUpdate):
    """Altera só os campos enviados."""
    return service.editar(current_user(), "janela", path.id_item, _dados(body))


@bp.delete(
    "/agenda/grade/<int:id_item>",
    summary="Remove uma janela da grade (master)",
    responses={200: MsgIdResponse, 404: ErrorSchema, **_ERROS},
)
@master_required
def remover_janela(path: IdPath):
    """Apaga a janela (ordens já agendadas não são afetadas)."""
    return service.remover_janela(current_user(), path.id_item)


# ── bloqueios de agenda ──────────────────────────────────────────────────


@bp.get(
    "/agenda/bloqueios",
    summary="Lista as datas bloqueadas (master)",
    responses={200: BloqueioListResponse, **_ERROS},
)
@master_required
def listar_bloqueios():
    """Datas bloqueadas de hoje em diante."""
    return service.listar_bloqueios()


@bp.post(
    "/agenda/bloqueios",
    summary="Bloqueia uma data (master)",
    responses={201: MsgIdResponse, 409: ErrorSchema, **_ERROS},
)
@master_required
def criar_bloqueio(body: BloqueioCreate):
    """Feriado, folga ou outro motivo: a data some da disponibilidade."""
    return service.criar_bloqueio(current_user(), _dados(body)), 201


@bp.delete(
    "/agenda/bloqueios/<int:id_bloqueio>",
    summary="Libera uma data bloqueada (master)",
    responses={200: MsgIdResponse, 404: ErrorSchema, **_ERROS},
)
@master_required
def remover_bloqueio(path: BloqueioPath):
    """Remove o bloqueio da data."""
    return service.remover_bloqueio(current_user(), path.id_bloqueio)


# ── catálogo ─────────────────────────────────────────────────────────────


@bp.get(
    "/servicos/catalogo",
    summary="Serviços que o cliente pode pedir, com o desconto do plano",
    responses={200: CatalogoResponse, 401: ErrorSchema},
)
def catalogo(query: CatalogoQuery):
    """Cliente: tipos liberados para pedido. Master: todos os ativos (simula uma empresa)."""
    return service.catalogo(current_user(), query.id_empresa)
