"""Consultas de dispositivos (refrigeradores) e vínculo com empresa/câmera (SQL parametrizado)."""
# ruff: noqa: S608, E501  (só se concatenam trechos constantes; todos os valores vão como %s)

from typing import Optional

from app.db import execute, fetch_all, fetch_one

# colunas que o master pode alterar (nomes fixos: nunca vêm da entrada do usuário)
_COLUNAS_EDITAVEIS = ("tipo", "temp_min", "temp_max", "tolerancia_min", "id_empresa", "ativo")


def listar_com_empresa(
    id_empresa: Optional[int] = None, incluir_inativos: bool = False
) -> list[dict]:
    """Último estado de cada dispositivo + empresa + câmera ativa. id_empresa=None traz todos (master)."""
    sql = (
        "SELECT d.deviceid, d.nome, d.modelo, d.marca, d.tipo, d.temp_min, d.temp_max, d.tolerancia_min,"
        " d.online, d.temperatura, d.umidade,"
        " d.rele, d.sinal, d.limite_min, d.limite_max, d.data_leitura, d.ativo,"
        " e.id_empresa, e.nome AS empresa,"
        " (SELECT c.id_camera FROM camera c WHERE c.id_dispositivo = d.id_dispositivo AND c.ativo = 1"
        " ORDER BY c.id_camera LIMIT 1) AS id_camera,"
        " (SELECT c.online FROM camera c WHERE c.id_dispositivo = d.id_dispositivo AND c.ativo = 1"
        " ORDER BY c.id_camera LIMIT 1) AS camera_online"
        " FROM dispositivo d LEFT JOIN empresa e ON e.id_empresa = d.id_empresa"
        " WHERE " + ("1 = 1" if incluir_inativos else "d.ativo = 1")
    )
    params: list = []
    if id_empresa is not None:
        sql += " AND d.id_empresa = %s"
        params.append(id_empresa)
    sql += " ORDER BY d.nome"
    return fetch_all(sql, params)


def buscar_por_deviceid(deviceid: str) -> Optional[dict]:
    """Sem filtro de ativo (permite reativar um refrigerador desativado)."""
    return fetch_one("SELECT * FROM dispositivo WHERE deviceid = %s", [deviceid])


def buscar_empresa_ativa(id_empresa: int) -> Optional[dict]:
    return fetch_one(
        "SELECT id_empresa, nome, tipo FROM empresa WHERE id_empresa = %s AND ativo = 1",
        [id_empresa],
    )


def atualizar(id_dispositivo: int, campos: dict) -> int:
    colunas = [c for c in _COLUNAS_EDITAVEIS if c in campos]
    if not colunas:
        return 0
    sets = ", ".join(f"{c} = %s" for c in colunas)
    return execute(
        f"UPDATE dispositivo SET {sets} WHERE id_dispositivo = %s",
        [campos[c] for c in colunas] + [id_dispositivo],
    )
