import pytest

from app import create_app
from app.config import Settings


@pytest.fixture()
def settings() -> Settings:
    # sem banco: os testes de rotas trocam os repositories por dublês (monkeypatch)
    return Settings(app_env="testing", _env_file=None)


@pytest.fixture()
def client(settings):
    return create_app(settings).test_client()


@pytest.fixture()
def login_as(monkeypatch, client):
    """Simula uma sessão sem tocar no banco: `login_as(tipo_empresa="master", perfil="admin", id_empresa=1)`.

    Define o cookie e troca `usuario_da_sessao` por um usuário fixo. Use também com `tipo_empresa="cliente"`
    para testar o isolamento entre empresas (cliente nunca enxerga dados de outra empresa).
    """

    def _login(tipo_empresa="cliente", perfil="admin", id_empresa=2, id_usuario=10):
        from app.services import auth as auth_service

        monkeypatch.setattr(
            auth_service,
            "usuario_da_sessao",
            lambda token: {
                "id_usuario": id_usuario,
                "id_empresa": id_empresa,
                "tipo_empresa": tipo_empresa,
                "perfil": perfil,
            },
        )
        client.set_cookie("ratual_session", "token-de-teste", domain="localhost", path="/")
        return client

    return _login
