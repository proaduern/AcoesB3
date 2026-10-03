"""Linha de comando do pipeline. Usada pelos workflows do GitHub Actions.

Exemplos:
    acoesb3 migrate
    acoesb3 cvm --doc DFP --from-year 2010 --to-year 2025
    acoesb3 cotahist --from-year 2010 --to-year 2025
    acoesb3 daily
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta

from psycopg.types.json import Jsonb

from . import load
from .db import connect, get_config, migrate

log = logging.getLogger("acoesb3")


def _run(conn, job: str, fn):
    run_id = conn.execute(
        "INSERT INTO collection_run (job) VALUES (%s) RETURNING id", (job,)
    ).fetchone()[0]
    conn.commit()
    try:
        detail = fn()
    except Exception as e:
        conn.rollback()
        conn.execute(
            "UPDATE collection_run SET status = 'failed', finished_at = now(), detail = %s"
            " WHERE id = %s",
            (Jsonb({"error": repr(e)}), run_id),
        )
        conn.commit()
        raise
    conn.execute(
        "UPDATE collection_run SET status = 'ok', finished_at = now(), detail = %s WHERE id = %s",
        (Jsonb(detail), run_id),
    )
    conn.commit()
    log.info("%s: %s", job, json.dumps(detail, default=str, ensure_ascii=False))
    return detail


def _years(a, first_key, conn) -> range:
    start = a.from_year or int(get_config(conn, first_key))
    end = a.to_year or date.today().year
    return range(start, end + 1)


def cmd_cvm(conn, a) -> None:
    for year in _years(a, "cvm.first_year", conn):
        _run(
            conn,
            f"cvm_{a.doc.lower()}_{year}",
            lambda y=year: load.load_doc_year(conn, a.doc, y, a.force),
        )


def cmd_cotahist(conn, a) -> None:
    for year in _years(a, "cotahist.first_year", conn):
        url = load.cotahist_year_url(year)
        _run(conn, f"cotahist_{year}", lambda u=url: load.load_cotahist(conn, u, a.force))


def recent_weekdays(today: date, n: int) -> list[date]:
    days, d = [], today
    while len(days) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            days.append(d)
    return sorted(days)


def cmd_daily(conn, a) -> None:
    """Coleta diária: cadastro, documentos do ano corrente e anterior, cotações recentes.

    Uma etapa com erro não impede as demais; no fim, qualquer erro faz o comando falhar
    (o GitHub Actions então manda e-mail de falha).
    """
    today = date.today()
    steps = [("cvm_cad", lambda: load.load_cad(conn))]
    for doc in ("FCA", "DFP", "ITR"):
        for year in (today.year - 1, today.year):
            steps.append(
                (f"cvm_{doc.lower()}_{year}", lambda d=doc, y=year: load.load_doc_year(conn, d, y))
            )
    lookback = int(get_config(conn, "collect.daily_lookback_days"))
    for day in recent_weekdays(today, lookback):
        url = load.cotahist_day_url(day)
        steps.append((f"cotahist_{day:%Y%m%d}", lambda u=url: load.load_cotahist(conn, u)))
    failed = []
    for job, fn in steps:
        try:
            _run(conn, job, fn)
        except Exception:
            log.exception("falha em %s", job)
            failed.append(job)
    cmd_size(conn, a)
    if failed:
        raise SystemExit(f"etapas com falha: {', '.join(failed)}")


def cmd_size(conn, a) -> None:
    report = load.size_report(conn)
    mb = report["database_bytes"] / 1024 / 1024
    print(f"Tamanho do banco: {mb:.1f} MB")
    for name, size, rows in report["tables"]:
        rows_txt = f"~{rows} linhas" if rows >= 0 else "sem estatística"
        print(f"  {name:20} {size / 1024 / 1024:8.1f} MB  {rows_txt}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="acoesb3")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("cad")
    c = sub.add_parser("cvm")
    c.add_argument("--doc", required=True, choices=["DFP", "ITR", "FCA"])
    for s in (c, sub.add_parser("cotahist")):
        s.add_argument("--from-year", type=int)
        s.add_argument("--to-year", type=int)
        s.add_argument("--force", action="store_true", help="reprocessa mesmo sem mudança")
    sub.add_parser("daily")
    sub.add_parser("size")
    a = p.parse_args(argv)

    with connect() as conn:
        applied = migrate(conn)
        if applied:
            log.info("migrações aplicadas: %s", applied)
        if a.cmd == "cad":
            _run(conn, "cvm_cad", lambda: load.load_cad(conn, force=True))
        elif a.cmd == "cvm":
            cmd_cvm(conn, a)
        elif a.cmd == "cotahist":
            cmd_cotahist(conn, a)
        elif a.cmd == "daily":
            cmd_daily(conn, a)
        elif a.cmd == "size":
            cmd_size(conn, a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
