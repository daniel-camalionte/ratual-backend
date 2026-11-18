"""Consultas da gestão: empresas, usuários, auditoria e vínculo de refrigeradores."""

from typing import Optional

from app.db import execute, fetch_all, fetch_one, insert

# colunas que o service pode gravar (nome da coluna nunca vem do cliente)
_CAMPOS_EMPRESA = {"nome", "documento", "ativo", "id_plano"}
_CAMPOS_USUARIO = {"nome", "login", "telefone", "perfil", "ativo", "id_empresa"}
_CAMPOS_DISPOSITIVO = {"id_empresa", "ativo"}


def _set(campos: dict, permitidos: set) -> tuple:
    chaves = [k for k in campos if k in permitidos]
    return ", ".join(f"{k} = %s" for k in chaves), [campos[k] for k in chaves]


# ── empresas ─────────────────────────────────────────────────────────────


def listar_empresas() -> list:
    return fetch_all(
        "SELECT e.id_empresa, e.nome, e.documento, e.tipo, e.ativo, e.criado_em,"
        " p.id_plano, p.nome AS plano, p.desconto_servico,"
        " (SELECT COUNT(*) FROM usuario u"
        "  WHERE u.id_empresa = e.id_empresa AND u.ativo = 1) AS usuarios,"
        " (SELECT COUNT(*) FROM dispositivo d"
        "  WHERE d.id_empresa = e.id_empresa AND d.ativo = 1) AS dispositivos"
        " FROM empresa e LEFT JOIN plano p ON p.id_plano = e.id_plano"
        " ORDER BY e.tipo = 'master' DESC, e.nome"
    )


def buscar_empresa(id_empresa: int) -> Optional[dict]:
    return fetch_one("SELECT * FROM empresa WHERE id_empresa = %s", [id_empresa])


def documento_em_uso(documento: str, id_ignorar: Optional[int] = None) -> bool:
    rows = fetch_all("SELECT id_empresa FROM empresa WHERE documento = %s", [documento])
    return any(r["id_empresa"] != id_ignorar for r in rows)


def criar_empresa(nome: str, documento: Optional[str]) -> int:
    return insert(
        "INSERT INTO empresa (nome, documento, tipo, ativo) VALUES (%s, %s, 'cliente', 1)",
        [nome, documento],
    )


def atualizar_empresa(id_empresa: int, campos: dict) -> None:
    sets, params = _set(campos, _CAMPOS_EMPRESA)
    execute(f"UPDATE empresa SET {sets} WHERE id_empresa = %s", params + [id_empresa])  # noqa: S608


def buscar_plano(id_plano: int) -> Optional[dict]:
    return fetch_one("SELECT id_plano, ativo FROM plano WHERE id_plano = %s", [id_plano])


# ── usuários ─────────────────────────────────────────────────────────────


def listar_usuarios(id_empresa: Optional[int]) -> list:
    sql = (
        "SELECT u.id_usuario, u.nome, u.login, u.telefone, u.perfil, u.ativo,"
        " u.ultimo_login, u.criado_em, e.id_empresa, e.nome AS empresa, e.tipo AS tipo_empresa"
        " FROM usuario u JOIN empresa e ON e.id_empresa = u.id_empresa WHERE 1 = 1"
    )
    params: list = []
    if id_empresa is not None:
        sql += " AND u.id_empresa = %s"
        params.append(id_empresa)
    sql += " ORDER BY e.tipo = 'master' DESC, e.nome, u.nome"
    return fetch_all(sql, params)


def buscar_usuario(id_usuario: int) -> Optional[dict]:
    return fetch_one(
        "SELECT u.id_usuario, u.id_empresa, u.nome, u.login, u.telefone, u.perfil, u.ativo,"
        " e.tipo AS tipo_empresa FROM usuario u JOIN empresa e ON e.id_empresa = u.id_empresa"
        " WHERE u.id_usuario = %s",
        [id_usuario],
    )


def login_em_uso(login: str, id_ignorar: Optional[int] = None) -> bool:
    rows = fetch_all("SELECT id_usuario FROM usuario WHERE login = %s", [login])
    return any(r["id_usuario"] != id_ignorar for r in rows)


def criar_usuario(id_empresa, nome, login, telefone, perfil) -> int:
    return insert(
        "INSERT INTO usuario (id_empresa, nome, login, telefone, perfil, ativo)"
        " VALUES (%s, %s, %s, %s, %s, 1)",
        [id_empresa, nome, login, telefone, perfil],
    )


def atualizar_usuario(id_usuario: int, campos: dict) -> None:
    sets, params = _set(campos, _CAMPOS_USUARIO)
    execute(f"UPDATE usuario SET {sets} WHERE id_usuario = %s", params + [id_usuario])  # noqa: S608


# ── refrigeradores: vínculo e ativação ───────────────────────────────────


def atualizar_dispositivo(id_dispositivo: int, campos: dict) -> None:
    sets, params = _set(campos, _CAMPOS_DISPOSITIVO)
    execute(f"UPDATE dispositivo SET {sets} WHERE id_dispositivo = %s", params + [id_dispositivo])  # noqa: S608


# ── auditoria ────────────────────────────────────────────────────────────


def listar_auditoria(limite: int) -> list:
    return fetch_all(
        "SELECT a.id_auditoria, a.acao, a.entidade, a.id_entidade, a.detalhe, a.criado_em,"
        " u.nome AS usuario, u.login FROM auditoria a JOIN usuario u ON u.id_usuario = a.id_usuario"
        " ORDER BY a.id_auditoria DESC LIMIT %s",
        [limite],
    )
