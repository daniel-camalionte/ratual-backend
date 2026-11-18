"""Consultas das ordens de serviço e da agenda (SQL parametrizado)."""

from collections.abc import Sequence
from datetime import date, time
from typing import Optional

from app.db import fetch_all, fetch_one
from app.repositories import servicos as cadastros

COLUNAS = (
    "id_empresa",
    "id_dispositivo",
    "id_tipo_servico",
    "id_tecnico",
    "status",
    "origem",
    "data",
    "hora_inicio",
    "hora_fim",
    "descricao",
    "valor_servico",
    "desconto_percentual",
    "valor_desconto",
    "valor_pecas",
    "descricao_pecas",
    "valor_total",
    "observacao_tecnica",
    "motivo_cancelamento",
    "id_usuario_solicitante",
    "concluido_em",
)

SQL_LISTA = (
    "SELECT o.*, e.nome AS empresa, d.deviceid, d.nome AS dispositivo, t.nome AS tipo_servico,"
    " tc.nome AS tecnico, tc.telefone AS tecnico_telefone, u.nome AS solicitante"
    " FROM ordem_servico o"
    " JOIN empresa e ON e.id_empresa = o.id_empresa"
    " JOIN tipo_servico t ON t.id_tipo_servico = o.id_tipo_servico"
    " LEFT JOIN dispositivo d ON d.id_dispositivo = o.id_dispositivo"
    " LEFT JOIN tecnico tc ON tc.id_tecnico = o.id_tecnico"
    " LEFT JOIN usuario u ON u.id_usuario = o.id_usuario_solicitante"
    " WHERE 1 = 1"
)


def janelas_ativas() -> list:
    return fetch_all("SELECT * FROM agenda_janela WHERE ativo = 1 ORDER BY dia_semana, hora_inicio")


def bloqueios_entre(inicio: date, fim: date) -> list:
    return fetch_all("SELECT data FROM agenda_bloqueio WHERE data BETWEEN %s AND %s", [inicio, fim])


def ocupacao_entre(inicio: date, fim: date) -> list:
    return fetch_all(
        "SELECT data, hora_inicio, COUNT(*) AS n FROM ordem_servico"
        " WHERE data BETWEEN %s AND %s AND status IN ('solicitado','confirmado','em_atendimento')"
        " GROUP BY data, hora_inicio",
        [inicio, fim],
    )


def listar(
    id_empresa: Optional[int],
    id_tecnico: Optional[int],
    status: Sequence[str],
    inicio: Optional[date],
    fim: Optional[date],
) -> list:
    sql, params = SQL_LISTA, []
    if id_empresa:
        sql += " AND o.id_empresa = %s"
        params.append(id_empresa)
    if id_tecnico:
        sql += " AND o.id_tecnico = %s"
        params.append(id_tecnico)
    if status:
        sql += " AND o.status IN (" + ",".join(["%s"] * len(status)) + ")"
        params += list(status)
    if inicio:
        sql += " AND o.data >= %s"
        params.append(inicio)
    if fim:
        sql += " AND o.data <= %s"
        params.append(fim)
    sql += " ORDER BY o.data, o.hora_inicio, o.id_os LIMIT 1000"
    return fetch_all(sql, params)


def buscar(id_os: int) -> Optional[dict]:
    return fetch_one(SQL_LISTA + " AND o.id_os = %s", [id_os])


def tipo_servico(id_tipo: int) -> Optional[dict]:
    return cadastros.buscar("tipo_servico", id_tipo)


def tecnico(id_tecnico: int) -> Optional[dict]:
    return cadastros.buscar("tecnico", id_tecnico)


def id_dispositivo(deviceid: str, id_empresa: int) -> Optional[int]:
    row = fetch_one(
        "SELECT id_dispositivo FROM dispositivo"
        " WHERE deviceid = %s AND id_empresa = %s AND ativo = 1",
        [deviceid, id_empresa],
    )
    return row["id_dispositivo"] if row else None


def empresa_cliente_ativa(id_empresa: int) -> bool:
    return (
        fetch_one(
            "SELECT id_empresa FROM empresa"
            " WHERE id_empresa = %s AND tipo = 'cliente' AND ativo = 1",
            [id_empresa],
        )
        is not None
    )


def conflitos_tecnico(id_tecnico: int, dia: date, inicio: time, fim: time, id_ignorar: int) -> list:
    return fetch_all(
        "SELECT o.id_os, e.nome AS empresa, o.hora_inicio, o.hora_fim FROM ordem_servico o"
        " JOIN empresa e ON e.id_empresa = o.id_empresa"
        " WHERE o.id_tecnico = %s AND o.data = %s"
        " AND o.status IN ('solicitado','confirmado','em_atendimento')"
        " AND o.hora_inicio < %s AND o.hora_fim > %s AND o.id_os <> %s",
        [id_tecnico, dia, fim, inicio, id_ignorar],
    )


def criar(campos: dict) -> int:
    return cadastros.inserir_campos("ordem_servico", COLUNAS, campos)


def atualizar(id_os: int, campos: dict) -> int:
    return cadastros.atualizar_campos("ordem_servico", "id_os", COLUNAS, campos, id_os)
