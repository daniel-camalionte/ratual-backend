"""Gera `dist/` para envio (FTP) à KingHost e mostra o que mudou desde o último pacote.

    python scripts/package.py

Saída:
    dist/api/            conteúdo para enviar a /apps_wsgi/<app>/   (app, scripts, migrations, ...)
    dist/api.final.wsgi  conteúdo para /apps_wsgi/<app>.wsgi
    dist/api.diagnostic.wsgi  (opcional) mostra o Python do servidor; usar antes do definitivo
    dist/manifest.json   hashes do pacote (usado para listar as mudanças da próxima vez)

Nunca inclui .env, .venv, tests, .git nem __pycache__.
"""

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP_DIR = DIST / "api"

INCLUDE_DIRS = ["app", "scripts"]
INCLUDE_FILES = ["wsgi.py", "requirements.txt"]
WSGI_SOURCE = ROOT / "deploy" / "kinghost" / "api.wsgi"
WSGI_TARGET = "api.final.wsgi"
DIAGNOSTIC_SOURCE = ROOT / "deploy" / "kinghost" / "api.diagnostic.wsgi"
DIAGNOSTIC_TARGET = "api.diagnostic.wsgi"
SKIP_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", "local"}
SKIP_SUFFIXES = {".pyc", ".pyo"}
# nunca vão para o servidor, mesmo que estejam dentro de uma pasta incluída
SKIP_NAMES = {
    ".env",
    ".gitkeep",
    "package.py",
    "init_project.py",
    "check_frozen.py",
}  # ferramentas só de desenvolvimento


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect() -> dict:
    files = {}
    for name in INCLUDE_DIRS:
        for p in sorted((ROOT / name).rglob("*")):
            rel = p.relative_to(ROOT)
            if not p.is_file() or SKIP_PARTS & set(rel.parts):
                continue
            if p.suffix in SKIP_SUFFIXES or p.name in SKIP_NAMES or p.name.startswith(".env"):
                continue
            files[f"api/{rel.as_posix()}"] = p
    for name in INCLUDE_FILES:
        files[f"api/{name}"] = ROOT / name
    files[WSGI_TARGET] = WSGI_SOURCE
    files[DIAGNOSTIC_TARGET] = DIAGNOSTIC_SOURCE
    return files


def main() -> int:
    files = collect()
    missing = [k for k, p in files.items() if not p.exists()]
    if missing:
        print("ERRO: arquivos ausentes:", ", ".join(missing))
        return 1

    old = {}
    manifest_path = DIST / "manifest.json"
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text(encoding="utf-8"))

    if DIST.exists():
        shutil.rmtree(DIST)
    new = {}
    for rel, src in files.items():
        dest = DIST / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        new[rel] = sha(src)
    # identificador do pacote: aparece no cabeçalho X-Build, para conferir o que está no ar
    try:
        commit = subprocess.run(  # noqa: S603 - comando fixo
            [shutil.which("git") or "git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except OSError:
        commit = ""
    build = f"{datetime.now():%Y%m%d-%H%M%S}-{commit or 'semgit'}"
    (DIST / "api" / "app" / "BUILD").write_text(build + "\n", encoding="utf-8")
    new["api/app/BUILD"] = hashlib.sha256((build + "\n").encode()).hexdigest()
    manifest_path.write_text(json.dumps(new, indent=1, sort_keys=True), encoding="utf-8")

    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(k for k in new if k in old and new[k] != old[k])

    print(f"Pacote gerado em: {DIST}  ({len(new)} arquivos)")
    print(f"Identificador do pacote (X-Build): {build}\n")
    if not old:
        print("Primeiro pacote: envie tudo.")
    elif not (added or removed or changed):
        print("Nada mudou desde o último pacote.")
    else:
        for title, items in (("NOVOS", added), ("ALTERADOS", changed), ("REMOVIDOS", removed)):
            if items:
                print(f"{title} ({len(items)}):")
                for k in items:
                    print(f"  {k}")
        print("\nEnvie os NOVOS e ALTERADOS (e apague os REMOVIDOS no servidor).")
    print(
        "\nLembretes: requirements.txt alterado => `pip install -r requirements.txt` no servidor;"
        "\n           migrations/ (quando existir) alterado => `python -m alembic upgrade head`;"
        "\n           api.final.wsgi alterado => copie para /apps_wsgi/<app>.wsgi."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
