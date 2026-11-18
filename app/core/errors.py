"""Erros de domínio e handlers globais. Respostas de erro nunca vazam detalhes internos."""

import logging
from typing import Optional

from flask import Flask, Response, current_app, g
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)


class AppError(Exception):
    """Erro esperado da aplicação, convertido em resposta JSON padronizada."""

    status_code = 400
    code = "bad_request"

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        code: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


def error_response(status: int, code: str, message: str):
    body = {
        "error": {"code": code, "message": message, "request_id": getattr(g, "request_id", None)}
    }
    return body, status


def validation_error_response(err: ValidationError) -> Response:
    """Erros de validação (422) no mesmo envelope, sem ecoar a entrada do usuário."""
    details = [
        {"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"], "type": e["type"]}
        for e in err.errors()
    ]
    body = {
        "error": {
            "code": "validation_error",
            "message": "Dados inválidos.",
            "details": details,
            "request_id": getattr(g, "request_id", None),
        }
    }
    resp = current_app.json.response(body)
    resp.status_code = 422
    return resp


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(AppError)
    def _app_error(err: AppError):
        body = {
            "error": {
                "code": err.code,
                "message": err.message,
                "request_id": getattr(g, "request_id", None),
            }
        }
        if err.details:
            body["error"]["details"] = err.details
        resp = app.json.response(body)
        resp.status_code = err.status_code
        retry_after = err.details.get("retry_after")
        if err.status_code == 429 and retry_after:
            resp.headers["Retry-After"] = str(int(retry_after))
        return resp

    @app.errorhandler(HTTPException)
    def _http_error(err: HTTPException):
        code = (err.name or "error").lower().replace(" ", "_")
        response, status = error_response(err.code or 500, code, err.description or err.name)
        resp = app.json.response(response)
        resp.status_code = status
        return resp

    @app.errorhandler(Exception)
    def _unexpected(err: Exception):
        log.exception("unhandled_exception")
        return error_response(500, "internal_error", "Erro interno. Tente novamente mais tarde.")
