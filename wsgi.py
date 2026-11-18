"""Ponto de entrada WSGI local (Docker/flask run). A KingHost usa deploy/kinghost/api.wsgi.

A API é publicada sob um prefixo (padrão /api): https://<dominio>/api/v1/hello.
Em produção quem monta a app no prefixo é o Apache/mod_wsgi; aqui emulamos o mesmo comportamento
(SCRIPT_NAME=/api), para que local e produção tenham URLs idênticas.
"""

from werkzeug.exceptions import NotFound
from werkzeug.middleware.dispatcher import DispatcherMiddleware

from app import create_app
from app.config import get_settings

flask_app = create_app()
_prefix = get_settings().openapi_base_path

application = DispatcherMiddleware(NotFound(), {_prefix: flask_app}) if _prefix else flask_app

# alias para servidores/configurações que esperam `app`
app = application

if __name__ == "__main__":  # execução local rápida: python wsgi.py
    from werkzeug.serving import run_simple

    run_simple("127.0.0.1", 8000, application)
