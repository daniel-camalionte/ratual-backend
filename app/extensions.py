"""Extensões e fábricas, inicializadas em create_app()."""

from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from app.config import Settings

cors = CORS()


def build_limiter(settings: Settings) -> Limiter:
    """Cria o limitador por app (evita estado compartilhado entre instâncias/testes)."""
    return Limiter(
        key_func=get_remote_address,
        default_limits=[settings.rate_limit_default],
        storage_uri=settings.rate_limit_storage_uri,
        headers_enabled=True,
        enabled=not settings.is_testing,
    )
