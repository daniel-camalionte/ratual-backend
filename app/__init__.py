from typing import Optional

from flask_openapi3 import Info, OpenAPI, Server

from app.api import register_blueprints
from app.config import Settings, get_settings
from app.core.errors import register_error_handlers, validation_error_response
from app.core.http import register_http_hooks
from app.core.logging import configure_logging
from app.extensions import build_limiter, cors
from app.schemas.common import ErrorResponse
from app.version import __version__


def create_app(settings: Optional[Settings] = None) -> OpenAPI:
    """Application factory: cria e configura a aplicação Flask (com OpenAPI/Swagger)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = OpenAPI(
        __name__,
        info=Info(
            title="Ratual API",
            version=__version__,
            description="API do Ratual.",
        ),
        servers=[Server(url=settings.openapi_base_path or "/")],
        responses={429: ErrorResponse, 500: ErrorResponse},
        validation_error_callback=validation_error_response,
        doc_ui=settings.docs_on,  # desligado => nem a UI nem o openapi.json são expostos
        doc_prefix="/docs",
        doc_url="/openapi.json",
    )
    app.config.update(
        SECRET_KEY=settings.secret_key,
        MAX_CONTENT_LENGTH=settings.max_content_length,
        TESTING=settings.is_testing,
        JSON_SORT_KEYS=False,
    )
    app.extensions["settings"] = settings

    register_http_hooks(app, is_production=settings.is_production)
    cors.init_app(
        app,
        resources={r"/v1/*": {"origins": settings.cors_origin_list}},
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
        max_age=600,
        supports_credentials=True,  # cookie de sessão (etapa de autenticação); origens restritas
    )
    limiter = build_limiter(settings)
    limiter.init_app(app)
    app.extensions["limiter"] = limiter
    register_error_handlers(app)
    register_blueprints(app)
    limiter.exempt(app.blueprints["health"])  # monitoramento não consome cota
    return app
