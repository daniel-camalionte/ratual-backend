"""Gestão: empresas, usuários, auditoria e vínculo de refrigeradores. Tudo é auditado.

Permissões:
- empresas, auditoria e vínculo de refrigeradores: somente empresa master
- usuários: admin da master (todas as empresas) ou admin do cliente (somente a própria empresa)
"""

import json
import re
from typing import Optional

from app.core.auth import is_master
from app.core.errors import AppError
from app.repositories import auditoria
from app.repositories import gestao as repo

PERFIS = ("admin", "operador", "visualizador")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
TELEFONE = re.compile(r"^\d{10,13}$")


def _invalido(msg: str, status: int = 400, code: str = "bad_request") -> AppError:
    return AppError(msg, status_code=status, code=code)


def _fmt(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _e_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _texto(body: dict, chave: str, obrigatorio: bool = False, maximo: int = 150) -> Optional[str]:
    if chave not in body:
        if obrigatorio:
            raise _invalido(f"{chave} é obrigatório")
        return None
    v = body[chave]
    if not isinstance(v, str) or not v.strip():
        raise _invalido(f"{chave} não pode ficar vazio")
    v = v.strip()
    if len(v) > maximo:
        raise _invalido(f"{chave} deve ter no máximo {maximo} caracteres")
    return v


def _telefone(body: dict) -> Optional[str]:
    """Telefone opcional: guarda só os dígitos; vazio vira None."""
    v = body.get("telefone")
    if v in (None, ""):
        return None
    if not isinstance(v, str):
        raise _invalido("telefone inválido")
    digitos = re.sub(r"\D", "", v)
    if not digitos:
        return None
    if not TELEFONE.match(digitos):
        raise _invalido("telefone deve ter DDD e número (10 a 13 dígitos)")
    return digitos


def _login(body: dict, obrigatorio: bool) -> Optional[str]:
    login = _texto(body, "login", obrigatorio=obrigatorio)
    if login is None:
        return None
    login = login.lower()
    if not EMAIL.match(login):
        raise _invalido("login deve ser um e-mail válido")
    return login


def _ativo(body: dict) -> int:
    if not isinstance(body["ativo"], bool):
        raise _invalido("ativo deve ser true ou false")
    return 1 if body["ativo"] else 0


def _empresa_ativa(id_empresa) -> Optional[dict]:
    if not _e_int(id_empresa):
        return None
    e = repo.buscar_empresa(id_empresa)
    return e if e and e["ativo"] else None


# ── empresas (master) ────────────────────────────────────────────────────


def listar_empresas() -> dict:
    rows = repo.listar_empresas()
    return {
        "total": len(rows),
        "empresas": [
            {
                "id_empresa": r["id_empresa"],
                "nome": r["nome"],
                "documento": r["documento"],
                "tipo": r["tipo"],
                "ativo": bool(r["ativo"]),
                "usuarios": int(r["usuarios"]),
                "dispositivos": int(r["dispositivos"]),
                "plano": {
                    "id_plano": r["id_plano"],
                    "nome": r["plano"],
                    "desconto_servico": float(r["desconto_servico"]),
                }
                if r["id_plano"]
                else None,
                "criado_em": _fmt(r["criado_em"]),
            }
            for r in rows
        ],
    }


def criar_empresa(autor: dict, body: dict) -> dict:
    nome = _texto(body, "nome", obrigatorio=True)
    documento = _texto(body, "documento", maximo=20)
    if documento and repo.documento_em_uso(documento):
        raise _invalido("Já existe uma empresa com esse documento", 409, "conflict")
    id_empresa = repo.criar_empresa(nome, documento)
    auditoria.registrar(
        autor["id_usuario"],
        "empresa_criada",
        "empresa",
        id_empresa,
        {"nome": nome, "documento": documento},
    )
    return {"msg": "Empresa criada", "id_empresa": id_empresa}


def editar_empresa(autor: dict, id_empresa: int, body: dict) -> dict:
    atual = repo.buscar_empresa(id_empresa)
    if not atual:
        raise _invalido("Empresa não encontrada", 404, "not_found")

    campos: dict = {}
    nome = _texto(body, "nome")
    if nome is not None:
        campos["nome"] = nome
    if "documento" in body:
        if body["documento"] in (None, ""):
            campos["documento"] = None
        else:
            documento = _texto(body, "documento", maximo=20)
            if repo.documento_em_uso(documento, id_empresa):
                raise _invalido("Já existe uma empresa com esse documento", 409, "conflict")
            campos["documento"] = documento
    if "ativo" in body:
        ativo = _ativo(body)
        if not ativo and atual["tipo"] == "master":
            raise _invalido("A empresa master não pode ser desativada")
        campos["ativo"] = ativo
    if "id_plano" in body:
        id_plano = body["id_plano"]
        if id_plano is not None:
            if not _e_int(id_plano):
                raise _invalido("id_plano deve ser um número")
            plano = repo.buscar_plano(id_plano)
            if not plano or not plano["ativo"]:
                raise _invalido("Plano não encontrado ou inativo")
        campos["id_plano"] = id_plano
    if not campos:
        raise _invalido("Envie ao menos um campo: nome, documento, ativo, id_plano")

    repo.atualizar_empresa(id_empresa, campos)
    antes = {k: atual[k] for k in campos}
    auditoria.registrar(
        autor["id_usuario"],
        "empresa_alterada",
        "empresa",
        id_empresa,
        {"antes": antes, "depois": campos},
    )
    return {"msg": "Empresa atualizada", "id_empresa": id_empresa}


# ── usuários (admin) ─────────────────────────────────────────────────────


def listar_usuarios(autor: dict, id_empresa: Optional[int] = None) -> dict:
    # admin do cliente: só a própria empresa; a master pode filtrar
    escopo = id_empresa if is_master(autor) else autor["id_empresa"]
    rows = repo.listar_usuarios(escopo)
    return {
        "total": len(rows),
        "usuarios": [
            {
                "id_usuario": r["id_usuario"],
                "nome": r["nome"],
                "login": r["login"],
                "telefone": r["telefone"],
                "perfil": r["perfil"],
                "ativo": bool(r["ativo"]),
                "ultimo_login": _fmt(r["ultimo_login"]),
                "criado_em": _fmt(r["criado_em"]),
                "empresa": {
                    "id_empresa": r["id_empresa"],
                    "nome": r["empresa"],
                    "tipo": r["tipo_empresa"],
                },
                "eu": r["id_usuario"] == autor["id_usuario"],
            }
            for r in rows
        ],
    }


def criar_usuario(autor: dict, body: dict) -> dict:
    nome = _texto(body, "nome", obrigatorio=True)
    login = _login(body, obrigatorio=True)
    perfil = body.get("perfil", "visualizador")
    if perfil not in PERFIS:
        raise _invalido(f"perfil deve ser um de: {', '.join(PERFIS)}")
    telefone = _telefone(body)

    # admin do cliente sempre cria na própria empresa; master escolhe
    id_empresa = body.get("id_empresa") if is_master(autor) else autor["id_empresa"]
    if not _e_int(id_empresa):
        raise _invalido("id_empresa é obrigatório")
    if not _empresa_ativa(id_empresa):
        raise _invalido("Empresa não encontrada ou inativa")
    if repo.login_em_uso(login):
        raise _invalido("Já existe um usuário com esse e-mail", 409, "conflict")

    id_usuario = repo.criar_usuario(id_empresa, nome, login, telefone, perfil)
    auditoria.registrar(
        autor["id_usuario"],
        "usuario_criado",
        "usuario",
        id_usuario,
        {"login": login, "perfil": perfil, "id_empresa": id_empresa},
    )
    return {
        "msg": "Usuário criado. Ele entra com o e-mail e o código enviado para ele.",
        "id_usuario": id_usuario,
    }


def _alvo(autor: dict, id_usuario: int) -> dict:
    """Usuário que o autor pode gerenciar; de outra empresa responde como inexistente (404)."""
    alvo = repo.buscar_usuario(id_usuario)
    if not alvo or (not is_master(autor) and alvo["id_empresa"] != autor["id_empresa"]):
        raise _invalido("Usuário não encontrado", 404, "not_found")
    return alvo


def editar_usuario(autor: dict, id_usuario: int, body: dict) -> dict:
    alvo = _alvo(autor, id_usuario)
    proprio = alvo["id_usuario"] == autor["id_usuario"]

    campos: dict = {}
    nome = _texto(body, "nome")
    if nome is not None:
        campos["nome"] = nome
    login = _login(body, obrigatorio=False)
    if login is not None:
        if repo.login_em_uso(login, id_usuario):
            raise _invalido("Já existe um usuário com esse e-mail", 409, "conflict")
        campos["login"] = login
    if "telefone" in body:
        campos["telefone"] = _telefone(body)
    if "perfil" in body:
        if body["perfil"] not in PERFIS:
            raise _invalido(f"perfil deve ser um de: {', '.join(PERFIS)}")
        if proprio and body["perfil"] != "admin":
            raise _invalido("Você não pode remover o seu próprio perfil de administrador")
        campos["perfil"] = body["perfil"]
    if "ativo" in body:
        ativo = _ativo(body)
        if proprio and not ativo:
            raise _invalido("Você não pode desativar o seu próprio usuário")
        campos["ativo"] = ativo
    if "id_empresa" in body:
        if not is_master(autor):
            raise _invalido(
                "Somente a empresa master pode mover usuários de empresa", 403, "forbidden"
            )
        if proprio:
            raise _invalido("Você não pode mover o seu próprio usuário de empresa")
        if not _empresa_ativa(body["id_empresa"]):
            raise _invalido("Empresa não encontrada ou inativa")
        campos["id_empresa"] = body["id_empresa"]
    if not campos:
        raise _invalido("Envie ao menos um campo: nome, login, telefone, perfil, ativo, id_empresa")

    repo.atualizar_usuario(id_usuario, campos)
    antes = {k: alvo[k] for k in campos}
    auditoria.registrar(
        autor["id_usuario"],
        "usuario_alterado",
        "usuario",
        id_usuario,
        {"antes": antes, "depois": campos},
    )
    return {"msg": "Usuário atualizado", "id_usuario": id_usuario}


# ── refrigeradores: vínculo e ativação (master) ──────────────────────────


def vincular_dispositivo(autor: dict, dispositivo: dict, body: dict) -> Optional[dict]:
    """Uso interno do módulo de dispositivos (rota lá, só master). `dispositivo`: linha atual com
    id_dispositivo, deviceid, id_empresa, ativo. Aceita id_empresa (int ou null) e ativo.
    Retorna os campos gravados, ou None se nada foi enviado."""
    campos: dict = {}
    if "id_empresa" in body:
        id_empresa = body["id_empresa"]
        if id_empresa is not None:
            if not _e_int(id_empresa):
                raise _invalido("id_empresa deve ser um número ou null")
            empresa = _empresa_ativa(id_empresa)
            if not empresa:
                raise _invalido("Empresa não encontrada ou inativa")
            if empresa["tipo"] == "master":
                raise _invalido("Vincule o refrigerador a um cliente (a master já vê todos)")
        campos["id_empresa"] = id_empresa
    if "ativo" in body:
        campos["ativo"] = _ativo(body)
    if not campos:
        return None
    repo.atualizar_dispositivo(dispositivo["id_dispositivo"], campos)
    antes = {k: dispositivo[k] for k in campos}
    auditoria.registrar(
        autor["id_usuario"],
        "dispositivo_alterado",
        "dispositivo",
        dispositivo["deviceid"],
        {"antes": antes, "depois": campos},
    )
    return campos


# ── auditoria (master) ───────────────────────────────────────────────────


def listar_auditoria(limite) -> dict:
    try:
        limite = min(500, max(1, int(limite)))
    except (TypeError, ValueError):
        raise _invalido("limite deve ser inteiro") from None
    registros = []
    for r in repo.listar_auditoria(limite):
        det = r["detalhe"]
        if isinstance(det, (str, bytes)):
            try:
                det = json.loads(det or "{}")
            except ValueError:
                det = {}
        registros.append(
            {
                "id_auditoria": r["id_auditoria"],
                "acao": r["acao"],
                "entidade": r["entidade"],
                "id_entidade": r["id_entidade"],
                "detalhe": det if isinstance(det, dict) else {},
                "quando": _fmt(r["criado_em"]),
                "usuario": {"nome": r["usuario"], "login": r["login"]},
            }
        )
    return {"total": len(registros), "registros": registros}
