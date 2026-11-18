from app.api.v1 import bp
from app.schemas.system import HelloResponse
from app.version import SERVICE_NAME, __version__


@bp.get("/hello", summary="Hello world", responses={200: HelloResponse})
def hello():
    """Rota de teste: confirma que a API está respondendo."""
    return HelloResponse(
        message="Hello, World!", service=SERVICE_NAME, version=__version__
    ).model_dump()
