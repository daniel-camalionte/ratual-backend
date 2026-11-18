# -*- coding: utf-8 -*-
# PASSO 1 (temporário): descobre qual Python o servidor WSGI usa.
# Substitua o conteúdo de /home/investimentos/apps_wsgi/api.wsgi por este arquivo,
# abra a URL da aplicação e me envie o texto exibido. Depois troque pelo api.wsgi definitivo.
import os
import sys


def application(environ, start_response):
    lines = [
        "python    : %s" % sys.version.replace("\n", " "),
        "executable: %s" % sys.executable,
        "prefix    : %s" % sys.prefix,
        "cwd       : %s" % os.getcwd(),
        "user      : %s" % os.environ.get("USER", "?"),
    ]
    body = ("\n".join(lines) + "\n").encode("utf-8")
    start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8"),
                              ("Content-Length", str(len(body)))])
    return [body]
