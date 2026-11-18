from datetime import datetime

import pytest
from pydantic import SecretStr

from app import create_app
from app.config import Settings
from app.core import crypto
from app.integrations.ezviz import Ezviz, EzvizError
from app.repositories import auditoria
from app.repositories import cameras as repo
from app.services import cameras as service

AGORA = datetime(2026, 11, 18, 10, 0, 0)


def _cam(id_camera, id_empresa, **extra):
    base = {
        "id_camera": id_camera,
        "deviceserial": f"SERIAL{id_camera}",
        "canal": 1,
        "nome": f"Cam {id_camera}",
        "modelo": "C6N",
        "id_dispositivo": 100 + id_camera,
        "criptografada": 0,
        "codigo_cifrado": None,
        "online": 1,
        "data_status": AGORA,
        "ultimo_alarme_em": None,
        "ativo": 1,
        "deviceid": f"dev{id_camera}",
        "refrigerador": "Freezer",
        "id_empresa": id_empresa,
        "refrigerador_ativo": 1,
        "empresa": f"Emp {id_empresa}",
    }
    base.update(extra)
    return base


CAMERAS = {1: _cam(1, 2), 2: _cam(2, 3)}  # câmera 1 da empresa 2; câmera 2 da empresa 3


class FakeEzviz:
    chamadas: list = []

    def endereco(self, serial, canal=1, **kw):
        FakeEzviz.chamadas.append((serial, kw))
        return {"url": f"https://ezviz.test/{serial}.m3u8"}

    def info(self, serial):
        if serial == "NAOEXISTE":
            raise EzvizError("não encontrada", 502)
        return {"deviceName": "Câmera nova", "model": "C6N", "isEncrypt": 0, "status": 1}

    def listar_cameras(self):
        return [
            {
                "deviceSerial": "SERIAL1",
                "channelNo": 1,
                "channelName": "Cam",
                "status": 1,
                "isEncrypt": 0,
            }
        ]

    def status_token(self):
        return {"token_salvo": True, "expira_ms": 1_800_000_000_000, "servidor": "https://x"}

    def alarmes(self, serial, ini, fim):
        return [
            {
                "alarmId": "A1",
                "alarmTime": 1_800_000_000_000,
                "alarmType": 10002,
                "alarmPicUrl": "http://f/1.jpg",
            },
            {"alarmId": "A2", "alarmTime": 1_800_000_100_000, "alarmType": 10002, "isEncrypt": 1},
        ]

    @staticmethod
    def baixar(url):
        return b"\xff\xd8jpeg"


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    return app.test_client()


@pytest.fixture(autouse=True)
def fakes(monkeypatch, tmp_path):
    FakeEzviz.chamadas = []
    service._LINKS_AO_VIVO.clear()
    monkeypatch.setattr(service, "_cliente", lambda settings: FakeEzviz())
    monkeypatch.setenv("EZVIZ_FOTOS_DIR", str(tmp_path / "fotos"))
    monkeypatch.setattr(repo, "buscar", lambda i: CAMERAS.get(i))
    monkeypatch.setattr(
        repo,
        "listar",
        lambda id_empresa=None, incluir_inativas=False: [
            c for c in CAMERAS.values() if id_empresa is None or c["id_empresa"] == id_empresa
        ],
    )
    monkeypatch.setattr(auditoria, "registrar", lambda *a, **k: 1)
    monkeypatch.setattr(crypto, "decrypt", lambda s: "ABCDEF")
    monkeypatch.setattr(crypto, "encrypt", lambda s: "cifrado")


# ── autenticação e perfis ────────────────────────────────────────────────


def test_sem_login_401(client):
    for url in ("/v1/cameras", "/v1/cameras/1/ao-vivo", "/v1/cameras/alarmes/1/foto"):
        assert client.get(url).status_code == 401
    assert client.get("/v1/ezviz/conta").status_code == 401
    assert client.get("/v1/ezviz/status").status_code == 401


def test_cliente_nao_cadastra_nem_edita_403(client, login_as):
    login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2)
    assert client.post("/v1/cameras", json={"deviceserial": "X"}).status_code == 403
    assert client.put("/v1/cameras/1", json={"nome": "x"}).status_code == 403
    assert client.get("/v1/ezviz/conta").status_code == 403
    assert client.get("/v1/ezviz/status").status_code == 403


# ── isolamento entre empresas ────────────────────────────────────────────


def test_listagem_cliente_so_da_propria_empresa(client, login_as):
    login_as(tipo_empresa="cliente", id_empresa=2)
    r = client.get("/v1/cameras")
    assert r.status_code == 200
    assert [c["id_camera"] for c in r.json["cameras"]] == [1]
    assert "codigo_cifrado" not in r.json["cameras"][0]
    assert r.json["cameras"][0]["data_status"] == "2026-11-18T10:00:00"


def test_master_ve_todas(client, login_as):
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.get("/v1/cameras").json["total"] == 2


@pytest.mark.parametrize(
    "sufixo",
    ["/ao-vivo", "/gravacao?inicio=2026-11-18 08:00:00&fim=2026-11-18 09:00:00", "/alarmes"],
)
def test_cliente_nao_acessa_camera_de_outra_empresa(client, login_as, sufixo):
    login_as(tipo_empresa="cliente", id_empresa=2)
    assert client.get(f"/v1/cameras/2{sufixo}").status_code == 404
    assert FakeEzviz.chamadas == []


def test_foto_de_outra_empresa_404(client, login_as, monkeypatch):
    monkeypatch.setattr(
        repo,
        "buscar_alarme",
        lambda i: {
            "id_alarme": i,
            "id_camera": 2,
            "foto_arquivo": "a.jpg",
            "foto_criptografada": 0,
        },
    )
    login_as(tipo_empresa="cliente", id_empresa=2)
    assert client.get("/v1/cameras/alarmes/9/foto").status_code == 404


def test_camera_inativa_oculta_do_cliente(client, login_as, monkeypatch):
    monkeypatch.setitem(CAMERAS, 1, _cam(1, 2, ativo=0))
    try:
        login_as(tipo_empresa="cliente", id_empresa=2)
        assert client.get("/v1/cameras/1/ao-vivo").status_code == 404
    finally:
        CAMERAS[1] = _cam(1, 2)


# ── vídeo ────────────────────────────────────────────────────────────────


def test_ao_vivo_devolve_so_link_temporario_e_reaproveita(client, login_as):
    login_as(tipo_empresa="cliente", id_empresa=2)
    r = client.get("/v1/cameras/1/ao-vivo")
    assert r.status_code == 200
    assert r.json["url"] == "https://ezviz.test/SERIAL1.m3u8"
    assert r.json["camera"] == {"id_camera": 1, "nome": "Cam 1"}
    assert "accessToken" not in r.get_data(as_text=True)
    client.get("/v1/cameras/1/ao-vivo")
    assert len(FakeEzviz.chamadas) == 1  # segundo pedido reaproveita o link


def test_ao_vivo_qualidade_invalida_400(client, login_as):
    login_as(tipo_empresa="cliente", id_empresa=2)
    assert client.get("/v1/cameras/1/ao-vivo?qualidade=4k").status_code == 400


def test_ao_vivo_usa_codigo_decifrado(client, login_as, monkeypatch):
    monkeypatch.setitem(CAMERAS, 1, _cam(1, 2, codigo_cifrado="x"))
    try:
        login_as(tipo_empresa="cliente", id_empresa=2)
        client.get("/v1/cameras/1/ao-vivo")
        assert FakeEzviz.chamadas[0][1]["codigo"] == "ABCDEF"
    finally:
        CAMERAS[1] = _cam(1, 2)


def test_ao_vivo_erro_da_ezviz_vira_409(client, login_as, monkeypatch):
    class Off(FakeEzviz):
        def endereco(self, *a, **k):
            raise EzvizError("Câmera offline", 409, {"ezviz_code": "20007"})

    monkeypatch.setattr(service, "_cliente", lambda s: Off())
    login_as(tipo_empresa="cliente", id_empresa=2)
    r = client.get("/v1/cameras/1/ao-vivo")
    assert r.status_code == 409
    assert r.json["error"]["details"]["ezviz_code"] == "20007"


def test_gravacao_valida_periodo(client, login_as):
    login_as(tipo_empresa="cliente", id_empresa=2)
    ok = client.get("/v1/cameras/1/gravacao?inicio=2026-11-18 08:00:00&fim=2026-11-18 09:00:00")
    assert ok.status_code == 200
    assert client.get("/v1/cameras/1/gravacao").status_code == 400
    longo = client.get("/v1/cameras/1/gravacao?inicio=2026-11-18 01:00:00&fim=2026-11-18 09:00:00")
    assert longo.status_code == 400
    assert (
        client.get(
            "/v1/cameras/1/gravacao?inicio=2026-11-18 08:00:00&fim=2026-11-18 09:00:00&origem=x"
        ).status_code
        == 400
    )


# ── cadastro e edição (master) ───────────────────────────────────────────


def test_cadastrar_ok_e_conflito(client, login_as, monkeypatch):
    salvo = {}
    monkeypatch.setattr(repo, "buscar_por_serial_canal", lambda s, c: None)
    monkeypatch.setattr(repo, "id_dispositivo_por_deviceid", lambda d: 7)
    monkeypatch.setattr(repo, "inserir", lambda campos: salvo.update(campos) or 55)
    login_as(tipo_empresa="master", id_empresa=1)
    r = client.post(
        "/v1/cameras", json={"deviceserial": "abc123", "deviceid": "dev1", "codigo": "abcdef"}
    )
    assert r.status_code == 201 and r.json["id_camera"] == 55
    assert (
        salvo["deviceserial"] == "ABC123"
        and salvo["id_dispositivo"] == 7
        and salvo["codigo_cifrado"] == "cifrado"
    )

    monkeypatch.setattr(repo, "buscar_por_serial_canal", lambda s, c: {"id_camera": 9})
    r = client.post("/v1/cameras", json={"deviceserial": "ABC123"})
    assert r.status_code == 409


def test_cadastrar_erros(client, login_as, monkeypatch):
    monkeypatch.setattr(repo, "buscar_por_serial_canal", lambda s, c: None)
    monkeypatch.setattr(repo, "id_dispositivo_por_deviceid", lambda d: None)
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.post("/v1/cameras", json={"deviceserial": "NAOEXISTE"}).status_code == 400
    assert (
        client.post("/v1/cameras", json={"deviceserial": "A", "deviceid": "x"}).status_code == 400
    )
    assert (
        client.post("/v1/cameras", json={"deviceserial": "A", "codigo": "123"}).status_code == 400
    )
    assert client.post("/v1/cameras", json={"deviceserial": "A", "canal": 0}).status_code == 422


def test_editar(client, login_as, monkeypatch):
    novos = {}
    monkeypatch.setattr(repo, "atualizar", lambda i, campos: novos.update(campos))
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.put("/v1/cameras/1", json={"nome": " Nova ", "ativo": False}).status_code == 200
    assert novos == {"nome": "Nova", "ativo": 0}
    assert client.put("/v1/cameras/1", json={}).status_code == 400
    assert client.put("/v1/cameras/1", json={"nome": "  "}).status_code == 400
    assert client.put("/v1/cameras/99", json={"nome": "x"}).status_code == 404
    novos.clear()
    client.put("/v1/cameras/1", json={"deviceid": None})
    assert novos == {"id_dispositivo": None}


# ── alarmes ──────────────────────────────────────────────────────────────


def test_alarmes_e_foto(client, login_as, monkeypatch, tmp_path):
    foto = tmp_path / "fotos" / "SERIAL1" / "a.jpg"
    foto.parent.mkdir(parents=True)
    foto.write_bytes(b"\xff\xd8x")
    monkeypatch.setattr(
        repo,
        "listar_alarmes",
        lambda i, ini, fim, lim: [
            {
                "id_alarme": 5,
                "tipo": 1,
                "data_alarme": AGORA,
                "foto_arquivo": "SERIAL1/a.jpg",
                "foto_criptografada": 0,
            }
        ],
    )
    alarme = {
        "id_alarme": 5,
        "id_camera": 1,
        "foto_arquivo": "SERIAL1/a.jpg",
        "foto_criptografada": 0,
    }
    monkeypatch.setattr(repo, "buscar_alarme", lambda i: alarme)
    login_as(tipo_empresa="cliente", id_empresa=2)
    r = client.get("/v1/cameras/1/alarmes")
    assert r.json["alarmes"][0] == {
        "id_alarme": 5,
        "tipo": 1,
        "data": "2026-11-18T10:00:00",
        "tem_foto": True,
        "foto_criptografada": False,
    }
    f = client.get("/v1/cameras/alarmes/5/foto")
    assert f.status_code == 200 and f.mimetype == "image/jpeg"
    alarme["foto_arquivo"] = "../../etc/passwd"  # traversal bloqueado
    assert client.get("/v1/cameras/alarmes/5/foto").status_code == 404


# ── conta, status, coleta ────────────────────────────────────────────────


def test_conta_e_status_master(client, login_as, monkeypatch):
    monkeypatch.setattr(
        repo,
        "listar_cadastradas",
        lambda: [{"id_camera": 1, "deviceserial": "SERIAL1", "canal": 1}],
    )
    monkeypatch.setattr(
        repo,
        "ultimas_coletas",
        lambda n=10: [
            {
                "inicio": AGORA,
                "status": "ok",
                "dispositivos": 1,
                "leituras": 2,
                "chamadas_api": 2,
                "duracao_ms": 5,
                "mensagem": None,
            }
        ],
    )
    login_as(tipo_empresa="master", id_empresa=1)
    assert client.get("/v1/ezviz/conta").json["cameras"][0]["id_camera"] == 1
    s = client.get("/v1/ezviz/status").json
    assert "accessToken" not in str(s) and s["token"]["token_salvo"] is True
    assert s["ultimas_execucoes"][0]["alarmes_novos"] == 2


def test_coletar_exige_segredo(monkeypatch, settings):
    monkeypatch.delenv("SCHEDULER_SECRET", raising=False)
    app = create_app(settings)
    c = app.test_client()
    assert c.post("/v1/ezviz/coletar").status_code == 401  # sem segredo configurado
    monkeypatch.setenv("SCHEDULER_SECRET", "s3gredo")
    assert c.post("/v1/ezviz/coletar").status_code == 401
    assert c.post("/v1/ezviz/coletar", headers={"X-Scheduler-Secret": "errado"}).status_code == 401


def test_coletar_importa_alarmes(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("SCHEDULER_SECRET", "s3gredo")
    app = create_app(settings)
    cam = _cam(1, 2, ultimo_alarme_em=None)
    eventos, atualizacoes, alarmes = [], [], []
    monkeypatch.setattr(service, "_trava", lambda: __import__("contextlib").nullcontext(True))
    monkeypatch.setattr(repo, "ultima_coleta_ok", lambda: None)
    monkeypatch.setattr(repo, "listar_ativas", lambda: [cam])
    monkeypatch.setattr(repo, "eventos_offline_abertos", lambda: {})
    monkeypatch.setattr(repo, "alarmes_existentes", lambda ids: {"A2"})
    monkeypatch.setattr(repo, "inserir_alarme", lambda c: alarmes.append(c) or 77)
    monkeypatch.setattr(repo, "inserir_evento", lambda *a: eventos.append(a) or 1)
    monkeypatch.setattr(repo, "atualizar", lambda i, campos: atualizacoes.append(campos))
    monkeypatch.setattr(repo, "inserir_log", lambda c: 1)
    r = app.test_client().post("/v1/ezviz/coletar", headers={"X-Scheduler-Secret": "s3gredo"})
    assert r.status_code == 200, r.get_data(as_text=True)
    assert r.json["alarmes_novos"] == 1 and r.json["online"] == 1
    assert alarmes[0]["alarm_id"] == "A1" and alarmes[0]["foto_arquivo"].endswith("A1.jpg")
    assert eventos[0][1] == "camera_deteccao"
    assert atualizacoes[0]["ultimo_alarme_em"] is not None
    assert (tmp_path / "fotos" / alarmes[0]["foto_arquivo"]).is_file()


# ── cliente EZVIZ (HTTP dublê) ───────────────────────────────────────────


class _Resp:
    def __init__(self, corpo):
        self._c = corpo

    def json(self):
        return self._c


def test_ezviz_renova_token_e_repete_uma_vez(monkeypatch, tmp_path):
    import app.integrations.ezviz as mod

    chamadas = []

    def post(url, data=None, timeout=None):
        chamadas.append(url)
        assert timeout
        if url.endswith("/token/get"):
            n = sum(1 for u in chamadas if u.endswith("/token/get"))
            return _Resp(
                {
                    "code": "200",
                    "data": {
                        "accessToken": f"tk{n}",
                        "expireTime": 9_999_999_999_999,
                        "areaDomain": "https://area.test",
                    },
                }
            )
        if data["accessToken"] == "tk1":
            return _Resp({"code": "10002", "msg": "expirado"})
        return _Resp({"code": "200", "data": {"url": "u"}, "page": None})

    monkeypatch.setattr(mod.requests, "post", post)
    ez = Ezviz(
        "k", SecretStr("s").get_secret_value(), "https://open.test", str(tmp_path / "t.json")
    )
    assert ez.endereco("S1") == {"url": "u"}
    assert chamadas.count("https://open.test/api/lapp/token/get") == 2
    assert "tk2" in (tmp_path / "t.json").read_text()


def test_ezviz_sem_credenciais():
    with pytest.raises(EzvizError):
        Ezviz("", "", "https://x")


def test_settings_fixture_usa_campos_ezviz():
    s = Settings(app_env="testing", ezviz_app_key="k", ezviz_app_secret="s", _env_file=None)
    assert Ezviz.from_settings(s).app_key == "k"
