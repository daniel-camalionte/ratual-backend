# -*- coding: utf-8 -*-
# PASSO 2 (definitivo): carrega a API Flask a partir do virtualenv.
# Copiar para /home/<USUARIO-KINGHOST>/apps_wsgi/api.wsgi e AJUSTAR `BASE` abaixo.
import os
import site
import sys

BASE = "/home/<USUARIO-KINGHOST>/apps_wsgi"  # AJUSTAR: usuário do plano na KingHost
if "<" in BASE:
    raise RuntimeError("Ajuste BASE em api.wsgi para o caminho real em /home/<usuario>/apps_wsgi")

APP_DIR = os.path.join(BASE, "api")  # onde ficam app/, scripts/, .env
VENV = os.path.join(BASE, "venv")
SITE_PACKAGES = os.path.join(
    VENV, "lib", "python%d.%d" % sys.version_info[:2], "site-packages"
)

# O venv precisa vir ANTES dos pacotes do sistema (/usr/local/lib/...), que no servidor têm
# versões antigas (ex.: typing_extensions) e quebrariam o pydantic.
# Atenção: o mod_wsgi reaproveita o mesmo processo ao recarregar este arquivo, então o sys.path
# pode já conter o venv no FIM de uma execução anterior. Por isso removemos e reinserimos sempre.
site.addsitedir(SITE_PACKAGES)  # também processa arquivos .pth
sys.path[:] = [p for p in sys.path if p not in (SITE_PACKAGES, APP_DIR)]
sys.path[0:0] = [APP_DIR, SITE_PACKAGES]
os.chdir(APP_DIR)

# Descarta módulos já carregados (versão do sistema, import que falhou antes ou código/config
# antigos), para serem reimportados do venv e do disco.
# "app" = o próprio código/configuração: sem isso, salvar o .wsgi não recarrega mudanças em app/*.py
# nem no .env (as Settings ficam em cache no módulo já importado).
_PREFIXES = (
    "app",
    "typing_extensions",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "flask_openapi3",
)
for _name in list(sys.modules):
    if any(_name == p or _name.startswith(p + ".") for p in _PREFIXES):
        del sys.modules[_name]

from app import create_app  # noqa: E402

application = create_app()
