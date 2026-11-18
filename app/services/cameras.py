"""Câmeras EZVIZ: cadastro e vínculo (master), vídeo ao vivo/gravação, alarmes com foto e coleta.

Acesso: a câmera herda a empresa do refrigerador que vigia. Master vê todas; cliente, só as câmeras
dos refrigeradores da própria empresa (outra empresa responde 404). O token da EZVIZ nunca sai do
backend: o app recebe apenas um link temporário de vídeo daquela câmera.
"""

import json
import os
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.config import Settings
from app.core import crypto
from app.core.auth import is_master
from app.core.errors import AppError
from app.integrations.ezviz import Ezviz, EzvizError
from app.repositories import auditoria
from app.repositories import cameras as repo

try:
    import fcntl  # Linux (KingHost, Docker)
except ImportError:  # Windows: sem trava de arquivo
    fcntl = None

BRASILIA = timezone(timedelta(hours=-3))
FORMATO = "%Y-%m-%d %H:%M:%S"
CODIGO = re.compile(r"^[A-Z]{6}$")  # código de verificação da etiqueta: 6 letras maiúsculas
QUALIDADES = ("hd", "sd")
EXPIRA_LINK_S = 300  # link de vídeo vale 5 min (o player renova ao reabrir)
REUSO_MIN_RESTANTE_S = 120  # só reaproveita link ao vivo que ainda tenha pelo menos 2 min
_LINKS_AO_VIVO: dict = {}  # (id_camera, qualidade, h265) -> (resposta, vence_em); por processo
MAX_GRAVACAO_H = 6  # trecho máximo de gravação por pedido
PRIMEIRA_IMPORTACAO_H = 24  # na 1ª coleta de uma câmera, importa os alarmes das últimas 24h
ESPACAMENTO_MINIMO_S = 60


def _agora() -> datetime:
    return datetime.now(BRASILIA).replace(tzinfo=None, microsecond=0)


def _iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _raiz_storage() -> str:
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(raiz, "storage")


def pasta_fotos() -> str:
    return os.environ.get("EZVIZ_FOTOS_DIR") or os.path.join(_raiz_storage(), "cameras")


def _cliente(settings: Settings) -> Ezviz:
    try:
        return Ezviz.from_settings(settings)
    except EzvizError as e:
        raise _como_app_error(e) from None


def _como_app_error(e: EzvizError) -> AppError:
    return AppError(
        e.msg,
        status_code=e.status_code,
        code="ezviz_unavailable" if e.status_code >= 500 else "ezviz_error",
        details=e.data,
    )


def _publica(c: dict) -> dict:
    return {
        "id_camera": c["id_camera"],
        "deviceserial": c["deviceserial"],
        "canal": c["canal"],
        "nome": c["nome"],
        "modelo": c["modelo"],
        "online": bool(c["online"]),
        "criptografada": bool(c["criptografada"]),
        "codigo_cadastrado": bool(c["codigo_cifrado"]),  # o código em si nunca sai
        "ativo": bool(c["ativo"]),
        "data_status": _iso(c["data_status"]),
        "ultimo_alarme_em": _iso(c["ultimo_alarme_em"]),
        "refrigerador": (
            {"deviceid": c["deviceid"], "nome": (c["refrigerador"] or "").strip()}
            if c.get("deviceid")
            else None
        ),
        "empresa": (
            {"id_empresa": c["id_empresa"], "nome": c["empresa"]} if c.get("id_empresa") else None
        ),
    }


def _nao_encontrada() -> AppError:
    return AppError("Câmera não encontrada", status_code=404, code="not_found")


def _visivel(usuario: dict, id_camera: int) -> dict:
    """Câmera que o usuário pode ver. Outra empresa responde como inexistente (404)."""
    c = repo.buscar(id_camera)
    if not c:
        raise _nao_encontrada()
    if not is_master(usuario) and (
        not c["ativo"] or not c["refrigerador_ativo"] or c["id_empresa"] != usuario["id_empresa"]
    ):
        raise _nao_encontrada()
    return c


def _codigo(c: dict) -> Optional[str]:
    return crypto.decrypt(c["codigo_cifrado"]) if c.get("codigo_cifrado") else None


# ── listagem e cadastro ──────────────────────────────────────────────────


def listar(usuario: dict, incluir_inativas: bool = False) -> dict:
    master = is_master(usuario)
    rows = repo.listar(None if master else usuario["id_empresa"], master and incluir_inativas)
    return {"total": len(rows), "cameras": [_publica(c) for c in rows]}


def conta(settings: Settings) -> dict:
    """Master: câmeras da conta EZVIZ e se já estão cadastradas no sistema."""
    try:
        canais = _cliente(settings).listar_cameras()
    except EzvizError as e:
        raise _como_app_error(e) from None
    idx = {(c["deviceserial"], c["canal"]): c["id_camera"] for c in repo.listar_cadastradas()}
    return {
        "total": len(canais),
        "cameras": [
            {
                "deviceserial": c["deviceSerial"],
                "canal": c["channelNo"],
                "nome": c.get("channelName"),
                "online": c.get("status") == 1,
                "criptografada": c.get("isEncrypt") == 1,
                "id_camera": idx.get((c["deviceSerial"], c["channelNo"])),
            }
            for c in canais
        ],
    }


def _id_dispositivo(deviceid: Optional[str]) -> Optional[int]:
    if deviceid is None:
        return None
    id_disp = repo.id_dispositivo_por_deviceid(deviceid)
    if id_disp is None:
        raise AppError("Refrigerador não encontrado", status_code=400, code="bad_request")
    return id_disp


def _codigo_cifrado(codigo: Optional[str]) -> Optional[str]:
    if codigo is None:
        return None
    limpo = codigo.strip().upper()
    if not CODIGO.match(limpo):
        raise AppError(
            "codigo deve ter 6 letras (código de verificação da etiqueta da câmera)",
            status_code=400,
        )
    return crypto.encrypt(limpo)


def cadastrar(settings: Settings, autor: dict, dados: dict) -> dict:
    serial = str(dados.get("deviceserial") or "").strip().upper()
    canal = dados.get("canal", 1)
    if not serial:
        raise AppError("deviceserial é obrigatório", status_code=400)
    existe = repo.buscar_por_serial_canal(serial, canal)
    if existe:
        raise AppError(
            "Câmera já cadastrada",
            status_code=409,
            code="conflict",
            details={"id_camera": existe["id_camera"]},
        )
    # confirma que a câmera existe na conta EZVIZ e pega modelo/criptografia
    try:
        info = _cliente(settings).info(serial) or {}
    except EzvizError as e:
        raise AppError(
            f"Câmera não encontrada na conta EZVIZ: {e.msg}", status_code=400, details=e.data
        ) from None

    id_disp = _id_dispositivo(dados.get("deviceid"))
    cifrado = _codigo_cifrado(dados.get("codigo"))
    nome = str(dados.get("nome") or info.get("deviceName") or serial).strip()[:150]
    id_camera = repo.inserir(
        {
            "deviceserial": serial,
            "canal": canal,
            "nome": nome,
            "modelo": info.get("model"),
            "id_dispositivo": id_disp,
            "criptografada": 1 if info.get("isEncrypt") == 1 else 0,
            "codigo_cifrado": cifrado,
            "online": 1 if info.get("status") == 1 else 0,
            "data_status": _agora(),
            "ativo": 1,
        }
    )
    auditoria.registrar(
        autor["id_usuario"],
        "camera_cadastrada",
        "camera",
        id_camera,
        {
            "deviceserial": serial,
            "canal": canal,
            "deviceid": dados.get("deviceid"),
            "codigo": bool(cifrado),
        },
    )
    return {"msg": "Câmera cadastrada", "id_camera": id_camera}


def editar(autor: dict, id_camera: int, dados: dict) -> dict:
    """`dados` só tem as chaves enviadas (nome, deviceid, codigo, ativo)."""
    c = repo.buscar(id_camera)
    if not c:
        raise _nao_encontrada()

    campos: dict = {}
    if "nome" in dados:
        if not isinstance(dados["nome"], str) or not dados["nome"].strip():
            raise AppError("nome não pode ficar vazio", status_code=400)
        campos["nome"] = dados["nome"].strip()[:150]
    if "deviceid" in dados:
        campos["id_dispositivo"] = _id_dispositivo(dados["deviceid"])
    if "codigo" in dados:
        campos["codigo_cifrado"] = _codigo_cifrado(dados["codigo"])
    if "ativo" in dados:
        if not isinstance(dados["ativo"], bool):
            raise AppError("ativo deve ser true ou false", status_code=400)
        campos["ativo"] = 1 if dados["ativo"] else 0
    if not campos:
        raise AppError("Envie ao menos um campo: nome, deviceid, codigo, ativo", status_code=400)

    repo.atualizar(id_camera, campos)
    # nunca registra o código na auditoria, só se ele mudou
    antes = {k: (bool(c[k]) if k == "codigo_cifrado" else c[k]) for k in campos}
    depois = {k: (bool(v) if k == "codigo_cifrado" else v) for k, v in campos.items()}
    auditoria.registrar(
        autor["id_usuario"],
        "camera_alterada",
        "camera",
        id_camera,
        {"antes": antes, "depois": depois},
    )
    return {"msg": "Câmera atualizada", "id_camera": id_camera}


# ── vídeo ────────────────────────────────────────────────────────────────


def _link(settings: Settings, c: dict, h265: bool = False, **kw) -> dict:
    # Sem checar a playlist aqui: a EZVIZ segura essa resposta até acordar a câmera (segundos).
    try:
        dados = _cliente(settings).endereco(
            c["deviceserial"],
            c["canal"],
            codigo=_codigo(c),
            expira_s=EXPIRA_LINK_S,
            h265=h265,
            **kw,
        )
    except EzvizError as e:
        raise _como_app_error(e) from None
    return {
        "url": (dados or {}).get("url"),
        "protocolo": kw.get("protocolo", "hls"),
        "expira_em": _iso(_agora() + timedelta(seconds=EXPIRA_LINK_S)),
        "camera": {"id_camera": c["id_camera"], "nome": c["nome"]},
    }


def ao_vivo(settings: Settings, usuario: dict, id_camera: int, qualidade: str, h265: bool) -> dict:
    c = _visivel(usuario, id_camera)
    if qualidade not in QUALIDADES:
        raise AppError("qualidade deve ser hd ou sd", status_code=400)
    # O link ao vivo é da câmera, não do usuário (acesso já checado): reaproveita por minutos.
    chave = (c["id_camera"], qualidade, bool(h265))
    guardado = _LINKS_AO_VIVO.get(chave)
    if guardado and guardado[1] - time.time() > REUSO_MIN_RESTANTE_S:
        return guardado[0]
    resp = _link(settings, c, h265=h265, tipo="ao_vivo", qualidade=qualidade)
    _LINKS_AO_VIVO[chave] = (resp, time.time() + EXPIRA_LINK_S)
    return resp


def gravacao(
    settings: Settings,
    usuario: dict,
    id_camera: int,
    inicio: Optional[str],
    fim: Optional[str],
    origem: str,
    h265: bool,
) -> dict:
    c = _visivel(usuario, id_camera)
    if origem not in ("nuvem", "sd"):
        raise AppError(
            "origem deve ser nuvem (CloudPlay) ou sd (cartão da câmera)", status_code=400
        )
    try:
        dt_ini, dt_fim = datetime.strptime(inicio, FORMATO), datetime.strptime(fim, FORMATO)
    except (TypeError, ValueError):
        raise AppError(
            "inicio e fim são obrigatórios no formato YYYY-MM-DD HH:MM:SS", status_code=400
        ) from None
    if dt_ini >= dt_fim or dt_fim - dt_ini > timedelta(hours=MAX_GRAVACAO_H):
        raise AppError(
            f"Período inválido: inicio < fim e no máximo {MAX_GRAVACAO_H} horas", status_code=400
        )
    return _link(settings, c, h265=h265, tipo=origem, inicio=inicio, fim=fim)


# ── alarmes ──────────────────────────────────────────────────────────────


def alarmes(
    usuario: dict, id_camera: int, limite: int, inicio: Optional[str], fim: Optional[str]
) -> dict:
    _visivel(usuario, id_camera)
    rows = repo.listar_alarmes(id_camera, inicio, fim, min(200, max(1, limite)))
    return {
        "total": len(rows),
        "alarmes": [
            {
                "id_alarme": r["id_alarme"],
                "tipo": r["tipo"],
                "data": _iso(r["data_alarme"]),
                "tem_foto": bool(r["foto_arquivo"]),
                "foto_criptografada": bool(r["foto_criptografada"]),
            }
            for r in rows
        ],
    }


def foto(usuario: dict, id_alarme: int) -> str:
    """Caminho absoluto da foto do alarme (ou 404)."""
    a = repo.buscar_alarme(id_alarme)
    if not a:
        raise AppError("Alarme não encontrado", status_code=404, code="not_found")
    try:
        _visivel(usuario, a["id_camera"])
    except AppError:
        raise AppError("Alarme não encontrado", status_code=404, code="not_found") from None
    if not a["foto_arquivo"]:
        sufixo = " (câmera com criptografia ativa)" if a["foto_criptografada"] else ""
        raise AppError("Foto não disponível" + sufixo, status_code=404, code="not_found")
    base = os.path.realpath(pasta_fotos())
    caminho = os.path.realpath(os.path.join(base, a["foto_arquivo"]))
    if os.path.commonpath([base, caminho]) != base or not os.path.isfile(caminho):
        raise AppError("Arquivo da foto não encontrado", status_code=404, code="not_found")
    return caminho


# ── coleta (cron) ────────────────────────────────────────────────────────


@contextmanager
def _trava():
    """True se conseguiu a trava; False se outra coleta de câmeras já está rodando."""
    if fcntl is None:
        yield True
        return
    pasta = _raiz_storage()
    os.makedirs(pasta, exist_ok=True)
    with open(os.path.join(pasta, "coleta_ezviz.lock"), "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _log(status, inicio, t0, mensagem=None, cameras=0, alarmes=0, chamadas=0) -> None:
    repo.inserir_log(
        {
            "inicio": inicio,
            "fim": _agora(),
            "status": status,
            "dispositivos": cameras,
            "leituras": alarmes,
            "chamadas_api": chamadas,
            "duracao_ms": int((time.monotonic() - t0) * 1000),
            "mensagem": mensagem,
        }
    )


def coletar(settings: Settings) -> dict:
    """Cron: status (online) de cada câmera e importação dos alarmes novos com foto."""
    inicio, t0 = _agora(), time.monotonic()
    with _trava() as conseguiu:
        if not conseguiu:
            _log("ignorada", inicio, t0, "Outra coleta de câmeras em andamento")
            return {"msg": "Outra coleta de câmeras em andamento", "status": "ignorada"}
        ultima = repo.ultima_coleta_ok()
        if ultima and (inicio - ultima["inicio"]).total_seconds() < ESPACAMENTO_MINIMO_S:
            _log("ignorada", inicio, t0, "Coleta de câmeras recente")
            return {"msg": "Coleta de câmeras recente", "status": "ignorada"}
        try:
            return _executar(settings, inicio, t0)
        except EzvizError as e:
            _log("erro", inicio, t0, e.msg)
            raise _como_app_error(e) from None


def _executar(settings: Settings, inicio: datetime, t0: float) -> dict:
    cams = repo.listar_ativas()
    if not cams:
        _log("ok", inicio, t0, "Nenhuma câmera cadastrada")
        return {"msg": "Nenhuma câmera cadastrada", "status": "ok", "cameras": 0}

    ez = _cliente(settings)
    status = {(c["deviceSerial"], c["channelNo"]): c for c in ez.listar_cameras()}
    chamadas, novos_total, avisos = 1, 0, []
    abertos = repo.eventos_offline_abertos()
    agora_ms = int(time.time() * 1000)
    pasta = pasta_fotos()

    for c in cams:
        s = status.get((c["deviceserial"], c["canal"]))
        online = 1 if s and s.get("status") == 1 else 0
        campos = {"online": online, "data_status": inicio}
        if s:
            campos["criptografada"] = 1 if s.get("isEncrypt") == 1 else 0
        else:
            avisos.append(f"{c['deviceserial']} não está mais na conta EZVIZ")

        # câmera vigiando um refrigerador: offline vira alerta na linha do tempo dele
        if c["id_dispositivo"]:
            aberto = abertos.get(c["id_dispositivo"])
            if not online and not aberto:
                repo.inserir_evento(
                    c["id_dispositivo"],
                    "camera_offline",
                    inicio,
                    None,
                    json.dumps(
                        {"id_camera": c["id_camera"], "camera": c["nome"]}, ensure_ascii=False
                    ),
                )
            elif online and aberto:
                duracao = int((inicio - aberto["inicio"]).total_seconds() // 60)
                detalhe = {**json.loads(aberto["detalhe"] or "{}"), "duracao_min": duracao}
                repo.fechar_evento(
                    aberto["id_evento"], inicio, json.dumps(detalhe, ensure_ascii=False)
                )

        # alarmes desde o último importado (1 min de folga; duplicados são ignorados pelo alarm_id)
        desde = (
            c["ultimo_alarme_em"] - timedelta(minutes=1)
            if c["ultimo_alarme_em"]
            else inicio - timedelta(hours=PRIMEIRA_IMPORTACAO_H)
        )
        desde_ms = int(desde.replace(tzinfo=BRASILIA).timestamp() * 1000)
        try:
            lista = ez.alarmes(c["deviceserial"], desde_ms, agora_ms)
            chamadas += 1
        except EzvizError as e:
            avisos.append(f"{c['deviceserial']}: {e.msg}")
            repo.atualizar(c["id_camera"], campos)
            continue

        ja = repo.alarmes_existentes([a["alarmId"] for a in lista if a.get("alarmId")])
        mais_recente = c["ultimo_alarme_em"]
        for a in sorted(lista, key=lambda x: x.get("alarmTime", 0)):
            if not a.get("alarmId") or a["alarmId"] in ja:
                continue
            data = datetime.fromtimestamp(a["alarmTime"] / 1000, BRASILIA).replace(tzinfo=None)
            cripto = a.get("isEncrypt") == 1
            arquivo = None
            # foto criptografada não é visualizável sem a chave da câmera: não baixa
            if a.get("alarmPicUrl") and not cripto:
                conteudo = ez.baixar(a["alarmPicUrl"])
                if conteudo:
                    rel = os.path.join(
                        c["deviceserial"], data.strftime("%Y-%m"), f"{a['alarmId']}.jpg"
                    )
                    destino = os.path.join(pasta, rel)
                    os.makedirs(os.path.dirname(destino), exist_ok=True)
                    with open(destino, "wb") as f:
                        f.write(conteudo)
                    arquivo = rel.replace(os.sep, "/")
            id_alarme = repo.inserir_alarme(
                {
                    "id_camera": c["id_camera"],
                    "alarm_id": a["alarmId"],
                    "tipo": a.get("alarmType"),
                    "data_alarme": data,
                    "foto_arquivo": arquivo,
                    "foto_criptografada": 1 if cripto else 0,
                }
            )
            novos_total += 1
            if c["id_dispositivo"]:
                detalhe = {
                    "id_camera": c["id_camera"],
                    "camera": c["nome"],
                    "id_alarme": id_alarme,
                    "tipo_alarme": a.get("alarmType"),
                    "tem_foto": bool(arquivo),
                }
                repo.inserir_evento(
                    c["id_dispositivo"],
                    "camera_deteccao",
                    data,
                    data,
                    json.dumps(detalhe, ensure_ascii=False),
                )
            if not mais_recente or data > mais_recente:
                mais_recente = data
        if mais_recente:
            campos["ultimo_alarme_em"] = mais_recente
        repo.atualizar(c["id_camera"], campos)

    online_total = sum(
        1 for c in cams if (status.get((c["deviceserial"], c["canal"])) or {}).get("status") == 1
    )
    msg = f"{online_total}/{len(cams)} câmeras online, {novos_total} alarmes novos" + (
        " | " + "; ".join(avisos) if avisos else ""
    )
    _log("ok", inicio, t0, msg, len(cams), novos_total, chamadas)
    return {
        "msg": "Coleta de câmeras realizada",
        "status": "ok",
        "cameras": len(cams),
        "online": online_total,
        "alarmes_novos": novos_total,
        "chamadas_api": chamadas,
        "avisos": avisos,
    }


def status(settings: Settings) -> dict:
    ultimas = repo.ultimas_coletas(10)
    try:
        token = _cliente(settings).status_token()  # estado do token, nunca o valor
        if token.get("expira_ms"):
            token["expira_em"] = _iso(
                datetime.fromtimestamp(token.pop("expira_ms") / 1000, BRASILIA).replace(tzinfo=None)
            )
    except AppError as e:
        token = {"msg": e.message}
    return {
        "token": token,
        "ultimas_execucoes": [
            {
                "inicio": _iso(r["inicio"]),
                "status": r["status"],
                "cameras": r["dispositivos"],
                "alarmes_novos": r["leituras"],
                "chamadas_api": r["chamadas_api"],
                "duracao_ms": r["duracao_ms"],
                "mensagem": r["mensagem"],
            }
            for r in ultimas
        ],
    }
