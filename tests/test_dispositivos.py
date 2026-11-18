from datetime import datetime

import pytest

from app import create_app
from app.repositories import auditoria
from app.repositories import dispositivos as repo


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    return app.test_client()


def _row(deviceid="D1", id_empresa=2, **kw):
    base = {
        "deviceid": deviceid,
        "nome": " Freezer 1 ",
        "modelo": "TH16",
        "marca": "Sonoff",
        "tipo": "congelado",
        "temp_min": -22.0,
        "temp_max": -15.0,
        "tolerancia_min": 30,
        "online": 1,
        "temperatura": -18.5,
        "umidade": None,
        "rele": 1,
        "sinal": -60,
        "limite_min": None,
        "limite_max": None,
        "data_leitura": datetime(2026, 11, 18, 10, 30),
        "ativo": 1,
        "id_empresa": id_empresa,
        "empresa": "Cliente",
        "id_camera": None,
        "camera_online": None,
        "id_dispositivo": 7,
    }
    base.update(kw)
    return base


@pytest.fixture()
def listagem(monkeypatch):
    """Dublê do repository que respeita o filtro de empresa, como o SQL."""
    todos = [_row("D1", 2), _row("D2", 3), _row("D3", None, ativo=0)]
    chamadas = []

    def fake(id_empresa=None, incluir_inativos=False):
        chamadas.append((id_empresa, incluir_inativos))
        return [
            r
            for r in todos
            if (id_empresa is None or r["id_empresa"] == id_empresa)
            and (incluir_inativos or r["ativo"])
        ]

    monkeypatch.setattr(repo, "listar_com_empresa", fake)
    return chamadas


def test_listar_requer_login(client):
    assert client.get("/v1/dispositivos").status_code == 401


def test_listar_cliente_ve_so_a_propria_empresa(login_as, listagem):
    c = login_as(tipo_empresa="cliente", id_empresa=2)
    r = c.get("/v1/dispositivos?todos=1")
    assert r.status_code == 200
    corpo = r.get_json()
    assert [d["deviceid"] for d in corpo["dispositivos"]] == ["D1"]
    assert listagem == [(2, False)]  # cliente nunca inclui inativos
    d = corpo["dispositivos"][0]
    assert d["nome"] == "Freezer 1"
    assert d["data_leitura"] == "2026-11-18T10:30:00"
    assert d["faixa"] == {"min": -22.0, "max": -15.0, "tolerancia_min": 30}
    assert d["rele"] is True and d["camera"] is None
    assert d["empresa"] == {"id_empresa": 2, "nome": "Cliente"}
    assert corpo["intervalo_coleta_min"] == 5


def test_listar_master_ve_tudo(login_as, listagem):
    c = login_as(tipo_empresa="master", id_empresa=1)
    ids = [d["deviceid"] for d in c.get("/v1/dispositivos").get_json()["dispositivos"]]
    assert ids == ["D1", "D2"]
    ids = [d["deviceid"] for d in c.get("/v1/dispositivos?todos=true").get_json()["dispositivos"]]
    assert ids == ["D1", "D2", "D3"]
    assert listagem[-1] == (None, True)


@pytest.fixture()
def escrita(monkeypatch):
    estado = {"atual": _row("D1", 2, temp_min=-22.0, temp_max=-15.0), "updates": [], "audit": []}
    monkeypatch.setattr(
        repo, "buscar_por_deviceid", lambda d: estado["atual"] if d == "D1" else None
    )
    monkeypatch.setattr(
        repo,
        "buscar_empresa_ativa",
        lambda i: (
            {"id_empresa": i, "nome": "X", "tipo": "master" if i == 1 else "cliente"}
            if i < 10
            else None
        ),
    )
    monkeypatch.setattr(repo, "atualizar", lambda i, c: estado["updates"].append((i, dict(c))) or 1)
    monkeypatch.setattr(auditoria, "registrar", lambda *a, **k: estado["audit"].append(a) or 1)
    return estado


def test_put_requer_login(client):
    assert client.put("/v1/dispositivos/D1", json={"tipo": "resfriado"}).status_code == 401


def test_put_403_para_cliente(login_as, escrita):
    c = login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2)
    assert c.put("/v1/dispositivos/D1", json={"tipo": "resfriado"}).status_code == 403
    assert escrita["updates"] == []


def test_put_calibra_faixa(login_as, escrita):
    c = login_as(tipo_empresa="master", id_empresa=1)
    r = c.put("/v1/dispositivos/D1", json={"tipo": "resfriado", "temp_min": 2, "temp_max": 8.04})
    assert r.status_code == 200
    corpo = r.get_json()
    assert corpo["tipo"] == "resfriado"
    assert corpo["faixa"] == {"min": 2.0, "max": 8.0, "tolerancia_min": 30}
    assert escrita["updates"] == [(7, {"tipo": "resfriado", "temp_min": 2.0, "temp_max": 8.0})]
    assert escrita["audit"][0][1] == "faixa_alterada"


def test_put_vinculo_e_ativo(login_as, escrita):
    c = login_as(tipo_empresa="master", id_empresa=1)
    r = c.put("/v1/dispositivos/D1", json={"id_empresa": 3, "ativo": False})
    assert r.status_code == 200
    assert r.get_json()["id_empresa"] == 3 and r.get_json()["ativo"] == 0
    assert escrita["updates"] == [(7, {"id_empresa": 3, "ativo": 0})]
    assert escrita["audit"][0][1] == "dispositivo_alterado"
    # null desvincula
    r = c.put("/v1/dispositivos/D1", json={"id_empresa": None})
    assert r.status_code == 200 and escrita["updates"][-1] == (7, {"id_empresa": None})


@pytest.mark.parametrize(
    "corpo",
    [
        {"tipo": "quente"},
        {"temp_min": 99},
        {"temp_max": -70},
        {"temp_min": -10},  # >= temp_max atual (-15)
        {"tolerancia_min": 99999},
        {"tolerancia_min": -1},
        {"id_empresa": 1},  # master
        {"id_empresa": 99},  # inexistente
        {"ativo": None},
        {},
    ],
)
def test_put_validacoes_400(login_as, escrita, corpo):
    c = login_as(tipo_empresa="master", id_empresa=1)
    assert c.put("/v1/dispositivos/D1", json=corpo).status_code == 400
    assert escrita["updates"] == []


def test_put_404(login_as, escrita):
    c = login_as(tipo_empresa="master", id_empresa=1)
    assert c.put("/v1/dispositivos/XX", json={"tipo": "resfriado"}).status_code == 404


def test_put_tipos_invalidos_422(login_as, escrita):
    c = login_as(tipo_empresa="master", id_empresa=1)
    assert c.put("/v1/dispositivos/D1", json={"temp_min": True}).status_code == 422
    assert c.put("/v1/dispositivos/D1", json={"tolerancia_min": 1.5}).status_code == 422
