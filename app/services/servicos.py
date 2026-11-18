"""Cadastros da central de serviços (master): planos, tipos de serviço, técnicos, grade e bloqueios.

Nada é apagado, só desativado, exceto janelas e bloqueios de agenda.
O catálogo do cliente (tipos que ele pode pedir, com o desconto do plano) também fica aqui.
"""

from datetime import date, datetime, time, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.core.auth import is_master
from app.core.errors import AppError
from app.repositories import auditoria
from app.repositories import servicos as repo

BRASILIA = timezone(timedelta(hours=-3))
DIAS = ("domingo", "segunda", "terça", "quarta", "quinta", "sexta", "sábado")


# ── conversões ───────────────────────────────────────────────────────────


def hoje() -> date:
    return datetime.now(BRASILIA).date()


def agora() -> datetime:
    return datetime.now(BRASILIA).replace(tzinfo=None)


def como_time(v):
    """O driver devolve colunas TIME como timedelta; texto 'HH:MM' também é aceito."""
    if isinstance(v, timedelta):
        minutos = int(v.total_seconds() // 60)
        return time(minutos // 60, minutos % 60)
    if isinstance(v, str):
        return time.fromisoformat(v)
    return v


def hora_str(v) -> Optional[str]:
    v = como_time(v)
    return v.strftime("%H:%M") if v is not None else None


def num(v) -> Optional[float]:
    return float(v) if v is not None else None


def nao_encontrado(rotulo: str) -> AppError:
    return AppError(f"{rotulo} não encontrado", status_code=404, code="not_found")


# ── saídas ───────────────────────────────────────────────────────────────


def _plano(r: dict) -> dict:
    return {
        "id_plano": r["id_plano"],
        "nome": r["nome"],
        "descricao": r["descricao"],
        "preco_mensal": num(r["preco_mensal"]),
        "desconto_servico": num(r["desconto_servico"]),
        "visitas_preventivas_ano": r["visitas_preventivas_ano"],
        "pontos_inclusos": r["pontos_inclusos"],
        "ativo": bool(r["ativo"]),
        "clientes": int(r.get("clientes") or 0),
    }


def _tipo(r: dict) -> dict:
    return {
        "id_tipo_servico": r["id_tipo_servico"],
        "nome": r["nome"],
        "descricao": r["descricao"],
        "valor": num(r["valor"]),
        "cliente_pode_solicitar": bool(r["cliente_pode_solicitar"]),
        "ativo": bool(r["ativo"]),
    }


def _tecnico(r: dict) -> dict:
    return {
        "id_tecnico": r["id_tecnico"],
        "nome": r["nome"],
        "telefone": r["telefone"],
        "ativo": bool(r["ativo"]),
    }


def _janela(r: dict) -> dict:
    return {
        "id_janela": r["id_janela"],
        "dia_semana": r["dia_semana"],
        "dia": DIAS[r["dia_semana"]],
        "hora_inicio": hora_str(r["hora_inicio"]),
        "hora_fim": hora_str(r["hora_fim"]),
        "vagas": r["vagas"],
        "ativo": bool(r["ativo"]),
    }


CADASTROS = {
    "plano": {"chave": "planos", "rotulo": "Plano", "saida": _plano},
    "tipo_servico": {"chave": "tipos", "rotulo": "Tipo de serviço", "saida": _tipo},
    "tecnico": {"chave": "tecnicos", "rotulo": "Técnico", "saida": _tecnico},
    "janela": {"chave": "janelas", "rotulo": "Janela", "saida": _janela},
}
_TEXTOS_OPCIONAIS = ("descricao", "telefone", "motivo")


def _normalizar(campos: dict) -> dict:
    """Texto vazio vira NULL nos campos opcionais; booleano vira 0/1."""
    saida = {}
    for chave, valor in campos.items():
        if chave in _TEXTOS_OPCIONAIS and isinstance(valor, str) and not valor.strip():
            valor = None
        if isinstance(valor, bool):
            valor = 1 if valor else 0
        saida[chave] = valor
    return saida


# ── cadastros genéricos ──────────────────────────────────────────────────


def listar(entidade: str) -> dict:
    spec = CADASTROS[entidade]
    rows = repo.listar(entidade)
    return {"total": len(rows), spec["chave"]: [spec["saida"](r) for r in rows]}


def criar(autor: dict, entidade: str, dados: dict) -> dict:
    spec = CADASTROS[entidade]
    campos = _normalizar(dados)
    _validar(entidade, campos, None)
    novo_id = repo.criar(entidade, campos)
    auditoria.registrar(autor["id_usuario"], f"{entidade}_criado", entidade, novo_id, campos)
    return {"msg": f"{spec['rotulo']} criado", "id": novo_id}


def editar(autor: dict, entidade: str, id_item: int, dados: dict) -> dict:
    spec = CADASTROS[entidade]
    atual = repo.buscar(entidade, id_item)
    if not atual:
        raise nao_encontrado(spec["rotulo"])
    campos = _normalizar(dados)
    if not campos:
        raise AppError("Envie ao menos um campo para alterar", code="bad_request")
    _validar(entidade, {**atual, **campos}, id_item)
    repo.atualizar(entidade, id_item, campos)
    antes = {k: atual.get(k) for k in campos}
    auditoria.registrar(
        autor["id_usuario"],
        f"{entidade}_alterado",
        entidade,
        id_item,
        {"antes": antes, "depois": campos},
    )
    return {"msg": f"{spec['rotulo']} atualizado", "id": id_item}


def remover_janela(autor: dict, id_janela: int) -> dict:
    atual = repo.buscar("janela", id_janela)
    if not atual:
        raise nao_encontrado("Janela")
    repo.remover("janela", id_janela)
    auditoria.registrar(autor["id_usuario"], "janela_removida", "janela", id_janela, _janela(atual))
    return {"msg": "Janela removida"}


def _validar(entidade: str, dados: dict, id_ignorar: Optional[int]) -> None:
    """Regras além do formato dos campos."""
    if entidade == "plano" and any(
        r["id_plano"] != id_ignorar for r in repo.plano_por_nome(dados["nome"])
    ):
        raise AppError("Já existe um plano com esse nome", status_code=409, code="conflict")
    if entidade == "janela":
        inicio, fim = como_time(dados["hora_inicio"]), como_time(dados["hora_fim"])
        if fim <= inicio:
            raise AppError("A hora de fim deve ser depois da hora de início", code="bad_request")
        if dados.get("ativo", 1):
            # janelas do mesmo dia não se sobrepõem: cada visita pertence a uma janela só
            rows = repo.janelas_sobrepostas(dados["dia_semana"], inicio, fim)
            if any(r["id_janela"] != id_ignorar for r in rows):
                raise AppError(
                    f"Já existe uma janela nesse horário de {DIAS[dados['dia_semana']]}",
                    status_code=409,
                    code="conflict",
                )


# ── bloqueios de agenda ──────────────────────────────────────────────────


def listar_bloqueios() -> dict:
    rows = repo.listar_bloqueios()
    return {
        "total": len(rows),
        "bloqueios": [
            {"id_bloqueio": r["id_bloqueio"], "data": r["data"], "motivo": r["motivo"]}
            for r in rows
        ],
    }


def criar_bloqueio(autor: dict, dados: dict) -> dict:
    dia, motivo = dados["data"], dados.get("motivo") or None
    if dia < hoje():
        raise AppError("A data já passou", code="bad_request")
    if repo.bloqueio_da_data(dia):
        raise AppError("Essa data já está bloqueada", status_code=409, code="conflict")
    novo_id = repo.criar("bloqueio", {"data": dia, "motivo": motivo})
    auditoria.registrar(
        autor["id_usuario"], "bloqueio_criado", "bloqueio", novo_id, {"data": dia, "motivo": motivo}
    )
    return {"msg": "Data bloqueada", "id": novo_id}


def remover_bloqueio(autor: dict, id_bloqueio: int) -> dict:
    atual = repo.buscar("bloqueio", id_bloqueio)
    if not atual:
        raise nao_encontrado("Bloqueio")
    repo.remover("bloqueio", id_bloqueio)
    auditoria.registrar(
        autor["id_usuario"], "bloqueio_removido", "bloqueio", id_bloqueio, {"data": atual["data"]}
    )
    return {"msg": "Data liberada"}


# ── catálogo para o cliente ──────────────────────────────────────────────


def plano_da_empresa(id_empresa: int) -> Optional[dict]:
    return repo.plano_da_empresa(id_empresa)


def catalogo(usuario: dict, id_empresa: Optional[int] = None) -> dict:
    """Tipos de serviço que o cliente pode pedir, com o valor já com o desconto do plano.

    Master vê todos os tipos ativos e pode simular para uma empresa (id_empresa)."""
    master = is_master(usuario)
    empresa = id_empresa if master else usuario["id_empresa"]
    plano = plano_da_empresa(empresa) if empresa else None
    desconto = Decimal(plano["desconto_servico"]) if plano else Decimal("0")

    tipos = []
    for r in repo.tipos_ativos(so_cliente=not master):
        valor = Decimal(r["valor"])
        com_desconto = (valor - valor * desconto / 100).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        tipos.append({**_tipo(r), "valor_com_desconto": float(com_desconto)})
    return {
        "plano": (
            {
                "id_plano": plano["id_plano"],
                "nome": plano["nome"],
                "desconto_servico": float(desconto),
            }
            if plano
            else None
        ),
        "tipos": tipos,
    }
