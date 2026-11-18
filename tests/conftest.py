import pytest

from app import create_app
from app.config import Settings


@pytest.fixture()
def settings() -> Settings:
    return Settings(app_env="testing", _env_file=None)


@pytest.fixture()
def client(settings):
    return create_app(settings).test_client()
