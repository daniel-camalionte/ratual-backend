from datetime import datetime, timedelta

import pytest

from app import create_app
from app.repositories import eventos as repo
from app.services import eventos as service
from app.services.eventos import Detector

T0 = datetime(2026, 11, 18, 10, 0)
FAIXA = {"min": -22.0, "max": -15.0, "tolerancia_min": 30, "fora_desde": None}


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    return app.test_client()


def det():
    return Detector(subida_c=3, intervalo_min=5)


def atual(temp=-18.0, online=True, rele=1):
    return {"online": online, "temperatura": temp, "rele": rele}


def ant(temp=-18.0, minutos=5, online=True, rele=1):
    return {
        "online": online,
        "temperatura": temp,
        "rele": rele,
        "data": T0 - timedelta(minutes=minutos),
    }


# ── Detector ─────────────────────────────────────────────────────────────


def test_offline_abre_e_fecha_com_duracao():
    a = det().avaliar(1, ant(), atual(online=False, temp=None), FAIXA, {}, T0)
    assert a["novos"][0]["tipo"] == "offline" and a["novos"][0]["fim"] is None
    aberto = {
        (1, "offline"): {"id_evento": 9, "inicio": T0 - timedelta(minutes=90), "detalhe": "{}"}
    }
    # offline continua: não duplica
    assert det().avaliar(1, ant(), atual(online=False), FAIXA, aberto, T0)["novos"] == []
    # voltou: fecha com duração
    b = det().avaliar(1, ant(online=False), atual(), FAIXA, aberto, T0)
    assert b["fechar"][0][0] == 9 and b["fechar"][0][2]["duracao_min"] == 90


def test_fora_da_faixa_respeita_tolerancia():
    desde = T0 - timedelta(minutes=10)
    a = det().avaliar(1, ant(-14), atual(-14), {**FAIXA, "fora_desde": desde}, {}, T0)
    assert a["novos"] == [] and a["fora_desde"] == desde  # 10 min < 30 min de tolerância
    desde = T0 - timedelta(minutes=45)
    b = det().avaliar(1, ant(-14), atual(-14), {**FAIXA, "fora_desde": desde}, {}, T0)
    ev = b["novos"][0]
    assert (
        ev["tipo"] == "fora_faixa" and ev["inicio"] == desde and ev["detalhe"]["direcao"] == "acima"
    )


def test_fora_da_faixa_marca_inicio_e_atualiza_pico_e_fecha():
    a = det().avaliar(1, ant(-18), atual(-10), FAIXA, {}, T0)
    assert a["fora_desde"] == T0
    aberto = {
        (1, "fora_faixa"): {
            "id_evento": 3,
            "inicio": T0 - timedelta(hours=1),
            "valor": -12.0,
            "detalhe": "{}",
        }
    }
    assert det().avaliar(1, ant(-12), atual(-10), {**FAIXA, "fora_desde": T0}, aberto, T0)[
        "pico"
    ] == [(3, -10.0)]
    c = det().avaliar(1, ant(-12), atual(-18), {**FAIXA, "fora_desde": T0}, aberto, T0)
    assert c["fora_desde"] is None and c["fechar"][0][2]["normalizou_em"] == -18.0


def test_subida_rapida_e_excecoes():
    a = det().avaliar(1, ant(-18.0), atual(-14.5), FAIXA, {}, T0)
    assert [n["tipo"] for n in a["novos"]] == ["subida_rapida"] and a["novos"][0]["detalhe"][
        "delta"
    ] == 3.5
    # compressor desligado: subida esperada (degelo), não registra
    assert det().avaliar(1, ant(-18.0, rele=0), atual(-14.5, rele=0), FAIXA, {}, T0)["novos"] == []
    # leitura anterior muito antiga (buraco na coleta): não é "seguida"
    assert det().avaliar(1, ant(-18.0, minutos=60), atual(-14.5), FAIXA, {}, T0)["novos"] == []
    # abaixo do limiar
    assert det().avaliar(1, ant(-18.0), atual(-16.0), FAIXA, {}, T0)["novos"] == []


def test_rele_externo():
    a = det().avaliar(1, ant(rele=1), atual(rele=0), FAIXA, {}, T0)
    ev = a["novos"][0]
    assert ev["tipo"] == "rele_desligado" and ev["origem"] == "externo"


def test_descrever_textos():
    base = {"inicio": T0, "fim": None, "origem": "sistema"}
    assert (
        service.descrever({**base, "tipo": "offline", "detalhe": "{}"})
        == "Sem comunicação desde 10:00"
    )
    d = service.descrever({**base, "tipo": "fora_faixa", "valor": -10.0,
                           "detalhe": '{"min": -22, "max": -15, "direcao": "acima"}'})  # fmt: skip
    assert "acima da faixa (-22,0 a -15,0 °C) desde 10:00" in d and "pico -10,0" in d
    assert "por Maria" in service.descrever(
        {**base, "tipo": "rele_ligado", "origem": "app", "usuario": "Maria", "detalhe": None}
    )


# ── rotas ────────────────────────────────────────────────────────────────


def _evento(id_empresa=2, tipo="offline", fim=None):
    return {
        "id_evento": 1, "tipo": tipo, "origem": "sistema", "inicio": T0, "fim": fim, "valor": None,
        "detalhe": '{"duracao_min": 20}', "deviceid": "D1", "dispositivo": " Freezer ", "temp_min": -22,  # noqa: E501
        "temp_max": -15, "id_empresa": id_empresa, "empresa": "Cliente", "usuario": None,
    }  # fmt: skip


@pytest.fixture()
def listagem(monkeypatch):
    chamadas = []

    def fake(**kw):
        chamadas.append(kw)
        return [_evento()]

    monkeypatch.setattr(repo, "listar", fake)
    return chamadas


@pytest.mark.parametrize("url", ["/v1/eventos", "/v1/alertas"])
def test_listagens_exigem_login(client, url):
    assert client.get(url).status_code == 401


def test_cliente_so_ve_a_propria_empresa(client, login_as, listagem):
    login_as(tipo_empresa="cliente", id_empresa=2)
    r = client.get("/v1/eventos?tipo=offline,fora_faixa&limite=10&deviceid=D1")
    assert r.status_code == 200
    j = r.get_json()
    assert j["total"] == 1 and j["limite"] == 10
    e = j["eventos"][0]
    assert e["inicio"] == "2026-11-18T10:00:00" and e["ativo"] is True
    assert e["dispositivo"] == {"deviceid": "D1", "nome": "Freezer"}
    assert e["descricao"].startswith("Sem comunicação")
    kw = listagem[0]
    assert (
        kw["id_empresa"] == 2
        and kw["tipos"] == ["offline", "fora_faixa"]
        and kw["deviceid"] == "D1"
    )


def test_master_ve_todas(client, login_as, listagem):
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.get("/v1/eventos").status_code == 200
    assert listagem[0]["id_empresa"] is None and listagem[0]["limite"] == 100


def test_alertas_filtra_tipos_e_ativos(client, login_as, listagem):
    login_as(tipo_empresa="cliente", id_empresa=2)
    assert client.get("/v1/alertas").status_code == 200
    kw = listagem[0]
    assert kw["tipos"] == service.TIPOS_ALERTA and kw["ativos"] is True and kw["id_empresa"] == 2


@pytest.mark.parametrize("qs", ["tipo=bobagem", "limite=abc", "offset=x"])
def test_listagem_parametros_invalidos_400(client, login_as, listagem, qs):
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.get(f"/v1/eventos?{qs}").status_code == 400


def test_limite_e_limitado_a_500(client, login_as, listagem):
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.get("/v1/eventos?limite=9999").get_json()["limite"] == 500


def test_reprocessar_so_master(client, login_as):
    assert client.post("/v1/eventos/reprocessar").status_code == 401
    login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2)
    assert client.post("/v1/eventos/reprocessar").status_code == 403


def test_reprocessar_recria_eventos(client, login_as, monkeypatch):
    criados, apagou = [], []
    monkeypatch.setattr(
        repo,
        "faixas_dispositivos",
        lambda: [{"id_dispositivo": 1, "temp_min": -22, "temp_max": -15, "tolerancia_min": 0}],
    )
    monkeypatch.setattr(
        repo, "todas_leituras",
        lambda: [
            {"id_dispositivo": 1, "temperatura": -18, "rele": 1, "online": 1, "data_leitura": T0},
            {"id_dispositivo": 1, "temperatura": -10, "rele": 1, "online": 1, "data_leitura": T0 + timedelta(minutes=5)},  # noqa: E501
            {"id_dispositivo": 1, "temperatura": -18, "rele": 1, "online": 1, "data_leitura": T0 + timedelta(minutes=10)},  # noqa: E501
        ],
    )  # fmt: skip
    monkeypatch.setattr(repo, "apagar_eventos_de_sistema", lambda: apagou.append(1))
    monkeypatch.setattr(repo, "criar", lambda *a, **k: criados.append(a) or 1)
    monkeypatch.setattr(repo, "atualizar_fora_desde", lambda *a: None)
    login_as(tipo_empresa="master", id_empresa=1)
    r = client.post("/v1/eventos/reprocessar")
    assert r.status_code == 200
    j = r.get_json()
    assert apagou and j["leituras"] == 3
    assert (
        j["por_tipo"]["fora_faixa"] == 1
        and j["por_tipo"]["subida_rapida"] == 1
        and j["ativos"] == 0
    )
