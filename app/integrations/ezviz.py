"""Cliente da EZVIZ Open Platform (câmeras).

- Token: gerado com AppKey + AppSecret (`/api/lapp/token/get`), dura ~7 dias e é renovado sozinho
  1 dia antes de vencer. Junto vem o `areaDomain` (servidor da região), usado nas demais chamadas.
- As chamadas são POST form-urlencoded; a resposta tem {"code": "200", "data": ..., "page": ...}.
- O token nunca sai do backend: para o vídeo, o app recebe só um link temporário da câmera.
- Nunca registre o token, o AppSecret nem o código de verificação das câmeras em log.
"""

import json
import os
import time
from typing import Optional

import requests

TIMEOUT_S = 20
RENOVAR_ANTES_MS = 24 * 60 * 60 * 1000
ERROS_TOKEN = ("10001", "10002")  # token nulo/inválido ou expirado
PROTOCOLO = {"ezopen": 1, "hls": 2, "rtmp": 3, "flv": 4}
QUALIDADE = {"hd": 1, "sd": 2}
TIPO_STREAM = {"ao_vivo": 1, "sd": 2, "nuvem": 3}  # ao vivo, cartão da câmera, nuvem


class EzvizError(Exception):
    def __init__(self, msg: str, status_code: int = 502, data: Optional[dict] = None):
        super().__init__(msg)
        self.msg = msg
        self.status_code = status_code
        self.data = data or {}


def arquivo_token_padrao() -> str:
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.environ.get("EZVIZ_TOKEN_FILE") or os.path.join(raiz, "storage", "ezviz_token.json")


class Ezviz:
    def __init__(
        self, app_key: str, app_secret: str, api_url: str, token_file: Optional[str] = None
    ):
        self.app_key = app_key
        self.app_secret = app_secret
        self.api_url = (api_url or "").rstrip("/")
        self.token_file = token_file or arquivo_token_padrao()
        if not self.app_key or not self.app_secret:
            raise EzvizError("EZVIZ_APP_KEY/EZVIZ_APP_SECRET não configurados", 500)

    @classmethod
    def from_settings(cls, settings) -> "Ezviz":
        return cls(
            settings.ezviz_app_key,
            settings.ezviz_app_secret.get_secret_value(),
            settings.ezviz_api_url,
        )

    # ── token ────────────────────────────────────────────────────────────

    def _ler(self) -> dict:
        try:
            with open(self.token_file, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, ValueError):
            return {}

    def _gravar(self, dados: dict) -> None:
        os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(dados, f, indent=2)

    def _renovar(self) -> dict:
        try:
            resp = requests.post(
                f"{self.api_url}/api/lapp/token/get",
                data={"appKey": self.app_key, "appSecret": self.app_secret},
                timeout=TIMEOUT_S,
            )
            corpo = resp.json()
        except (requests.RequestException, ValueError):
            raise EzvizError("EZVIZ indisponível ao gerar token", 503) from None
        if str(corpo.get("code")) != "200":
            raise EzvizError(
                f"EZVIZ recusou as credenciais: {corpo.get('msg')}",
                503,
                {"ezviz_code": corpo.get("code")},
            )
        d = corpo["data"]
        token = {
            "accessToken": d["accessToken"],
            "expireTime": d["expireTime"],
            "areaDomain": (d.get("areaDomain") or self.api_url).rstrip("/"),
        }
        self._gravar(token)
        return token

    def token(self, forcar: bool = False) -> dict:
        t = self._ler()
        agora = int(time.time() * 1000)
        if forcar or not t.get("accessToken") or agora >= t.get("expireTime", 0) - RENOVAR_ANTES_MS:
            t = self._renovar()
        return t

    def status_token(self) -> dict:
        """Estado do token SEM o valor dele."""
        t = self._ler()
        return {
            "token_salvo": bool(t.get("accessToken")),
            "expira_ms": t.get("expireTime"),
            "servidor": t.get("areaDomain"),
        }

    # ── chamadas ─────────────────────────────────────────────────────────

    def _post(self, caminho: str, params: Optional[dict] = None, _repetiu: bool = False):
        t = self.token()
        try:
            resp = requests.post(
                f"{t['areaDomain']}{caminho}",
                data={"accessToken": t["accessToken"], **(params or {})},
                timeout=TIMEOUT_S,
            )
            corpo = resp.json()
        except (requests.RequestException, ValueError):
            raise EzvizError("EZVIZ indisponível", 503) from None

        code = str(corpo.get("code"))
        if code == "200":
            return corpo.get("data"), corpo.get("page")
        msg = str(corpo.get("msg") or code)
        detalhe = {"ezviz_code": code}
        if code in ERROS_TOKEN and not _repetiu:
            self.token(forcar=True)  # revogado/expirado antes do previsto: renova e tenta uma vez
            return self._post(caminho, params, _repetiu=True)
        if code == "60019":
            raise EzvizError(
                "A câmera está com a criptografia de vídeo ativa: cadastre o código de verificação "
                "(etiqueta da câmera) ou desative a criptografia no app EZVIZ",
                409,
                detalhe,
            )
        if code in ("20007", "20008"):
            raise EzvizError(f"Câmera offline ou sem resposta: {msg}", 409, detalhe)
        if any(p in msg.lower() for p in ("limit", "frequen", "exceed", "too many")):
            detalhe["limite"] = True
        raise EzvizError(f"EZVIZ: {msg}", 502, detalhe)

    def listar_cameras(self) -> list:
        """Todos os canais de câmera da conta (paginado)."""
        cameras, pagina = [], 0
        while True:
            dados, page = self._post("/api/lapp/camera/list", {"pageStart": pagina, "pageSize": 50})
            cameras += dados or []
            if not page or len(cameras) >= int(page.get("total") or 0) or not dados:
                return cameras
            pagina += 1

    def info(self, serial: str):
        dados, _ = self._post("/api/lapp/device/info", {"deviceSerial": serial})
        return dados

    def endereco(
        self,
        serial,
        canal=1,
        tipo="ao_vivo",
        protocolo="hls",
        qualidade="hd",
        expira_s=300,
        codigo=None,
        inicio=None,
        fim=None,
        h265=False,
    ):
        """Link temporário de vídeo (só desta câmera). inicio/fim: YYYY-MM-DD HH:MM:SS."""
        params = {
            "deviceSerial": serial,
            "channelNo": canal,
            "protocol": PROTOCOLO[protocolo],
            "quality": QUALIDADE[qualidade],
            "type": TIPO_STREAM[tipo],
            "expireTime": expira_s,
        }
        if h265:
            params["supportH265"] = 1
        if codigo:
            params["code"] = codigo
        if inicio:
            params["startTime"] = inicio
        if fim:
            params["stopTime"] = fim
        dados, _ = self._post("/api/lapp/v2/live/address/get", params)
        return dados

    def alarmes(self, serial, inicio_ms, fim_ms, max_paginas=5) -> list:
        """Alarmes da câmera no período (mais recentes primeiro)."""
        todos = []
        for pagina in range(max_paginas):
            dados, page = self._post(
                "/api/lapp/alarm/device/list",
                {
                    "deviceSerial": serial,
                    "startTime": int(inicio_ms),
                    "endTime": int(fim_ms),
                    "alarmType": -1,
                    "status": 2,
                    "pageStart": pagina,
                    "pageSize": 50,
                },
            )
            todos += dados or []
            if not dados or not page or len(todos) >= int(page.get("total") or 0):
                break
        return todos

    @staticmethod
    def baixar(url: str) -> Optional[bytes]:
        """Baixa a foto do alarme (o link da EZVIZ expira). Retorna bytes ou None."""
        try:
            r = requests.get(url, timeout=TIMEOUT_S)
            if r.status_code == 200 and r.content:
                return r.content
        except requests.RequestException:
            pass
        return None
