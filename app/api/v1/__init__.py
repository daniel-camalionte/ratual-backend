from flask_openapi3 import APIBlueprint, Tag

bp = APIBlueprint("v1", __name__, url_prefix="/v1", abp_tags=[Tag(name="Sistema")])

from app.api.v1 import hello  # noqa: E402,F401  (registra as rotas no blueprint)
from app.api.v1.auth import bp as auth_bp  # noqa: E402

__all__ = ["auth_bp", "bp"]
