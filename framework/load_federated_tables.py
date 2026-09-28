#!/usr/bin/env python3
"""
Load the per-table CSVs in datasets/raw_tables/ into the federated stack.

Facts (postgresql.public.*) come from datasets/raw_tables/postgresql/;
dimensions (mysql.bcdr_framework.*) come from datasets/raw_tables/mysql/.
Table and column names are read from the CSV headers, so this needs no schema
file and stays correct if a source is re-exported.

Connection settings come from the environment, with the docker-compose defaults:

    POSTGRES_HOST  POSTGRES_PORT  POSTGRES_DB  POSTGRES_USER  POSTGRES_PASSWORD
    MARIADB_HOST   MARIADB_PORT   MARIADB_DB   MARIADB_USER   MARIADB_PASSWORD

Usage:
    python3 framework/load_federated_tables.py
    python3 framework/load_federated_tables.py --verify     # also print row counts
"""
import argparse
import csv
import gzip
import os
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = Path(os.environ.get("RAW_TABLES_DIR", HERE.parent / "datasets" / "raw_tables"))

PG = dict(
    host=os.environ.get("POSTGRES_HOST", "127.0.0.1"),
    port=int(os.environ.get("POSTGRES_PORT", 5432)),
    dbname=os.environ.get("POSTGRES_DB", os.environ.get("POSTGRES_DB_FRAMEWORK", "framework_data")),
    user=os.environ.get("POSTGRES_USER", "framework"),
    password=os.environ.get("POSTGRES_PASSWORD", "framework"),
)
MY = dict(
    host=os.environ.get("MARIADB_HOST", "127.0.0.1"),
    port=int(os.environ.get("MARIADB_PORT", 3306)),
    user=os.environ.get("MARIADB_USER", "framework"),
    password=os.environ.get("MARIADB_PASSWORD", "framework"),
    database=os.environ.get("MARIADB_DB", "bcdr_framework"),
)

# Values are loaded as text and the engine casts on use. That keeps the load
# faithful to the source files: no silent numeric coercion or date re-formatting.
TEXT = "text"


def _read_header(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", newline="", encoding="utf-8", errors="replace") as fh:
        return next(csv.reader(fh))


def _table_files(subdir: str):
    """CSVs under raw_tables/<subdir>, accepting .csv and .csv.gz.

    If both forms of the same table are present, the plain .csv wins, so a
    directory holding an archive and its expansion does not load twice.
    """
    base = RAW / subdir

    def table_key(p: Path) -> str:
        return p.name[:-7] if p.name.endswith(".csv.gz") else p.name[:-4]

    chosen = {}
    for p in sorted(list(base.rglob("*.csv.gz")) + list(base.rglob("*.csv"))):
        if not p.name.endswith((".csv", ".csv.gz")):
            continue
        key = table_key(p)
        # a plain .csv replaces a previously chosen .gz, never the reverse
        if key not in chosen or not p.name.endswith(".gz"):
            chosen[key] = p
    return [chosen[k] for k in sorted(chosen)]


def load_postgres():
    import psycopg2
    conn = psycopg2.connect(**PG)
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("CREATE SCHEMA IF NOT EXISTS public")
    total = 0
    files = _table_files("postgresql")
    if not files:
        sys.exit(f"no CSVs found under {RAW / 'postgresql'}\n"
                 "  fetch them first:  python3 tools/fetch_datasets.py")
    for path in files:
        table = path.stem
        cols = _read_header(path)
        cur.execute(f'DROP TABLE IF EXISTS public."{table}" CASCADE')
        cur.execute(
            f'CREATE TABLE public."{table}" (' +
            ", ".join(f'"{c}" {TEXT}' for c in cols) + ")"
        )
        # copy_from streams the file straight in; the handle is positioned just
        # past the header line so it is not loaded as a data row.
        fh = _skip_header(path)
        try:
            cur.copy_from(fh, f'"{table}"', sep=",", null="")
        finally:
            _cleanup(fh)
        cur.execute(f'SELECT count(*) FROM public."{table}"')
        n = cur.fetchone()[0]
        total += n
        print(f"  postgresql.public.{table:<24} {n:>9,} rows")
    conn.close()
    return total


def _skip_header(path: Path):
    """Return a readable handle positioned just after the header line.

    A .csv.gz is decompressed to a temporary file first, because copy_from and
    the MariaDB reader both need a seekable text stream.
    """
    if path.suffix == ".gz":
        tmp = tempfile.NamedTemporaryFile("wb", suffix=".csv", delete=False)
        with gzip.open(path, "rb") as src:
            shutil.copyfileobj(src, tmp)
        tmp.close()
        fh = open(tmp.name, "r", newline="", encoding="utf-8", errors="replace")
        fh.__dict__["_tmpname"] = tmp.name      # so callers can clean up
    else:
        fh = path.open(newline="", encoding="utf-8", errors="replace")
    fh.readline()
    return fh


def _cleanup(fh):
    name = fh.__dict__.pop("_tmpname", None)
    fh.close()
    if name:
        try:
            os.unlink(name)
        except OSError:
            pass


def load_mariadb():
    import mysql.connector
    conn = mysql.connector.connect(**MY)
    cur = conn.cursor()
    cur.execute(f"CREATE DATABASE IF NOT EXISTS `{MY['database']}`")
    cur.execute(f"USE `{MY['database']}`")
    total = 0
    files = _table_files("mysql")
    if not files:
        sys.exit(f"no CSVs found under {RAW / 'mysql'}\n"
                 "  fetch them first:  python3 tools/fetch_datasets.py")
    for path in files:
        table = path.name[:-4] if path.name.endswith(".csv") else path.name[:-7]
        cols = _read_header(path)
        cur.execute(f"DROP TABLE IF EXISTS `{table}`")
        cur.execute(
            f"CREATE TABLE `{table}` (" +
            ", ".join(f"`{c}` TEXT" for c in cols) + ")"
        )
        fh = _skip_header(path)
        reader = csv.reader(fh)
        chunk, n = [], 0
        for row in reader:
            chunk.append(row)
            if len(chunk) >= 5000:
                cur.executemany(
                    f"INSERT INTO `{table}` VALUES (" +
                    ",".join(["%s"] * len(cols)) + ")", chunk)
                n += len(chunk); chunk = []
        if chunk:
            cur.executemany(
                f"INSERT INTO `{table}` VALUES (" +
                ",".join(["%s"] * len(cols)) + ")", chunk)
            n += len(chunk)
        _cleanup(fh)
        conn.commit()
        total += n
        print(f"  mysql.{MY['database']}.{table:<20} {n:>9,} rows")
    conn.close()
    return total


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true",
                    help="print row counts after loading")
    args = ap.parse_args()

    print(f"raw tables: {RAW}")
    print("\nloading facts into PostgreSQL")
    pg_total = load_postgres()
    print("\nloading dimensions into MariaDB")
    my_total = load_mariadb()

    print(f"\ntotal: {pg_total + my_total:,} rows "
          f"({pg_total:,} postgresql + {my_total:,} mariadb)")
    if not args.verify:
        print("\nnext: ./reproduce.sh   (asserts every gold query executes)")


if __name__ == "__main__":
    main()
