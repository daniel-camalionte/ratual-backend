"""Aplica as migrações SQL de `migrations/sql/` (em ordem) no banco do ambiente escolhido.

    RATUAL_ENV=stg python scripts/migrar.py        # STG (padrão local)
    RATUAL_ENV=prd python scripts/migrar.py        # PRODUÇÃO

Registra o que já foi aplicado em `migracao_aplicada`. Se o banco já tem a estrutura vinda do Brain
(tabela `usuario`) e nada está registrado, as migrações 001-012 entram como já aplicadas (baseline).
Os arquivos devem ser idempotentes (IF NOT EXISTS). Não imprime segredos.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from app.config import get_settings  # noqa: E402

BASELINE_ATE = "012"


def statements(sql: str) -> list[str]:
    linhas = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(linhas).split(";") if s.strip()]


def main() -> int:
    s = get_settings()
    if not s.database_configured:
        print("Banco não configurado.")
        return 1
    print(f"Ambiente: {s.app_env} | banco: {s.mysql_db_name}@{s.mysql_db_hostname}")
    engine = create_engine(s.sqlalchemy_url, pool_pre_ping=True)
    arquivos = sorted(Path(__file__).resolve().parent.parent.glob("migrations/sql/*.sql"))
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS migracao_aplicada ("
                " arquivo VARCHAR(120) NOT NULL PRIMARY KEY,"
                " aplicada_em DATETIME NOT NULL DEFAULT UTC_TIMESTAMP())"
                " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"
            )
        )
        feitas = {r[0] for r in conn.execute(text("SELECT arquivo FROM migracao_aplicada"))}
        tem_estrutura = conn.execute(text("SHOW TABLES LIKE 'usuario'")).first() is not None
        if not feitas and tem_estrutura:
            for a in arquivos:
                if a.name[:3] <= BASELINE_ATE:
                    conn.execute(text("INSERT INTO migracao_aplicada (arquivo) VALUES (:a)"), {"a": a.name})
                    feitas.add(a.name)
            print(f"Baseline: {len(feitas)} migrações do Brain marcadas como aplicadas.")
        for a in arquivos:
            if a.name in feitas:
                continue
            for stmt in statements(a.read_text(encoding="utf-8")):
                conn.exec_driver_sql(stmt.replace("%", "%%"))
            conn.execute(text("INSERT INTO migracao_aplicada (arquivo) VALUES (:a)"), {"a": a.name})
            print(f"Aplicada: {a.name}")
    print("Migrações em dia.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
