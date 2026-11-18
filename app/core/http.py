"""Comportamentos transversais de HTTP: request id, cabeçalhos de segurança e JSON (orjson)."""

import re
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal

import orjson
from flask import Flask, Response, g, request
from flask.json.provider import JSONProvider

from app.version import build_id

# A UI do Swagger precisa de scripts/estilos próprios (servidos do mesmo domínio, sem CDN).
_BUILD = build_id()  # identifica o pacote no ar (cabeçalho X-Build)
_DOCS_CSP = (
    "default-src 'none'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'"
)
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def _default(obj):
    """Tipos que vêm do MySQL: Decimal -> número; datas -> ISO 8601 (sem fuso: horário de Brasília)."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat(sep="T") if isinstance(obj, datetime) else obj.isoformat()
    if isinstance(obj, timedelta):
        return int(obj.total_seconds())
    raise TypeError(f"Tipo não serializável: {type(obj).__name__}")


class OrjsonProvider(JSONProvider):
    """Serialização JSON com orjson (bem mais rápida que o json da stdlib)."""

    def dumps(self, obj, **kwargs) -> str:
        return orjson.dumps(obj, default=_default, option=orjson.OPT_NON_STR_KEYS).decode()

    def loads(self, s, **kwargs):
        return orjson.loads(s)

    def response(self, *args, **kwargs) -> Response:
        obj = self._prepare_response_obj(args, kwargs)
        return Response(
            orjson.dumps(obj, default=_default, option=orjson.OPT_NON_STR_KEYS),
            mimetype="application/json",
        )


def register_http_hooks(app: Flask, *, is_production: bool) -> None:
    app.json = OrjsonProvider(app)

    @app.before_request
    def _start():
        incoming = request.headers.get("X-Request-ID", "")
        # só aceitamos IDs bem formados (evita log injection); senão geramos um novo
        g.request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        g.started_at = time.perf_counter()

    @app.after_request
    def _finish(response: Response) -> Response:
        response.headers["X-Request-ID"] = g.get("request_id", "")
        response.headers["X-Build"] = _BUILD
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        is_docs_page = request.path.startswith("/docs") and response.mimetype == "text/html"
        response.headers["Content-Security-Policy"] = _DOCS_CSP if is_docs_page else _API_CSP
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        response.headers.setdefault("Cache-Control", "no-store")
        if is_production:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        started = g.get("started_at")
        if started is not None:
            app.logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000, 2),
                },
            )
        return response
