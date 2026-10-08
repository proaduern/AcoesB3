"""Linha de comando do pipeline. Usada pelos workflows do GitHub Actions.

Exemplos:
    acoesb3 migrate
    acoesb3 cvm --doc DFP --from-year 2010 --to-year 2025
    acoesb3 cotahist --from-year 2010 --to-year 2025
    acoesb3 daily
    acoesb3 compute
    acoesb3 review list
    acoesb3 backtest run
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from decimal import Decimal

from psycopg.types.json import Jsonb

from . import backtest_run, compute, load, review, watch
from .db import connect, get_config, migrate

log = logging.getLogger("acoesb3")


def _dumps(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)


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
            (Jsonb({"error": repr(e)}, dumps=_dumps), run_id),
        )
        conn.commit()
        raise
    conn.execute(
        "UPDATE collection_run SET status = 'ok', finished_at = now(), detail = %s WHERE id = %s",
        (Jsonb(detail, dumps=_dumps), run_id),
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


COMPUTE_STEPS = ("annual", "outliers", "events", "screens", "ceilings")


def cmd_compute(conn, a) -> None:
    """Fases 2 e 3: fatos anuais -> outliers -> eventos societários -> retratos do filtro ->
    preço teto da lista acompanhada.

    As etapas dependem umas das outras; se uma falha, as seguintes não rodam.
    """
    steps = a.step or list(COMPUTE_STEPS)
    cfg = compute.load_config(conn)
    fns = {
        "annual": lambda: compute.build_annual(conn),
        "outliers": lambda: compute.build_outliers(conn, cfg),
        "events": lambda: {
            **compute.detect_events(conn, cfg),
            **compute.build_company_events(conn, cfg),
        },
        "screens": lambda: compute.build_screens(conn, cfg),
        "ceilings": lambda: compute.build_ceilings(conn, cfg, a.as_of),
    }
    for step in COMPUTE_STEPS:
        if step in steps:
            _run(conn, f"compute_{step}", fns[step])


def cmd_review(conn, a) -> None:
    r = a.review_cmd
    if r == "list" and a.priority:
        rows = review.priority(conn)
        print(
            f"{len(rows)} outliers sem decisão que mudam um resultado (aprovadas primeiro, depois"
            " por volume negociado):"
        )
        for cvm, name, ref, total, med, ratio, dva, fre, st, check in rows[: a.limit]:
            fmt = lambda v: "-" if v is None else f"{v:,.0f}"  # noqa: E731
            print(
                f"  {cvm:>6} {name[:30]:30} {ref} [{st}] total={fmt(total)} mediana={fmt(med)}"
                f" x{ratio:.1f} | DVA={fmt(dva)} FRE={fmt(fre)} -> {check}: {review.HINTS[check]}"
            )
    elif r == "list":
        p = review.pending(conn)
        print("Proventos suspeitos (sem decisão ficam FORA do histórico):")
        for cvm, name, ref, total, med, ratio, dec in p["outliers"][: a.limit]:
            print(
                f"  {cvm:>6} {name[:32]:32} {ref} total={total:,.0f} mediana={med:,.0f}"
                f" x{ratio:.1f} -> {dec or 'pendente'}"
            )
        print("Proventos a lançar à mão (DVA zerada depois de o FRE mostrar pagamentos):")
        for cvm, name, years in p["dividends_to_enter"][: a.limit]:
            print(f"  {cvm:>6} {name[:40]:40} exercícios {', '.join(map(str, years))}")
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
    elif r == "dcf-growth":
        if a.growth is None and not a.clear:
            raise SystemExit("informe --growth ou --clear")
        review.set_dcf_growth(conn, a.cvm, None if a.clear else Decimal(a.growth), a.note)


def cmd_watch(conn, a) -> None:
    w = a.watch_cmd
    if w == "find":
        for text in a.name:
            print(f"== {text}")
            for cvm, name, st, sector, screen, as_of in watch.find(conn, text):
                print(
                    f"  {cvm:>6} {name[:44]:44} CVM={st} setor={sector} filtro={screen} ({as_of})"
                )
    elif w == "add":
        watch.add(conn, a.cvm, a.role, a.segment, a.note)
    elif w == "remove":
        watch.remove(conn, a.cvm)
    elif w == "list":
        for role, seg, cvm, name, st in watch.listing(conn):
            print(f"  {role:8} {seg:12} {cvm:>6} {name[:44]:44} filtro={st}")
    elif w == "explain":
        for cvm in a.cvm:
            e = watch.explain(conn, cvm)
            print(f"== {cvm} retrato de {e['as_of']}")
            for crit, st, value, thr, detail in e["criteria"]:
                print(f"  {crit}: {st} valor={value} limite={thr}")
                if crit == "queda_dividendo_por_acao":
                    print("    ", json.dumps(detail, ensure_ascii=False, default=str))
            print("  ano | total DVA/manual | total FRE | fonte | ações ON | ações PN | nota")
            for ref, tot, fre, src, on, pn, note in e["annual"]:
                print(f"  {ref} | {tot} | {fre} | {src} | {on} | {pn} | {note or ''}")
            print("  eventos: data | fator | origem | base da data | tipo | antes | depois")
            for ev in e["events"]:
                print("  ", " | ".join(str(x) for x in ev))
    elif w == "candidates":
        for seg, rows in watch.candidates(conn, a.per_segment).items():
            print(f"== {seg}")
            for cvm, name, _sector, st, vol, issues, fails in rows:
                print(
                    f"  {cvm:>6} {name[:40]:40} {st:20} volume={vol or 0:,.0f}"
                    f" reprovados={fails} {issues}"
                )


BANDS_PT = {
    "strong_buy": "compra forte",
    "buy": "compra",
    "hold": "manter",
    "expensive": "cara, avaliar venda",
}


def _print_fcfe(inputs: dict) -> None:
    """Por exercício: o FCFE e as contas do DFC em cada grupo (para conferir a classificação)."""
    for year, d in sorted((inputs.get("fcfe_detail") or {}).items()):
        print(
            f"       {year}: FCFE={d['fcfe']} = operacional {d['cfo']} + capex {d['capex']}"
            f" + dividendos recebidos {d['inflow']} + dívida {d['debt']}"
            + (f" [{d['reason']}]" if d.get("reason") else "")
        )
        for kind in ("capex", "inflow", "debt", "excluded"):
            for code, desc, value in d["lines"].get(kind, []):
                if Decimal(value) != 0:
                    print(f"           {kind:8} {code:8} {desc[:70]:70} {Decimal(value):>18,.0f}")
    for key in ("base", "g_raw", "g", "growth_source", "equity_value"):
        if key in inputs:
            print(f"       {key} = {inputs[key]}")


def cmd_ceilings(conn, a) -> None:
    rep = watch.ceilings(conn, a.cvm)
    if rep["as_of"] is None:
        print("Nenhum preço teto calculado: rode `acoesb3 compute --step ceilings`.")
        return
    print(f"Preço teto em {rep['as_of']} (valores por ação, na base de ações dessa data)")
    for c in rep["companies"]:
        ceil_ = "indisponível" if c["ceiling"] is None else f"{c['ceiling']:.2f}"
        k = "-" if c["k"] is None else c["k"]
        print(
            f"== {c['cvm']} {c['name']} [{c['plan']}] teto={ceil_} métodos={c['methods_ok']} K={k}"
            f" ({'dados insuficientes' if c['status'] == 'insufficient' else 'ok'})"
            f" exercício={c['data_base']}"
        )
        for method, st, value, reason, inputs in c["methods"]:
            shown = f"{value:.2f}" if value is not None else f"{st}: {reason}"
            print(f"     {method:10} {shown}")
            if method == "dcf" and a.dcf:
                _print_fcfe(inputs)
        for tk, kind, price, pdate, ceil_, ratio, band, votes, kreq, buy, why in c["classes"]:
            if ceil_ is None:
                print(f"   {tk:8} {kind:4} preço={price:.2f} ({pdate}) sem teto: {why}")
                continue
            print(
                f"   {tk:8} {kind:4} preço={price:.2f} ({pdate}) teto={ceil_:.2f}"
                f" {ratio:.0%} {BANDS_PT[band]} votos={votes}/{kreq} {'COMPRA' if buy else ''}"
            )


def _pct(v) -> str:
    return "n/d" if v is None else f"{float(v):.1%}"


def _print_segment(seg: dict) -> None:
    print(f"   período {seg['start']} a {seg['end']}")
    for name in ("strategy_net", "strategy_gross", "idiv", "ibov", "cdi"):
        st = seg["series"].get(name)
        if not st:
            print(f"   {name:15} indisponível")
            continue
        print(
            f"   {name:15} retorno={_pct(st['total_return'])} a.a.={_pct(st['cagr'])}"
            f" queda máx={_pct(st['max_drawdown'])} vol={_pct(st['volatility'])}"
        )
    for ref, w in seg["windows"].items():
        print(
            f"   janelas vs {ref:5} {w['lost']}/{w['windows']} perdidas ({_pct(w['lost_share'])})"
        )
    d = seg["death"]
    verdict = {None: "indisponível", True: "ACIONADO", False: "não acionado"}[d["triggered"]]
    print(
        f"   critério de morte: {verdict} (janelas {_pct(d['lost_share'])} > 50%?"
        f" {d['windows_rule_triggered']}; queda extra {_pct(d['extra_drawdown'])} > 10 p.p.?"
        f" {d['drawdown_rule_triggered']})"
    )


def cmd_backtest(conn, a) -> None:
    cfg = compute.load_config(conn)
    c = a.backtest_cmd
    if c == "benchmarks":
        _run(conn, "backtest_benchmarks", lambda: backtest_run.load_benchmarks(conn, cfg))
    elif c == "run":
        detail = _run(conn, "backtest_fit", lambda: backtest_run.run_fit(conn, cfg, a.scenario))
        print(f"Ajuste (até {backtest_run.fit_end(cfg)}); a validação não foi calculada.")
        for name, row in detail.items():
            print(
                f"== {name}: líquido {_pct(row['net_cagr'])} a.a."
                f" (bruto {_pct(row['gross_cagr'])});"
                f" IDIV {_pct(row['idiv_cagr'])}, Ibovespa {_pct(row['ibov_cagr'])},"
                f" CDI {_pct(row['cdi_cagr'])}; queda máx {_pct(row['net_mdd'])}"
                f" (IDIV {_pct(row['idiv_mdd'])}); morte={row['death']['triggered']}"
            )
    elif c == "report":
        for r in backtest_run.report(conn):
            m = r["metrics"]
            print(
                f"## {r['kind']} {r['scenario']} (execução {r['id']}, {r['created_at']:%Y-%m-%d})"
            )
            for seg_name in ("fit", "validation"):
                if seg_name in m:
                    print(f"  [{seg_name}]")
                    _print_segment(m[seg_name])
            fl = m["flows"]
            print(
                f"  aportes={fl['net_invested']} valor final líquido={fl['net_final_value']}"
                f" taxas={fl['net_fees']} impostos={fl['net_taxes']}"
                f" proventos={fl['net_dividends']} 1ª compra={fl['net_first_buy']}"
            )
            if a.warnings:
                for w in r["warnings"]:
                    print(f"  ! {w}")
    elif c == "freeze":
        print(_dumps(backtest_run.freeze(conn, cfg, a.scenario, a.note)))
    elif c == "validate":
        detail = _run(conn, "backtest_validation", lambda: backtest_run.validate(conn, cfg))
        print(_dumps(detail))


def cmd_sql(conn, a) -> None:
    """Consulta de leitura (diagnóstico): cada consulta roda numa transação somente leitura."""
    for query in a.query:
        print(f"-- {query}")
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            cur = conn.execute(query)
            print("\t".join(c.name for c in cur.description))
            for row in cur.fetchmany(a.limit):
                print("\t".join("" if v is None else str(v) for v in row))


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
    c.add_argument("--doc", required=True, choices=["DFP", "ITR", "FCA", "FRE"])
    for s in (c, sub.add_parser("cotahist")):
        s.add_argument("--from-year", type=int)
        s.add_argument("--to-year", type=int)
        s.add_argument("--force", action="store_true", help="reprocessa mesmo sem mudança")
    sub.add_parser("daily")
    sub.add_parser("size")
    cp = sub.add_parser("compute", help="indicadores, outliers, eventos e filtro (fase 2)")
    cp.add_argument("--step", action="append", choices=COMPUTE_STEPS)
    cp.add_argument(
        "--as-of", type=date.fromisoformat, help="data-base do preço teto (padrão: hoje)"
    )
    ce = sub.add_parser("ceilings", help="preço teto da lista acompanhada (fase 3)")
    cs = ce.add_subparsers(dest="ceilings_cmd", required=True)
    x = cs.add_parser("list", help="último preço teto calculado, com métodos e papéis")
    x.add_argument("--cvm", type=int, action="append", help="só estas empresas")
    x.add_argument("--dcf", action="store_true", help="detalha o FCFE por exercício e por conta")
    bk = sub.add_parser("backtest", help="backtest, comparação e validação (fase 4)")
    bs = bk.add_subparsers(dest="backtest_cmd", required=True)
    bs.add_parser("benchmarks", help="coleta Ibovespa e IDIV (B3) e CDI (Banco Central)")
    x = bs.add_parser("run", help="ajuste: roda os cenários até validation_start - 1")
    x.add_argument("--scenario", action="append", help="só estes cenários (padrão: todos)")
    x = bs.add_parser("report", help="resultados gravados")
    x.add_argument(
        "--warnings", action="store_true", help="imprime também os avisos de cada execução"
    )
    x = bs.add_parser("freeze", help="congela o cenário escolhido com os dados de ajuste")
    x.add_argument("--scenario", required=True)
    x.add_argument("--note")
    bs.add_parser("validate", help="mede a validação, uma única vez, com o cenário congelado")
    sq = sub.add_parser("sql", help="consulta somente leitura, para diagnóstico")
    sq.add_argument("--query", action="append", required=True)
    sq.add_argument("--limit", type=int, default=200)
    wt = sub.add_parser("watch", help="lista de empresas acompanhadas (carteira e radar)")
    ws = wt.add_subparsers(dest="watch_cmd", required=True)
    x = ws.add_parser("find", help="procura empresas pelo nome")
    x.add_argument("--name", action="append", required=True)
    x = ws.add_parser("add")
    x.add_argument("--cvm", type=int, required=True)
    x.add_argument("--role", choices=watch.ROLES, required=True)
    x.add_argument("--segment", required=True)
    x.add_argument("--note")
    x = ws.add_parser("explain", help="critérios, fatos anuais e eventos de uma empresa")
    x.add_argument("--cvm", type=int, action="append", required=True)
    x = ws.add_parser("remove")
    x.add_argument("--cvm", type=int, required=True)
    ws.add_parser("list")
    x = ws.add_parser("candidates", help="candidatas ao radar por segmento, a partir do filtro")
    x.add_argument("--per-segment", type=int, default=6)
    rv = sub.add_parser("review", help="revisão manual (outliers, eventos, correções)")
    rs = rv.add_subparsers(dest="review_cmd", required=True)
    rl = rs.add_parser("list")
    rl.add_argument("--limit", type=int, default=100, help="linhas por seção")
    rl.add_argument(
        "--priority",
        action="store_true",
        help="só os outliers que mudam um resultado (empresas líquidas aprovadas ou sem payout/DY)",
    )
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
    x = rs.add_parser("dcf-growth", help="crescimento anual do FCFE da empresa no DCF")
    x.add_argument("--cvm", type=int, required=True)
    x.add_argument("--growth", help="fração ao ano (0.03 = 3%%)")
    x.add_argument("--clear", action="store_true", help="volta ao crescimento histórico")
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
        elif a.cmd == "watch":
            cmd_watch(conn, a)
        elif a.cmd == "ceilings":
            cmd_ceilings(conn, a)
        elif a.cmd == "backtest":
            cmd_backtest(conn, a)
        elif a.cmd == "sql":
            cmd_sql(conn, a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
