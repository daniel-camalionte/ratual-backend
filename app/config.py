"""Configuração tipada e validada a partir de variáveis de ambiente (.env em desenvolvimento).

Princípio: a aplicação **recusa iniciar** em produção com configuração insegura.
"""

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env na raiz do projeto, independente do diretório de trabalho do servidor WSGI
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
_INSECURE_KEY_MARKER = "troque-esta-chave"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(
        default="development", pattern="^(development|staging|production|testing)$"
    )
    secret_key: str = f"{_INSECURE_KEY_MARKER}-em-desenvolvimento-somente"
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"
    rate_limit_default: str = "120 per minute"
    rate_limit_storage_uri: str = "memory://"
    max_content_length: int = 1_048_576
    # Swagger: padrão = ligado fora de produção. Defina DOCS_ENABLED para forçar.
    docs_enabled: Optional[bool] = None
    # Prefixo público da API: https://dominio/<prefixo>/v1/...
    # Produção: a hospedagem monta a app nele (KingHost: nome da aplicação no painel).
    # Local: o wsgi.py emula a montagem. Vazio = app na raiz do domínio.
    public_base_path: str = "/api"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"

    @property
    def docs_on(self) -> bool:
        return self.docs_enabled if self.docs_enabled is not None else not self.is_production

    @property
    def openapi_base_path(self) -> str:
        path = self.public_base_path.strip().strip("/")
        return f"/{path}" if path else ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _enforce_safety(self) -> "Settings":
        if self.is_production:
            if len(self.secret_key) < 32 or _INSECURE_KEY_MARKER in self.secret_key:
                raise ValueError(
                    "SECRET_KEY inválida para produção (mín. 32 caracteres, aleatória)."
                )
            if "*" in self.cors_origin_list:
                raise ValueError("CORS_ORIGINS não pode conter '*' em produção.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
