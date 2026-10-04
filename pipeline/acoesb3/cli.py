"""Linha de comando do pipeline. Usada pelos workflows do GitHub Actions.

Exemplos:
    acoesb3 migrate
    acoesb3 cvm --doc DFP --from-year 2010 --to-year 2025
    acoesb3 cotahist --from-year 2010 --to-year 2025
    acoesb3 daily
    acoesb3 compute
    acoesb3 review list
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from decimal import Decimal

from psycopg.types.json import Jsonb

from . import compute, load, review
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


def _run_all(conn, steps) -> None:
    """Executa todas as etapas; uma falha não impede as seguintes, mas o comando falha no fim
    (o GitHub Actions então manda e-mail de falha)."""
    failed = []
    for job, fn in steps:
        try:
            _run(conn, job, fn)
        except Exception:
            log.exception("falha em %s", job)
            failed.append(job)
    if failed:
        raise SystemExit(f"etapas com falha: {', '.join(failed)}")


def cmd_cvm(conn, a) -> None:
    _run_all(
        conn,
        [
            (f"cvm_{a.doc.lower()}_{y}", lambda y=y: load.load_doc_year(conn, a.doc, y, a.force))
            for y in _years(a, "cvm.first_year", conn)
        ],
    )


def cmd_cotahist(conn, a) -> None:
    _run_all(
        conn,
        [
            (
                f"cotahist_{y}",
                lambda y=y: load.load_cotahist(conn, load.cotahist_year_url(y), a.force),
            )
            for y in _years(a, "cotahist.first_year", conn)
        ],
    )


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
    try:
        _run_all(conn, steps)
    finally:
        cmd_size(conn, a)


COMPUTE_STEPS = ("annual", "outliers", "events", "screens")


def cmd_compute(conn, a) -> None:
    """Fase 2: fatos anuais -> outliers -> eventos societários -> retratos do filtro.

    As etapas dependem umas das outras; se uma falha, as seguintes não rodam.
    """
    steps = a.step or list(COMPUTE_STEPS)
    cfg = compute.load_config(conn)
    fns = {
        "annual": lambda: compute.build_annual(conn),
        "outliers": lambda: compute.build_outliers(conn, cfg),
        "events": lambda: compute.detect_events(conn, cfg),
        "screens": lambda: compute.build_screens(conn, cfg),
    }
    for step in COMPUTE_STEPS:
        if step in steps:
            _run(conn, f"compute_{step}", fns[step])


def cmd_review(conn, a) -> None:
    r = a.review_cmd
    if r == "list":
        p = review.pending(conn)
        print("Proventos suspeitos (sem decisão ficam FORA do histórico):")
        for cvm, name, ref, total, med, ratio, dec in p["outliers"][: a.limit]:
            print(
                f"  {cvm:>6} {name[:32]:32} {ref} total={total:,.0f} mediana={med:,.0f}"
                f" x{ratio:.1f} -> {dec or 'pendente'}"
            )
        print("Eventos societários detectados (suspected só vale depois de confirmar):")
        for eid, tk, d, f, ratio, dis, st in p["events"][: a.limit]:
            print(f"  id={eid:<6} {tk:8} {d} fator={f} razão={ratio} DISMES mudou={dis} -> {st}")
    elif r == "outlier":
        review.decide_outlier(conn, a.cvm, a.date, a.decision, a.note)
    elif r == "event":
        review.decide_event(conn, a.id, a.decision)
    elif r == "event-add":
        review.add_event(conn, a.ticker, a.date, Decimal(a.factor), a.note)
    elif r == "dividend":
        review.set_dividends(
            conn, a.cvm, a.date, Decimal(a.jcp), Decimal(a.dividends), a.source, a.note
        )
    elif r == "dividend-clear":
        review.clear_dividends(conn, a.cvm, a.date)
    elif r == "class":
        review.set_class(conn, a.cvm, a.sector, a.plan, a.note)
    elif r == "ticker":
        review.set_ticker_root(conn, a.root, a.cvm, a.note)


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
    cp = sub.add_parser("compute", help="indicadores, outliers, eventos e filtro (fase 2)")
    cp.add_argument("--step", action="append", choices=COMPUTE_STEPS)
    rv = sub.add_parser("review", help="revisão manual (outliers, eventos, correções)")
    rs = rv.add_subparsers(dest="review_cmd", required=True)
    rl = rs.add_parser("list")
    rl.add_argument("--limit", type=int, default=100, help="linhas por seção")
    x = rs.add_parser("outlier")
    x.add_argument("--cvm", type=int, required=True)
    x.add_argument("--date", type=date.fromisoformat, required=True, help="data-base da DFP")
    x.add_argument("--decision", choices=["include", "exclude", "reset"], required=True)
    x.add_argument("--note")
    x = rs.add_parser("event")
    x.add_argument("--id", type=int, required=True)
    x.add_argument("--decision", choices=["confirm", "reject", "reset"], required=True)
    x = rs.add_parser("event-add")
    x.add_argument("--ticker", required=True)
    x.add_argument("--date", type=date.fromisoformat, required=True)
    x.add_argument("--factor", required=True, help="ações novas / antigas (2 = desdobra 1:2)")
    x.add_argument("--note")
    x = rs.add_parser("dividend")
    x.add_argument("--cvm", type=int, required=True)
    x.add_argument("--date", type=date.fromisoformat, required=True, help="data-base da DFP")
    x.add_argument("--jcp", required=True, help="R$ brutos")
    x.add_argument("--dividends", required=True, help="R$ brutos")
    x.add_argument("--source", default="manual")
    x.add_argument("--note")
    x = rs.add_parser("dividend-clear")
    x.add_argument("--cvm", type=int, required=True)
    x.add_argument("--date", type=date.fromisoformat, required=True)
    x = rs.add_parser("class")
    x.add_argument("--cvm", type=int, required=True)
    x.add_argument("--sector")
    x.add_argument("--plan", choices=["comum", "banco", "seguradora"])
    x.add_argument("--note")
    x = rs.add_parser("ticker")
    x.add_argument("--root", required=True)
    x.add_argument("--cvm", type=int, required=True)
    x.add_argument("--note")
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
        elif a.cmd == "compute":
            cmd_compute(conn, a)
        elif a.cmd == "review":
            cmd_review(conn, a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
