"""Verificação de saúde (monitoramento). Não expõe informações internas."""

from flask_openapi3 import APIBlueprint, Tag

from app.schemas.system import HealthResponse
from app.version import SERVICE_NAME, __version__

bp = APIBlueprint("health", __name__, abp_tags=[Tag(name="Sistema")])


@bp.get("/health", summary="Liveness", responses={200: HealthResponse})
def liveness():
    """Indica que o processo está de pé. Isento de rate limit."""
    return HealthResponse(status="ok", service=SERVICE_NAME, version=__version__).model_dump()
