"""Diagnóstico do ambiente (usa só a biblioteca padrão). Rode no servidor via SSH:

    python scripts/check_env.py

Informa versão do Python, arquitetura, glibc e se as dependências importam corretamente.
"""

import importlib
import importlib.metadata as md
import os
import platform
import sys

# módulo -> nome da distribuição no PyPI
DEPENDENCIES = {
    "flask": "flask",
    "flask_cors": "flask-cors",
    "flask_limiter": "flask-limiter",
    "orjson": "orjson",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "flask_openapi3": "flask-openapi3",
    "flask_openapi3_swagger": "flask-openapi3-swagger",
}


def main() -> int:
    print(f"python       : {sys.version.split()[0]} ({sys.executable})")
    print(f"plataforma   : {platform.platform()}")
    print(f"arquitetura  : {platform.machine()} / {platform.architecture()[0]}")
    print(f"libc         : {' '.join(platform.libc_ver())}")
    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    print(f"virtualenv   : {'sim' if in_venv else 'NAO'}")
    print(f"diretório    : {os.getcwd()} (gravável: {os.access('.', os.W_OK)})")
    if sys.version_info < (3, 9):  # noqa: UP036 - diagnóstico explícito
        print("ERRO: é necessário Python >= 3.9")
        return 1

    failed = 0
    for name, dist in DEPENDENCIES.items():
        try:
            importlib.import_module(name)
            print(f"  ok   {dist} {md.version(dist)}")
        except Exception as exc:  # noqa: BLE001 - diagnóstico: queremos mostrar qualquer falha
            failed += 1
            print(f"  FALHA {name}: {exc}")

    if not failed:
        try:
            from app import create_app

            create_app()
            print("  ok   create_app() inicializa")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FALHA create_app(): {exc}")
    print("RESULTADO:", "tudo certo" if not failed else f"{failed} problema(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raise SystemExit(main())
