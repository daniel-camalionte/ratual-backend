"""Criptografia AES-CBC dos segredos guardados no banco (tokens eWeLink/EZVIZ).

Compatível com o Brain: mesmo formato (base64 de IV + dados, PKCS7) e mesma chave `CRYPTO_KEY`,
para ler os registros migrados. Nunca registre o texto claro nem a chave em log.
"""

import base64
import os

from Crypto.Cipher import AES
from flask import current_app

_BLOCK = 16


def _key() -> bytes:
    key = current_app.extensions["settings"].crypto_key.get_secret_value()
    if not key:
        raise RuntimeError("CRYPTO_KEY não configurada.")
    return key.encode("utf-8")


def encrypt(message: str) -> str:
    raw = message.encode("utf-8")
    pad = _BLOCK - len(raw) % _BLOCK
    iv = os.urandom(AES.block_size)
    cipher = AES.new(_key(), AES.MODE_CBC, iv)
    return base64.b64encode(iv + cipher.encrypt(raw + bytes([pad]) * pad)).decode("utf-8")


def decrypt(message: str) -> str:
    raw = base64.b64decode(message)
    iv, data = raw[:_BLOCK], raw[_BLOCK:]
    plain = AES.new(_key(), AES.MODE_CBC, iv).decrypt(data)
    return plain[: -plain[-1]].decode("utf-8")
