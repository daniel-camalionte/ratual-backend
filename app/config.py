"""Configuração tipada e validada a partir de variáveis de ambiente (.env em desenvolvimento).

Princípio: a aplicação **recusa iniciar** em produção com configuração insegura.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

_ROOT = Path(__file__).resolve().parent.parent


def resolve_env_file() -> Path:
    """Arquivo de variáveis do ambiente, na raiz do projeto (independe do diretório de trabalho).

    `RATUAL_ENV=stg|prd` escolhe `.env.stg` / `.env.prd`. Sem ela: `.env` se existir (servidor) e,
    em desenvolvimento, `.env.stg` (local = STG; o banco de produção nunca é o padrão).
    """
    target = os.environ.get("RATUAL_ENV", "").strip().lower()
    if target:
        if target not in ("stg", "prd"):
            raise RuntimeError("RATUAL_ENV deve ser 'stg' ou 'prd'.")
        return _ROOT / f".env.{target}"
    for name in (".env", ".env.stg"):
        if (_ROOT / name).exists():
            return _ROOT / name
    return _ROOT / ".env"


_ENV_FILE = resolve_env_file()
_INSECURE_KEY_MARKER = "troque-esta-chave"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

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

    # --- banco (MySQL/MariaDB) ---
    mysql_db_hostname: str = ""
    mysql_db_user: str = ""
    mysql_db_password: SecretStr = SecretStr("")
    mysql_db_name: str = ""
    mysql_db_port: int = 3306
    db_pool_size: int = 5
    db_max_overflow: int = 5
    db_pool_recycle: int = 1800
    db_connect_timeout: int = 10
    db_echo: bool = False

    # --- sessão (cookie httpOnly; no banco fica só o hash do token) ---
    auth_cookie_name: str = "ratual_session"
    auth_session_days: int = 30
    auth_cookie_secure: Optional[bool] = None  # padrão: só em produção
    # login por código de 6 dígitos enviado por e-mail (sem senha)
    auth_code_ttl_seconds: int = 600
    auth_resend_seconds: int = 60
    auth_max_attempts: int = 5
    auth_max_codes_per_hour: int = 10

    # --- e-mail (SMTP com SSL, como no Brain) ---
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_from: str = ""
    smtp_pass: SecretStr = SecretStr(
        ""
    )  # legado do Brain (login = SMTP_FROM); preferir SMTP_USER/SMTP_PASSWORD
    smtp_user: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_security: str = Field(default="ssl", pattern="^(ssl|starttls|none)$")
    ticket_support_emails: str = ""
    lead_emails: str = ""
    os_emails: str = ""

    # --- criptografia dos tokens guardados (AES-CBC, mesma chave do Brain para ler os dados migrados) ---
    crypto_key: SecretStr = SecretStr("")

    # --- eWeLink (OAuth 2.0) e EZVIZ (câmeras) ---
    ewelink_appid: str = ""
    ewelink_app_secret: SecretStr = SecretStr("")
    ewelink_redirect_url: str = ""
    ewelink_region: str = "us"
    ewelink_coleta_intervalo_min: int = 5
    evento_subida_rapida_c: float = 2.0
    ezviz_app_key: str = ""
    ezviz_app_secret: SecretStr = SecretStr("")
    ezviz_api_url: str = "https://open.ezvizlife.com"
    ewelink_uiactive_s: int = 60
    ewelink_uiactive_espera_s: float = 6.0
    trial_days: int = 10
    # segredo do agendador (cron) que dispara as coletas: header X-Scheduler-Secret ou Basic (senha)
    scheduler_secret: SecretStr = SecretStr("")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        return self.app_env == "testing"

    @property
    def cookie_secure(self) -> bool:
        return (
            self.auth_cookie_secure if self.auth_cookie_secure is not None else self.is_production
        )

    @property
    def database_configured(self) -> bool:
        return bool(self.mysql_db_hostname and self.mysql_db_user and self.mysql_db_name)

    @property
    def sqlalchemy_url(self) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_db_user,
            password=self.mysql_db_password.get_secret_value(),
            host=self.mysql_db_hostname,
            port=self.mysql_db_port,
            database=self.mysql_db_name,
            query={"charset": "utf8mb4"},
        )

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
    return Settings(_env_file=resolve_env_file())
