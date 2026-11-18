from flask_openapi3 import OpenAPI

from app.api import health
from app.api.v1 import auth_bp
from app.api.v1 import bp as v1_bp


def register_blueprints(app: OpenAPI, limiter=None, auth_rate_limit: str = "10 per minute") -> None:
    app.register_api(health.bp)
    app.register_api(v1_bp)
    if limiter is not None:
        # limite mais rígido (por IP) só nos POSTs de autenticação (força bruta)
        limiter.limit(auth_rate_limit, methods=["POST"])(auth_bp)
    app.register_api(auth_bp)
