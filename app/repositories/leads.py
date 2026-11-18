"""Contatos da landing page (SQL parametrizado)."""

from app.db import execute, insert

COLUNAS = (
    "nome",
    "empresa",
    "telefone",
    "cidade",
    "negocio",
    "quantidade",
    "plano",
    "origem",
    "status",
    "ip",
)


def criar(campos: dict) -> int:
    colunas = [c for c in campos if c in COLUNAS]
    sql = f"INSERT INTO lead ({', '.join(colunas)}) VALUES ({', '.join(['%s'] * len(colunas))})"  # noqa: S608
    return insert(sql, [campos[c] for c in colunas])


def marcar_email_enviado(id_lead: int) -> None:
    execute("UPDATE lead SET email_enviado = 1 WHERE id_lead = %s", [id_lead])
