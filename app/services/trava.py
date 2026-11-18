"""Trava de execução simultânea da coleta (arquivo + flock). Cada fonte tem a própria trava.

Sem `fcntl` (Windows de desenvolvimento) não há trava: sempre concede.
"""

import os
import tempfile
from contextlib import contextmanager

try:
    import fcntl  # Linux (KingHost, Docker)
except ImportError:  # pragma: no cover - só no Windows
    fcntl = None


def _caminho(fonte: str) -> str:
    return os.path.join(tempfile.gettempdir(), f"ratual_coleta_{fonte}.lock")


@contextmanager
def trava(fonte: str = "ewelink"):
    """Entrega True se conseguiu a trava; False se outra coleta da mesma fonte já está rodando."""
    if fcntl is None:
        yield True
        return
    with open(_caminho(fonte), "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
