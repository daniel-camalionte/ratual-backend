import pytest
from pydantic import ValidationError

from app import create_app
from app.config import Settings


def test_security_headers_present(client):
    h = client.get("/v1/hello").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert h["Referrer-Policy"] == "no-referrer"
    assert "default-src 'none'" in h["Content-Security-Policy"]
    assert h["Cache-Control"] == "no-store"
    assert "Strict-Transport-Security" not in h  # só em produção


def test_hsts_in_production():
    settings = Settings(app_env="production", secret_key="x" * 40, _env_file=None)
    h = create_app(settings).test_client().get("/health").headers
    assert "max-age=31536000" in h["Strict-Transport-Security"]


def test_production_rejects_insecure_secret():
    with pytest.raises(ValidationError):
        Settings(app_env="production", _env_file=None)  # chave padrão de desenvolvimento
    with pytest.raises(ValidationError):
        Settings(app_env="production", secret_key="curta", _env_file=None)


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError):
        Settings(app_env="production", secret_key="x" * 40, cors_origins="*", _env_file=None)


def test_cors_only_for_allowed_origin(client):
    ok = client.get("/v1/hello", headers={"Origin": "http://localhost:3000"})
    assert ok.headers.get("Access-Control-Allow-Origin") == "http://localhost:3000"
    bad = client.get("/v1/hello", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in bad.headers


def test_rate_limit_returns_429():
    settings = Settings(app_env="development", rate_limit_default="2 per minute", _env_file=None)
    client = create_app(settings).test_client()
    codes = [client.get("/v1/hello").status_code for _ in range(3)]
    assert codes == [200, 200, 429]
