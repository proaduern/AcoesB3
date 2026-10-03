"""Conexão com o Postgres (Neon em produção) e aplicação de migrações."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def connect(url: str | None = None) -> psycopg.Connection:
    url = url or os.environ.get("NEON_DATABASE_URL")
    if not url:
        raise RuntimeError("NEON_DATABASE_URL não definida")
    return psycopg.connect(url)


def migrate(conn: psycopg.Connection) -> list[str]:
    """Aplica, em ordem, os arquivos .sql ainda não aplicados. Retorna os aplicados."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migration ("
        " name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
    )
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migration")}
    applied = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migration (name) VALUES (%s)", (path.name,))
        applied.append(path.name)
    conn.commit()
    return applied


def get_config(conn: psycopg.Connection, key: str):
    row = conn.execute("SELECT value FROM app_config WHERE key = %s", (key,)).fetchone()
    if row is None:
        raise KeyError(f"parâmetro ausente em app_config: {key}")
    return row[0]
