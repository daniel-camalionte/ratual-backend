"""Ordens de serviço: pedidos dos clientes, agendamentos da equipe e a disponibilidade da grade.

Fluxo: o cliente escolhe uma janela livre da grade -> 'solicitado' -> a equipe confirma (pode trocar
data, horário e técnico) -> 'em_atendimento' -> 'concluido'.
A equipe também agenda direto ('confirmado').

Valores: o valor do tipo de serviço e o desconto do plano do cliente são gravados na ordem
no momento
do pedido; mudar o plano ou a tabela de preços depois não altera ordens já abertas.
O desconto vale só sobre a mão de obra (valor_servico); peças entram cheias no total.
"""

import html
from datetime import date, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from app.core.auth import is_master
from app.core.errors import AppError
from app.integrations import email
from app.repositories import auditoria
from app.repositories import ordens as repo
from app.services import servicos
from app.services.servicos import agora, como_time, hoje, hora_str, num

STATUS = ("solicitado", "confirmado", "em_atendimento", "concluido", "cancelado")
OCUPAM_VAGA = ("solicitado", "confirmado", "em_atendimento")
TRANSICOES = {
    "solicitado": {"confirmado", "cancelado"},
    "confirmado": {"em_atendimento", "concluido", "cancelado"},
    "em_atendimento": {"concluido", "cancelado"},
    "concluido": set(),
    "cancelado": set(),
}
CLIENTE_CANCELA = ("solicitado", "confirmado")
PERFIS_QUE_SOLICITAM = ("admin", "operador")
HORIZONTE_DIAS = 60
CENTAVO = Decimal("0.01")


def _valores(valor_servico, desconto_percentual, valor_pecas) -> dict:
    valor_servico = Decimal(valor_servico)
    valor_desconto = (valor_servico * Decimal(desconto_percentual) / 100).quantize(
        CENTAVO, rounding=ROUND_HALF_UP
    )
    total = (valor_servico - valor_desconto + Decimal(valor_pecas)).quantize(
        CENTAVO, rounding=ROUND_HALF_UP
    )
    return {"valor_desconto": valor_desconto, "valor_total": total}


def _saida(r: dict) -> dict:
    return {
        "id_os": r["id_os"],
        "status": r["status"],
        "origem": r["origem"],
        "data": r["data"],
        "hora_inicio": hora_str(r["hora_inicio"]),
        "hora_fim": hora_str(r["hora_fim"]),
        "empresa": {"id_empresa": r["id_empresa"], "nome": r["empresa"]},
        "dispositivo": {"deviceid": r["deviceid"], "nome": r["dispositivo"]}
        if r["deviceid"]
        else None,
        "tipo_servico": {"id_tipo_servico": r["id_tipo_servico"], "nome": r["tipo_servico"]},
        "tecnico": (
            {"id_tecnico": r["id_tecnico"], "nome": r["tecnico"], "telefone": r["tecnico_telefone"]}
            if r["id_tecnico"]
            else None
        ),
        "descricao": r["descricao"],
        "valores": {
            "servico": num(r["valor_servico"]),
            "desconto_percentual": num(r["desconto_percentual"]),
            "desconto": num(r["valor_desconto"]),
            "pecas": num(r["valor_pecas"]),
            "total": num(r["valor_total"]),
        },
        "descricao_pecas": r["descricao_pecas"],
        "observacao_tecnica": r["observacao_tecnica"],
        "motivo_cancelamento": r["motivo_cancelamento"],
        "solicitante": r["solicitante"],
        "criado_em": r["criado_em"],
        "concluido_em": r["concluido_em"],
    }


def _vazio_none(v):
    return None if isinstance(v, str) and not v.strip() else v


# ── disponibilidade ──────────────────────────────────────────────────────


def disponibilidade(inicio: Optional[date] = None, dias: int = 21) -> dict:
    """Janelas com vaga a partir de amanhã (ou de `inicio`, se for depois), dia a dia."""
    primeiro = max(hoje() + timedelta(days=1), inicio or date.min)
    dias = max(1, min(int(dias), HORIZONTE_DIAS))
    ultimo = primeiro + timedelta(days=dias - 1)

    janelas = repo.janelas_ativas()
    bloqueados = {r["data"] for r in repo.bloqueios_entre(primeiro, ultimo)}
    ocupadas = {
        (r["data"], como_time(r["hora_inicio"])): int(r["n"])
        for r in repo.ocupacao_entre(primeiro, ultimo)
    }

    resultado = []
    dia = primeiro
    while dia <= ultimo:
        dia_semana = (dia.weekday() + 1) % 7  # Python: segunda = 0; a grade: domingo = 0
        if dia not in bloqueados:
            livres = []
            for j in janelas:
                if j["dia_semana"] != dia_semana:
                    continue
                inicio_j = como_time(j["hora_inicio"])
                vagas = j["vagas"] - ocupadas.get((dia, inicio_j), 0)
                if vagas > 0:
                    livres.append(
                        {
                            "hora_inicio": hora_str(inicio_j),
                            "hora_fim": hora_str(j["hora_fim"]),
                            "vagas_livres": vagas,
                        }
                    )
            if livres:
                resultado.append({"data": dia, "janelas": livres})
        dia += timedelta(days=1)
    return {"inicio": primeiro, "fim": ultimo, "dias": resultado}


def _janela_livre(dia: date, hora_inicio: time) -> Optional[dict]:
    for d in disponibilidade(dia, 1)["dias"]:
        if d["data"] == dia:
            for j in d["janelas"]:
                if j["hora_inicio"] == hora_inicio.strftime("%H:%M"):
                    return j
    return None


# ── consulta ─────────────────────────────────────────────────────────────


def listar(usuario: dict, filtros: dict) -> dict:
    """Master: todas as ordens (com filtros). Cliente: só as da própria empresa."""
    if is_master(usuario):
        id_empresa, id_tecnico = filtros.get("id_empresa"), filtros.get("id_tecnico")
    else:
        id_empresa, id_tecnico = usuario["id_empresa"], None
    status = [s for s in (filtros.get("status") or "").split(",") if s in STATUS]
    rows = repo.listar(id_empresa, id_tecnico, status, filtros.get("inicio"), filtros.get("fim"))
    return {"total": len(rows), "ordens": [_saida(r) for r in rows]}


def _buscar(id_os: int) -> dict:
    row = repo.buscar(id_os)
    if not row:
        raise servicos.nao_encontrado("Ordem de serviço")
    return row


def _bad(msg: str) -> AppError:
    return AppError(msg, code="bad_request")


# ── criação ──────────────────────────────────────────────────────────────


def _tipo_ativo(id_tipo: int, so_cliente: bool) -> dict:
    tipo = repo.tipo_servico(id_tipo)
    if not tipo or not tipo["ativo"] or (so_cliente and not tipo["cliente_pode_solicitar"]):
        raise _bad("Tipo de serviço indisponível")
    return tipo


def _tecnico_ativo(id_tecnico: Optional[int]) -> None:
    if id_tecnico:
        tecnico = repo.tecnico(id_tecnico)
        if not tecnico or not tecnico["ativo"]:
            raise _bad("Técnico não encontrado ou inativo")


def _conflitos_tecnico(id_tecnico, dia, inicio, fim, id_ignorar=0) -> list:
    """Outras visitas do mesmo técnico que se sobrepõem a esse horário (só aviso, não bloqueia)."""
    if not id_tecnico:
        return []
    return [
        f"O técnico já tem a ordem #{r['id_os']} ({r['empresa']}) das {hora_str(r['hora_inicio'])}"
        f" às {hora_str(r['hora_fim'])}"
        for r in repo.conflitos_tecnico(id_tecnico, dia, inicio, fim, id_ignorar)
    ]


def criar(usuario: dict, body: dict) -> dict:
    if is_master(usuario):
        return _criar_interno(usuario, body)
    return _criar_pedido(usuario, body)


def _comum(body: dict, id_empresa: int, so_cliente: bool) -> tuple:
    tipo = _tipo_ativo(body["id_tipo_servico"], so_cliente)
    id_dispositivo = None
    if body.get("deviceid"):
        id_dispositivo = repo.id_dispositivo(str(body["deviceid"]), id_empresa)
        if not id_dispositivo:
            raise _bad("Equipamento não encontrado para esta empresa")
    dados = {
        "id_empresa": id_empresa,
        "id_tipo_servico": tipo["id_tipo_servico"],
        "id_dispositivo": id_dispositivo,
        "descricao": _vazio_none(body.get("descricao")),
        "data": body["data"],
        "hora_inicio": time.fromisoformat(body["hora_inicio"]),
    }
    return dados, tipo


def _gravar(autor: dict, dados: dict, valor_servico: Decimal) -> dict:
    plano = servicos.plano_da_empresa(dados["id_empresa"])
    desconto = Decimal(plano["desconto_servico"]) if plano else Decimal("0")
    registro = {
        **dados,
        "valor_servico": valor_servico,
        "desconto_percentual": desconto,
        "valor_pecas": Decimal("0"),
        **_valores(valor_servico, desconto, 0),
    }
    id_os = repo.criar(registro)
    auditoria.registrar(
        autor["id_usuario"],
        "os_criada",
        "ordem",
        id_os,
        {
            "status": dados["status"],
            "data": dados["data"],
            "hora_inicio": dados["hora_inicio"],
            "id_empresa": dados["id_empresa"],
            "valor_total": registro["valor_total"],
        },
    )
    ordem = repo.buscar(id_os)
    return _saida(ordem) if ordem else {"id_os": id_os, "origem": dados["origem"]}


def _criar_pedido(usuario: dict, body: dict) -> dict:
    if usuario["perfil"] not in PERFIS_QUE_SOLICITAM:
        raise AppError(
            "Seu perfil só pode visualizar. Peça a um administrador da empresa.",
            status_code=403,
            code="forbidden",
        )
    dados, tipo = _comum(body, usuario["id_empresa"], so_cliente=True)
    if dados["data"] <= hoje() or dados["data"] > hoje() + timedelta(days=HORIZONTE_DIAS):
        raise _bad("Escolha uma data a partir de amanhã")
    janela = _janela_livre(dados["data"], dados["hora_inicio"])
    if not janela:
        raise AppError(
            "Esse horário não está mais disponível. Escolha outro.",
            status_code=409,
            code="conflict",
        )
    dados.update(
        {
            "hora_fim": time.fromisoformat(janela["hora_fim"]),
            "status": "solicitado",
            "origem": "cliente",
            "id_usuario_solicitante": usuario["id_usuario"],
        }
    )
    ordem = _gravar(usuario, dados, Decimal(tipo["valor"]))
    return {"msg": "Pedido enviado. A equipe vai confirmar o horário.", "ordem": ordem}


def _criar_interno(usuario: dict, body: dict) -> dict:
    if not body.get("id_empresa"):
        raise _bad("Cliente é obrigatório")
    if not body.get("hora_fim"):
        raise _bad("Hora de fim é obrigatória")
    if not repo.empresa_cliente_ativa(body["id_empresa"]):
        raise _bad("Cliente não encontrado ou inativo")
    dados, tipo = _comum(body, body["id_empresa"], so_cliente=False)
    hora_fim = time.fromisoformat(body["hora_fim"])
    if hora_fim <= dados["hora_inicio"]:
        raise _bad("A hora de fim deve ser depois da hora de início")
    if dados["data"] < hoje():
        raise _bad("A data já passou")
    id_tecnico = body.get("id_tecnico")
    _tecnico_ativo(id_tecnico)
    valor = body.get("valor_servico")
    dados.update(
        {
            "hora_fim": hora_fim,
            "id_tecnico": id_tecnico,
            "status": "confirmado",
            "origem": "interno",
            "id_usuario_solicitante": usuario["id_usuario"],
        }
    )
    avisos = _conflitos_tecnico(id_tecnico, dados["data"], dados["hora_inicio"], hora_fim)
    ordem = _gravar(usuario, dados, valor if valor is not None else Decimal(tipo["valor"]))
    return {"msg": "Agendamento criado", "ordem": ordem, "avisos": avisos}


# ── alteração (equipe) ───────────────────────────────────────────────────


def editar(usuario: dict, id_os: int, body: dict) -> dict:
    atual = _buscar(id_os)
    if atual["status"] == "cancelado":
        raise _bad("Ordem cancelada não pode ser alterada")

    campos = {}
    if "status" in body:
        novo = body["status"]
        if novo != atual["status"]:
            if novo not in TRANSICOES[atual["status"]]:
                raise _bad(f"Não é possível passar de '{atual['status']}' para '{novo}'")
            campos["status"] = novo
            if novo == "concluido":
                campos["concluido_em"] = agora()
            if novo == "cancelado":
                campos["motivo_cancelamento"] = _vazio_none(body.get("motivo_cancelamento"))

    if atual["status"] != "concluido":
        if "id_tecnico" in body:
            _tecnico_ativo(body["id_tecnico"])
            campos["id_tecnico"] = body["id_tecnico"]
        for chave in ("data", "hora_inicio", "hora_fim"):
            if chave in body:
                valor = body[chave]
                campos[chave] = time.fromisoformat(valor) if chave != "data" else valor

    for chave in ("valor_servico", "valor_pecas"):
        if chave in body:
            campos[chave] = body[chave]
    for chave in ("descricao_pecas", "observacao_tecnica"):
        if chave in body:
            campos[chave] = _vazio_none(body[chave])
    if not campos:
        raise _bad("Nada para alterar")

    inicio = campos.get("hora_inicio", como_time(atual["hora_inicio"]))
    fim = campos.get("hora_fim", como_time(atual["hora_fim"]))
    if fim <= inicio:
        raise _bad("A hora de fim deve ser depois da hora de início")
    if "valor_servico" in campos or "valor_pecas" in campos:
        campos.update(
            _valores(
                campos.get("valor_servico", atual["valor_servico"]),
                atual["desconto_percentual"],
                campos.get("valor_pecas", atual["valor_pecas"]),
            )
        )

    repo.atualizar(id_os, campos)
    antes = {k: atual.get(k) for k in campos}
    auditoria.registrar(
        usuario["id_usuario"], "os_alterada", "ordem", id_os, {"antes": antes, "depois": campos}
    )

    avisos = []
    if campos.get("status", atual["status"]) in OCUPAM_VAGA:
        avisos = _conflitos_tecnico(
            campos.get("id_tecnico", atual["id_tecnico"]),
            campos.get("data", atual["data"]),
            inicio,
            fim,
            id_os,
        )
    ordem = repo.buscar(id_os)
    return {
        "msg": "Ordem de serviço atualizada",
        "ordem": _saida(ordem) if ordem else None,
        "avisos": avisos,
    }


# ── cancelamento (cliente ou equipe) ─────────────────────────────────────


def cancelar(usuario: dict, id_os: int, motivo: Optional[str]) -> dict:
    atual = _buscar(id_os)
    if not is_master(usuario):
        if atual["id_empresa"] != usuario["id_empresa"]:
            raise servicos.nao_encontrado("Ordem de serviço")  # isolamento: outra empresa = 404
        if usuario["perfil"] not in PERFIS_QUE_SOLICITAM:
            raise AppError("Seu perfil só pode visualizar", status_code=403, code="forbidden")
        if atual["status"] not in CLIENTE_CANCELA:
            raise _bad("Esta visita não pode mais ser cancelada pelo app. Fale com a equipe.")
    elif "cancelado" not in TRANSICOES[atual["status"]]:
        raise _bad("Esta ordem não pode ser cancelada")

    motivo = _vazio_none(motivo)
    repo.atualizar(id_os, {"status": "cancelado", "motivo_cancelamento": motivo})
    auditoria.registrar(
        usuario["id_usuario"],
        "os_cancelada",
        "ordem",
        id_os,
        {"antes": {"status": atual["status"]}, "motivo": motivo},
    )
    return {"msg": "Visita cancelada"}


# ── aviso por e-mail ─────────────────────────────────────────────────────


def avisar_pedido(ordem: dict, destinos_csv: str) -> None:
    """E-mail para a equipe quando um cliente pede uma visita (settings.os_emails)."""
    destinos = [e.strip() for e in (destinos_csv or "").split(",") if e.strip()]
    if not destinos:
        return
    dia = ordem["data"].strftime("%d/%m/%Y")
    linhas = [
        ("Cliente", ordem["empresa"]["nome"]),
        ("Serviço", ordem["tipo_servico"]["nome"]),
        ("Data", f"{dia}, {ordem['hora_inicio']} às {ordem['hora_fim']}"),
        ("Equipamento", ordem["dispositivo"]["nome"] if ordem["dispositivo"] else "—"),
        ("Pedido por", ordem["solicitante"] or "—"),
        ("Relato", ordem["descricao"] or "—"),
    ]
    tabela = "".join(
        f"<tr><td style='padding:6px 12px;color:#64748b'>{k}</td>"
        f"<td style='padding:6px 12px;font-weight:600'>{html.escape(str(v))}</td></tr>"
        for k, v in linhas
    )
    corpo = (
        "<div style='font-family:Arial,sans-serif;font-size:14px;color:#0f172a'>"
        f"<h2 style='color:#0a8bb5'>Novo pedido de visita #{ordem['id_os']}</h2>"
        f"<table style='border-collapse:collapse'>{tabela}</table>"
        "<p style='color:#64748b'>Confirme o pedido na Central de serviços do app.</p></div>"
    )
    titulo = f"Pedido de visita #{ordem['id_os']}: {ordem['empresa']['nome']}"
    for d in destinos:
        email.enviar(d, titulo, corpo)
