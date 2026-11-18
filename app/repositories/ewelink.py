"""SQL da integração eWeLink: estado/token, coleta (log, dispositivo, leitura), comando e gráfico.

Escreve em `dispositivo` e `leitura` só no que a coleta precisa (estado atual e leitura nova);
o cadastro/listagem de dispositivos fica em `app.repositories.dispositivos`.
"""

import json
from datetime import datetime
from typing import Optional

from app.db import execute, fetch_all, fetch_one, insert

PROVEDOR = "ewelink"
CHAVE_TOKEN = "ewelink_token"  # noqa: S105
CHAVE_STATE = "ewelink_state"
CHAVE_COLETA = "ewelink_coleta"

# colunas atualizadas a cada coleta (o vínculo com a empresa nunca é alterado aqui)
COLUNAS_COLETA = (
    "nome", "modelo", "marca", "online", "temperatura", "umidade",
    "rele", "sinal", "limite_min", "limite_max", "data_leitura",
)  # fmt: skip
# só são atualizadas quando o aparelho está online (offline: a eWeLink repete o último valor)
COLUNAS_SO_ONLINE = ("temperatura", "umidade", "rele", "sinal", "data_leitura")


# ── estado (chave/valor) ─────────────────────────────────────────────────


def ler_estado(chave: str) -> Optional[str]:
    row = fetch_one("SELECT valor FROM integracao_estado WHERE chave = %s", [chave])
    return row["valor"] if row else None


def gravar_estado(chave: str, valor: str) -> None:
    execute(
        "INSERT INTO integracao_estado (chave, valor) VALUES (%s, %s)"
        " ON DUPLICATE KEY UPDATE valor = VALUES(valor)",
        [chave, valor],
    )


def apagar_estado(chave: str) -> None:
    execute("DELETE FROM integracao_estado WHERE chave = %s", [chave])


# ── dispositivos (só o que a coleta/rotas da eWeLink precisam) ──────────


def deviceids_da_empresa(id_empresa: int) -> set:
    rows = fetch_all(
        "SELECT deviceid FROM dispositivo WHERE provedor = %s AND id_empresa = %s AND ativo = 1",
        [PROVEDOR, id_empresa],
    )
    return {r["deviceid"] for r in rows}


def deviceids_online() -> list:
    rows = fetch_all(
        "SELECT deviceid FROM dispositivo WHERE provedor = %s AND online = 1", [PROVEDOR]
    )
    return [r["deviceid"] for r in rows]


def estado_anterior() -> dict:
    """Estado de cada dispositivo antes da coleta: base para detectar eventos. {id_dispositivo: linha}."""  # noqa: E501
    rows = fetch_all(
        "SELECT id_dispositivo, online, temperatura, rele, data_leitura, temp_min, temp_max,"
        " tolerancia_min, fora_faixa_desde FROM dispositivo WHERE provedor = %s",
        [PROVEDOR],
    )
    return {r["id_dispositivo"]: r for r in rows}


def salvar_lote(dispositivos: list) -> None:
    """Insere ou atualiza o estado atual vindo do provedor. Dispositivo novo entra sem empresa."""
    colunas = ("provedor", "deviceid") + COLUNAS_COLETA
    linha = "(" + ",".join(["%s"] * len(colunas)) + ")"
    sql = (
        f"INSERT INTO dispositivo ({', '.join(colunas)}) VALUES "  # noqa: S608
        + ",".join([linha] * len(dispositivos))
        + " ON DUPLICATE KEY UPDATE "
        + ", ".join(
            f"{c}=IF(VALUES(online)=1, VALUES({c}), {c})"
            if c in COLUNAS_SO_ONLINE
            else f"{c}=VALUES({c})"
            for c in COLUNAS_COLETA
        )
    )
    params: list = []
    for d in dispositivos:
        params += [PROVEDOR, d["deviceid"]] + [d[c] for c in COLUNAS_COLETA]
    execute(sql, params)


def mapa_ids(deviceids: list) -> dict:
    """{deviceid: id_dispositivo}."""
    sql = (
        "SELECT id_dispositivo, deviceid FROM dispositivo WHERE provedor = %s AND deviceid IN ("  # noqa: S608
        + ",".join(["%s"] * len(deviceids))
        + ")"
    )
    return {
        r["deviceid"]: r["id_dispositivo"] for r in fetch_all(sql, [PROVEDOR] + list(deviceids))
    }


def buscar_ativo(deviceid: str, id_empresa: Optional[int]) -> Optional[dict]:
    """Dispositivo ativo pelo deviceid; `id_empresa` None = master (qualquer empresa)."""
    sql = (
        "SELECT id_dispositivo, id_empresa, deviceid, nome, modelo, online, temperatura, rele,"
        " temp_min, temp_max, data_leitura FROM dispositivo"
        " WHERE provedor = %s AND deviceid = %s AND ativo = 1"
    )
    params: list = [PROVEDOR, deviceid]
    if id_empresa is not None:
        sql += " AND id_empresa = %s"
        params.append(id_empresa)
    return fetch_one(sql, params)


def atualizar_rele(id_dispositivo: int, ligado: bool) -> None:
    execute(
        "UPDATE dispositivo SET rele = %s WHERE id_dispositivo = %s",
        [1 if ligado else 0, id_dispositivo],
    )


# ── leituras ─────────────────────────────────────────────────────────────


def salvar_leituras(leituras: list) -> None:
    sql = (
        "INSERT INTO leitura (id_dispositivo, temperatura, umidade, rele, online, data_leitura) VALUES "  # noqa: E501, S608
        + ",".join(["(%s,%s,%s,%s,%s,%s)"] * len(leituras))
    )
    params: list = []
    for item in leituras:
        params += [
            item["id_dispositivo"], item["temperatura"], item["umidade"],
            item["rele"], item["online"], item["data"],
        ]  # fmt: skip
    execute(sql, params)


def leituras_pontos(
    id_dispositivo: int, inicio: datetime, fim: datetime, agrupamento_min: int
) -> list:
    filtro = [id_dispositivo, inicio, fim]
    if agrupamento_min:
        seg = agrupamento_min * 60
        return fetch_all(
            "SELECT FROM_UNIXTIME(FLOOR(UNIX_TIMESTAMP(data_leitura) / %s) * %s) AS data_leitura,"
            " ROUND(AVG(temperatura), 1) AS temperatura, MIN(temperatura) AS tmin, MAX(temperatura) AS tmax,"  # noqa: E501
            " AVG(rele) AS rele, MAX(online) AS online"
            " FROM leitura WHERE id_dispositivo = %s AND data_leitura BETWEEN %s AND %s"
            " GROUP BY 1 ORDER BY 1",
            [seg, seg] + filtro,
        )
    return fetch_all(
        "SELECT data_leitura, temperatura, rele, online FROM leitura"
        " WHERE id_dispositivo = %s AND data_leitura BETWEEN %s AND %s ORDER BY data_leitura",
        filtro,
    )


def leituras_resumo(id_dispositivo: int, inicio: datetime, fim: datetime) -> dict:
    return (
        fetch_one(
            "SELECT MIN(temperatura) AS minima, MAX(temperatura) AS maxima, ROUND(AVG(temperatura), 1) AS media,"  # noqa: E501
            " ROUND(AVG(rele) * 100) AS compressor_pct, COUNT(*) AS leituras, SUM(online = 0) AS offline"  # noqa: E501
            " FROM leitura WHERE id_dispositivo = %s AND data_leitura BETWEEN %s AND %s",
            [id_dispositivo, inicio, fim],
        )
        or {}
    )


# ── log da coleta ────────────────────────────────────────────────────────


def registrar_log(
    inicio: datetime, fim: datetime, status: str, mensagem: Optional[str],
    dispositivos: int, leituras: int, chamadas: int, duracao_ms: int,
) -> None:  # fmt: skip
    insert(
        "INSERT INTO coleta_log (fonte, inicio, fim, status, dispositivos, leituras, chamadas_api,"
        " duracao_ms, mensagem) VALUES ('ewelink', %s, %s, %s, %s, %s, %s, %s, %s)",
        [inicio, fim, status, dispositivos, leituras, chamadas, duracao_ms, mensagem],
    )


def ultima_coleta_ok() -> Optional[dict]:
    return fetch_one(
        "SELECT inicio FROM coleta_log WHERE fonte = 'ewelink' AND status = 'ok' ORDER BY id_coleta DESC LIMIT 1"  # noqa: E501
    )


def ultimas_execucoes(limite: int = 10) -> list:
    return fetch_all(
        "SELECT inicio, status, dispositivos, leituras, chamadas_api, duracao_ms, mensagem FROM coleta_log"  # noqa: E501
        " WHERE fonte = 'ewelink' ORDER BY id_coleta DESC LIMIT %s",
        [limite],
    )


def resumo_status(desde: datetime) -> list:
    return fetch_all(
        "SELECT status, COUNT(*) AS total FROM coleta_log WHERE fonte = 'ewelink' AND inicio >= %s"
        " GROUP BY status",
        [desde],
    )


# ── comando (auditoria do relé) ──────────────────────────────────────────


def registrar_comando(
    id_dispositivo: int, id_usuario: int, acao: str, parametros: dict, sucesso: bool, resposta: dict
) -> int:
    return insert(
        "INSERT INTO comando (id_dispositivo, id_usuario, acao, parametros, sucesso, resposta)"
        " VALUES (%s, %s, %s, %s, %s, %s)",
        [
            id_dispositivo, id_usuario, acao, json.dumps(parametros),
            1 if sucesso else 0, json.dumps(resposta, ensure_ascii=False),
        ],
    )  # fmt: skip
