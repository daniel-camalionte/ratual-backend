from app import create_app
from app.config import Settings


def test_openapi_spec_describes_routes(client):
    spec = client.get("/docs/openapi.json").get_json()
    assert spec["info"]["title"] == "Ratual API"
    assert "/health" in spec["paths"]
    assert "HealthResponse" in spec["components"]["schemas"]


def test_swagger_ui_is_served(client):
    resp = client.get("/docs/swagger")
    assert resp.status_code == 200
    assert "text/html" in resp.content_type
    csp = resp.headers["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "http" not in csp  # sem CDNs externos


def test_swagger_assets_are_local(client):
    html = client.get("/docs/swagger").get_data(as_text=True)
    assert "https://" not in html and "//cdn" not in html


def test_api_csp_stays_strict(client):
    csp = client.get("/v1/hello").headers["Content-Security-Policy"]
    assert csp == "default-src 'none'; frame-ancestors 'none'"


def test_docs_disabled_by_default_in_production():
    settings = Settings(app_env="production", secret_key="x" * 40, _env_file=None)
    client = create_app(settings).test_client()
    assert client.get("/docs/swagger").status_code == 404
    assert client.get("/docs/openapi.json").status_code == 404
    assert client.get("/v1/hello").status_code == 200


def test_docs_can_be_enabled_in_production():
    settings = Settings(
        app_env="production", secret_key="x" * 40, docs_enabled=True, _env_file=None
    )
    assert create_app(settings).test_client().get("/docs/openapi.json").status_code == 200


def test_openapi_server_uses_public_base_path():
    settings = Settings(app_env="testing", public_base_path="/api/", _env_file=None)
    spec = create_app(settings).test_client().get("/docs/openapi.json").get_json()
    assert spec["servers"][0]["url"] == "/api"


def test_openapi_server_root_when_prefix_empty():
    settings = Settings(app_env="testing", public_base_path="", _env_file=None)
    spec = create_app(settings).test_client().get("/docs/openapi.json").get_json()
    assert spec["servers"][0]["url"] == "/"


def test_local_wsgi_mounts_api_under_prefix(monkeypatch):
    """wsgi.py emula a montagem da hospedagem: /api/v1/hello (e não /v1/hello) na borda."""
    import importlib

    monkeypatch.setenv("APP_ENV", "testing")
    from app.config import get_settings

    get_settings.cache_clear()
    import wsgi

    importlib.reload(wsgi)
    from werkzeug.test import Client

    c = Client(wsgi.application)
    assert c.get("/api/v1/hello").status_code == 200
    assert c.get("/api/health").status_code == 200
    assert c.get("/v1/hello").status_code == 404
    get_settings.cache_clear()
