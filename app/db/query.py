"""Acesso a dados com SQL parametrizado (placeholders `%s`), sobre a sessão da requisição.

Substitui o BaseModel/QueryBuilder do Brain: o SQL fica explícito nos repositories e os valores
vão SEMPRE como parâmetros (nunca concatenados). Linhas voltam como dict.
Escritas (`execute`/`insert`) confirmam a transação ao final, como no Brain; para várias escritas
atômicas use `get_session()` e `commit()` por conta própria.
"""

from collections.abc import Sequence
from typing import Any, Optional

from app.db.session import get_session


def _params(params: Optional[Sequence[Any]]) -> tuple:
    return tuple(params) if params else ()


def fetch_all(sql: str, params: Optional[Sequence[Any]] = None) -> list[dict]:
    result = get_session().connection().exec_driver_sql(sql, _params(params))
    return [dict(row) for row in result.mappings().all()]


def fetch_one(sql: str, params: Optional[Sequence[Any]] = None) -> Optional[dict]:
    result = get_session().connection().exec_driver_sql(sql, _params(params))
    row = result.mappings().first()
    return dict(row) if row is not None else None


def execute(sql: str, params: Optional[Sequence[Any]] = None, *, commit: bool = True) -> int:
    """UPDATE/DELETE/INSERT sem retorno de id. Devolve as linhas afetadas."""
    session = get_session()
    result = session.connection().exec_driver_sql(sql, _params(params))
    if commit:
        session.commit()
    return result.rowcount


def insert(sql: str, params: Optional[Sequence[Any]] = None, *, commit: bool = True) -> int:
    """INSERT; devolve o id gerado (AUTO_INCREMENT)."""
    session = get_session()
    result = session.connection().exec_driver_sql(sql, _params(params))
    if commit:
        session.commit()
    return int(result.lastrowid or 0)
