import base64
import time
from datetime import datetime

import pytest

from app import create_app
from app.config import Settings
from app.integrations import ewelink as integ
from app.repositories import eventos as repo_ev
from app.repositories import ewelink as repo
from app.services import coleta
from app.services import ewelink as service

SEGREDO = "segredo-da-cron"


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        app_env="testing",
        _env_file=None,
        ewelink_appid="appid-teste",
        ewelink_app_secret="app-secret-teste",
        ewelink_redirect_url="https://exemplo.test/api/v1/ewelink/callback",
        scheduler_secret=SEGREDO,
        crypto_key="0123456789abcdef0123456789abcdef",
    )


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    return app.test_client()


@pytest.fixture()
def rede(monkeypatch):
    """Dublê da eWeLink: nenhuma chamada sai para a rede. Registra as chamadas e responde por rota."""  # noqa: E501
    chamadas = []
    respostas = {}

    def fake(method, url, headers, body=None):
        chamadas.append({"method": method, "url": url, "headers": headers, "body": body})
        for trecho, resp in respostas.items():
            if trecho in url:
                return resp
        raise AssertionError(f"chamada inesperada: {method} {url}")

    monkeypatch.setattr(integ, "http_request", fake)
    return chamadas, respostas


@pytest.fixture()
def token_ok(monkeypatch):
    agora = int(time.time() * 1000)
    token = {
        "region": "us",
        "at": "AT",
        "rt": "RT",
        "at_expira": agora + 20 * 86400000,
        "rt_expira": agora + 50 * 86400000,
    }
    monkeypatch.setattr(service, "ler_token", lambda: dict(token))
    return token


def _ok(data):
    return {"status_code": 200, "data": {"error": 0, "data": data}}


# ── OAuth ────────────────────────────────────────────────────────────────


def test_auth_exige_login_e_master(client, login_as):
    assert client.get("/v1/ewelink/auth").status_code == 401
    login_as(tipo_empresa="cliente", perfil="admin")
    assert client.get("/v1/ewelink/auth").status_code == 403


def test_auth_gera_url_com_state_e_guarda(client, login_as, monkeypatch):
    guardado = {}
    monkeypatch.setattr(repo, "gravar_estado", lambda chave, valor: guardado.update({chave: valor}))
    login_as(tipo_empresa="master", perfil="admin", id_empresa=1)
    r = client.get("/v1/ewelink/auth")
    assert r.status_code == 200
    url = r.get_json()["url"]
    state = guardado[repo.CHAVE_STATE].split("|")[0]
    assert "state=" + state in url
    assert "clientId=appid-teste" in url
    assert "app-secret-teste" not in url


def test_callback_sem_code_400(client):
    assert client.get("/v1/ewelink/callback").status_code == 400


def test_callback_state_invalido_400(client, monkeypatch):
    monkeypatch.setattr(repo, "ler_estado", lambda chave: f"abc|{int(time.time())}")
    r = client.get("/v1/ewelink/callback?code=C&state=errado")
    assert r.status_code == 400
    assert r.get_json()["error"]["code"] == "invalid_state"


def test_callback_state_expirado_400(client, monkeypatch):
    monkeypatch.setattr(repo, "ler_estado", lambda chave: f"abc|{int(time.time()) - 3600}")
    assert client.get("/v1/ewelink/callback?code=C&state=abc").status_code == 400


def test_callback_troca_code_e_guarda_token_criptografado(client, monkeypatch, rede):
    chamadas, respostas = rede
    respostas["/v2/user/oauth/token"] = _ok(
        {
            "accessToken": "AT-SECRETO",
            "refreshToken": "RT-SECRETO",
            "atExpiredTime": 1,
            "rtExpiredTime": 2,
        }
    )
    estado = {repo.CHAVE_STATE: f"abc|{int(time.time())}"}
    monkeypatch.setattr(repo, "ler_estado", lambda chave: estado.get(chave))
    monkeypatch.setattr(
        repo, "gravar_estado", lambda chave, valor: estado.__setitem__(chave, valor)
    )
    monkeypatch.setattr(repo, "apagar_estado", lambda chave: estado.pop(chave, None))

    r = client.get("/v1/ewelink/callback?code=C1&region=eu&state=abc")
    assert r.status_code == 200
    assert r.get_json() == {"msg": "Autenticado na eWeLink", "region": "eu"}
    assert repo.CHAVE_STATE not in estado  # state de uso único
    assert "AT-SECRETO" not in estado[repo.CHAVE_TOKEN]  # criptografado
    assert chamadas[0]["url"].startswith("https://eu-apia.coolkit.cc")
    assert chamadas[0]["headers"]["Authorization"].startswith("Sign ")
    with client.application.app_context():
        assert service.ler_token()["at"] == "AT-SECRETO"


def test_renovacao_do_token_perto_de_expirar(settings, rede):
    chamadas, respostas = rede
    respostas["/v2/user/refresh"] = _ok({"at": "AT2", "rt": "RT2"})
    agora = int(time.time() * 1000)
    guardado = {}
    token = {
        "region": "us",
        "at": "AT1",
        "rt": "RT1",
        "at_expira": agora + 1000,
        "rt_expira": agora + 10**10,
    }
    c = integ.Ewelink(settings, lambda: dict(token), guardado.update)
    novo = c.token()
    assert novo["at"] == "AT2" and guardado["rt"] == "RT2"
    assert chamadas[0]["headers"]["Authorization"] == "Bearer AT1"


def test_sessao_expirada_503(settings):
    agora = int(time.time() * 1000)
    c = integ.Ewelink(
        settings,
        lambda: {"region": "us", "at": "a", "rt": "r", "rt_expira": agora - 1},
        lambda t: None,
    )
    with pytest.raises(integ.EwelinkError) as e:
        c.token()
    assert e.value.status_code == 503


# ── diagnóstico e status ─────────────────────────────────────────────────


def test_dispositivos_so_master(client, login_as):
    login_as(tipo_empresa="cliente")
    assert client.get("/v1/ewelink/dispositivos").status_code == 403


def test_dispositivos_lista_da_ewelink(client, login_as, token_ok, rede):
    _, respostas = rede
    respostas["/v2/device/thing"] = _ok(
        {
            "thingList": [
                {
                    "itemData": {
                        "deviceid": "D1",
                        "name": "F1",
                        "online": True,
                        "params": {"switch": "on"},
                    }
                }
            ],
            "total": 1,
        }
    )
    login_as(tipo_empresa="master", id_empresa=1)
    r = client.get("/v1/ewelink/dispositivos")
    assert r.status_code == 200
    assert r.get_json()["dispositivos"][0]["deviceid"] == "D1"


def test_dispositivos_sem_login_ewelink_503(client, login_as, monkeypatch, rede):
    monkeypatch.setattr(service, "ler_token", lambda: None)
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.get("/v1/ewelink/dispositivos").status_code == 503


def test_status_coleta(client, login_as, monkeypatch, token_ok):
    agora = service._agora()
    monkeypatch.setattr(repo, "ultimas_execucoes", lambda n=10: [])
    monkeypatch.setattr(repo, "ultima_coleta_ok", lambda: {"inicio": agora})
    monkeypatch.setattr(repo, "resumo_status", lambda desde: [{"status": "ok", "total": 3}])
    monkeypatch.setattr(coleta, "pausada_ate", lambda: None)
    assert client.get("/v1/ewelink/coleta/status").status_code == 401
    login_as(tipo_empresa="cliente")
    assert client.get("/v1/ewelink/coleta/status").status_code == 403
    login_as(tipo_empresa="master", id_empresa=1)
    j = client.get("/v1/ewelink/coleta/status").get_json()
    assert (
        j["atrasada"] is False
        and j["ultimas_24h"] == {"ok": 3}
        and j["eWeLink"]["token_salvo"] is True
    )


# ── coleta (cron) ────────────────────────────────────────────────────────


def test_coletar_exige_secret(client):
    assert client.post("/v1/ewelink/coletar").status_code == 401
    assert (
        client.post("/v1/ewelink/coletar", headers={"X-Scheduler-Secret": "errado"}).status_code
        == 401
    )
    basic = base64.b64encode(b"cron:errado").decode()
    assert (
        client.post("/v1/ewelink/coletar", headers={"Authorization": f"Basic {basic}"}).status_code
        == 401
    )
    assert (
        client.post("/v1/ewelink/coletar", headers={"Authorization": "Basic ###"}).status_code
        == 401
    )


def test_coletar_sem_secret_configurado_nega(settings):
    app = create_app(Settings(app_env="testing", _env_file=None))
    r = app.test_client().post("/v1/ewelink/coletar", headers={"X-Scheduler-Secret": ""})
    assert r.status_code == 401


@pytest.fixture()
def banco_coleta(monkeypatch):
    """Dublê do banco da coleta; devolve o que foi gravado."""
    g = {"logs": [], "lote": None, "leituras": None, "estado": {}, "ids_online": []}
    monkeypatch.setattr(repo, "registrar_log", lambda *a: g["logs"].append(a))
    monkeypatch.setattr(repo, "ultima_coleta_ok", lambda: None)
    monkeypatch.setattr(repo, "deviceids_online", lambda: g["ids_online"])
    monkeypatch.setattr(repo, "estado_anterior", lambda: {7: _anterior()})
    monkeypatch.setattr(repo, "salvar_lote", lambda d: g.update(lote=d))
    monkeypatch.setattr(repo, "mapa_ids", lambda ids: dict.fromkeys(ids, 7))
    monkeypatch.setattr(repo, "salvar_leituras", lambda l: g.update(leituras=l))  # noqa: E741
    monkeypatch.setattr(repo, "ler_estado", lambda chave: g["estado"].get(chave))
    monkeypatch.setattr(
        repo, "gravar_estado", lambda chave, valor: g["estado"].__setitem__(chave, valor)
    )
    monkeypatch.setattr(repo, "apagar_estado", lambda chave: g["estado"].pop(chave, None))
    monkeypatch.setattr(repo_ev, "abertos", lambda: {})
    monkeypatch.setattr(repo_ev, "criar", lambda *a, **k: 1)
    monkeypatch.setattr(repo_ev, "fechar", lambda *a: None)
    monkeypatch.setattr(repo_ev, "atualizar_pico", lambda *a: None)
    monkeypatch.setattr(repo_ev, "atualizar_fora_desde", lambda *a: None)
    return g


def _anterior(**kw):
    base = {
        "id_dispositivo": 7, "online": 1, "temperatura": -18.0, "rele": 1,
        "data_leitura": datetime(2026, 1, 1), "temp_min": -22.0, "temp_max": -15.0,
        "tolerancia_min": 30, "fora_faixa_desde": None,
    }  # fmt: skip
    base.update(kw)
    return base


def test_coletar_grava_dispositivos_e_leituras(client, token_ok, rede, banco_coleta):
    _, respostas = rede
    respostas["/v2/device/thing"] = _ok(
        {
            "thingList": [
                {"itemData": {"deviceid": "D1", "name": " F1 ", "online": True, "productModel": "THR316",  # noqa: E501
                              "params": {"currentTemperature": "-18.4", "switch": "on", "rssi": -60,
                                         "updateListTempLower": ["-22"], "updateListTempUpper": ["-15"]}}},  # noqa: E501
                {"itemData": {"deviceid": "D2", "name": "F2", "online": False,
                              "params": {"currentTemperature": "9.0", "switch": "off"}}},
                {"itemData": {"name": "grupo sem deviceid"}},
            ],
            "total": 3,
        }
    )  # fmt: skip
    r = client.post("/v1/ewelink/coletar", headers={"X-Scheduler-Secret": SEGREDO})
    assert r.status_code == 200, r.get_json()
    j = r.get_json()
    assert j["status"] == "ok" and j["total"] == 2
    d1, d2 = banco_coleta["lote"]
    assert (
        d1["nome"] == "F1" and d1["temperatura"] == -18.4 and d1["rele"] == 1 and d1["sinal"] == -60
    )
    assert d1["limite_min"] == -22.0 and d1["limite_max"] == -15.0
    # offline: não grava temperatura nem relé (a eWeLink repete o último valor)
    assert (
        d2["online"] == 0
        and d2["temperatura"] is None
        and d2["rele"] is None
        and d2["data_leitura"] is None
    )
    assert banco_coleta["logs"][-1][2] == "ok"


def test_coletar_aceita_basic(client, token_ok, rede, banco_coleta):
    _, respostas = rede
    respostas["/v2/device/thing"] = _ok({"thingList": [], "total": 0})
    basic = base64.b64encode(f"cron:{SEGREDO}".encode()).decode()
    r = client.post("/v1/ewelink/coletar", headers={"Authorization": f"Basic {basic}"})
    assert r.status_code == 200
    assert r.get_json()["total"] == 0


def test_coletar_limite_pausa_e_proxima_e_ignorada(client, token_ok, rede, banco_coleta):
    _, respostas = rede
    respostas["/v2/device/thing"] = {
        "status_code": 429,
        "data": {"error": 0, "msg": "too many requests"},
    }
    h = {"X-Scheduler-Secret": SEGREDO}
    r = client.post("/v1/ewelink/coletar", headers=h)
    assert r.status_code == 502
    assert "pausada por 5 min" in r.get_json()["error"]["message"]
    assert (
        coleta.pausada_ate() is not None or "pausa_ate" in banco_coleta["estado"][repo.CHAVE_COLETA]
    )
    # a próxima chamada é ignorada sem falar com a eWeLink
    respostas.clear()
    r2 = client.post("/v1/ewelink/coletar", headers=h)
    assert r2.status_code == 200 and r2.get_json()["status"] == "ignorada"


def test_coletar_espacamento_minimo(client, token_ok, rede, banco_coleta, monkeypatch):
    monkeypatch.setattr(repo, "ultima_coleta_ok", lambda: {"inicio": service._agora()})
    r = client.post("/v1/ewelink/coletar", headers={"X-Scheduler-Secret": SEGREDO})
    assert r.get_json()["status"] == "ignorada"


def test_coletar_gera_evento_de_subida_rapida(client, token_ok, rede, banco_coleta, monkeypatch):
    novos = []
    monkeypatch.setattr(repo_ev, "criar", lambda *a, **k: novos.append(a) or 1)
    monkeypatch.setattr(
        repo,
        "estado_anterior",
        lambda: {7: _anterior(data_leitura=service._agora(), temperatura=-18.0)},
    )
    _, respostas = rede
    respostas["/v2/device/thing"] = _ok(
        {"thingList": [{"itemData": {"deviceid": "D1", "name": "F", "online": True,
                                     "params": {"currentTemperature": "-14.0", "switch": "on"}}}], "total": 1}  # noqa: E501
    )  # fmt: skip
    client.post("/v1/ewelink/coletar", headers={"X-Scheduler-Secret": SEGREDO})
    assert "subida_rapida" in [n[1] for n in novos]


# ── gráfico ──────────────────────────────────────────────────────────────


@pytest.fixture()
def disp(monkeypatch):
    """Dublê de buscar_ativo que respeita o filtro de empresa, como o SQL."""
    linhas = {
        "D1": {"id_dispositivo": 7, "id_empresa": 2, "deviceid": "D1", "nome": "F1", "modelo": "TH", "online": 1,  # noqa: E501
               "temperatura": -18.0, "rele": 1, "temp_min": -22.0, "temp_max": -15.0,
               "data_leitura": datetime(2026, 11, 18, 10, 0)},
    }  # fmt: skip
    consultas = []

    def fake(deviceid, id_empresa):
        consultas.append(id_empresa)
        d = linhas.get(deviceid)
        return d if d and (id_empresa is None or d["id_empresa"] == id_empresa) else None

    monkeypatch.setattr(repo, "buscar_ativo", fake)
    monkeypatch.setattr(
        repo, "leituras_pontos",
        lambda i, a, b, g: [{"data_leitura": datetime(2026, 11, 18, 9, 0), "temperatura": -18.5, "rele": 1, "online": 1}],  # noqa: E501
    )  # fmt: skip
    monkeypatch.setattr(
        repo, "leituras_resumo",
        lambda i, a, b: {"minima": -19, "maxima": -17, "media": -18.2, "compressor_pct": 60, "leituras": 5, "offline": 0},  # noqa: E501
    )  # fmt: skip
    return consultas


def test_grafico_exige_login(client):
    assert client.get("/v1/ewelink/dispositivo/D1/grafico").status_code == 401


def test_grafico_feliz_e_iso(client, login_as, disp):
    login_as(tipo_empresa="cliente", id_empresa=2)
    r = client.get("/v1/ewelink/dispositivo/D1/grafico?horas=12")
    assert r.status_code == 200
    j = r.get_json()
    assert j["pontos"][0]["data"] == "2026-11-18T09:00:00"
    assert j["resumo"]["compressor_ligado_pct"] == 60 and j["agrupamento_min"] == 0
    assert disp == [2]


def test_grafico_isolamento_outra_empresa_404(client, login_as, disp):
    login_as(tipo_empresa="cliente", id_empresa=3)
    assert client.get("/v1/ewelink/dispositivo/D1/grafico").status_code == 404
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.get("/v1/ewelink/dispositivo/D1/grafico").status_code == 200


@pytest.mark.parametrize(
    "qs", ["horas=abc", "inicio=lixo", "inicio=2026-11-18&fim=2026-11-17", "inicio=2020-01-01"]
)
def test_grafico_parametros_invalidos_400(client, login_as, disp, qs):
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.get(f"/v1/ewelink/dispositivo/D1/grafico?{qs}").status_code == 400


# ── relé ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def comandos(monkeypatch, disp):
    reg = {"comandos": [], "rele": [], "eventos": []}
    monkeypatch.setattr(
        repo, "registrar_comando",
        lambda *a: reg["comandos"].append(a) or 55,
    )  # fmt: skip
    monkeypatch.setattr(repo, "atualizar_rele", lambda i, l: reg["rele"].append((i, l)))  # noqa: E741
    monkeypatch.setattr(repo_ev, "criar", lambda *a, **k: reg["eventos"].append((a, k)) or 1)
    return reg


def test_rele_exige_login_antes_da_validacao(client):
    assert client.post("/v1/ewelink/dispositivo/D1/rele", json={"ligado": True}).status_code == 401


def test_rele_corpo_invalido_400(client, login_as, comandos):
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.post("/v1/ewelink/dispositivo/D1/rele", json={"ligado": "sim"}).status_code == 400
    assert client.post("/v1/ewelink/dispositivo/D1/rele", json={}).status_code == 400


def test_rele_so_admin(client, login_as, comandos):
    login_as(tipo_empresa="cliente", perfil="operador", id_empresa=2)
    assert client.post("/v1/ewelink/dispositivo/D1/rele", json={"ligado": True}).status_code == 403
    assert comandos["comandos"] == []


def test_rele_isolamento_404(client, login_as, comandos):
    login_as(tipo_empresa="cliente", perfil="admin", id_empresa=3)
    assert client.post("/v1/ewelink/dispositivo/D1/rele", json={"ligado": False}).status_code == 404


def test_rele_offline_409(client, login_as, comandos, disp, monkeypatch):
    base = repo.buscar_ativo
    monkeypatch.setattr(repo, "buscar_ativo", lambda d, e: {**base(d, e), "online": 0})
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.post("/v1/ewelink/dispositivo/D1/rele", json={"ligado": False}).status_code == 409


def test_rele_feliz_audita_e_cria_evento(client, login_as, comandos, token_ok, rede):
    chamadas, respostas = rede
    respostas["/v2/device/thing/status"] = _ok({})
    login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2, id_usuario=10)
    r = client.post("/v1/ewelink/dispositivo/D1/rele", json={"ligado": False})
    assert r.status_code == 200
    assert r.get_json() == {"msg": "Compressor desligado", "deviceid": "D1", "ligado": False}
    assert '"switch": "off"' in chamadas[0]["body"]
    id_disp, id_usuario, acao, _params, sucesso, _resp = comandos["comandos"][0]
    assert (id_disp, id_usuario, acao, sucesso) == (7, 10, "rele_desligar", True)
    assert comandos["rele"] == [(7, False)]
    args, _kw = comandos["eventos"][0]
    assert args[1] == "rele_desligado" and args[2] == "app"


def test_rele_falha_na_ewelink_audita_e_502(client, login_as, comandos, token_ok, rede):
    _, respostas = rede
    respostas["/v2/device/thing/status"] = {
        "status_code": 200,
        "data": {"error": 500, "msg": "device offline"},
    }
    login_as(tipo_empresa="master", id_empresa=1)
    r = client.post("/v1/ewelink/dispositivo/D1/rele", json={"ligado": True})
    assert r.status_code == 502
    assert comandos["comandos"][0][4] is False  # sucesso=False auditado
    assert comandos["rele"] == [] and comandos["eventos"] == []


def test_acordar_nao_toca_no_banco_dentro_das_threads(monkeypatch, settings):
    """Regressão do 500 em produção: as threads do `uiActive` não têm contexto da app nem sessão de banco."""
    import threading

    from app.integrations import ewelink as integ
    from app.services import coleta

    principal = threading.get_ident()
    chamadas_banco = []

    def ler_token():
        # simula `repo.ler_estado`: no banco real, fora do contexto da app, isto levantaria RuntimeError
        if threading.get_ident() != principal:
            raise RuntimeError("Working outside of application context.")
        chamadas_banco.append(1)
        return {
            "at": "x",
            "region": "us",
            "at_expira": 9_999_999_999_999,
            "rt_expira": 9_999_999_999_999,
        }

    cliente = integ.Ewelink(settings, ler_token, lambda t: None)
    chamados = []
    monkeypatch.setattr(
        integ,
        "http_request",
        lambda m, u, h, b=None: (
            chamados.append(u) or {"status_code": 200, "data": {"error": 0, "data": {}}}
        ),
    )
    monkeypatch.setattr(coleta.repo, "deviceids_online", lambda: [f"d{i}" for i in range(12)])
    monkeypatch.setattr(coleta.time, "sleep", lambda s: None)

    assert coleta._acordar(settings, cliente) == 12
    assert len(chamados) == 12  # todas as chamadas saíram, de threads, sem ler o banco
    assert len(chamadas_banco) == 1  # o token foi lido uma única vez, na thread principal


def test_o_codigo_antigo_realmente_quebrava_nas_threads(monkeypatch, settings):
    """Prova de que o teste acima detecta o defeito: usar o cliente do banco dentro das threads estoura."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from app.integrations import ewelink as integ

    principal = threading.get_ident()

    def ler_token():
        if threading.get_ident() != principal:
            raise RuntimeError("Working outside of application context.")
        return {
            "at": "x",
            "region": "us",
            "at_expira": 9_999_999_999_999,
            "rt_expira": 9_999_999_999_999,
        }

    cliente = integ.Ewelink(settings, ler_token, lambda t: None)
    monkeypatch.setattr(
        integ,
        "http_request",
        lambda *a, **k: {"status_code": 200, "data": {"error": 0, "data": {}}},
    )
    with ThreadPoolExecutor(max_workers=2) as pool, pytest.raises(RuntimeError):
        list(pool.map(lambda d: cliente.alterar_status(d, {"uiActive": 60}), ["a", "b"]))
