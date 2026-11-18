"""Cliente da eWeLink Open API v2 (CoolKit) com login via OAuth 2.0.

Fluxo: `url_autorizacao(state)` -> usuário loga na eWeLink -> redirect com `code` -> `trocar_code()`
devolve os tokens (quem chama os guarda, criptografados) -> `get()/post()` usam o token e o renovam
perto de expirar. Este módulo não conhece banco: o armazenamento entra por
`ler_token`/`gravar_token`.
Nunca registre tokens, segredos ou o corpo das respostas em log.
"""

import base64
import hashlib
import hmac
import json
import secrets
import string
import time
import urllib.parse
from typing import Callable, Optional

import requests

from app.config import Settings

OAUTH_URL = "https://c2ccdn.coolkit.cc/oauth/index.html"
API_URL = "https://{region}-apia.coolkit.cc"
RENOVAR_ANTES_MS = 24 * 60 * 60 * 1000  # renova o accessToken 1 dia antes de expirar
POR_PAGINA = 30
TIMEOUT_S = 30
# códigos da eWeLink para token inválido/expirado (vêm com HTTP 200)
ERROS_SESSAO = (401, 402)


class EwelinkError(Exception):
    def __init__(self, msg: str, status_code: int = 502, data: Optional[dict] = None):
        super().__init__(msg)
        self.msg = msg
        self.status_code = status_code
        self.data = data or {}


def http_request(method: str, url: str, headers: dict, body: Optional[str] = None) -> dict:
    """Chamada HTTP com timeout. Devolve {"status_code", "data"}; falha de rede vira status_code 0."""  # noqa: E501
    try:
        resp = requests.request(
            method,
            url,
            headers=headers,
            data=body.encode("utf-8") if body else None,
            timeout=TIMEOUT_S,
        )
        try:
            data = resp.json()
        except ValueError:
            data = {"error": resp.text[:200]}
        return {
            "status_code": resp.status_code,
            "data": data if isinstance(data, dict) else {"error": data},
        }
    except requests.RequestException as exc:
        return {"status_code": 0, "data": {"error": type(exc).__name__}}


def _nonce() -> str:
    alfabeto = string.ascii_letters + string.digits
    return "".join(secrets.choice(alfabeto) for _ in range(8))


def _agora_ms() -> int:
    return int(time.time() * 1000)


class Ewelink:
    def __init__(
        self,
        settings: Settings,
        ler_token: Callable[[], Optional[dict]],
        gravar_token: Callable[[dict], None],
    ):
        self.appid = settings.ewelink_appid
        self.secret = settings.ewelink_app_secret.get_secret_value()
        self.redirect_url = settings.ewelink_redirect_url
        self.region = settings.ewelink_region
        self._ler_token = ler_token
        self._gravar_token = gravar_token
        if not self.appid or not self.secret:
            raise EwelinkError("EWELINK_APPID/EWELINK_APP_SECRET não configurados", 500)

    # ── assinatura ───────────────────────────────────────────────────

    def _assinar(self, mensagem: str) -> str:
        digest = hmac.new(
            self.secret.encode("utf-8"), mensagem.encode("utf-8"), hashlib.sha256
        ).digest()
        return base64.b64encode(digest).decode("utf-8")

    def _headers(self, authorization: str) -> dict:
        return {
            "Content-Type": "application/json",
            "X-CK-Appid": self.appid,
            "X-CK-Nonce": _nonce(),
            "Authorization": authorization,
        }

    # ── OAuth 2.0 ────────────────────────────────────────────────────

    def url_autorizacao(self, state: str) -> str:
        if not self.redirect_url:
            raise EwelinkError("EWELINK_REDIRECT_URL não configurado", 500)
        seq = str(_agora_ms())
        params = {
            "clientId": self.appid,
            "seq": seq,
            "authorization": self._assinar(f"{self.appid}_{seq}"),
            "redirectUrl": self.redirect_url,
            "grantType": "authorization_code",
            "state": state,
            "nonce": _nonce(),
        }
        return f"{OAUTH_URL}?{urllib.parse.urlencode(params)}"

    def trocar_code(self, code: str, region: Optional[str] = None) -> dict:
        """Troca o code do callback por tokens (o `state` já foi validado por quem chama)."""
        region = region or self.region
        body = json.dumps(
            {"code": code, "redirectUrl": self.redirect_url, "grantType": "authorization_code"}
        )
        resp = http_request(
            "POST",
            f"{API_URL.format(region=region)}/v2/user/oauth/token",
            self._headers(f"Sign {self._assinar(body)}"),
            body,
        )
        data = self._validar(resp)
        token = {
            "region": region,
            "at": data["accessToken"],
            "rt": data["refreshToken"],
            "at_expira": data.get("atExpiredTime"),
            "rt_expira": data.get("rtExpiredTime"),
        }
        self._gravar_token(token)
        return token

    def _renovar(self, token: dict) -> dict:
        body = json.dumps({"rt": token["rt"]})
        resp = http_request(
            "POST",
            f"{API_URL.format(region=token['region'])}/v2/user/refresh",
            self._headers(f"Bearer {token['at']}"),
            body,
        )
        data = self._validar(resp)
        agora = _agora_ms()
        token.update(
            {
                "at": data["at"],
                "rt": data["rt"],
                # a resposta do refresh não traz expiração: at vale 30 dias e rt 60 dias
                "at_expira": agora + 30 * 24 * 60 * 60 * 1000,
                "rt_expira": agora + 60 * 24 * 60 * 60 * 1000,
            }
        )
        self._gravar_token(token)
        return token

    def token(self) -> dict:
        """Token válido, renovado se estiver perto de expirar."""
        token = self._ler_token()
        if not token:
            raise EwelinkError("Não autenticado na eWeLink: acesse /ewelink/auth", 503)
        agora = _agora_ms()
        if token.get("rt_expira") and agora >= token["rt_expira"]:
            raise EwelinkError("Sessão eWeLink expirada: acesse /ewelink/auth novamente", 503)
        if token.get("at_expira") and agora >= token["at_expira"] - RENOVAR_ANTES_MS:
            token = self._renovar(token)
        return token

    # ── chamadas autenticadas ────────────────────────────────────────

    @staticmethod
    def _validar(resp: dict) -> dict:
        data = resp.get("data") or {}
        if resp.get("status_code") == 200 and data.get("error") == 0:
            return data.get("data") or {}

        detalhe = {"http_status": resp.get("status_code"), "ewelink_error": data.get("error")}
        msg = str(data.get("msg") or data.get("error") or "erro desconhecido")
        if data.get("error") in ERROS_SESSAO:
            raise EwelinkError(
                "Sessão eWeLink inválida ou expirada: acesse /ewelink/auth novamente", 503, detalhe
            )
        # a eWeLink não documenta um código único de limite: trata HTTP 429 e mensagens típicas
        if resp.get("status_code") == 429 or any(
            p in msg.lower() for p in ("limit", "frequen", "too many")
        ):
            detalhe["limite"] = True
        raise EwelinkError(f"eWeLink: {msg}", 502, detalhe)

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        token = self.token()
        url = f"{API_URL.format(region=token['region'])}{path}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        return self._validar(http_request("GET", url, self._headers(f"Bearer {token['at']}")))

    def post(self, path: str, payload: Optional[dict] = None) -> dict:
        token = self.token()
        url = f"{API_URL.format(region=token['region'])}{path}"
        body = json.dumps(payload) if payload else None
        return self._validar(
            http_request("POST", url, self._headers(f"Bearer {token['at']}"), body)
        )

    # ── dispositivos ─────────────────────────────────────────────────

    def listar_dispositivos(self) -> dict:
        """Todos os dispositivos da conta: {"thingList": [...], "total": n, "chamadas": k}.

        A 1ª chamada é sem paginação (como sempre funcionou); só pagina se vierem menos itens
        que o total.
        """
        data = self.get("/v2/device/thing", {"lang": "en"})
        itens = list(data.get("thingList", []))
        total = data.get("total") or len(itens)
        chamadas = 1
        while len(itens) < total:
            pagina = self.get(
                "/v2/device/thing", {"lang": "en", "num": POR_PAGINA, "beginIndex": len(itens)}
            )
            chamadas += 1
            novos = pagina.get("thingList", [])
            if not novos:
                break
            itens.extend(novos)
        return {"thingList": itens, "total": total, "chamadas": chamadas}

    def alterar_status(self, deviceid: str, params: dict) -> dict:
        """Envia um comando ao dispositivo, ex.: {"switch": "off"}."""
        return self.post("/v2/device/thing/status", {"type": 1, "id": deviceid, "params": params})
