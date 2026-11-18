"""Consultas de câmeras EZVIZ, alarmes, eventos da linha do tempo e log de coleta (SQL)."""

from datetime import datetime
from typing import Optional

from app.db import execute, fetch_all, fetch_one, insert

_SELECT_COMPLETO = (
    "SELECT c.*, d.deviceid, d.nome AS refrigerador, d.id_empresa, d.ativo AS refrigerador_ativo,"
    " e.nome AS empresa FROM camera c"
    " LEFT JOIN dispositivo d ON d.id_dispositivo = c.id_dispositivo"
    " LEFT JOIN empresa e ON e.id_empresa = d.id_empresa"
)
# nomes de coluna aceitos em INSERT/UPDATE (lista fixa: nunca vêm do cliente)
_CAMPOS_CAMERA = {
    "deviceserial",
    "canal",
    "nome",
    "modelo",
    "id_dispositivo",
    "criptografada",
    "codigo_cifrado",
    "online",
    "data_status",
    "ultimo_alarme_em",
    "ativo",
}


def listar(id_empresa: Optional[int] = None, incluir_inativas: bool = False) -> list:
    """id_empresa=None: todas (master). Cliente: só câmeras ativas de refrigeradores da empresa."""
    sql, params = _SELECT_COMPLETO + " WHERE 1 = 1", []
    if id_empresa is not None:
        sql += " AND c.ativo = 1 AND d.ativo = 1 AND d.id_empresa = %s"
        params.append(id_empresa)
    elif not incluir_inativas:
        sql += " AND c.ativo = 1"
    return fetch_all(sql + " ORDER BY c.nome", params)


def buscar(id_camera: int) -> Optional[dict]:
    return fetch_one(_SELECT_COMPLETO + " WHERE c.id_camera = %s", [id_camera])


def listar_cadastradas() -> list:
    return fetch_all("SELECT id_camera, deviceserial, canal FROM camera")


def buscar_por_serial_canal(serial: str, canal: int) -> Optional[dict]:
    return fetch_one(
        "SELECT id_camera FROM camera WHERE deviceserial = %s AND canal = %s", [serial, canal]
    )


def listar_ativas() -> list:
    return fetch_all("SELECT * FROM camera WHERE ativo = 1")


def id_dispositivo_por_deviceid(deviceid: str) -> Optional[int]:
    row = fetch_one("SELECT id_dispositivo FROM dispositivo WHERE deviceid = %s", [deviceid])
    return row["id_dispositivo"] if row else None


def inserir(campos: dict) -> int:
    cols = [c for c in campos if c in _CAMPOS_CAMERA]
    return insert(
        f"INSERT INTO camera ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",  # noqa: S608
        [campos[c] for c in cols],
    )


def atualizar(id_camera: int, campos: dict) -> None:
    cols = [c for c in campos if c in _CAMPOS_CAMERA]
    if cols:
        execute(
            f"UPDATE camera SET {', '.join(c + ' = %s' for c in cols)} WHERE id_camera = %s",  # noqa: S608
            [campos[c] for c in cols] + [id_camera],
        )


# ── alarmes ──────────────────────────────────────────────────────────────


def listar_alarmes(id_camera: int, inicio: Optional[str], fim: Optional[str], limite: int) -> list:
    sql, params = "SELECT * FROM camera_alarme WHERE id_camera = %s", [id_camera]
    if inicio:
        sql += " AND data_alarme >= %s"
        params.append(inicio)
    if fim:
        sql += " AND data_alarme <= %s"
        params.append(fim)
    return fetch_all(sql + " ORDER BY data_alarme DESC LIMIT %s", params + [limite])


def buscar_alarme(id_alarme: int) -> Optional[dict]:
    return fetch_one("SELECT * FROM camera_alarme WHERE id_alarme = %s", [id_alarme])


def alarmes_existentes(alarm_ids: list) -> set:
    if not alarm_ids:
        return set()
    rows = fetch_all(
        "SELECT alarm_id FROM camera_alarme WHERE alarm_id IN ("  # noqa: S608
        + ",".join(["%s"] * len(alarm_ids))
        + ")",
        list(alarm_ids),
    )
    return {r["alarm_id"] for r in rows}


def inserir_alarme(campos: dict) -> int:
    return insert(
        "INSERT INTO camera_alarme (id_camera, alarm_id, tipo, data_alarme, foto_arquivo,"
        " foto_criptografada) VALUES (%s, %s, %s, %s, %s, %s)",
        [
            campos["id_camera"],
            campos["alarm_id"],
            campos["tipo"],
            campos["data_alarme"],
            campos["foto_arquivo"],
            campos["foto_criptografada"],
        ],
    )


# ── linha do tempo do refrigerador ───────────────────────────────────────


def eventos_offline_abertos() -> dict:
    """id_dispositivo -> evento camera_offline em aberto."""
    rows = fetch_all(
        "SELECT id_evento, id_dispositivo, inicio, detalhe FROM evento"
        " WHERE tipo = 'camera_offline' AND fim IS NULL ORDER BY inicio"
    )
    return {r["id_dispositivo"]: r for r in rows}


def inserir_evento(
    id_dispositivo: int, tipo: str, inicio: datetime, fim: Optional[datetime], detalhe: str
) -> int:
    return insert(
        "INSERT INTO evento (id_dispositivo, tipo, origem, inicio, fim, valor, detalhe)"
        " VALUES (%s, %s, 'sistema', %s, %s, NULL, %s)",
        [id_dispositivo, tipo, inicio, fim, detalhe],
    )


def fechar_evento(id_evento: int, fim: datetime, detalhe: str) -> None:
    execute(
        "UPDATE evento SET fim = %s, detalhe = %s WHERE id_evento = %s", [fim, detalhe, id_evento]
    )


# ── log de coleta ────────────────────────────────────────────────────────


def inserir_log(campos: dict) -> int:
    return insert(
        "INSERT INTO coleta_log (fonte, inicio, fim, status, dispositivos, leituras, chamadas_api,"
        " duracao_ms, mensagem) VALUES ('ezviz', %s, %s, %s, %s, %s, %s, %s, %s)",
        [
            campos["inicio"],
            campos["fim"],
            campos["status"],
            campos["dispositivos"],
            campos["leituras"],
            campos["chamadas_api"],
            campos["duracao_ms"],
            campos["mensagem"],
        ],
    )


def ultima_coleta_ok() -> Optional[dict]:
    return fetch_one(
        "SELECT inicio FROM coleta_log WHERE fonte = 'ezviz' AND status = 'ok'"
        " ORDER BY id_coleta DESC LIMIT 1"
    )


def ultimas_coletas(limite: int = 10) -> list:
    return fetch_all(
        "SELECT * FROM coleta_log WHERE fonte = 'ezviz' ORDER BY id_coleta DESC LIMIT %s", [limite]
    )
