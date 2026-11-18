"""Central de serviços: cadastros (só master), grade, bloqueios e catálogo. Sem banco."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from app import create_app
from app.repositories import auditoria
from app.repositories import servicos as repo
from app.services import servicos as service


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    return app.test_client()


@pytest.fixture(autouse=True)
def banco(monkeypatch):
    """Banco em memória mínimo: grava as chamadas de escrita para conferir."""
    estado = {"criados": [], "atualizados": [], "removidos": [], "auditoria": []}
    monkeypatch.setattr(auditoria, "registrar", lambda *a, **k: estado["auditoria"].append(a))
    monkeypatch.setattr(
        repo, "criar", lambda ent, campos: (estado["criados"].append((ent, campos)), 77)[1]
    )
    monkeypatch.setattr(
        repo, "atualizar", lambda ent, id_, campos: estado["atualizados"].append((ent, id_, campos))
    )
    monkeypatch.setattr(repo, "remover", lambda ent, id_: estado["removidos"].append((ent, id_)))
    monkeypatch.setattr(repo, "plano_por_nome", lambda nome: [])
    monkeypatch.setattr(repo, "janelas_sobrepostas", lambda *a: [])
    return estado


PLANO = {
    "id_plano": 1,
    "nome": "Prevenção",
    "descricao": None,
    "preco_mensal": Decimal("199.90"),
    "desconto_servico": Decimal("10.00"),
    "visitas_preventivas_ano": 4,
    "pontos_inclusos": 5,
    "ativo": 1,
    "clientes": 3,
}


def test_401_sem_login(client):
    for metodo, rota in (
        ("get", "/v1/planos"),
        ("get", "/v1/servicos/catalogo"),
        ("post", "/v1/agenda/bloqueios"),
    ):
        assert getattr(client, metodo)(rota).status_code == 401


@pytest.mark.parametrize(
    "rota",
    ["/v1/planos", "/v1/tipos-servico", "/v1/tecnicos", "/v1/agenda/grade", "/v1/agenda/bloqueios"],
)
def test_cliente_nao_acessa_cadastros(client, login_as, rota):
    login_as(tipo_empresa="cliente", perfil="admin")
    assert client.get(rota).status_code == 403


def test_cliente_nao_cria_nem_edita_nem_remove(client, login_as, banco):
    login_as(tipo_empresa="cliente", perfil="admin")
    assert client.post("/v1/planos", json={"nome": "X", "desconto_servico": 5}).status_code == 403
    assert client.put("/v1/tecnicos/1", json={"nome": "Y"}).status_code == 403
    assert client.delete("/v1/agenda/grade/1").status_code == 403
    assert client.delete("/v1/agenda/bloqueios/1").status_code == 403
    assert banco["criados"] == banco["atualizados"] == banco["removidos"] == []


def test_lista_planos(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(repo, "listar", lambda ent: [PLANO])
    resp = client.get("/v1/planos")
    assert resp.status_code == 200
    corpo = resp.get_json()
    assert corpo["total"] == 1
    assert corpo["planos"][0]["preco_mensal"] == 199.9
    assert corpo["planos"][0]["clientes"] == 3


def test_cria_plano_com_virgula_decimal(client, login_as, banco):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    resp = client.post(
        "/v1/planos", json={"nome": " Premium ", "desconto_servico": "15,5", "ativo": True}
    )
    assert resp.status_code == 201
    assert resp.get_json() == {"msg": "Plano criado", "id": 77}
    ent, campos = banco["criados"][0]
    assert ent == "plano" and campos["nome"] == "Premium"
    assert campos["desconto_servico"] == Decimal("15.50") and campos["ativo"] == 1
    assert banco["auditoria"][0][1] == "plano_criado"


def test_plano_nome_duplicado_409(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(repo, "plano_por_nome", lambda nome: [{"id_plano": 9}])
    resp = client.post("/v1/planos", json={"nome": "Prevenção", "desconto_servico": 5})
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "conflict"


def test_desconto_acima_de_100_e_invalido(client, login_as):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    assert client.post("/v1/planos", json={"nome": "X", "desconto_servico": 101}).status_code == 422


def test_editar_inexistente_404_e_sem_campos_400(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(repo, "buscar", lambda ent, id_: None)
    assert client.put("/v1/tecnicos/5", json={"nome": "Zé"}).status_code == 404
    monkeypatch.setattr(
        repo,
        "buscar",
        lambda ent, id_: {"id_tecnico": 5, "nome": "Zé", "telefone": None, "ativo": 1},
    )
    assert client.put("/v1/tecnicos/5", json={}).status_code == 400


def test_edita_tecnico_e_limpa_telefone(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(
        repo,
        "buscar",
        lambda ent, id_: {"id_tecnico": 5, "nome": "Zé", "telefone": "11", "ativo": 1},
    )
    resp = client.put("/v1/tecnicos/5", json={"telefone": "  ", "ativo": False})
    assert resp.status_code == 200
    assert banco["atualizados"] == [("tecnico", 5, {"telefone": None, "ativo": 0})]


def test_janela_fim_antes_do_inicio_400(client, login_as):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    resp = client.post(
        "/v1/agenda/grade",
        json={"dia_semana": 1, "hora_inicio": "10:00", "hora_fim": "09:00", "vagas": 2},
    )
    assert resp.status_code == 400


def test_janela_sobreposta_409_e_hora_invalida_422(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    body = {"dia_semana": 1, "hora_inicio": "08:00", "hora_fim": "12:00", "vagas": 2}
    monkeypatch.setattr(repo, "janelas_sobrepostas", lambda *a: [{"id_janela": 3}])
    assert client.post("/v1/agenda/grade", json=body).status_code == 409
    assert client.post("/v1/agenda/grade", json={**body, "hora_inicio": "8h"}).status_code == 422


def test_remove_janela(client, login_as, monkeypatch, banco):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(
        repo,
        "buscar",
        lambda ent, id_: {
            "id_janela": id_,
            "dia_semana": 2,
            "hora_inicio": "08:00",
            "hora_fim": "12:00",
            "vagas": 2,
            "ativo": 1,
        },
    )
    assert client.delete("/v1/agenda/grade/4").status_code == 200
    assert banco["removidos"] == [("janela", 4)]


def test_bloqueio_no_passado_400_e_duplicado_409(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    ontem = (date.today() - timedelta(days=2)).isoformat()
    assert client.post("/v1/agenda/bloqueios", json={"data": ontem}).status_code == 400
    futuro = (date.today() + timedelta(days=5)).isoformat()
    monkeypatch.setattr(repo, "bloqueio_da_data", lambda d: {"id_bloqueio": 1})
    assert client.post("/v1/agenda/bloqueios", json={"data": futuro}).status_code == 409
    monkeypatch.setattr(repo, "bloqueio_da_data", lambda d: None)
    assert (
        client.post("/v1/agenda/bloqueios", json={"data": futuro, "motivo": "Feriado"}).status_code
        == 201
    )


def test_lista_bloqueios_serializa_data(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    monkeypatch.setattr(
        repo,
        "listar_bloqueios",
        lambda: [{"id_bloqueio": 1, "data": date(2026, 12, 25), "motivo": "Natal"}],
    )
    assert client.get("/v1/agenda/bloqueios").get_json()["bloqueios"][0]["data"] == "2026-12-25"


TIPOS = [
    {
        "id_tipo_servico": 1,
        "nome": "Preventiva",
        "descricao": None,
        "valor": Decimal("200.00"),
        "cliente_pode_solicitar": 1,
        "ativo": 1,
    },
    {
        "id_tipo_servico": 2,
        "nome": "Instalação",
        "descricao": None,
        "valor": Decimal("99.99"),
        "cliente_pode_solicitar": 0,
        "ativo": 1,
    },
]


def test_catalogo_cliente_usa_o_plano_da_propria_empresa(client, login_as, monkeypatch):
    login_as(tipo_empresa="cliente", perfil="visualizador", id_empresa=2)
    consultas = []
    monkeypatch.setattr(
        repo, "plano_da_empresa", lambda id_empresa: (consultas.append(id_empresa), PLANO)[1]
    )
    monkeypatch.setattr(
        repo, "tipos_ativos", lambda so_cliente: [TIPOS[0]] if so_cliente else TIPOS
    )
    resp = client.get("/v1/servicos/catalogo?id_empresa=999")  # cliente não escolhe a empresa
    assert resp.status_code == 200
    corpo = resp.get_json()
    assert consultas == [2]
    assert corpo["plano"]["desconto_servico"] == 10.0
    assert [t["nome"] for t in corpo["tipos"]] == ["Preventiva"]
    assert corpo["tipos"][0]["valor_com_desconto"] == 180.0


def test_catalogo_master_ve_todos_e_simula_empresa(client, login_as, monkeypatch):
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    consultas = []
    monkeypatch.setattr(
        repo, "plano_da_empresa", lambda id_empresa: (consultas.append(id_empresa), PLANO)[1]
    )
    monkeypatch.setattr(
        repo, "tipos_ativos", lambda so_cliente: [TIPOS[0]] if so_cliente else TIPOS
    )
    corpo = client.get("/v1/servicos/catalogo?id_empresa=7").get_json()
    assert consultas == [7]
    assert len(corpo["tipos"]) == 2
    assert corpo["tipos"][1]["valor_com_desconto"] == 89.99  # 99,99 - 10% = 89,991 -> 89,99


def test_catalogo_sem_plano(client, login_as, monkeypatch):
    login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2)
    monkeypatch.setattr(repo, "plano_da_empresa", lambda id_empresa: None)
    monkeypatch.setattr(repo, "tipos_ativos", lambda so_cliente: [TIPOS[0]])
    corpo = client.get("/v1/servicos/catalogo").get_json()
    assert corpo["plano"] is None and corpo["tipos"][0]["valor_com_desconto"] == 200.0


def test_hora_do_banco_vira_texto():
    # o driver devolve TIME como timedelta
    assert service.hora_str(timedelta(hours=13, minutes=5)) == "13:05"
    assert service.hora_str("08:30") == "08:30"
