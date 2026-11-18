from flask_openapi3 import OpenAPI

from app.api import health
from app.api.v1 import bp as v1_bp


def register_blueprints(app: OpenAPI) -> None:
    app.register_api(health.bp)
    app.register_api(v1_bp)
