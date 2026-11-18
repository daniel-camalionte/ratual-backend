"""Coleta periódica da eWeLink (cron): 1 consulta à conta, 1 leitura por aparelho e eventos.

Protegida contra execução simultânea (trava) e com pausa progressiva se a eWeLink sinalizar limite.
Toda execução fica em coleta_log: ok, erro ou ignorada.
"""

import contextlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import Settings
from app.core.errors import AppError
from app.integrations.ewelink import Ewelink, EwelinkError
from app.repositories import ewelink as repo
from app.services import eventos
from app.services.trava import trava

log = logging.getLogger(__name__)

BRASILIA = timezone(timedelta(hours=-3))
PAUSA_INICIAL_MIN = 5
PAUSA_MAXIMA_MIN = 60
# não deixa duas coletas seguidas em menos de 1 minuto (cron + chamada manual, por exemplo)
ESPACAMENTO_MINIMO_S = 60
UIACTIVE_PARALELO = 5  # chamadas simultâneas ao acordar os aparelhos (não sobrecarregar a eWeLink)


def _agora() -> datetime:
    return datetime.now(BRASILIA).replace(tzinfo=None, microsecond=0)


# ── pausa por limite ─────────────────────────────────────────────────────


def _ler_pausa() -> dict:
    try:
        return json.loads(repo.ler_estado(repo.CHAVE_COLETA) or "{}")
    except ValueError:
        return {}


def pausada_ate() -> Optional[float]:
    """Epoch (segundos) até quando a coleta está pausada, ou None."""
    ate = _ler_pausa().get("pausa_ate")
    return ate if ate and ate > time.time() else None


def registrar_limite() -> int:
    """eWeLink sinalizou limite: pausa e dobra o tempo a cada ocorrência seguida (5, 10, 20... até 60 min)."""  # noqa: E501
    estado = _ler_pausa()
    minutos = min(PAUSA_MAXIMA_MIN, max(PAUSA_INICIAL_MIN, estado.get("pausa_min", 0) * 2))
    repo.gravar_estado(
        repo.CHAVE_COLETA,
        json.dumps({"pausa_min": minutos, "pausa_ate": time.time() + minutos * 60}),
    )
    return minutos


def registrar_sucesso() -> None:
    estado = _ler_pausa()
    if estado.get("pausa_min") or estado.get("pausa_ate"):
        repo.apagar_estado(repo.CHAVE_COLETA)


# ── conversão dos parâmetros da eWeLink ──────────────────────────────────


def _numero(valor) -> Optional[float]:
    """A eWeLink manda temperatura como texto e 'unavailable' quando não há sensor."""
    try:
        return round(float(valor), 1)
    except (TypeError, ValueError):
        return None


def _primeiro_numero(params: dict, chaves: tuple) -> Optional[float]:
    for chave in chaves:
        valor = _numero(params.get(chave))
        if valor is not None:
            return valor
    return None


def _rele(valor) -> Optional[int]:
    if valor == "on":
        return 1
    if valor == "off":
        return 0
    return None


def _primeiro_da_lista(valor) -> Optional[float]:
    """updateListTempLower/Upper vêm como lista de textos, ex.: ["-7"]."""
    return _numero(valor[0]) if isinstance(valor, list) and valor else None


# ── coleta ───────────────────────────────────────────────────────────────


def _log(status, inicio, t0, mensagem=None, dispositivos=0, leituras=0, chamadas=0) -> None:
    repo.registrar_log(
        inicio,
        _agora(),
        status,
        mensagem,
        dispositivos,
        leituras,
        chamadas,
        int((time.monotonic() - t0) * 1000),
    )


def coletar(settings: Settings, cliente: Ewelink) -> dict:
    """Executada pela cron. `cliente` já vem montado (com o armazenamento do token)."""
    inicio, t0 = _agora(), time.monotonic()

    pausa = pausada_ate()
    if pausa:
        ate = datetime.fromtimestamp(pausa, BRASILIA).strftime("%H:%M")
        msg = f"Coleta pausada até {ate} por limite da eWeLink"
        _log("ignorada", inicio, t0, msg)
        return {"msg": msg, "status": "ignorada"}

    with trava() as conseguiu:
        if not conseguiu:
            msg = "Outra coleta já está em andamento"
            _log("ignorada", inicio, t0, msg)
            return {"msg": msg, "status": "ignorada"}

        ultima = repo.ultima_coleta_ok()
        if ultima:
            decorrido = (inicio - ultima["inicio"]).total_seconds()
            if decorrido < ESPACAMENTO_MINIMO_S:
                msg = f"Coleta anterior há {int(decorrido)}s (mínimo {ESPACAMENTO_MINIMO_S}s)"
                _log("ignorada", inicio, t0, msg)
                return {"msg": msg, "status": "ignorada"}

        return _executar(settings, cliente, inicio, t0)


def _acordar(settings: Settings, cliente: Ewelink) -> int:
    """Pede aos aparelhos online (na coleta anterior) que enviem a leitura atual à nuvem.

    O THR316 só atualiza a temperatura na nuvem com frequência enquanto o app da Sonoff está aberto
    (uiActive). Falha aqui não impede a coleta. Retorna o número de chamadas feitas.
    """
    uiactive = int(getattr(settings, "ewelink_uiactive_s", 60))
    espera = float(getattr(settings, "ewelink_uiactive_espera_s", 6))
    if uiactive <= 0:
        return 0
    ids = repo.deviceids_online()
    if not ids:
        return 0
    # Renova o token AQUI, na thread principal. As threads abaixo NÃO têm contexto da aplicação (nem
    # sessão de banco): o cliente delas usa só este token, em memória, sem ler nem gravar no banco.
    token = cliente.token()
    cliente_threads = Ewelink(settings, lambda: token, lambda _t: None)

    def acordar(deviceid):
        # limite/offline/qualquer falha de rede: a leitura logo abaixo trata (o limite pausa a coleta)
        with contextlib.suppress(EwelinkError):
            cliente_threads.alterar_status(deviceid, {"uiActive": uiactive})

    with ThreadPoolExecutor(max_workers=UIACTIVE_PARALELO) as pool:
        list(pool.map(acordar, ids))
    time.sleep(espera)  # tempo para os aparelhos responderem
    return len(ids)


def _normalizar(item: dict, inicio: datetime) -> Optional[dict]:
    d = item.get("itemData", {})
    if not d.get("deviceid"):
        return None  # grupos não têm deviceid
    params = d.get("params") or {}
    sinal = _numero(params.get("rssi"))
    if sinal is None:
        sinal = _numero(params.get("subDevRssi"))  # sensores Zigbee atrás de um hub
    online = 1 if d.get("online") else 0
    # offline: a eWeLink repete o último valor enviado (pode ter dias). Não é leitura nova, então não grava  # noqa: E501
    # temperatura/relé; o dispositivo mantém a última leitura real.
    valida = bool(online)
    return {
        "deviceid": d["deviceid"],
        "nome": (d.get("name") or "").strip(),
        "modelo": d.get("productModel"),
        "marca": d.get("brandName"),
        "online": online,
        "temperatura": _primeiro_numero(params, ("currentTemperature", "temperature"))
        if valida
        else None,
        "umidade": _primeiro_numero(params, ("currentHumidity", "humidity")) if valida else None,
        "rele": _rele(params.get("switch")) if valida else None,
        "sinal": int(sinal) if valida and sinal is not None else None,
        "limite_min": _primeiro_da_lista(params.get("updateListTempLower")),
        "limite_max": _primeiro_da_lista(params.get("updateListTempUpper")),
        "data_leitura": inicio if valida else None,
    }


def _executar(settings: Settings, cliente: Ewelink, inicio: datetime, t0: float) -> dict:
    try:
        acordados = _acordar(settings, cliente)
        data = cliente.listar_dispositivos()
    except EwelinkError as e:
        msg = e.msg
        if e.data.get("limite"):
            msg = f"{msg} (coleta pausada por {registrar_limite()} min)"
        _log("erro", inicio, t0, msg)
        raise AppError(msg, status_code=e.status_code, code="ewelink_error", details=e.data) from e

    chamadas = data.get("chamadas", 1) + acordados
    dispositivos = [d for d in (_normalizar(i, inicio) for i in data.get("thingList", [])) if d]
    if not dispositivos:
        _log("ok", inicio, t0, "Nenhum dispositivo na conta", chamadas=chamadas)
        registrar_sucesso()
        return {"msg": "Nenhum dispositivo encontrado na conta", "status": "ok", "total": 0}

    # estado antes desta coleta: base para detectar eventos (offline, fora da faixa, relé...)
    anteriores = repo.estado_anterior()
    try:
        # dispositivo novo entra sem empresa (id_empresa NULL) até ser vinculado
        repo.salvar_lote(dispositivos)
        ids = repo.mapa_ids([d["deviceid"] for d in dispositivos])
        leituras = [
            {
                "id_dispositivo": ids[d["deviceid"]], "temperatura": d["temperatura"], "umidade": d["umidade"],  # noqa: E501
                "rele": d["rele"], "online": d["online"], "data": inicio,
            }
            for d in dispositivos
            if d["deviceid"] in ids
        ]  # fmt: skip
        if leituras:
            repo.salvar_leituras(leituras)
    except Exception:
        log.exception("coleta_gravacao_erro")
        _log(
            "erro",
            inicio,
            t0,
            "Erro ao gravar dispositivos/leituras",
            len(dispositivos),
            0,
            chamadas,
        )
        raise AppError("Erro ao gravar a coleta", status_code=500, code="internal_error") from None

    # eventos: falha aqui não invalida a coleta (as leituras já estão gravadas)
    atuais = {
        ids[d["deviceid"]]: {
            "online": bool(d["online"]),
            "temperatura": d["temperatura"],
            "rele": d["rele"],
        }
        for d in dispositivos
        if d["deviceid"] in ids
    }
    try:
        resumo_eventos = eventos.processar_coleta(settings, anteriores, atuais, inicio)
    except Exception as exc:  # noqa: BLE001
        log.exception("coleta_eventos_erro")
        resumo_eventos = f"eventos: erro ({type(exc).__name__})"

    registrar_sucesso()
    _log("ok", inicio, t0, resumo_eventos, len(dispositivos), len(leituras), chamadas)
    return {
        "msg": "Coleta realizada",
        "status": "ok",
        "total": len(leituras),
        "chamadas_api": chamadas,
        "data_leitura": inicio,
        "eventos": resumo_eventos,
    }
