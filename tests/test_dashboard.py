from datetime import date, datetime

import pytest

from app import create_app
from app.repositories import leituras
from app.services import dashboard as service

AGORA = datetime(2026, 11, 18, 12, 0, 0)


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    return app.test_client()


@pytest.fixture()
def repo(monkeypatch):
    chamadas = {"temp": [], "comp": []}
    monkeypatch.setattr(service, "agora_brasilia", lambda: AGORA)

    def temp(desde, id_empresa):
        chamadas["temp"].append((desde, id_empresa))
        return [
            {"data_leitura": datetime(2026, 11, 18, 10, 0), "tipo": "congelado", "media": -18.5},
            {"data_leitura": datetime(2026, 11, 18, 10, 0), "tipo": "resfriado", "media": 4.0},
            {"data_leitura": datetime(2026, 11, 18, 10, 5), "tipo": "congelado", "media": -18.0},
        ]

    def comp(desde, id_empresa):
        chamadas["comp"].append((desde, id_empresa))
        return [
            {"dia": date(2026, 11, 18), "id_dispositivo": 1, "ligadas": 6, "amostras": 12},
            {"dia": date(2026, 11, 18), "id_dispositivo": 2, "ligadas": 12, "amostras": 12},
        ]

    monkeypatch.setattr(leituras, "temperatura_por_coleta", temp)
    monkeypatch.setattr(leituras, "compressor_por_dia", comp)
    return chamadas


def test_graficos_requer_login(client):
    assert client.get("/v1/dashboard/graficos").status_code == 401


def test_graficos_series(login_as, repo):
    c = login_as(tipo_empresa="master", id_empresa=1)
    r = c.get("/v1/dashboard/graficos?horas=6&dias=3")
    assert r.status_code == 200
    corpo = r.get_json()
    assert corpo["horas"] == 6 and corpo["dias"] == 3
    assert corpo["temperatura_media"] == [
        {"data": "2026-11-18T10:00:00", "congelados": -18.5, "resfriados": 4.0},
        {"data": "2026-11-18T10:05:00", "congelados": -18.0, "resfriados": None},
    ]
    dias = corpo["compressor_por_dia"]
    assert [d["dia"] for d in dias] == ["2026-11-16", "2026-11-17", "2026-11-18"]
    assert dias[0]["horas_media"] is None and dias[0]["aparelhos"] == 0
    # 6 amostras de 5 min = 0,5 h; 12 = 1 h; média 0,75 -> 0,8; 18/24 = 75%
    assert dias[2] == {
        "dia": "2026-11-18",
        "hoje": True,
        "horas_media": 0.8,
        "ligado_pct": 75,
        "aparelhos": 2,
    }
    assert repo["temp"][0] == (datetime(2026, 11, 18, 6, 0), None)
    assert repo["comp"][0] == (datetime(2026, 11, 16, 0, 0), None)


def test_graficos_cliente_filtra_pela_empresa(login_as, repo):
    c = login_as(tipo_empresa="cliente", id_empresa=2)
    assert c.get("/v1/dashboard/graficos").status_code == 200
    assert repo["temp"][0][1] == 2 and repo["comp"][0][1] == 2


def test_graficos_limites_e_erro(login_as, repo):
    c = login_as(tipo_empresa="master", id_empresa=1)
    corpo = c.get("/v1/dashboard/graficos?horas=9999&dias=0").get_json()
    assert corpo["horas"] == 168 and corpo["dias"] == 1
    assert c.get("/v1/dashboard/graficos?horas=abc").status_code == 400
