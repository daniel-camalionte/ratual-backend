"""Execução em segundo plano (ex.: e-mail de aviso), com o contexto da aplicação."""

import threading

from flask import current_app


def em_segundo_plano(funcao, *args) -> None:
    app = current_app._get_current_object()

    def _executar():
        with app.app_context():
            funcao(*args)

    threading.Thread(target=_executar, daemon=True).start()
