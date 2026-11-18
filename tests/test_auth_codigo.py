"""Login sem senha (e-mail + código de 6 dígitos): repositório em memória e e-mail simulado."""

from datetime import timedelta

import pytest

from app.services import auth as service

USER = {
    "id_usuario": 7,
    "nome": "Maria",
    "login": "maria@empresa.com.br",
    "email_verificacao": None,
    "telefone": None,
    "perfil": "admin",
    "ativo": 1,
    "id_empresa": 1,
    "empresa": "Empresa",
    "tipo_empresa": "cliente",
    "empresa_ativo": 1,
}
EMAIL = "maria@empresa.com.br"


@pytest.fixture()
def fake(monkeypatch):
    """Repositório em memória + e-mail que guarda as mensagens enviadas."""
    st = {"codigos": [], "sessoes": [], "emails": [], "email_ok": True, "user": dict(USER)}

    def buscar(login):
        return st["user"] if login == st["user"]["login"] else None

    def criar_codigo(uid, h, exp, ip):
        st["codigos"].append(
            {
                "id_codigo": len(st["codigos"]) + 1,
                "uid": uid,
                "codigo_hash": h,
                "expira_em": exp,
                "tentativas": 0,
                "usado_em": None,
                "criado_em": service.utcnow(),
            }
        )
        return len(st["codigos"])

    def ativo(uid, agora):
        c = [
            x
            for x in st["codigos"]
            if x["uid"] == uid and not x["usado_em"] and x["expira_em"] > agora
        ]
        return c[-1] if c else None

    def tentativa(idc, esgotar, agora):
        c = st["codigos"][idc - 1]
        c["tentativas"] += 1
        if esgotar:
            c["usado_em"] = agora

    def usado(idc, agora):
        st["codigos"][idc - 1]["usado_em"] = agora

    def invalidar(uid, agora):
        for c in st["codigos"]:
            if c["uid"] == uid and not c["usado_em"]:
                c["usado_em"] = agora

    r = service.repo
    monkeypatch.setattr(r, "buscar_para_login", buscar)
    monkeypatch.setattr(
        r, "ultimo_codigo", lambda uid: st["codigos"][-1] if st["codigos"] else None
    )
    monkeypatch.setattr(r, "contar_codigos_desde", lambda uid, d: len(st["codigos"]))
    monkeypatch.setattr(r, "invalidar_codigos", invalidar)
    monkeypatch.setattr(r, "criar_codigo", criar_codigo)
    monkeypatch.setattr(r, "codigo_ativo_para_update", ativo)
    monkeypatch.setattr(r, "somar_tentativa", tentativa)
    monkeypatch.setattr(r, "marcar_codigo_usado", usado)
    monkeypatch.setattr(r, "limpar_codigos_antigos", lambda limite: None)
    monkeypatch.setattr(r, "criar_sessao", lambda *a: st["sessoes"].append(a) or 1)
    monkeypatch.setattr(r, "registrar_login", lambda *a: None)
    monkeypatch.setattr(r, "limpar_sessoes_antigas", lambda *a: None)

    def enviar(para, assunto, html):
        st["emails"].append((para, assunto, html))
        return st["email_ok"]

    monkeypatch.setattr(service.email_sender, "enviar", enviar)
    return st


def _pedir(client, email=EMAIL):
    return client.post("/v1/auth/solicitar-codigo", json={"email": email})


def _verificar(client, codigo, email=EMAIL):
    return client.post("/v1/auth/verificar-codigo", json={"email": email, "codigo": codigo})


def _codigo(st):
    """Extrai o código de 6 dígitos do assunto do e-mail enviado."""
    return st["emails"][-1][1].split(" ")[0]


def test_solicitar_envia_codigo_e_nao_abre_sessao(client, fake):
    r = _pedir(client)
    assert r.status_code == 200
    body = r.get_json()
    assert body == {"email": "m***@empresa.com.br", "expira_em": 600, "reenvio_em": 60}
    assert "Set-Cookie" not in r.headers and fake["sessoes"] == []
    assert len(_codigo(fake)) == 6 and fake["emails"][0][0] == EMAIL
    assert _codigo(fake) not in fake["codigos"][0]["codigo_hash"]  # nunca em texto claro


def test_email_desconhecido_responde_igual_e_nao_envia(client, fake):
    r = _pedir(client, "ninguem@x.com")
    assert r.status_code == 200 and r.get_json()["email"] == "n***@x.com"
    assert fake["emails"] == [] and fake["codigos"] == []


def test_usuario_inativo_nao_recebe_codigo(client, fake):
    fake["user"]["ativo"] = 0
    assert _pedir(client).status_code == 200
    assert fake["emails"] == []


def test_codigo_certo_abre_sessao_com_cookie_httponly(client, fake):
    _pedir(client)
    r = _verificar(client, _codigo(fake))
    assert r.status_code == 200 and r.get_json()["usuario"]["login"] == EMAIL
    assert "trocar_senha" not in r.get_json()["usuario"]
    cookie = r.headers["Set-Cookie"]
    assert "ratual_session=" in cookie and "HttpOnly" in cookie and "SameSite=Lax" in cookie
    assert len(fake["sessoes"]) == 1


def test_codigo_vale_uma_vez(client, fake):
    _pedir(client)
    c = _codigo(fake)
    assert _verificar(client, c).status_code == 200
    again = _verificar(client, c)
    assert again.status_code == 400 and again.get_json()["error"]["code"] == "code_expired"


def test_codigo_errado_conta_tentativas_e_esgota(client, fake):
    _pedir(client)
    certo = _codigo(fake)
    errado = "000000" if certo != "000000" else "111111"
    for restantes in (4, 3, 2, 1):
        r = _verificar(client, errado)
        assert (
            r.status_code == 400 and r.get_json()["error"]["details"]["attempts_left"] == restantes
        )
    r = _verificar(client, errado)
    assert r.status_code == 429 and r.get_json()["error"]["code"] == "too_many_attempts"
    # esgotado: nem o código certo serve mais
    assert _verificar(client, certo).status_code == 400 and fake["sessoes"] == []


def test_codigo_expirado(client, fake):
    _pedir(client)
    fake["codigos"][0]["expira_em"] = service.utcnow() - timedelta(seconds=1)
    r = _verificar(client, _codigo(fake))
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "code_expired"


def test_reenvio_exige_intervalo_e_invalida_o_anterior(client, fake):
    _pedir(client)
    r = _pedir(client)
    assert r.status_code == 429 and "Retry-After" in r.headers
    fake["codigos"][0]["criado_em"] -= timedelta(minutes=5)
    antigo = _codigo(fake)
    assert _pedir(client).status_code == 200
    assert fake["codigos"][0]["usado_em"] is not None  # o anterior morreu
    assert antigo != _codigo(fake) or _verificar(client, antigo).status_code == 200


def test_falha_no_email_responde_503_e_descarta_o_codigo(client, fake):
    fake["email_ok"] = False
    r = _pedir(client)
    assert r.status_code == 503 and r.get_json()["error"]["code"] == "email_unavailable"
    assert fake["codigos"][0]["usado_em"] is not None


def test_usa_email_de_verificacao_quando_existe(client, fake):
    fake["user"]["email_verificacao"] = "real@gmail.com"
    body = _pedir(client).get_json()
    assert fake["emails"][0][0] == "real@gmail.com" and body["email"] == "r***@gmail.com"


def test_verificar_com_email_desconhecido_nao_revela_nada(client, fake):
    r = _verificar(client, "123456", "x@y.com")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "invalid_code"


def test_codigo_precisa_ter_6_digitos(client, fake):
    assert _verificar(client, "12ab").status_code == 422


def test_rotas_de_senha_nao_existem_mais(client, fake):
    assert client.post("/v1/auth/login", json={"login": EMAIL, "senha": "x"}).status_code == 404
    assert client.post("/v1/auth/senha", json={}).status_code == 404
