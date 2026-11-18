"""Envio de e-mail HTML via SMTP (KingHost: STARTTLS na 587, ou SSL na 465).

`enviar()` devolve True/False e nunca levanta nem registra o conteúdo, o código ou a senha. O destinatário
vem de cadastro; ainda assim barramos quebra de linha (injeção de cabeçalho). O certificado TLS é verificado.
"""

import logging
import smtplib
import ssl
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from flask import current_app

log = logging.getLogger(__name__)


def _abrir(s):
    ctx = ssl.create_default_context()
    if s.smtp_security == "ssl":
        return smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=ctx)
    srv = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
    if s.smtp_security == "starttls":
        srv.starttls(context=ctx)
    return srv


def enviar(para: str, assunto: str, html: str) -> bool:
    s = current_app.extensions["settings"]
    if not (s.smtp_host and s.smtp_from):
        log.warning("smtp_not_configured")
        return False
    if any(c in para + assunto for c in "\r\n"):
        return False
    nome, remetente = parseaddr(s.smtp_from)
    remetente = remetente or s.smtp_from
    usuario = s.smtp_user or remetente
    senha = (s.smtp_password or s.smtp_pass).get_secret_value()
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = assunto
    # só o NOME é codificado (RFC 2047); o endereço vai em texto puro, senão o Gmail descarta ou manda ao spam
    msg["From"] = formataddr((nome, remetente), charset="utf-8") if nome else remetente
    msg["To"] = para
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=remetente.rpartition("@")[2] or None)
    try:
        with _abrir(s) as srv:
            if senha:
                srv.login(usuario, senha)
            srv.sendmail(remetente, [para], msg.as_string())
        return True
    except Exception as exc:  # noqa: BLE001 - qualquer falha de rede/SMTP vira False
        log.warning("smtp_error", extra={"type": type(exc).__name__})
        return False
