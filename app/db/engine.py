"""Criação do engine SQLAlchemy a partir das Settings."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from app.config import Settings


def create_db_engine(settings: Settings) -> Engine:
    """Engine preguiçoso: não abre conexão até a primeira consulta (o app sobe mesmo sem banco)."""
    url = settings.sqlalchemy_url
    kwargs = {"echo": settings.db_echo, "future": True}

    if url.get_backend_name() == "sqlite":  # testes: um único banco em memória compartilhado
        from sqlalchemy import event
        from sqlalchemy.pool import StaticPool

        engine = create_engine(
            url,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
            **kwargs,
        )

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):  # o SQLite ignora FKs por padrão
            dbapi_connection.execute("PRAGMA foreign_keys=ON")

        return engine

    return create_engine(
        url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle,
        pool_pre_ping=True,  # descarta conexões mortas (a hospedagem derruba as ociosas)
        connect_args={"connect_timeout": settings.db_connect_timeout},
        **kwargs,
    )
