"""Integração HTTP da autenticação: cookie de sessão, usuário atual, perfis e proteção contra CSRF."""

from functools import wraps
from typing import Optional

from flask import Flask, Response, current_app, g, request

from app.config import Settings
from app.core.errors import AppError
from app.services import auth as auth_service

_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _settings() -> Settings:
    return current_app.extensions["settings"]


def set_session_cookie(response: Response, token: str) -> None:
    s = _settings()
    response.set_cookie(
        s.auth_cookie_name,
        token,
        max_age=s.auth_session_days * 86400,
        httponly=True,  # invisível ao JavaScript (mitiga roubo via XSS)
        secure=s.cookie_secure,  # só HTTPS em produção
        samesite="Lax",  # não vai em POSTs de outros sites (mitiga CSRF)
        path=s.openapi_base_path or "/",  # só vai para a API
    )


def clear_session_cookie(response: Response) -> None:
    s = _settings()
    response.delete_cookie(
        s.auth_cookie_name,
        path=s.openapi_base_path or "/",
        httponly=True,
        secure=s.cookie_secure,
        samesite="Lax",
    )


def current_token() -> Optional[str]:
    return request.cookies.get(_settings().auth_cookie_name)


def current_user() -> Optional[dict]:
    """Usuário da requisição (resolvido uma vez): id_usuario, id_empresa, tipo_empresa, perfil..."""
    if "current_user" in g:
        return g.current_user
    token = current_token()
    row = auth_service.usuario_da_sessao(token) if token else None
    g.current_user = (
        {
            "id_usuario": row["id_usuario"],
            "id_empresa": row["id_empresa"],
            "tipo_empresa": row["tipo_empresa"],
            "perfil": row["perfil"],
        }
        if row
        else None
    )
    return g.current_user


usuario_atual = current_user


def is_master(usuario: dict) -> bool:
    return usuario.get("tipo_empresa") == "master"


def is_admin(usuario: dict) -> bool:
    return usuario.get("perfil") == "admin"


def _exigir_login() -> dict:
    u = current_user()
    if u is None:
        raise AppError("Não autenticado.", status_code=401, code="unauthenticated")
    return u


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        _exigir_login()
        return view(*args, **kwargs)

    return wrapper


def master_required(view):
    """Só usuários da empresa master (ex.: conectar a conta eWeLink, cadastro de empresas)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_master(_exigir_login()):
            raise AppError("Acesso restrito à empresa master", status_code=403, code="forbidden")
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    """Gestão de usuários: admin da master (todas as empresas) ou admin do cliente (a própria)."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin(_exigir_login()):
            raise AppError("Acesso restrito a administradores", status_code=403, code="forbidden")
        return view(*args, **kwargs)

    return wrapper


def require_login_for_blueprint(blueprint) -> None:
    """Exige sessão em TODAS as rotas do blueprint ANTES da validação do corpo (401, não 422)."""

    @blueprint.before_request
    def _guard():
        if request.method == "OPTIONS":  # preflight do CORS não carrega cookie
            return None
        _exigir_login()
        return None


def register_origin_check(app: Flask, settings: Settings) -> None:
    """Defesa em profundidade contra CSRF: escrita vinda de navegador só passa de origem permitida."""
    allowed = set(settings.cors_origin_list)

    @app.before_request
    def _check_origin():
        if request.method not in _UNSAFE_METHODS:
            return None
        origin = request.headers.get("Origin")
        if origin is not None and origin not in allowed:
            raise AppError("Origem não permitida.", status_code=403, code="forbidden_origin")
        return None


def register_docs_guard(app: Flask, settings: Settings) -> None:
    """Em produção, o Swagger (/docs/*) só abre para usuário master logado; os demais veem 404.

    Ele lista todas as rotas e formatos da API: não deve ficar público. Em desenvolvimento/STG fica livre.
    O cookie de sessão é enviado porque o Swagger é servido sob o mesmo prefixo da API (/api).
    """
    if not (settings.docs_on and settings.is_production):
        return

    @app.before_request
    def _docs_so_master():
        if not request.path.startswith("/docs"):
            return None
        u = current_user()
        if u is None or not is_master(u):
            raise AppError("Recurso não encontrado.", status_code=404, code="not_found")
        return None
