"""Regras da integração eWeLink (sem Flask): OAuth, diagnóstico, gráfico e comando do relé.

O token OAuth fica no banco (`integracao_estado`), criptografado com `app.core.crypto`.
A coleta periódica está em `app.services.coleta`.
"""

import hmac
import json
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import Settings
from app.core import crypto
from app.core.auth import is_master
from app.core.errors import AppError
from app.integrations.ewelink import Ewelink, EwelinkError
from app.repositories import ewelink as repo
from app.services import coleta, eventos

# Brasil não tem horário de verão desde 2019: horário de Brasília é UTC-3 fixo
BRASILIA = timezone(timedelta(hours=-3))
FORMATO_DATA = "%Y-%m-%d %H:%M:%S"
MAX_HORAS = 24 * 90
STATE_VALIDADE_S = 15 * 60  # tempo para concluir o login na eWeLink


def _agora() -> datetime:
    return datetime.now(BRASILIA).replace(tzinfo=None, microsecond=0)


def _num(v) -> Optional[float]:
    return float(v) if v is not None else None


def erro_ewelink(e: EwelinkError) -> AppError:
    return AppError(e.msg, status_code=e.status_code, code="ewelink_error", details=e.data)


# ── token (criptografado no banco) ───────────────────────────────────────


def ler_token() -> Optional[dict]:
    bruto = repo.ler_estado(repo.CHAVE_TOKEN)
    if not bruto:
        return None
    try:
        return json.loads(crypto.decrypt(bruto))
    except Exception:  # noqa: BLE001 - chave trocada/dado corrompido: trata como "não autenticado"
        return None


def gravar_token(token: dict) -> None:
    repo.gravar_estado(repo.CHAVE_TOKEN, crypto.encrypt(json.dumps(token)))


def cliente(settings: Settings) -> Ewelink:
    try:
        return Ewelink(settings, ler_token, gravar_token)
    except EwelinkError as e:
        raise erro_ewelink(e) from e


# ── OAuth 2.0 ────────────────────────────────────────────────────────────


def auth(settings: Settings) -> dict:
    """Gera a URL de login da eWeLink; o state fica guardado para validar o callback."""
    c = cliente(settings)
    state = secrets.token_hex(16)
    try:
        url = c.url_autorizacao(state)
    except EwelinkError as e:
        raise erro_ewelink(e) from e
    repo.gravar_estado(repo.CHAVE_STATE, f"{state}|{int(time.time())}")
    return {"url": url, "msg": "Abra a URL no navegador e faça login na conta eWeLink"}


def _state_valido(state: Optional[str]) -> bool:
    bruto = repo.ler_estado(repo.CHAVE_STATE)
    if not state or not bruto or "|" not in bruto:
        return False
    esperado, _, criado = bruto.partition("|")
    if not criado.isdigit() or time.time() - int(criado) > STATE_VALIDADE_S:
        return False
    return hmac.compare_digest(state.encode(), esperado.encode())


def callback(
    settings: Settings, code: Optional[str], region: Optional[str], state: Optional[str]
) -> dict:
    """Chamado pela própria eWeLink (sem sessão): protegido pelo state gerado em /ewelink/auth."""
    if not code:
        raise AppError("parâmetro code ausente", status_code=400, code="bad_request")
    c = cliente(settings)
    if not _state_valido(state):
        raise AppError(
            "state inválido: gere uma nova URL em /ewelink/auth",
            status_code=400,
            code="invalid_state",
        )
    repo.apagar_estado(repo.CHAVE_STATE)  # uso único
    try:
        token = c.trocar_code(code, region)
    except EwelinkError as e:
        raise erro_ewelink(e) from e
    return {"msg": "Autenticado na eWeLink", "region": token["region"]}


# ── diagnóstico ──────────────────────────────────────────────────────────


def dispositivos(settings: Settings, usuario: dict) -> dict:
    """Diagnóstico (master): dispositivos direto da eWeLink, sem passar pelo banco."""
    try:
        data = cliente(settings).listar_dispositivos()
    except EwelinkError as e:
        raise erro_ewelink(e) from e

    permitidos = None if is_master(usuario) else repo.deviceids_da_empresa(usuario["id_empresa"])
    lista = []
    for item in data.get("thingList", []):
        d = item.get("itemData", {})
        if permitidos is not None and d.get("deviceid") not in permitidos:
            continue
        lista.append(
            {
                "deviceid": d.get("deviceid"),
                "nome": d.get("name"),
                "online": d.get("online"),
                "modelo": d.get("productModel"),
                "marca": d.get("brandName"),
                "params": d.get("params"),
            }
        )
    return {"msg": "Integração eWeLink OK", "total": len(lista), "dispositivos": lista}


def status_coleta(settings: Settings) -> dict:
    """Saúde da coleta para o master: última execução, atraso, erros recentes e sessão eWeLink."""
    intervalo = settings.ewelink_coleta_intervalo_min
    agora = _agora()
    ultimas = repo.ultimas_execucoes(10)
    ultima_ok = repo.ultima_coleta_ok()
    resumo = repo.resumo_status(agora - timedelta(hours=24))

    minutos_desde_ok = (
        int((agora - ultima_ok["inicio"]).total_seconds() // 60) if ultima_ok else None
    )

    def ms(v):
        return datetime.fromtimestamp(v / 1000, BRASILIA).replace(tzinfo=None) if v else None

    t = ler_token() or {}
    pausa = coleta.pausada_ate()
    return {
        "intervalo_min": intervalo,
        "ultima_coleta_ok": ultima_ok["inicio"] if ultima_ok else None,
        "minutos_desde_ultima_ok": minutos_desde_ok,
        # atrasada se passou mais que 2 intervalos sem uma coleta bem-sucedida
        "atrasada": minutos_desde_ok is None or minutos_desde_ok > 2 * intervalo,
        "pausada_ate": datetime.fromtimestamp(pausa, BRASILIA).replace(tzinfo=None) if pausa else None,  # noqa: E501
        "ultimas_24h": {r["status"]: r["total"] for r in resumo},
        "eWeLink": {
            "token_salvo": bool(t),
            "acesso_expira": ms(t.get("at_expira")),
            "sessao_expira": ms(t.get("rt_expira")),
        },
        "ultimas_execucoes": [
            {
                "inicio": x["inicio"], "status": x["status"], "dispositivos": x["dispositivos"],
                "leituras": x["leituras"], "chamadas_api": x["chamadas_api"],
                "duracao_ms": x["duracao_ms"], "mensagem": x["mensagem"],
            }
            for x in ultimas
        ],
    }  # fmt: skip


# ── gráfico ──────────────────────────────────────────────────────────────


def _parse_data(valor: str) -> Optional[datetime]:
    for formato in (FORMATO_DATA, "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            pass
    return None


def _bad(msg: str) -> AppError:
    return AppError(msg, status_code=400, code="bad_request")


def grafico(usuario: dict, deviceid: str, horas=None, inicio=None, fim=None) -> dict:
    """Série de leituras de um dispositivo para montar o gráfico."""
    agora = datetime.now(BRASILIA).replace(tzinfo=None)
    if inicio or fim:
        dt_inicio = _parse_data(inicio) if inicio else None
        dt_fim = _parse_data(fim) if fim else agora
        if not dt_inicio or not dt_fim:
            raise _bad("inicio/fim inválidos. Use YYYY-MM-DD ou YYYY-MM-DD HH:MM")
        if len(fim or "") == 10:
            dt_fim = dt_fim.replace(hour=23, minute=59, second=59)
    else:
        try:
            horas = int(horas or 24)
        except ValueError:
            raise _bad("horas deve ser um número inteiro") from None
        dt_fim = agora
        dt_inicio = dt_fim - timedelta(hours=horas)

    if dt_inicio >= dt_fim:
        raise _bad("inicio deve ser anterior a fim")
    if dt_fim - dt_inicio > timedelta(hours=MAX_HORAS):
        raise _bad(f"Período máximo é de {MAX_HORAS // 24} dias")

    d = repo.buscar_ativo(deviceid, None if is_master(usuario) else usuario["id_empresa"])
    if not d:  # cliente pedindo dispositivo de outra empresa cai aqui também
        raise AppError("Dispositivo não encontrado", status_code=404, code="not_found")

    # períodos longos são agrupados para não mandar milhares de pontos ao celular
    horas_periodo = (dt_fim - dt_inicio).total_seconds() / 3600
    agrupamento_min = 0 if horas_periodo <= 36 else 15 if horas_periodo <= 96 else 60
    leituras = repo.leituras_pontos(d["id_dispositivo"], dt_inicio, dt_fim, agrupamento_min)
    # resumo sempre sobre as leituras originais (online), não sobre os pontos agrupados
    resumo = repo.leituras_resumo(d["id_dispositivo"], dt_inicio, dt_fim)

    pontos = []
    for item in leituras:
        ponto = {
            "data": item["data_leitura"],
            "temperatura": _num(item["temperatura"]),
            # agrupado: relé ligado na maior parte do intervalo
            "rele": None if item["rele"] is None else float(item["rele"]) >= 0.5,
            "online": bool(item["online"]),
        }
        if agrupamento_min:
            ponto["min"], ponto["max"] = _num(item["tmin"]), _num(item["tmax"])
        pontos.append(ponto)

    return {
        "deviceid": d["deviceid"],
        "nome": d["nome"],
        "modelo": d["modelo"],
        "online": bool(d["online"]),
        "periodo": {"inicio": dt_inicio, "fim": dt_fim},
        "faixa": {"min": _num(d["temp_min"]), "max": _num(d["temp_max"])},
        "agrupamento_min": agrupamento_min,
        "resumo": {
            "temperatura_atual": _num(d.get("temperatura")),
            # leitura mais recente de verdade (com agrupamento, o último ponto é uma média)
            "ultima_leitura": d.get("data_leitura"),
            "minima": _num(resumo.get("minima")),
            "maxima": _num(resumo.get("maxima")),
            "media": _num(resumo.get("media")),
            "compressor_ligado_pct": _num(resumo.get("compressor_pct")),
            "leituras": int(resumo.get("leituras") or 0),
            "leituras_offline": int(resumo.get("offline") or 0),
        },
        "total_pontos": len(pontos),
        "pontos": pontos,
    }


# ── relé ─────────────────────────────────────────────────────────────────


def alterar_rele(settings: Settings, usuario: dict, deviceid: str, ligado) -> dict:
    """Liga/desliga o relé (compressor). Somente perfil admin: o da master comanda todos;
    o do cliente, os da própria empresa. Todo comando enviado fica registrado na tabela comando."""
    if not isinstance(ligado, bool):
        raise _bad('Envie {"ligado": true} ou {"ligado": false}')
    if usuario.get("perfil") != "admin":
        raise AppError(
            "Somente administradores podem ligar ou desligar o compressor",
            status_code=403,
            code="forbidden",
        )

    d = repo.buscar_ativo(deviceid, None if is_master(usuario) else usuario["id_empresa"])
    if not d:
        raise AppError("Dispositivo não encontrado", status_code=404, code="not_found")
    if not d["online"]:
        raise AppError(
            "Dispositivo offline: o comando não chegaria ao aparelho",
            status_code=409,
            code="offline",
        )

    params = {"switch": "on" if ligado else "off"}
    erro: Optional[EwelinkError] = None
    try:
        Ewelink(settings, ler_token, gravar_token).alterar_status(deviceid, params)
        resposta = {"msg": "ok"}
    except EwelinkError as e:
        erro = e
        resposta = {"msg": e.msg, **e.data}

    id_comando = repo.registrar_comando(
        d["id_dispositivo"], usuario["id_usuario"], "rele_ligar" if ligado else "rele_desligar",
        params, erro is None, resposta,
    )  # fmt: skip
    if erro is not None:
        raise AppError(erro.msg, status_code=502, code="ewelink_error", details=erro.data)

    # reflete na hora no app (que lê do banco), sem esperar a próxima coleta; como o estado já fica
    # atualizado, a coleta não registra esta mudança como "externa"
    repo.atualizar_rele(d["id_dispositivo"], ligado)
    eventos.registrar_comando(
        d["id_dispositivo"], ligado, usuario["id_usuario"], id_comando, d.get("temperatura")
    )
    return {
        "msg": f"Compressor {'ligado' if ligado else 'desligado'}",
        "deviceid": deviceid,
        "ligado": ligado,
    }


# ── coleta (cron) ────────────────────────────────────────────────────────


def coletar(settings: Settings) -> dict:
    return coleta.coletar(settings, cliente(settings))
