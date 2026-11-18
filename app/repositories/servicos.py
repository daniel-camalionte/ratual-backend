"""Consultas dos cadastros da central de serviços (SQL parametrizado).

Nomes de tabela e de coluna vêm só das constantes deste módulo (nunca da entrada do usuário);
os valores sempre vão como parâmetros.
"""

from datetime import date, time
from typing import Optional

from app.db import execute, fetch_all, fetch_one, insert

# entidade -> (tabela, chave primária, colunas graváveis)
TABELAS = {
    "plano": (
        "plano",
        "id_plano",
        (
            "nome",
            "descricao",
            "preco_mensal",
            "desconto_servico",
            "visitas_preventivas_ano",
            "pontos_inclusos",
            "ativo",
        ),
    ),
    "tipo_servico": (
        "tipo_servico",
        "id_tipo_servico",
        ("nome", "descricao", "valor", "cliente_pode_solicitar", "ativo"),
    ),
    "tecnico": ("tecnico", "id_tecnico", ("nome", "telefone", "ativo")),
    "janela": (
        "agenda_janela",
        "id_janela",
        ("dia_semana", "hora_inicio", "hora_fim", "vagas", "ativo"),
    ),
    "bloqueio": ("agenda_bloqueio", "id_bloqueio", ("data", "motivo")),
}

_LISTAGENS = {
    "plano": (
        "SELECT p.*, (SELECT COUNT(*) FROM empresa e"
        " WHERE e.id_plano = p.id_plano AND e.ativo = 1) AS clientes"
        " FROM plano p ORDER BY p.ativo DESC, p.preco_mensal IS NULL, p.preco_mensal, p.nome"
    ),
    "tipo_servico": "SELECT * FROM tipo_servico ORDER BY ativo DESC, nome",
    "tecnico": "SELECT * FROM tecnico ORDER BY ativo DESC, nome",
    "janela": "SELECT * FROM agenda_janela ORDER BY dia_semana, hora_inicio",
}


def inserir_campos(tabela: str, permitidas: tuple, campos: dict) -> int:
    colunas = [c for c in campos if c in permitidas]
    if not colunas:
        raise ValueError("sem colunas válidas")
    sql = f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({', '.join(['%s'] * len(colunas))})"  # noqa: S608
    return insert(sql, [campos[c] for c in colunas])


def atualizar_campos(tabela: str, pk: str, permitidas: tuple, campos: dict, id_: int) -> int:
    colunas = [c for c in campos if c in permitidas]
    if not colunas:
        raise ValueError("sem colunas válidas")
    sql = f"UPDATE {tabela} SET {', '.join(c + ' = %s' for c in colunas)} WHERE {pk} = %s"  # noqa: S608
    return execute(sql, [campos[c] for c in colunas] + [id_])


def listar(entidade: str) -> list:
    return fetch_all(_LISTAGENS[entidade])


def buscar(entidade: str, id_: int) -> Optional[dict]:
    tabela, pk, _ = TABELAS[entidade]
    return fetch_one(f"SELECT * FROM {tabela} WHERE {pk} = %s", [id_])  # noqa: S608


def criar(entidade: str, campos: dict) -> int:
    tabela, _, permitidas = TABELAS[entidade]
    return inserir_campos(tabela, permitidas, campos)


def atualizar(entidade: str, id_: int, campos: dict) -> int:
    tabela, pk, permitidas = TABELAS[entidade]
    return atualizar_campos(tabela, pk, permitidas, campos, id_)


def remover(entidade: str, id_: int) -> int:
    """Só janelas e bloqueios são apagados; os demais cadastros apenas se desativam."""
    if entidade not in ("janela", "bloqueio"):
        raise ValueError("entidade não removível")
    tabela, pk, _ = TABELAS[entidade]
    return execute(f"DELETE FROM {tabela} WHERE {pk} = %s", [id_])  # noqa: S608


def plano_por_nome(nome: str) -> list:
    return fetch_all("SELECT id_plano FROM plano WHERE nome = %s", [nome])


def janelas_sobrepostas(dia_semana: int, inicio: time, fim: time) -> list:
    return fetch_all(
        "SELECT id_janela FROM agenda_janela WHERE ativo = 1 AND dia_semana = %s"
        " AND hora_inicio < %s AND hora_fim > %s",
        [dia_semana, fim, inicio],
    )


def listar_bloqueios() -> list:
    return fetch_all("SELECT * FROM agenda_bloqueio WHERE data >= CURDATE() ORDER BY data")


def bloqueio_da_data(dia: date) -> Optional[dict]:
    return fetch_one("SELECT id_bloqueio FROM agenda_bloqueio WHERE data = %s", [dia])


def plano_da_empresa(id_empresa: int) -> Optional[dict]:
    return fetch_one(
        "SELECT p.* FROM empresa e JOIN plano p ON p.id_plano = e.id_plano WHERE e.id_empresa = %s",
        [id_empresa],
    )


def tipos_ativos(so_cliente: bool) -> list:
    sql = "SELECT * FROM tipo_servico WHERE ativo = 1"
    if so_cliente:
        sql += " AND cliente_pode_solicitar = 1"
    return fetch_all(sql + " ORDER BY nome")
