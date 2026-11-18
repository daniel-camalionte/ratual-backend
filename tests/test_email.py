"""Cabeçalhos do e-mail (sem rede): o remetente não pode ser codificado por inteiro."""

import smtplib
from email import message_from_string
from email.header import decode_header, make_header

import pytest

from app import create_app
from app.config import Settings
from app.integrations import email


class _Fake:
    enviado: dict = {}

    def __init__(self, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, **k):
        pass

    def login(self, *a):
        pass

    def sendmail(self, de, para, msg):
        _Fake.enviado = {"de": de, "para": para, "msg": msg}


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setattr(smtplib, "SMTP", _Fake)
    s = Settings(
        app_env="testing",
        _env_file=None,
        smtp_host="smtp.exemplo.test",
        smtp_port=587,
        smtp_security="starttls",
        smtp_user="contato@exemplo.test",
        smtp_from="Refrigeração Atual <contato@exemplo.test>",
    )
    return create_app(s)


def test_remetente_com_acento_mantem_o_endereco_em_texto_puro(app):
    with app.app_context():
        assert email.enviar("cliente@exemplo.test", "Seu código", "<p>oi</p>") is True
    bruto = _Fake.enviado["msg"]
    cab = next(ln for ln in bruto.splitlines() if ln.startswith("From:"))
    assert "<contato@exemplo.test>" in cab  # endereço legível pelos servidores de e-mail
    msg = message_from_string(bruto)
    assert str(make_header(decode_header(msg["From"]))).startswith("Refrigeração Atual")
    assert _Fake.enviado["de"] == "contato@exemplo.test" and _Fake.enviado["para"] == [
        "cliente@exemplo.test"
    ]


def test_tem_date_e_message_id_do_dominio_do_remetente(app):
    with app.app_context():
        email.enviar("cliente@exemplo.test", "x", "<p>oi</p>")
    msg = message_from_string(_Fake.enviado["msg"])
    assert msg["Date"] and msg["Message-ID"].endswith("@exemplo.test>")


def test_recusa_quebra_de_linha_no_destinatario(app):
    with app.app_context():
        assert email.enviar("a@b.test\r\nBcc: x@y.test", "x", "<p>oi</p>") is False
