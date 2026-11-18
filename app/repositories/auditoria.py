"""Trilha de auditoria da gestão (quem fez o quê). Nunca grave senhas aqui."""

import json
from typing import Optional

from app.db import insert


def registrar(
    id_usuario: int, acao: str, entidade: str, id_entidade, detalhe: Optional[dict] = None
) -> int:
    return insert(
        "INSERT INTO auditoria (id_usuario, acao, entidade, id_entidade, detalhe) VALUES (%s, %s, %s, %s, %s)",
        [
            id_usuario,
            acao,
            entidade,
            str(id_entidade),
            json.dumps(detalhe or {}, ensure_ascii=False, default=str),
        ],
    )
