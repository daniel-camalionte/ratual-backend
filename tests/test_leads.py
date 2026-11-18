"""Leads da landing page (público). Banco e e-mail em dublê: nenhum e-mail real é enviado."""

import pytest

from app import create_app
from app.integrations import email
from app.repositories import leads as repo
from app.services import leads as service

VALIDO = {
    "nome": "Ana",
    "empresa": "Açougue Central",
    "telefone": "(11) 99999-0000",
    "plano": "Prevenção",
}


@pytest.fixture()
def client(settings):
    settings.lead_emails = "vendas@exemplo.com"
    app = create_app(settings)
    return app.test_client()


@pytest.fixture(autouse=True)
def dubles(monkeypatch):
    estado = {"gravados": [], "enviados": [], "marcados": []}

    def criar(campos):
        estado["gravados"].append(campos)
        return len(estado["gravados"])

    monkeypatch.setattr(repo, "criar", criar)
    monkeypatch.setattr(
        repo, "marcar_email_enviado", lambda id_lead: estado["marcados"].append(id_lead)
    )
    monkeypatch.setattr(
        email, "enviar", lambda p, a, h: estado["enviados"].append((p, a, h)) or True
    )
    monkeypatch.setattr("app.api.v1.leads.em_segundo_plano", lambda f, *a: f(*a))
    service._envios.clear()
    return estado


def test_cria_lead_sem_login_e_avisa_por_email(client, dubles):
    resp = client.post("/v1/leads", json=VALIDO)  # sem cookie de sessão
    assert resp.status_code == 201
    assert resp.get_json()["id_lead"] == 1
    assert dubles["gravados"][0]["empresa"] == "Açougue Central"
    assert dubles["gravados"][0]["status"] == "novo" and dubles["gravados"][0]["origem"] == "site"
    para, titulo, corpo = dubles["enviados"][0]
    assert para == "vendas@exemplo.com" and "Açougue Central" in titulo
    assert "wa.me/5511999990000" in corpo
    assert dubles["marcados"] == [1]


def test_sem_destinatarios_grava_e_nao_envia(client, dubles, settings):
    settings.lead_emails = ""
    assert client.post("/v1/leads", json=VALIDO).status_code == 201
    assert dubles["enviados"] == [] and dubles["marcados"] == []


def test_campo_obrigatorio_e_vazio_422(client, dubles):
    assert client.post("/v1/leads", json={**VALIDO, "empresa": "  "}).status_code == 422
    assert client.post("/v1/leads", json={"nome": "Ana"}).status_code == 422
    assert dubles["gravados"] == []


def test_telefone_sem_ddd_400(client):
    assert client.post("/v1/leads", json={**VALIDO, "telefone": "9999-0000"}).status_code == 400


def test_html_do_formulario_e_escapado(client, dubles):
    client.post("/v1/leads", json={**VALIDO, "nome": "<script>x</script>", "empresa": "<b>X</b>"})
    assert "<script>" not in dubles["enviados"][0][2] and "<b>" not in dubles["enviados"][0][2]


def test_robo_no_campo_invisivel_nao_grava(client, dubles):
    resp = client.post("/v1/leads", json={**VALIDO, "site": "http://spam"})
    assert resp.status_code == 201
    assert dubles["gravados"] == [] and dubles["enviados"] == []


def test_limite_por_ip(client, dubles):
    for _ in range(service.LIMITE_POR_IP):
        assert client.post("/v1/leads", json=VALIDO).status_code == 201
    resp = client.post("/v1/leads", json=VALIDO)
    assert resp.status_code == 429
    assert resp.get_json()["error"]["code"] == "rate_limited"
    assert len(dubles["gravados"]) == service.LIMITE_POR_IP


def test_falha_no_smtp_nao_perde_o_contato(client, dubles, monkeypatch):
    monkeypatch.setattr(email, "enviar", lambda p, a, h: False)
    assert client.post("/v1/leads", json=VALIDO).status_code == 201
    assert len(dubles["gravados"]) == 1 and dubles["marcados"] == []
