"""Documentos congelados (imutáveis) não podem mudar.

Ver scripts/check_frozen.py e docs/frozen.sha256.
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args):
    return subprocess.run(  # noqa: S603 - comando fixo do próprio repositório
        [sys.executable, str(ROOT / "scripts" / "check_frozen.py"), *args],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )


def test_registry_exists():
    """Sem o registro a proteção sumiria em silêncio (ausência = "nada a verificar").

    Projetos derivados que optam por não congelar apagam este teste junto com o registro.
    """
    assert (ROOT / "docs" / "frozen.sha256").exists()


def test_frozen_documents_are_intact():
    result = run()
    assert result.returncode == 0, result.stdout
