"""Consultas de usuário e sessão (SQL parametrizado)."""

from datetime import datetime
from typing import Optional

from app.db import execute, fetch_one, insert

_USUARIO_EMPRESA = (
    "SELECT u.id_usuario, u.nome, u.login, u.email_verificacao, u.telefone, u.perfil, u.ativo,"
    " e.id_empresa, e.nome AS empresa, e.tipo AS tipo_empresa,"
    " e.ativo AS empresa_ativo FROM usuario u JOIN empresa e ON e.id_empresa = u.id_empresa"
)


def buscar_para_login(login: str) -> Optional[dict]:
    return fetch_one(_USUARIO_EMPRESA + " WHERE u.login = %s", [login])


def buscar_por_id(id_usuario: int) -> Optional[dict]:
    return fetch_one(_USUARIO_EMPRESA + " WHERE u.id_usuario = %s", [id_usuario])


def registrar_login(id_usuario: int, quando: datetime) -> None:
    execute("UPDATE usuario SET ultimo_login = %s WHERE id_usuario = %s", [quando, id_usuario])


def criar_sessao(id_usuario, token_hash, expira_em, ip, user_agent, agora) -> int:
    return insert(
        "INSERT INTO sessao (id_usuario, token_hash, expira_em, ip, user_agent, ultimo_uso_em)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        [id_usuario, token_hash, expira_em, ip, (user_agent or "")[:255] or None, agora],
    )


def sessao_ativa(token_hash: str, agora: datetime) -> Optional[dict]:
    return fetch_one(
        "SELECT id_sessao, id_usuario, ultimo_uso_em FROM sessao"
        " WHERE token_hash = %s AND revogada_em IS NULL AND expira_em > %s",
        [token_hash, agora],
    )


def tocar_sessao(id_sessao: int, agora: datetime) -> None:
    execute("UPDATE sessao SET ultimo_uso_em = %s WHERE id_sessao = %s", [agora, id_sessao])


def revogar_sessao(token_hash: str, agora: datetime) -> None:
    execute(
        "UPDATE sessao SET revogada_em = %s WHERE token_hash = %s AND revogada_em IS NULL",
        [agora, token_hash],
    )


def revogar_sessoes_usuario(
    id_usuario: int, agora: datetime, exceto_hash: Optional[str] = None
) -> None:
    execute(
        "UPDATE sessao SET revogada_em = %s WHERE id_usuario = %s AND revogada_em IS NULL"
        " AND (%s IS NULL OR token_hash <> %s)",
        [agora, id_usuario, exceto_hash, exceto_hash],
    )


def limpar_sessoes_antigas(limite: datetime) -> None:
    execute(
        "DELETE FROM sessao WHERE expira_em < %s OR (revogada_em IS NOT NULL AND revogada_em < %s)",
        [limite, limite],
    )


# --- códigos do 2º fator (só o HMAC fica no banco) ---


def ultimo_codigo(id_usuario: int) -> Optional[dict]:
    return fetch_one(
        "SELECT id_codigo, criado_em FROM codigo_login WHERE id_usuario = %s ORDER BY id_codigo DESC LIMIT 1",
        [id_usuario],
    )


def contar_codigos_desde(id_usuario: int, desde: datetime) -> int:
    row = fetch_one(
        "SELECT COUNT(*) AS n FROM codigo_login WHERE id_usuario = %s AND criado_em >= %s",
        [id_usuario, desde],
    )
    return int(row["n"]) if row else 0


def invalidar_codigos(id_usuario: int, agora: datetime) -> None:
    execute(
        "UPDATE codigo_login SET usado_em = %s WHERE id_usuario = %s AND usado_em IS NULL",
        [agora, id_usuario],
    )


def criar_codigo(id_usuario: int, codigo_hash: str, expira_em: datetime, ip) -> int:
    return insert(
        "INSERT INTO codigo_login (id_usuario, codigo_hash, expira_em, ip) VALUES (%s, %s, %s, %s)",
        [id_usuario, codigo_hash, expira_em, ip],
    )


def codigo_ativo_para_update(id_usuario: int, agora: datetime) -> Optional[dict]:
    """Código vigente, com trava de linha (sem corrida entre tentativas simultâneas)."""
    return fetch_one(
        "SELECT id_codigo, codigo_hash, tentativas FROM codigo_login"
        " WHERE id_usuario = %s AND usado_em IS NULL AND expira_em > %s"
        " ORDER BY id_codigo DESC LIMIT 1 FOR UPDATE",
        [id_usuario, agora],
    )


def somar_tentativa(id_codigo: int, esgotar: bool, agora: datetime) -> None:
    execute(
        "UPDATE codigo_login SET tentativas = tentativas + 1,"
        " usado_em = IF(%s, %s, usado_em) WHERE id_codigo = %s",
        [1 if esgotar else 0, agora, id_codigo],
    )


def marcar_codigo_usado(id_codigo: int, agora: datetime) -> None:
    execute("UPDATE codigo_login SET usado_em = %s WHERE id_codigo = %s", [agora, id_codigo])


def limpar_codigos_antigos(limite: datetime) -> None:
    execute("DELETE FROM codigo_login WHERE criado_em < %s", [limite])
