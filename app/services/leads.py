"""Contatos da landing page: valida, grava no banco e avisa por e-mail.

O contato é gravado antes do e-mail: se o SMTP falhar, ele não se perde
(fica com email_enviado = 0).
O e-mail sai em segundo plano (ver api/v1/leads.py) para o formulário responder na hora.
"""

import html
import re
import threading
import time

from app.core.errors import AppError
from app.integrations import email
from app.repositories import leads as repo

ROTULOS = {
    "nome": "Nome",
    "empresa": "Empresa",
    "telefone": "WhatsApp",
    "cidade": "Cidade",
    "negocio": "Tipo de negócio",
    "quantidade": "Equipamentos de frio",
    "plano": "Plano de interesse",
}
TELEFONE = re.compile(r"^\d{10,13}$")

# anti-spam simples: no máximo N envios por IP numa janela de tempo (memória do processo)
LIMITE_POR_IP = 5
JANELA_S = 3600
_envios: dict = {}
_trava = threading.Lock()


def _excedeu_limite(ip: str) -> bool:
    agora = time.time()
    with _trava:
        recentes = [t for t in _envios.get(ip, []) if agora - t < JANELA_S]
        if len(recentes) >= LIMITE_POR_IP:
            _envios[ip] = recentes
            return True
        recentes.append(agora)
        _envios[ip] = recentes
        if len(_envios) > 10000:  # não deixa o dicionário crescer sem fim
            for chave in [k for k, v in _envios.items() if not v or agora - v[-1] >= JANELA_S]:
                del _envios[chave]
        return False


def corpo_email(lead: dict) -> str:
    linhas = "".join(
        f"<tr><td style='padding:6px 12px;color:#64748b'>{ROTULOS[k]}</td>"
        f"<td style='padding:6px 12px;font-weight:600'>{html.escape(lead[k])}</td></tr>"
        for k in ROTULOS
        if lead.get(k)
    )
    numero = re.sub(r"\D", "", lead["telefone"])
    if len(numero) <= 11:
        numero = "55" + numero
    return (
        "<div style='font-family:Arial,sans-serif;font-size:14px;color:#0f172a'>"
        "<h2 style='color:#0a8bb5'>Novo contato pelo site</h2>"
        f"<table style='border-collapse:collapse'>{linhas}</table>"
        f"<p style='margin-top:20px'><a href='https://wa.me/{numero}' "
        "style='background:#12aedb;color:#fff;padding:10px 16px;border-radius:8px;"
        "text-decoration:none'>"
        "Responder no WhatsApp</a></p>"
        "</div>"
    )


def enviar_aviso(id_lead: int, lead: dict, destinos_csv: str) -> None:
    """Avisa a equipe comercial (settings.lead_emails) e marca o lead como notificado."""
    destinos = [e.strip() for e in (destinos_csv or "").split(",") if e.strip()]
    if not destinos:
        return
    titulo = f"Novo contato pelo site: {lead['empresa']}"
    corpo = corpo_email(lead)
    if sum(1 for d in destinos if email.enviar(d, titulo, corpo)):
        repo.marcar_email_enviado(id_lead)


def criar(dados: dict, ip: str) -> tuple:
    """Grava o contato. Retorna (resposta, lead_gravado ou None); None = nada a notificar (robô)."""
    # campo invisível no formulário: só robô preenche. Responde sucesso para não dar pista.
    if dados.get("site"):
        return {"msg": "Contato recebido"}, None

    lead = {k: v for k, v in dados.items() if k in ROTULOS and v}
    if not TELEFONE.match(re.sub(r"\D", "", lead["telefone"])):
        raise AppError("Informe um WhatsApp com DDD", code="bad_request")
    if _excedeu_limite(ip or "?"):
        raise AppError(
            "Muitos envios em pouco tempo. Tente novamente mais tarde.",
            status_code=429,
            code="rate_limited",
            details={"retry_after": JANELA_S},
        )
    id_lead = repo.criar({**lead, "origem": "site", "status": "novo", "ip": (ip or "")[:45]})
    return {"msg": "Contato recebido", "id_lead": id_lead}, lead
