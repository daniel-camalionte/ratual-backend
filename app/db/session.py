"""Sessão do SQLAlchemy por requisição, integrada ao Flask.

Uso nas rotas/serviços:

    from app.db import get_session
    session = get_session()
    session.execute(...)

A sessão é criada sob demanda e, ao fim da requisição, sofre rollback (se não houve commit
explícito) e é devolvida ao pool. Quem altera dados deve chamar `session.commit()`.
"""

from typing import Optional

from flask import Flask, current_app, g
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.engine import create_db_engine

_ENGINE_KEY = "db_engine"
_FACTORY_KEY = "db_session_factory"


def init_db(app: Flask, settings: Settings) -> None:
    """Registra engine e fábrica de sessões no app (se o banco estiver configurado)."""
    if not settings.database_configured:
        app.logger.warning("database_not_configured")
        return

    engine = create_db_engine(settings)
    app.extensions[_ENGINE_KEY] = engine
    app.extensions[_FACTORY_KEY] = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    @app.teardown_appcontext
    def _close_session(_exc: Optional[BaseException]) -> None:
        session = g.pop("db_session", None)
        if session is not None:
            session.rollback()  # nada pendente vaza para a próxima requisição
            session.close()


def get_engine() -> Optional[Engine]:
    return current_app.extensions.get(_ENGINE_KEY)


def get_session() -> Session:
    """Sessão da requisição atual. Levanta RuntimeError se o banco não estiver configurado."""
    factory = current_app.extensions.get(_FACTORY_KEY)
    if factory is None:
        raise RuntimeError("Banco de dados não configurado (defina DB_* no .env).")
    if "db_session" not in g:
        g.db_session = factory()
    return g.db_session
