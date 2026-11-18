"""Ordens de serviço e disponibilidade. Sem banco: repositories em dublê; e-mail nunca é enviado."""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

import pytest

from app import create_app
from app.integrations import email
from app.repositories import auditoria
from app.repositories import ordens as repo
from app.repositories import servicos as repo_servicos
from app.services import ordens as service


@pytest.fixture()
def client(settings):
    settings.os_emails = "equipe@exemplo.com, outro@exemplo.com"
    app = create_app(settings)
    return app.test_client()


@pytest.fixture(autouse=True)
def banco(monkeypatch):
    estado = {"criados": [], "atualizados": [], "emails": [], "auditoria": []}
    monkeypatch.setattr(auditoria, "registrar", lambda *a, **k: estado["auditoria"].append(a))
    monkeypatch.setattr(
        email,
        "enviar",
        lambda para, assunto, html: estado["emails"].append((para, assunto, html)) or True,
    )
    # o aviso roda "em segundo plano": nos testes, no mesmo fio
    monkeypatch.setattr("app.api.v1.ordens.em_segundo_plano", lambda f, *a: f(*a))
    monkeypatch.setattr(repo, "criar", lambda campos: (estado["criados"].append(campos), 500)[1])
    monkeypatch.setattr(
        repo, "atualizar", lambda id_os, campos: estado["atualizados"].append((id_os, campos))
    )
    monkeypatch.setattr(
        repo_servicos,
        "plano_da_empresa",
        lambda id_empresa: {"id_plano": 1, "nome": "P", "desconto_servico": Decimal("10")},
    )
    return estado


def amanha():
    return date.today() + timedelta(days=2)  # folga contra virada de dia/fuso


def dia_semana_grade(d):
    return (d.weekday() + 1) % 7


def linha(id_os=500, id_empresa=2, status="solicitado", **extra):
    base = {
        "id_os": id_os,
        "id_empresa": id_empresa,
        "status": status,
        "origem": "cliente",
        "data": amanha(),
        "hora_inicio": timedelta(hours=8),
        "hora_fim": timedelta(hours=12),
        "empresa": "Cliente SA",
        "deviceid": None,
        "dispositivo": None,
        "id_tipo_servico": 1,
        "tipo_servico": "Preventiva",
        "id_tecnico": None,
        "tecnico": None,
        "tecnico_telefone": None,
        "descricao": "Compressor ruidoso",
        "valor_servico": Decimal("200.00"),
        "desconto_percentual": Decimal("10.00"),
        "valor_desconto": Decimal("20.00"),
        "valor_pecas": Decimal("0.00"),
        "valor_total": Decimal("180.00"),
        "descricao_pecas": None,
        "observacao_tecnica": None,
        "motivo_cancelamento": None,
        "solicitante": "Ana",
        "criado_em": datetime(2026, 11, 1, 9, 0),
        "concluido_em": None,
    }
    base.update(extra)
    return base


def agenda(monkeypatch, ocupacao=None, bloqueios=None):
    d = amanha()
    monkeypatch.setattr(
        repo,
        "janelas_ativas",
        lambda: [
            {
                "dia_semana": dia_semana_grade(d),
                "hora_inicio": timedelta(hours=8),
                "hora_fim": timedelta(hours=12),
                "vagas": 2,
            },
        ],
    )
    monkeypatch.setattr(repo, "bloqueios_entre", lambda a, b: bloqueios or [])
    monkeypatch.setattr(repo, "ocupacao_entre", lambda a, b: ocupacao or [])


def tipos(monkeypatch, so_staff=False):
    monkeypatch.setattr(
        repo,
        "tipo_servico",
        lambda id_: {
            "id_tipo_servico": id_,
            "valor": Decimal("200.00"),
            "ativo": 1,
            "cliente_pode_solicitar": 0 if so_staff else 1,
        },
    )


PEDIDO = {"id_tipo_servico": 1, "data": None, "hora_inicio": "08:00", "descricao": "Barulho"}


def pedido():
    return {**PEDIDO, "data": amanha().isoformat()}


# ── acesso ───────────────────────────────────────────────────────────────


def test_401_sem_login(client):
    assert client.get("/v1/ordens").status_code == 401
    assert client.post("/v1/ordens", json=pedido()).status_code == 401
    assert client.put("/v1/ordens/1", json={"status": "confirmado"}).status_code == 401
    assert client.get("/v1/agenda/disponibilidade").status_code == 401


def test_cliente_nao_edita_ordem(client, login_as, banco):
    login_as(tipo_empresa="cliente", perfil="admin")
    assert client.put("/v1/ordens/500", json={"status": "confirmado"}).status_code == 403
    assert banco["atualizados"] == []


def test_visualizador_nao_pede_nem_cancela(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="cliente", perfil="visualizador")
    tipos(monkeypatch)
    agenda(monkeypatch)
    assert client.post("/v1/ordens", json=pedido()).status_code == 403
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha())
    assert client.post("/v1/ordens/500/cancelar", json={}).status_code == 403
    assert banco["criados"] == banco["atualizados"] == []


# ── disponibilidade ──────────────────────────────────────────────────────


def test_disponibilidade_desconta_vagas_ocupadas(client, login_as, monkeypatch):
    login_as()
    agenda(monkeypatch, ocupacao=[{"data": amanha(), "hora_inicio": timedelta(hours=8), "n": 1}])
    corpo = client.get(
        f"/v1/agenda/disponibilidade?inicio={amanha().isoformat()}&dias=1"
    ).get_json()
    assert corpo["dias"][0]["data"] == amanha().isoformat()
    assert corpo["dias"][0]["janelas"] == [
        {"hora_inicio": "08:00", "hora_fim": "12:00", "vagas_livres": 1}
    ]


def test_disponibilidade_esconde_dia_bloqueado_e_lotado(client, login_as, monkeypatch):
    login_as()
    agenda(monkeypatch, bloqueios=[{"data": amanha()}])
    assert (
        client.get(f"/v1/agenda/disponibilidade?inicio={amanha().isoformat()}&dias=1").get_json()[
            "dias"
        ]
        == []
    )
    agenda(monkeypatch, ocupacao=[{"data": amanha(), "hora_inicio": timedelta(hours=8), "n": 2}])
    assert (
        client.get(f"/v1/agenda/disponibilidade?inicio={amanha().isoformat()}&dias=1").get_json()[
            "dias"
        ]
        == []
    )


def test_disponibilidade_comeca_amanha_no_minimo(client, login_as, monkeypatch):
    login_as()
    agenda(monkeypatch)
    corpo = client.get("/v1/agenda/disponibilidade?inicio=2020-01-01&dias=500").get_json()
    assert corpo["inicio"] == (service.hoje() + timedelta(days=1)).isoformat()
    inicio, fim = date.fromisoformat(corpo["inicio"]), date.fromisoformat(corpo["fim"])
    assert (fim - inicio).days + 1 == service.HORIZONTE_DIAS


# ── pedido do cliente ────────────────────────────────────────────────────


def test_cliente_pede_visita_e_equipe_e_avisada(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="cliente", perfil="operador", id_empresa=2, id_usuario=10)
    tipos(monkeypatch)
    agenda(monkeypatch)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha(id_os))
    resp = client.post("/v1/ordens", json=pedido())
    assert resp.status_code == 201
    assert resp.get_json()["ordem"]["status"] == "solicitado"
    gravado = banco["criados"][0]
    assert (
        gravado["id_empresa"] == 2 and gravado["id_usuario_solicitante"] == 10
    )  # empresa vem da sessão
    assert gravado["origem"] == "cliente" and gravado["hora_fim"] == time(12, 0)
    assert gravado["valor_desconto"] == Decimal("20.00") and gravado["valor_total"] == Decimal(
        "180.00"
    )
    assert [e[0] for e in banco["emails"]] == ["equipe@exemplo.com", "outro@exemplo.com"]
    assert "#500" in banco["emails"][0][1]


def test_cliente_nao_escolhe_a_empresa_do_pedido(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2)
    tipos(monkeypatch)
    agenda(monkeypatch)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha(id_os))
    client.post(
        "/v1/ordens", json={**pedido(), "id_empresa": 99, "id_tecnico": 3, "valor_servico": 1}
    )
    gravado = banco["criados"][0]
    assert gravado["id_empresa"] == 2 and gravado["valor_servico"] == Decimal("200.00")
    assert gravado.get("id_tecnico") is None


def test_pedido_horario_fora_da_grade_409(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="cliente", perfil="admin")
    tipos(monkeypatch)
    agenda(monkeypatch, ocupacao=[{"data": amanha(), "hora_inicio": timedelta(hours=8), "n": 2}])
    assert client.post("/v1/ordens", json=pedido()).status_code == 409
    assert banco["criados"] == []


def test_pedido_data_passada_ou_tipo_indisponivel_400(client, login_as, monkeypatch):
    login_as(tipo_empresa="cliente", perfil="admin")
    agenda(monkeypatch)
    tipos(monkeypatch)
    assert (
        client.post("/v1/ordens", json={**pedido(), "data": date.today().isoformat()}).status_code
        == 400
    )
    tipos(monkeypatch, so_staff=True)  # tipo que o cliente não pode pedir
    assert client.post("/v1/ordens", json=pedido()).status_code == 400


def test_pedido_equipamento_de_outra_empresa_400(client, login_as, monkeypatch):
    login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2)
    tipos(monkeypatch)
    agenda(monkeypatch)
    consultas = []
    monkeypatch.setattr(
        repo, "id_dispositivo", lambda deviceid, id_empresa: (consultas.append(id_empresa), None)[1]
    )
    assert client.post("/v1/ordens", json={**pedido(), "deviceid": "abc"}).status_code == 400
    assert consultas == [2]


# ── agendamento interno (master) ─────────────────────────────────────────


def test_master_agenda_direto(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    tipos(monkeypatch, so_staff=True)
    monkeypatch.setattr(repo, "empresa_cliente_ativa", lambda id_: True)
    monkeypatch.setattr(repo, "tecnico", lambda id_: {"id_tecnico": id_, "ativo": 1})
    monkeypatch.setattr(
        repo,
        "conflitos_tecnico",
        lambda *a: [
            {
                "id_os": 9,
                "empresa": "Outro",
                "hora_inicio": timedelta(hours=9),
                "hora_fim": timedelta(hours=10),
            }
        ],
    )
    monkeypatch.setattr(
        repo, "buscar", lambda id_os: linha(id_os, status="confirmado", origem="interno")
    )
    corpo = {
        **pedido(),
        "id_empresa": 5,
        "hora_fim": "10:00",
        "id_tecnico": 3,
        "valor_servico": "300,00",
    }
    resp = client.post("/v1/ordens", json=corpo)
    assert resp.status_code == 201
    assert resp.get_json()["avisos"] == ["O técnico já tem a ordem #9 (Outro) das 09:00 às 10:00"]
    gravado = banco["criados"][0]
    assert (
        gravado["status"] == "confirmado"
        and gravado["origem"] == "interno"
        and gravado["id_empresa"] == 5
    )
    assert gravado["valor_total"] == Decimal("270.00")
    assert banco["emails"] == []  # agendamento interno não avisa a equipe


def test_master_agenda_exige_cliente_e_hora_fim(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    tipos(monkeypatch)
    assert client.post("/v1/ordens", json=pedido()).status_code == 400
    monkeypatch.setattr(repo, "empresa_cliente_ativa", lambda id_: False)
    assert (
        client.post(
            "/v1/ordens", json={**pedido(), "id_empresa": 5, "hora_fim": "10:00"}
        ).status_code
        == 400
    )


# ── listagem e isolamento ────────────────────────────────────────────────


def test_cliente_so_lista_a_propria_empresa(client, login_as, monkeypatch):
    login_as(tipo_empresa="cliente", perfil="visualizador", id_empresa=2)
    filtros = []
    monkeypatch.setattr(repo, "listar", lambda *a: (filtros.append(a), [linha()])[1])
    resp = client.get("/v1/ordens?id_empresa=99&id_tecnico=4&status=solicitado,xxx")
    assert resp.status_code == 200 and resp.get_json()["total"] == 1
    assert filtros[0] == (2, None, ["solicitado"], None, None)  # filtros de master ignorados
    assert resp.get_json()["ordens"][0]["valores"]["total"] == 180.0
    assert resp.get_json()["ordens"][0]["hora_inicio"] == "08:00"


def test_master_filtra_por_empresa(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="operador", id_empresa=1)
    filtros = []
    monkeypatch.setattr(repo, "listar", lambda *a: (filtros.append(a), [])[1])
    client.get("/v1/ordens?id_empresa=7&id_tecnico=4&inicio=2026-11-01&fim=2026-11-30")
    assert filtros[0] == (7, 4, [], date(2026, 11, 1), date(2026, 11, 30))


def test_cliente_nao_cancela_ordem_de_outra_empresa(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha(id_empresa=3))
    assert client.post("/v1/ordens/500/cancelar", json={}).status_code == 404
    assert banco["atualizados"] == []


def test_ordem_inexistente_404(client, login_as, monkeypatch):
    login_as(tipo_empresa="cliente", perfil="admin")
    monkeypatch.setattr(repo, "buscar", lambda id_os: None)
    assert client.post("/v1/ordens/1/cancelar", json={}).status_code == 404


# ── cancelamento ─────────────────────────────────────────────────────────


def test_cliente_cancela_a_propria(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="cliente", perfil="operador", id_empresa=2)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha())
    assert (
        client.post("/v1/ordens/500/cancelar", json={"motivo": " Não precisa mais "}).status_code
        == 200
    )
    assert banco["atualizados"] == [
        (500, {"status": "cancelado", "motivo_cancelamento": "Não precisa mais"})
    ]


def test_cliente_nao_cancela_visita_em_atendimento(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha(status="em_atendimento"))
    assert client.post("/v1/ordens/500/cancelar", json={}).status_code == 400
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    assert client.post("/v1/ordens/500/cancelar", json={}).status_code == 200  # a equipe pode
    assert len(banco["atualizados"]) == 1


# ── edição (master) ──────────────────────────────────────────────────────


def test_master_confirma_e_atribui_tecnico(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha())
    monkeypatch.setattr(repo, "tecnico", lambda id_: {"id_tecnico": id_, "ativo": 1})
    monkeypatch.setattr(repo, "conflitos_tecnico", lambda *a: [])
    resp = client.put(
        "/v1/ordens/500", json={"status": "confirmado", "id_tecnico": 3, "hora_inicio": "09:00"}
    )
    assert resp.status_code == 200
    assert banco["atualizados"][0] == (
        500,
        {"status": "confirmado", "id_tecnico": 3, "hora_inicio": time(9, 0)},
    )


def test_transicao_invalida_e_tecnico_inativo_400(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha(status="solicitado"))
    assert client.put("/v1/ordens/500", json={"status": "concluido"}).status_code == 400
    monkeypatch.setattr(repo, "tecnico", lambda id_: {"id_tecnico": id_, "ativo": 0})
    assert client.put("/v1/ordens/500", json={"id_tecnico": 3}).status_code == 400


def test_ordem_cancelada_nao_muda(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha(status="cancelado"))
    assert client.put("/v1/ordens/500", json={"valor_pecas": 10}).status_code == 400


def test_lancar_valores_recalcula_total_so_com_desconto_na_mao_de_obra(
    client, login_as, monkeypatch, banco
):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha(status="em_atendimento"))
    monkeypatch.setattr(repo, "conflitos_tecnico", lambda *a: [])
    resp = client.put(
        "/v1/ordens/500", json={"valor_servico": 300, "valor_pecas": "50,50", "status": "concluido"}
    )
    assert resp.status_code == 200
    campos = banco["atualizados"][0][1]
    assert campos["valor_desconto"] == Decimal("30.00") and campos["valor_total"] == Decimal(
        "320.50"
    )
    assert isinstance(campos["concluido_em"], datetime)


def test_ordem_concluida_aceita_valores_mas_nao_remarcar(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(repo, "buscar", lambda id_os: linha(status="concluido"))
    assert (
        client.put("/v1/ordens/500", json={"data": "2030-01-01"}).status_code == 400
    )  # nada alterável
    assert (
        client.put("/v1/ordens/500", json={"observacao_tecnica": "Trocado o capacitor"}).status_code
        == 200
    )
    assert banco["atualizados"] == [(500, {"observacao_tecnica": "Trocado o capacitor"})]


def test_valores_da_ordem():
    v = service._valores(Decimal("99.99"), Decimal("15"), 0)
    assert v == {"valor_desconto": Decimal("15.00"), "valor_total": Decimal("84.99")}
    assert service.TRANSICOES["concluido"] == service.TRANSICOES["cancelado"] == set()
