"""SQL dos eventos (linha do tempo e alertas) e do reprocessamento do histórico."""

from collections.abc import Sequence
from datetime import datetime
from typing import Optional

from app.db import execute, fetch_all, insert


def abertos() -> dict:
    """Eventos em andamento (fim NULL), indexados por (id_dispositivo, tipo)."""
    rows = fetch_all(
        "SELECT id_evento, id_dispositivo, tipo, inicio, valor, detalhe FROM evento WHERE fim IS NULL"  # noqa: E501
    )
    return {(r["id_dispositivo"], r["tipo"]): r for r in rows}


def criar(
    id_dispositivo: int, tipo: str, origem: str, inicio: datetime, fim: Optional[datetime],
    valor: Optional[float], detalhe: str, id_usuario: Optional[int] = None, id_comando: Optional[int] = None,  # noqa: E501
) -> int:  # fmt: skip
    return insert(
        "INSERT INTO evento (id_dispositivo, tipo, origem, id_usuario, id_comando, inicio, fim, valor, detalhe)"  # noqa: E501
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        [id_dispositivo, tipo, origem, id_usuario, id_comando, inicio, fim, valor, detalhe],
    )


def fechar(id_evento: int, fim: datetime, detalhe: str) -> None:
    execute(
        "UPDATE evento SET fim = %s, detalhe = %s WHERE id_evento = %s", [fim, detalhe, id_evento]
    )


def atualizar_pico(id_evento: int, valor: float) -> None:
    execute("UPDATE evento SET valor = %s WHERE id_evento = %s", [valor, id_evento])


def atualizar_fora_desde(id_dispositivo: int, desde: Optional[datetime]) -> None:
    execute(
        "UPDATE dispositivo SET fora_faixa_desde = %s WHERE id_dispositivo = %s",
        [desde, id_dispositivo],
    )


def listar(
    id_empresa: Optional[int], deviceid: Optional[str], tipos: Optional[Sequence[str]], ativos: bool,  # noqa: E501
    inicio: Optional[str], fim: Optional[str], limite: int, offset: int,
) -> list:  # fmt: skip
    """Eventos com nome do dispositivo, empresa e usuário, do mais recente para o mais antigo."""
    sql = (
        "SELECT e.id_evento, e.tipo, e.origem, e.inicio, e.fim, e.valor, e.detalhe,"
        " d.deviceid, d.nome AS dispositivo, d.temp_min, d.temp_max,"
        " emp.id_empresa, emp.nome AS empresa, u.nome AS usuario"
        " FROM evento e"
        " JOIN dispositivo d ON d.id_dispositivo = e.id_dispositivo"
        " LEFT JOIN empresa emp ON emp.id_empresa = d.id_empresa"
        " LEFT JOIN usuario u ON u.id_usuario = e.id_usuario"
        " WHERE d.ativo = 1"
    )
    params: list = []
    if id_empresa is not None:
        sql += " AND d.id_empresa = %s"
        params.append(id_empresa)
    if deviceid:
        sql += " AND d.deviceid = %s"
        params.append(deviceid)
    if tipos:
        sql += " AND e.tipo IN (" + ",".join(["%s"] * len(tipos)) + ")"
        params += list(tipos)
    if ativos:
        sql += " AND e.fim IS NULL"
    if inicio:
        sql += " AND e.inicio >= %s"
        params.append(inicio)
    if fim:
        sql += " AND e.inicio <= %s"
        params.append(fim)
    sql += " ORDER BY e.inicio DESC, e.id_evento DESC LIMIT %s OFFSET %s"
    params += [int(limite), int(offset)]
    return fetch_all(sql, params)


# ── reprocessamento do histórico ─────────────────────────────────────────


def faixas_dispositivos() -> list:
    return fetch_all("SELECT id_dispositivo, temp_min, temp_max, tolerancia_min FROM dispositivo")


def todas_leituras() -> list:
    return fetch_all(
        "SELECT id_dispositivo, temperatura, rele, online, data_leitura FROM leitura"
        " ORDER BY id_dispositivo, data_leitura"
    )


def apagar_eventos_de_sistema() -> None:
    """Preserva os comandos do app (origem app) e os eventos das câmeras."""
    execute(
        "DELETE FROM evento WHERE origem IN ('sistema', 'externo')"
        " AND tipo NOT IN ('camera_deteccao', 'camera_offline')"
    )
