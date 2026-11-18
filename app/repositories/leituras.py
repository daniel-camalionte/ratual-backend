"""Consultas de leituras (séries do painel), SQL parametrizado."""
# ruff: noqa: S608  (só se concatenam trechos constantes; todos os valores vão como %s)

from datetime import datetime
from typing import Optional

from app.db import fetch_all


def _filtro_empresa(id_empresa: Optional[int]):
    return (" AND d.id_empresa = %s", [id_empresa]) if id_empresa is not None else ("", [])


def temperatura_por_coleta(desde: datetime, id_empresa: Optional[int]) -> list[dict]:
    """Média de temperatura por tipo a cada horário de coleta (só aparelhos ativos e online)."""
    filtro, params = _filtro_empresa(id_empresa)
    return fetch_all(
        "SELECT l.data_leitura, COALESCE(d.tipo, 'congelado') AS tipo,"
        " ROUND(AVG(l.temperatura), 1) AS media"
        " FROM leitura l JOIN dispositivo d ON d.id_dispositivo = l.id_dispositivo"
        " WHERE d.ativo = 1 AND l.online = 1 AND l.temperatura IS NOT NULL"
        " AND l.data_leitura >= %s"
        + filtro
        + " GROUP BY l.data_leitura, COALESCE(d.tipo, 'congelado') ORDER BY l.data_leitura",
        [desde] + params,
    )


def compressor_por_dia(desde: datetime, id_empresa: Optional[int]) -> list[dict]:
    """Amostras com relé ligado e total de amostras por dia e aparelho."""
    filtro, params = _filtro_empresa(id_empresa)
    return fetch_all(
        "SELECT DATE(l.data_leitura) AS dia, l.id_dispositivo,"
        " SUM(l.rele = 1) AS ligadas, COUNT(*) AS amostras"
        " FROM leitura l JOIN dispositivo d ON d.id_dispositivo = l.id_dispositivo"
        " WHERE d.ativo = 1 AND l.online = 1 AND l.rele IS NOT NULL AND l.data_leitura >= %s"
        + filtro
        + " GROUP BY DATE(l.data_leitura), l.id_dispositivo",
        [desde] + params,
    )
