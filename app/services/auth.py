"""Login sem senha: e-mail + código de 6 dígitos enviado por e-mail. Sessão = cookie opaco; no banco, só o hash.

Fluxo: `solicitar_codigo` envia o código (sem abrir sessão); `verificar_codigo` confere e abre a sessão.
Se o e-mail não for de um usuário ativo, a resposta é a mesma e nada é enviado (não revela cadastros).

Segurança do código: 6 dígitos de `secrets` (CSPRNG); só o HMAC (chave = SECRET_KEY) fica no banco; vale
uma vez, expira (10 min), tem no máximo 5 tentativas (contadas com trava de linha), pedir outro invalida
os anteriores, e há intervalo (60 s) e teto por hora (10) por usuário.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import Settings
from app.core.errors import AppError
from app.integrations import email as email_sender
from app.repositories import auth as repo

BRASILIA = timezone(timedelta(hours=-3))
_PURGE_AFTER = timedelta(days=1)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def usuario_publico(u: dict) -> dict:
    return {
        "id_usuario": u["id_usuario"],
        "nome": u["nome"],
        "login": u["login"],
        "telefone": u.get("telefone"),
        "perfil": u["perfil"],
        "empresa": {"id_empresa": u["id_empresa"], "nome": u["empresa"], "tipo": u["tipo_empresa"]},
    }


def _abrir_sessao(settings: Settings, u: dict, ip, user_agent, agora: datetime) -> tuple:
    token = secrets.token_urlsafe(32)
    repo.criar_sessao(
        u["id_usuario"],
        hash_token(token),
        agora + timedelta(days=settings.auth_session_days),
        ip,
        user_agent,
        agora,
    )
    repo.registrar_login(u["id_usuario"], datetime.now(BRASILIA).replace(tzinfo=None))
    repo.limpar_sessoes_antigas(agora - _PURGE_AFTER)
    return usuario_publico(u), token


# ---- 2º fator: código de 6 dígitos por e-mail -------------------------------------------------


def gerar_codigo() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_codigo(settings: Settings, id_usuario: int, codigo: str) -> str:
    key = settings.secret_key.encode()
    return hmac.new(key, f"login-code:{id_usuario}:{codigo}".encode(), hashlib.sha256).hexdigest()


def mascarar_email(email: str) -> str:
    nome, _, dominio = email.partition("@")
    return f"{nome[:1]}***@{dominio}" if dominio else "***"


def _html_codigo(codigo: str, minutos: int) -> str:
    esp = " ".join(codigo)
    return (
        '<!doctype html><html lang="pt-BR"><body style="margin:0;padding:24px;background:#f4f7fb;'
        'font-family:Arial,sans-serif;"><table role="presentation" width="100%" style="max-width:480px;'
        'margin:0 auto;background:#fff;border-radius:10px;padding:32px;">'
        '<tr><td style="color:#1B84FF;font-size:13px;font-weight:bold;letter-spacing:1px;">'
        "REFRIGERAÇÃO ATUAL</td></tr>"
        '<tr><td style="color:#2a3547;font-size:16px;padding-top:12px;">Seu código de acesso:</td></tr>'
        '<tr><td style="padding:18px 0;text-align:center;font-size:34px;font-weight:bold;'
        f'letter-spacing:8px;color:#2a3547;">{esp}</td></tr>'
        '<tr><td style="color:#5a6a85;font-size:14px;line-height:1.5;">'
        f"Ele vale por {minutos} minutos e só pode ser usado uma vez.<br>"
        "Se você não tentou entrar, ignore este e-mail e troque sua senha.</td></tr>"
        "</table></body></html>"
    )


def _enviar_codigo(settings: Settings, u: dict, ip, agora: datetime) -> dict:
    uid = u["id_usuario"]
    ultimo = repo.ultimo_codigo(uid)
    if ultimo is not None:
        espera = settings.auth_resend_seconds - (agora - ultimo["criado_em"]).total_seconds()
        if espera > 0:
            raise AppError(
                "Aguarde para pedir um novo código.",
                status_code=429,
                code="rate_limited",
                details={"retry_after": int(espera) + 1},
            )
    if (
        repo.contar_codigos_desde(uid, agora - timedelta(hours=1))
        >= settings.auth_max_codes_per_hour
    ):
        raise AppError(
            "Muitos códigos solicitados. Tente novamente mais tarde.",
            status_code=429,
            code="rate_limited",
            details={"retry_after": 3600},
        )

    repo.invalidar_codigos(uid, agora)
    codigo = gerar_codigo()
    id_codigo = repo.criar_codigo(
        uid,
        hash_codigo(settings, uid, codigo),
        agora + timedelta(seconds=settings.auth_code_ttl_seconds),
        ip,
    )
    destino = u.get("email_verificacao") or u["login"]
    ok = email_sender.enviar(
        destino,
        f"{codigo} é o seu código de acesso",
        _html_codigo(codigo, settings.auth_code_ttl_seconds // 60),
    )
    if not ok:
        repo.marcar_codigo_usado(
            id_codigo, agora
        )  # não deixa um código "gasto" sem e-mail entregue
        raise AppError(
            "Não foi possível enviar o e-mail agora. Tente novamente em instantes.",
            status_code=503,
            code="email_unavailable",
        )
    repo.limpar_codigos_antigos(agora - _PURGE_AFTER)
    return {
        "etapa": "codigo",
        "email": mascarar_email(destino),
        "expira_em": settings.auth_code_ttl_seconds,
        "reenvio_em": settings.auth_resend_seconds,
    }


def solicitar_codigo(settings: Settings, email: str, ip: Optional[str]) -> dict:
    """Envia o código por e-mail (não abre sessão). E-mail desconhecido/inativo: mesma resposta, sem envio."""
    email = (email or "").strip().lower()
    u = repo.buscar_para_login(email)
    if not u or not u["ativo"] or not u["empresa_ativo"]:
        return {
            "email": mascarar_email(email),
            "expira_em": settings.auth_code_ttl_seconds,
            "reenvio_em": settings.auth_resend_seconds,
        }
    res = _enviar_codigo(settings, u, ip, utcnow())
    res.pop("etapa", None)
    return res


def verificar_codigo(
    settings: Settings, email: str, codigo: str, ip: Optional[str], user_agent: Optional[str]
) -> tuple:
    """Etapa 2: confere o código e abre a sessão. Retorna (usuario_publico, token)."""
    u = repo.buscar_para_login((email or "").strip().lower())
    if not u or not u["ativo"] or not u["empresa_ativo"]:
        raise AppError("Código inválido ou expirado.", status_code=400, code="invalid_code")
    agora = utcnow()
    rec = repo.codigo_ativo_para_update(u["id_usuario"], agora)
    if rec is None:
        raise AppError(
            "O código expirou. Entre de novo para receber outro.",
            status_code=400,
            code="code_expired",
        )
    muitas = AppError(
        "Muitas tentativas. Entre de novo para receber outro código.",
        status_code=429,
        code="too_many_attempts",
    )
    if rec["tentativas"] >= settings.auth_max_attempts:
        repo.marcar_codigo_usado(rec["id_codigo"], agora)
        raise muitas
    if not hmac.compare_digest(
        rec["codigo_hash"], hash_codigo(settings, u["id_usuario"], codigo or "")
    ):
        restantes = settings.auth_max_attempts - (rec["tentativas"] + 1)
        repo.somar_tentativa(rec["id_codigo"], restantes <= 0, agora)
        if restantes <= 0:
            raise muitas
        raise AppError(
            "Código incorreto.",
            status_code=400,
            code="invalid_code",
            details={"attempts_left": restantes},
        )
    repo.marcar_codigo_usado(rec["id_codigo"], agora)  # uso único
    return _abrir_sessao(settings, u, ip, user_agent, agora)


def usuario_da_sessao(token: str) -> Optional[dict]:
    """Usuário (com empresa) da sessão, lido do banco a cada requisição: desativar usuário/empresa ou
    mudar o perfil vale na hora. Retorna None se não houver sessão válida."""
    agora = utcnow()
    s = repo.sessao_ativa(hash_token(token), agora)
    if s is None:
        return None
    u = repo.buscar_por_id(s["id_usuario"])
    if not u or not u["ativo"] or not u["empresa_ativo"]:
        return None
    if s["ultimo_uso_em"] is None or (agora - s["ultimo_uso_em"]) > timedelta(minutes=5):
        repo.tocar_sessao(s["id_sessao"], agora)  # evita uma escrita por requisição
    return u


def logout(token: str) -> None:
    repo.revogar_sessao(hash_token(token), utcnow())
