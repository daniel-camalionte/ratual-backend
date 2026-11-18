"""Gestão: empresas, usuários e auditoria, sem banco (repositories trocados por dublês)."""

import datetime as dt

import pytest

from app import create_app
from app.repositories import auditoria
from app.repositories import gestao as repo
from app.services import gestao as service


@pytest.fixture()
def client(settings):
    app = create_app(settings)
    return app.test_client()


class Banco:
    """Estado em memória que os dublês dos repositories compartilham."""

    def __init__(self):
        self.empresas = {
            1: {
                "id_empresa": 1,
                "nome": "Ratual",
                "documento": "1",
                "tipo": "master",
                "ativo": 1,
                "id_plano": None,
            },
            2: {
                "id_empresa": 2,
                "nome": "Cliente A",
                "documento": "2",
                "tipo": "cliente",
                "ativo": 1,
                "id_plano": None,
            },
            3: {
                "id_empresa": 3,
                "nome": "Cliente B",
                "documento": "3",
                "tipo": "cliente",
                "ativo": 1,
                "id_plano": None,
            },
            4: {
                "id_empresa": 4,
                "nome": "Inativa",
                "documento": None,
                "tipo": "cliente",
                "ativo": 0,
                "id_plano": None,
            },
        }
        self.planos = {1: {"id_plano": 1, "ativo": 1}, 2: {"id_plano": 2, "ativo": 0}}
        self.usuarios = {
            10: self._u(10, 2, "admin@a.com", "admin"),  # admin do cliente A (o logado nos testes)
            11: self._u(11, 2, "op@a.com", "operador"),
            20: self._u(20, 3, "admin@b.com", "admin"),
            30: self._u(30, 1, "root@ratual.com", "admin"),
        }
        self.auditoria = []
        self.proximo = 100

    def _u(self, id_, emp, login, perfil):
        return {
            "id_usuario": id_,
            "id_empresa": emp,
            "nome": f"U{id_}",
            "login": login,
            "telefone": None,
            "perfil": perfil,
            "ativo": 1,
            "ultimo_login": None,
            "criado_em": dt.datetime(2026, 1, 1, 10, 0, 0),
        }

    def _tipo(self, u):
        return {**u, "tipo_empresa": self.empresas[u["id_empresa"]]["tipo"]}


@pytest.fixture()
def db(monkeypatch):
    b = Banco()

    def listar_usuarios(id_empresa):
        rows = [
            {
                **u,
                "empresa": b.empresas[u["id_empresa"]]["nome"],
                "tipo_empresa": b.empresas[u["id_empresa"]]["tipo"],
            }
            for u in b.usuarios.values()
            if id_empresa is None or u["id_empresa"] == id_empresa
        ]
        return rows

    def criar_usuario(id_empresa, nome, login, telefone, perfil):
        b.proximo += 1
        b.usuarios[b.proximo] = {
            **b._u(b.proximo, id_empresa, login, perfil),
            "nome": nome,
            "telefone": telefone,
        }
        return b.proximo

    def criar_empresa(nome, documento):
        b.proximo += 1
        b.empresas[b.proximo] = {
            "id_empresa": b.proximo,
            "nome": nome,
            "documento": documento,
            "tipo": "cliente",
            "ativo": 1,
            "id_plano": None,
        }
        return b.proximo

    fakes = {
        "listar_empresas": lambda: [
            {
                **e,
                "plano": None,
                "desconto_servico": None,
                "usuarios": 1,
                "dispositivos": 2,
                "criado_em": dt.datetime(2026, 1, 1),
            }
            for e in b.empresas.values()
        ],
        "buscar_empresa": lambda i: b.empresas.get(i),
        "documento_em_uso": lambda d, ign=None: any(
            e["documento"] == d and e["id_empresa"] != ign for e in b.empresas.values()
        ),
        "criar_empresa": criar_empresa,
        "atualizar_empresa": lambda i, c: b.empresas[i].update(c),
        "buscar_plano": lambda i: b.planos.get(i),
        "listar_usuarios": listar_usuarios,
        "buscar_usuario": lambda i: b._tipo(b.usuarios[i]) if i in b.usuarios else None,
        "login_em_uso": lambda lg, ign=None: any(
            u["login"] == lg and u["id_usuario"] != ign for u in b.usuarios.values()
        ),
        "criar_usuario": criar_usuario,
        "atualizar_usuario": lambda i, c: b.usuarios[i].update(c),
        "atualizar_dispositivo": lambda i, c: None,
        "listar_auditoria": lambda lim: [
            {
                "id_auditoria": 1,
                "acao": "x",
                "entidade": "usuario",
                "id_entidade": "1",
                "detalhe": '{"a": 1}',
                "criado_em": dt.datetime(2026, 1, 1),
                "usuario": "N",
                "login": "n@x.com",
            }
        ][:lim],
    }
    for nome, fn in fakes.items():
        monkeypatch.setattr(repo, nome, fn)
    monkeypatch.setattr(
        auditoria,
        "registrar",
        lambda uid, acao, ent, ide, detalhe=None: b.auditoria.append(
            (uid, acao, ent, str(ide), detalhe or {})
        ),
    )
    return b


# ── 401 / 403 por perfil ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "metodo,url",
    [
        ("get", "/v1/empresas"),
        ("post", "/v1/empresas"),
        ("put", "/v1/empresas/2"),
        ("get", "/v1/usuarios"),
        ("post", "/v1/usuarios"),
        ("put", "/v1/usuarios/10"),
        ("get", "/v1/auditoria"),
    ],
)
def test_sem_login_401(client, db, metodo, url):
    r = getattr(client, metodo)(url, json={})
    assert r.status_code == 401


@pytest.mark.parametrize(
    "metodo,url",
    [
        ("get", "/v1/empresas"),
        ("post", "/v1/empresas"),
        ("put", "/v1/empresas/2"),
        ("get", "/v1/auditoria"),
    ],
)
def test_empresas_e_auditoria_so_master(login_as, db, metodo, url):
    c = login_as(
        tipo_empresa="cliente", perfil="admin", id_empresa=2
    )  # até admin de cliente é barrado
    assert getattr(c, metodo)(url, json={"nome": "x"}).status_code == 403


def test_master_nao_admin_nao_gerencia_usuarios(login_as, db):
    c = login_as(tipo_empresa="master", perfil="operador", id_empresa=1)
    assert c.get("/v1/usuarios").status_code == 403
    assert c.post("/v1/usuarios", json={}).status_code == 403
    assert c.put("/v1/usuarios/10", json={}).status_code == 403


def test_cliente_nao_admin_403(login_as, db):
    c = login_as(tipo_empresa="cliente", perfil="operador", id_empresa=2)
    assert c.get("/v1/usuarios").status_code == 403


# ── empresas ────────────────────────────────────────────────────────────


def test_listar_empresas_master(login_as, db):
    r = login_as(tipo_empresa="master", perfil="admin", id_empresa=1, id_usuario=30).get(
        "/v1/empresas"
    )
    assert r.status_code == 200
    j = r.get_json()
    assert j["total"] == 4 and j["empresas"][0]["criado_em"] == "2026-01-01T00:00:00"
    assert j["empresas"][0]["plano"] is None


def test_criar_empresa(login_as, db):
    c = login_as(tipo_empresa="master", perfil="admin", id_empresa=1, id_usuario=30)
    r = c.post("/v1/empresas", json={"nome": "  Nova  ", "documento": "99"})
    assert r.status_code == 201
    novo = r.get_json()["id_empresa"]
    assert db.empresas[novo]["nome"] == "Nova" and db.empresas[novo]["tipo"] == "cliente"
    assert db.auditoria[-1][:4] == (30, "empresa_criada", "empresa", str(novo))
    assert c.post("/v1/empresas", json={"nome": "Outra", "documento": "99"}).status_code == 409
    assert c.post("/v1/empresas", json={}).status_code == 400
    assert c.post("/v1/empresas", json={"nome": "  "}).status_code == 400


def test_editar_empresa(login_as, db):
    c = login_as(tipo_empresa="master", perfil="admin", id_empresa=1, id_usuario=30)
    assert c.put("/v1/empresas/2", json={"ativo": False, "id_plano": 1}).status_code == 200
    assert db.empresas[2]["ativo"] == 0 and db.empresas[2]["id_plano"] == 1
    assert db.auditoria[-1][1] == "empresa_alterada"
    assert c.put("/v1/empresas/1", json={"ativo": False}).status_code == 400  # master não desativa
    assert c.put("/v1/empresas/2", json={"id_plano": 2}).status_code == 400  # plano inativo
    assert c.put("/v1/empresas/2", json={"documento": "3"}).status_code == 409
    assert c.put("/v1/empresas/2", json={"documento": None}).status_code == 200
    assert c.put("/v1/empresas/2", json={"ativo": "sim"}).status_code == 400
    assert c.put("/v1/empresas/2", json={}).status_code == 400
    assert c.put("/v1/empresas/999", json={"nome": "x"}).status_code == 404


# ── usuários: isolamento ────────────────────────────────────────────────


def test_admin_cliente_lista_so_a_propria_empresa(login_as, db):
    c = login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2, id_usuario=10)
    j = c.get("/v1/usuarios?id_empresa=3").get_json()  # filtro de outra empresa é ignorado
    assert {u["empresa"]["id_empresa"] for u in j["usuarios"]} == {2}
    assert j["total"] == 2
    assert [u["eu"] for u in j["usuarios"] if u["id_usuario"] == 10] == [True]


def test_admin_master_lista_todas_e_filtra(login_as, db):
    c = login_as(tipo_empresa="master", perfil="admin", id_empresa=1, id_usuario=30)
    assert c.get("/v1/usuarios").get_json()["total"] == 4
    assert c.get("/v1/usuarios?id_empresa=3").get_json()["total"] == 1


def test_admin_cliente_nao_acessa_usuario_de_outra_empresa(login_as, db):
    c = login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2, id_usuario=10)
    assert c.put("/v1/usuarios/20", json={"nome": "Hack"}).status_code == 404
    assert db.usuarios[20]["nome"] == "U20"


def test_admin_cliente_cria_sempre_na_propria_empresa(login_as, db):
    c = login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2, id_usuario=10)
    r = c.post("/v1/usuarios", json={"nome": "Novo", "login": "N@A.com", "id_empresa": 3})
    assert r.status_code == 201
    assert db.usuarios[r.get_json()["id_usuario"]]["id_empresa"] == 2


def test_admin_cliente_nao_move_usuario(login_as, db):
    c = login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2, id_usuario=10)
    assert c.put("/v1/usuarios/11", json={"id_empresa": 3}).status_code == 403
    assert db.usuarios[11]["id_empresa"] == 2


# ── usuários: regras ────────────────────────────────────────────────────


def test_criar_usuario_sem_senha(login_as, db):
    c = login_as(tipo_empresa="master", perfil="admin", id_empresa=1, id_usuario=30)
    r = c.post(
        "/v1/usuarios",
        json={
            "nome": "Ana",
            "login": " Ana@X.com ",
            "perfil": "operador",
            "id_empresa": 3,
            "telefone": "(11) 91234-5678",
        },
    )
    assert r.status_code == 201
    j = r.get_json()
    u = db.usuarios[j["id_usuario"]]
    assert u["login"] == "ana@x.com" and u["telefone"] == "11912345678"
    assert "senha" not in str(j).lower().replace("sem senha", "")
    assert db.auditoria[-1][1] == "usuario_criado"


@pytest.mark.parametrize(
    "corpo,status",
    [
        ({"login": "a@b.com", "id_empresa": 2}, 400),  # sem nome
        ({"nome": "A", "id_empresa": 2}, 400),  # sem login
        ({"nome": "A", "login": "invalido", "id_empresa": 2}, 400),
        ({"nome": "A", "login": "a@b.com", "perfil": "root", "id_empresa": 2}, 400),
        ({"nome": "A", "login": "a@b.com", "telefone": "123", "id_empresa": 2}, 400),
        ({"nome": "A", "login": "a@b.com"}, 400),  # master sem id_empresa
        ({"nome": "A", "login": "a@b.com", "id_empresa": 4}, 400),  # empresa inativa
        ({"nome": "A", "login": "a@b.com", "id_empresa": 999}, 400),
        ({"nome": "A", "login": "op@a.com", "id_empresa": 2}, 409),
    ],
)
def test_criar_usuario_erros(login_as, db, corpo, status):
    c = login_as(tipo_empresa="master", perfil="admin", id_empresa=1, id_usuario=30)
    assert c.post("/v1/usuarios", json=corpo).status_code == status


def test_editar_usuario(login_as, db):
    c = login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2, id_usuario=10)
    r = c.put(
        "/v1/usuarios/11",
        json={"perfil": "visualizador", "ativo": False, "telefone": "11 3333-4444"},
    )
    assert r.status_code == 200
    assert db.usuarios[11]["perfil"] == "visualizador" and db.usuarios[11]["ativo"] == 0
    assert db.usuarios[11]["telefone"] == "1133334444"
    assert db.auditoria[-1][1] == "usuario_alterado"
    assert c.put("/v1/usuarios/11", json={"login": "admin@a.com"}).status_code == 409
    assert c.put("/v1/usuarios/11", json={}).status_code == 400
    assert c.put("/v1/usuarios/999", json={"nome": "x"}).status_code == 404


def test_nao_se_rebaixa_nem_se_desativa(login_as, db):
    c = login_as(tipo_empresa="cliente", perfil="admin", id_empresa=2, id_usuario=10)
    assert c.put("/v1/usuarios/10", json={"perfil": "operador"}).status_code == 400
    assert c.put("/v1/usuarios/10", json={"ativo": False}).status_code == 400
    assert c.put("/v1/usuarios/10", json={"nome": "Eu mesmo"}).status_code == 200


def test_master_move_usuario_mas_nao_a_si_mesma(login_as, db):
    c = login_as(tipo_empresa="master", perfil="admin", id_empresa=1, id_usuario=30)
    assert c.put("/v1/usuarios/11", json={"id_empresa": 3}).status_code == 200
    assert db.usuarios[11]["id_empresa"] == 3
    assert c.put("/v1/usuarios/30", json={"id_empresa": 2}).status_code == 400
    assert c.put("/v1/usuarios/11", json={"id_empresa": 4}).status_code == 400


# ── auditoria ───────────────────────────────────────────────────────────


def test_auditoria_master(login_as, db):
    c = login_as(tipo_empresa="master", perfil="admin", id_empresa=1, id_usuario=30)
    j = c.get("/v1/auditoria?limite=5").get_json()
    assert j["total"] == 1 and j["registros"][0]["detalhe"] == {"a": 1}
    assert j["registros"][0]["quando"] == "2026-01-01T00:00:00"
    assert c.get("/v1/auditoria?limite=abc").status_code == 400


# ── vínculo de refrigerador ─────────────────────────────────────────────


def test_vincular_dispositivo(db):
    disp = {"id_dispositivo": 5, "deviceid": "abc", "id_empresa": None, "ativo": 1}
    autor = {"id_usuario": 30}
    assert service.vincular_dispositivo(autor, disp, {"id_empresa": 2, "ativo": False}) == {
        "id_empresa": 2,
        "ativo": 0,
    }
    assert db.auditoria[-1][1:4] == ("dispositivo_alterado", "dispositivo", "abc")
    assert service.vincular_dispositivo(autor, disp, {}) is None
    assert service.vincular_dispositivo(autor, disp, {"id_empresa": None}) == {"id_empresa": None}
    for ruim in (1, 4, 999, "2"):  # master, inativa, inexistente, tipo errado
        with pytest.raises(service.AppError):
            service.vincular_dispositivo(autor, disp, {"id_empresa": ruim})
