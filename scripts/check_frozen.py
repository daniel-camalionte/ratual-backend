"""Garante que documentos CONGELADOS (imutáveis) não foram alterados, removidos ou renomeados.

    python scripts/check_frozen.py                       # confere todos (usado por teste e hook)
    python scripts/check_frozen.py --add docs/ALGO_v2.md   # congela um documento NOVO

O registro fica em `docs/frozen.sha256` (formato `<sha256>  <caminho>`). O hash é calculado após
normalizar as quebras de linha para LF, então não muda entre Windows e Linux.

Congelar é um ato deliberado: --add recusa sobrescrever um arquivo já congelado. Para mudar um
documento congelado, crie uma NOVA versão (v2) e congele-a; a v1 permanece como está.
Se `docs/frozen.sha256` não existir, nada é verificado (projeto derivado sem congelamento).
"""

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "docs" / "frozen.sha256"


def digest(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def read_registry() -> dict:
    entries = {}
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            sha, _, rel = line.partition("  ")
            entries[rel.strip()] = sha.strip()
    return entries


def check() -> int:
    if not REGISTRY.exists():
        print("Nenhum documento congelado (docs/frozen.sha256 ausente): nada a verificar.")
        return 0
    problems = 0
    entries = read_registry()
    for rel, expected in sorted(entries.items()):
        path = ROOT / rel
        if not path.exists():
            print(f"CONGELADO REMOVIDO/RENOMEADO: {rel}")
            problems += 1
        elif digest(path) != expected:
            print(f"CONGELADO ALTERADO: {rel}")
            problems += 1
    if problems:
        print(
            "\nEsses documentos são imutáveis (referência da base de projetos futuros).\n"
            "Desfaça a alteração (git checkout -- <arquivo>). Para evoluir o conteúdo,\n"
            "crie uma nova\n"
            "versão (v2) e registre-a com: python scripts/check_frozen.py --add <arquivo>."
        )
        return 1
    print(f"OK: {len(entries)} documento(s) congelado(s) intacto(s).")
    return 0


def add(rel: str) -> int:
    path = (ROOT / rel).resolve()
    if not path.is_file() or ROOT not in path.parents:
        print(f"ERRO: arquivo inexistente ou fora do projeto: {rel}")
        return 1
    key = path.relative_to(ROOT).as_posix()
    entries = read_registry() if REGISTRY.exists() else {}
    if key in entries:
        print(f"ERRO: {key} já está congelado e não pode ser recongelado.")
        return 1
    entries[key] = digest(path)
    header = "# Documentos congelados (imutáveis). Gerado por scripts/check_frozen.py --add.\n"
    body = "".join(f"{sha}  {name}\n" for name, sha in sorted(entries.items()))
    REGISTRY.parent.mkdir(exist_ok=True)
    REGISTRY.write_bytes((header + body).encode("utf-8"))  # bytes: sempre LF (3.9 não tem newline=)
    print(f"Congelado: {key}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--add", metavar="ARQUIVO", help="congela um documento novo")
    args = parser.parse_args()
    return add(args.add) if args.add else check()


if __name__ == "__main__":
    sys.exit(main())
