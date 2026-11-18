"""Copia estrutura e dados de um banco MySQL/MariaDB para outro (carga inicial Brain -> Ratual).

Uso:
    python scripts/copiar_banco.py ORIGEM.env DESTINO.env [--yes]

Os .env precisam das chaves MYSQL_DB_*. Recusa-se a escrever se o destino ja tiver tabelas
(evita sobrescrever dados por engano). Nao imprime segredos.
"""
import re
import sys

import pymysql

BATCH = 1000


def load(path):
    d = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^\s*([A-Z0-9_]+)\s*=(.*)$", line.rstrip("\n"))
            if m:
                d[m.group(1)] = m.group(2).strip()
    return d


def connect(e):
    return pymysql.connect(
        host=e["MYSQL_DB_HOSTNAME"], user=e["MYSQL_DB_USER"], password=e["MYSQL_DB_PASSWORD"],
        database=e["MYSQL_DB_NAME"], port=int(e.get("MYSQL_DB_PORT", 3306)), charset="utf8mb4",
        connect_timeout=15, autocommit=False,
    )


def main(src_path, dst_path):
    src, dst = connect(load(src_path)), connect(load(dst_path))
    s, d = src.cursor(), dst.cursor()

    d.execute("select count(*) from information_schema.tables where table_schema=database()")
    if d.fetchone()[0] != 0:
        sys.exit("Destino nao esta vazio: abortando para nao sobrescrever dados.")

    s.execute("select table_name, table_type from information_schema.tables where table_schema=database() order by 1")
    objs = s.fetchall()
    tables = [t for t, ty in objs if ty == "BASE TABLE"]
    views = [t for t, ty in objs if ty != "BASE TABLE"]

    d.execute("SET FOREIGN_KEY_CHECKS=0")
    d.execute("SET sql_mode=''")
    for t in tables:
        s.execute(f"SHOW CREATE TABLE `{t}`")
        d.execute(s.fetchone()[1])
    for v in views:
        s.execute(f"SHOW CREATE VIEW `{v}`")
        d.execute(s.fetchone()[1])
    dst.commit()

    for t in tables:
        s.execute(f"select * from `{t}`")
        cols = [c[0] for c in s.description]
        sql = f"insert into `{t}` ({','.join('`'+c+'`' for c in cols)}) values ({','.join(['%s']*len(cols))})"
        total = 0
        while True:
            rows = s.fetchmany(BATCH)
            if not rows:
                break
            d.executemany(sql, rows)
            total += len(rows)
        dst.commit()
        print(f"{t:30s} {total}")
    d.execute("SET FOREIGN_KEY_CHECKS=1")

    # confere contagens
    bad = 0
    for t in tables:
        s.execute(f"select count(*) from `{t}`")
        d.execute(f"select count(*) from `{t}`")
        a, b = s.fetchone()[0], d.fetchone()[0]
        if a != b:
            bad += 1
            print(f"DIVERGENTE {t}: origem={a} destino={b}")
    print("OK: contagens conferem" if not bad else f"{bad} tabela(s) divergente(s)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
