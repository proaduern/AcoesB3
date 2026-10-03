"""Fase 2 no banco: fatos anuais, outliers, eventos societários e retratos do filtro."""

from __future__ import annotations

import itertools
import json
import logging
from collections import defaultdict
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.types.json import Jsonb

from . import corporate, indicators, mapping, screen

log = logging.getLogger(__name__)

# Contas lidas das demonstrações para os fatos anuais.
_NEEDED = sorted(
    {("DRE", p.profit) for p in indicators.PLANS.values()}
    | {("BPP", c) for p in indicators.PLANS.values() for c in (p.equity, p.equity_nci)}
    | {("DVA", c) for p in indicators.PLANS.values() for c in (p.jcp, p.dividends)}
    | {indicators.LPA_ON, indicators.LPA_PN}
)
_NEEDED_SET = frozenset(_NEEDED)
_APPLIED = ("auto", "confirmed")


def load_config(conn: psycopg.Connection) -> dict:
    return {k: v for k, v in conn.execute("SELECT key, value FROM app_config")}


# --- 1. Fatos anuais --------------------------------------------------------


def build_annual(conn: psycopg.Connection) -> dict:
    """Um registro de indicator_annual por versão de DFP com contas. Idempotente."""
    forced = dict(
        conn.execute("SELECT cvm_code, plan FROM company_class_override WHERE plan IS NOT NULL")
    )
    overrides = {
        (c, r): (j, d, s)
        for c, r, j, d, s in conn.execute(
            "SELECT cvm_code, reference_date, jcp, dividends, source FROM dividend_override"
        )
    }
    shares = {
        fid: (c, p, tc, tp)
        for fid, c, p, tc, tp in conn.execute(
            "SELECT filing_id, common, preferred, treasury_common, treasury_preferred"
            " FROM share_count"
        )
    }
    filings = {
        fid: (cvm, ref)
        for fid, cvm, ref in conn.execute(
            "SELECT id, cvm_code, reference_date FROM filing WHERE doc_type = 'DFP' AND has_lines"
        )
    }
    stmts = sorted({s for s, _ in _NEEDED})
    codes = sorted({c for _, c in _NEEDED})
    rows = []
    with conn.cursor(name="annual_lines") as cur:
        cur.execute(
            """
            SELECT fl.filing_id, fl.statement, fl.account_code, fl.value
            FROM financial_line fl JOIN filing f ON f.id = fl.filing_id
            WHERE f.doc_type = 'DFP' AND f.has_lines AND fl.period_end = f.reference_date
              AND fl.statement = ANY(%s) AND fl.account_code = ANY(%s)
            ORDER BY fl.filing_id
            """,
            (stmts, codes),
        )
        seen: set[int] = set()
        for fid, grp in itertools.groupby(cur, key=lambda r: r[0]):
            lines = {(s, c): v for _, s, c, v in grp if (s, c) in _NEEDED_SET}
            rows.append(_annual_row(fid, filings, lines, shares, forced, overrides))
            seen.add(fid)
    # DFP com contas mas sem nenhuma das linhas lidas: registrar tudo como indisponível.
    for fid in filings.keys() - seen:
        rows.append(_annual_row(fid, filings, {}, shares, forced, overrides))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO indicator_annual (filing_id, cvm_code, reference_date, plan, profit, equity,
                jcp, dividends, dividends_source, lpa_on, lpa_pn, shares_on, shares_pn, notes,
                computed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (filing_id) DO UPDATE SET plan = EXCLUDED.plan, profit = EXCLUDED.profit,
                equity = EXCLUDED.equity, jcp = EXCLUDED.jcp, dividends = EXCLUDED.dividends,
                dividends_source = EXCLUDED.dividends_source, lpa_on = EXCLUDED.lpa_on,
                lpa_pn = EXCLUDED.lpa_pn, shares_on = EXCLUDED.shares_on,
                shares_pn = EXCLUDED.shares_pn, notes = EXCLUDED.notes, computed_at = now()
            """,
            rows,
        )
        cur.execute(
            "DELETE FROM indicator_annual WHERE NOT (filing_id = ANY(%s))", (list(filings),)
        )
    conn.commit()
    plans: dict[str, int] = defaultdict(int)
    for r in rows:
        plans[r[3] or "indefinido"] += 1
    missing = {
        what: sum(1 for r in rows if r[idx] is None)
        for what, idx in (("profit", 4), ("equity", 5), ("dividends", 7), ("shares_on", 11))
    }
    return {"annual_rows": len(rows), "plans": dict(plans), "unavailable": missing}


def _annual_row(fid, filings, lines, shares, forced, overrides):
    cvm, ref = filings[fid]
    a = indicators.extract_annual(
        lines, shares.get(fid), forced.get(cvm), overrides.get((cvm, ref))
    )
    return (
        fid, cvm, ref, a.plan, a.profit, a.equity, a.jcp, a.dividends, a.dividends_source,
        a.lpa_on, a.lpa_pn, a.shares_on, a.shares_pn, Jsonb(a.notes),
    )  # fmt: skip


# --- 2. Outliers ------------------------------------------------------------


def _best_annual(conn) -> dict[tuple[int, date], tuple]:
    """Versão mais recente de cada (empresa, data-base) com fatos anuais."""
    best: dict[tuple[int, date], tuple] = {}
    for row in conn.execute(
        """
        SELECT a.cvm_code, a.reference_date, f.version, a.jcp, a.dividends
        FROM indicator_annual a JOIN filing f ON f.id = a.filing_id
        ORDER BY a.cvm_code, a.reference_date, f.version
        """
    ):
        best[(row[0], row[1])] = row[2:]
    return best


def build_outliers(conn: psycopg.Connection, cfg: dict) -> dict:
    p = screen.ScreenParams.from_config(cfg)
    best = _best_annual(conn)
    by_company: dict[int, dict[int, Decimal]] = defaultdict(dict)
    for (cvm, ref), (_ver, jcp, div) in best.items():
        if jcp is not None and div is not None:
            by_company[cvm][ref.year] = jcp + div
    refs = {(c, r.year): r for (c, r) in best}
    rows = []
    for cvm, totals in by_company.items():
        found = screen.find_outliers(
            totals, p.outlier_multiple, p.outlier_median_years, p.outlier_min_history
        )
        for y, (med, ratio, n) in found.items():
            rows.append((cvm, refs[(cvm, y)], totals[y], med, ratio, n))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM dividend_outlier")
        cur.executemany(
            "INSERT INTO dividend_outlier (cvm_code, reference_date, total, median, ratio,"
            " years_used) VALUES (%s, %s, %s, %s, %s, %s)",
            rows,
        )
    conn.commit()
    pending = conn.execute(
        "SELECT count(*) FROM dividend_outlier o LEFT JOIN outlier_review r USING (cvm_code,"
        " reference_date) WHERE r.cvm_code IS NULL"
    ).fetchone()[0]
    return {"outliers": len(rows), "pending_review": pending}


# --- 3. Eventos societários -------------------------------------------------


def split_params(cfg: dict) -> corporate.SplitParams:
    return corporate.SplitParams(
        candidate_low=float(cfg["split.candidate_low"]),
        candidate_high=float(cfg["split.candidate_high"]),
        ratio_tolerance=float(cfg["split.ratio_tolerance"]),
        auto_min_factor=float(cfg["split.auto_min_factor"]),
        max_gap_days=int(cfg["split.max_gap_days"]),
        simple_factors=tuple(cfg["split.simple_factors"]),
    )


def detect_events(conn: psycopg.Connection, cfg: dict) -> dict:
    sp = split_params(cfg)
    found: list[tuple] = []
    n_sec = 0
    with conn.cursor(name="quotes_for_events") as cur:
        cur.execute(
            "SELECT security_id, trade_date, close, distribution FROM quote_daily"
            " ORDER BY security_id, trade_date"
        )
        for sid, grp in itertools.groupby(cur, key=lambda r: r[0]):
            n_sec += 1
            qs = [(d, c, dis) for _, d, c, dis in grp]
            for e in corporate.detect_events(qs, sp):
                found.append(
                    (sid, e.event_date, e.factor, e.observed_ratio, e.dismes_changed, e.status)
                )
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE tmp_event (LIKE corporate_event INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        with cur.copy(
            "COPY tmp_event (security_id, event_date, factor, observed_ratio, dismes_changed,"
            " status, source) FROM STDIN"
        ) as copy:
            for row in found:
                copy.write_row((*row, "detected"))
        # Detecção removida do que o usuário não decidiu; decisões (confirmed/rejected) e
        # eventos manuais ficam.
        cur.execute(
            """
            DELETE FROM corporate_event c
            WHERE c.source = 'detected' AND c.status IN ('auto', 'suspected')
              AND NOT EXISTS (SELECT 1 FROM tmp_event t
                              WHERE t.security_id = c.security_id AND t.event_date = c.event_date)
            """
        )
        cur.execute(
            """
            INSERT INTO corporate_event (security_id, event_date, factor, observed_ratio,
                                         dismes_changed, status, source)
            SELECT security_id, event_date, factor, observed_ratio, dismes_changed, status, source
            FROM tmp_event
            ON CONFLICT (security_id, event_date) DO UPDATE SET
                factor = EXCLUDED.factor, observed_ratio = EXCLUDED.observed_ratio,
                dismes_changed = EXCLUDED.dismes_changed, detected_at = now(),
                status = CASE WHEN corporate_event.status IN ('confirmed', 'rejected')
                              THEN corporate_event.status ELSE EXCLUDED.status END
            """
        )
    conn.commit()
    counts = dict(conn.execute("SELECT status, count(*) FROM corporate_event GROUP BY status"))
    return {"securities_scanned": n_sec, "events": counts}


# --- 4. Retratos do filtro --------------------------------------------------


def snapshot_dates(today: date, first_year: int) -> list[date]:
    ends = [date(y, 12, 31) for y in range(first_year, today.year + 1)]
    return sorted({d for d in ends if d < today} | {today})


def _company_securities(conn):
    """cvm_code -> [(security_id, ticker, volume total)] e diagnósticos do mapeamento."""
    fca = [
        (t, c)
        for t, c in conn.execute(
            "SELECT DISTINCT ticker, cvm_code FROM company_security WHERE ticker IS NOT NULL"
        )
    ]
    over = dict(conn.execute("SELECT ticker_root, cvm_code FROM ticker_company_override"))
    root_map, ambiguous = mapping.build_root_map(fca, over)
    by_company: dict[int, list] = defaultdict(list)
    unmapped = []
    for sid, ticker, vol in conn.execute(
        "SELECT s.id, s.ticker, coalesce(sum(q.volume), 0) FROM security s"
        " LEFT JOIN quote_daily q ON q.security_id = s.id GROUP BY s.id, s.ticker"
    ):
        root = mapping.ticker_root(ticker)
        cvm = root_map.get(root) if root else None
        if cvm is None:
            unmapped.append((ticker, float(vol)))
        else:
            by_company[cvm].append((sid, ticker, float(vol)))
    return by_company, ambiguous, unmapped


def _applied_events(conn) -> dict[int, list[tuple[date, Decimal]]]:
    ev: dict[int, list] = defaultdict(list)
    for sid, d, f in conn.execute(
        "SELECT security_id, event_date, factor FROM corporate_event WHERE status = ANY(%s)"
        " ORDER BY event_date",
        (list(_APPLIED),),
    ):
        ev[sid].append((d, f))
    return ev


def _fiscal_year_end_prices(conn, wanted: set[tuple[int, date]], lookback: int):
    if not wanted:
        return {}
    sids, dts = zip(*sorted(wanted), strict=True)
    out = {}
    for sid, d, close in conn.execute(
        """
        SELECT t.sec, t.d, q.close
        FROM unnest(%s::int[], %s::date[]) AS t(sec, d)
        JOIN LATERAL (
            SELECT close FROM quote_daily
            WHERE security_id = t.sec AND trade_date <= t.d
              AND trade_date > t.d - %s::int
            ORDER BY trade_date DESC LIMIT 1) q ON true
        """,
        (list(sids), list(dts), lookback),
    ):
        out[(sid, d)] = close
    return out


def _liquidity(conn, as_of: date, months: int, sec_company: dict[int, int]):
    """cvm_code -> Liquidity. Volume médio sobre todos os pregões da janela."""
    days = conn.execute(
        "SELECT count(DISTINCT trade_date) FROM quote_daily"
        " WHERE trade_date > %s::date - make_interval(months => %s) AND trade_date <= %s",
        (as_of, months, as_of),
    ).fetchone()[0]
    if not days:
        return {}, 0
    per_sec = conn.execute(
        """
        SELECT security_id, sum(volume), array_agg(trade_date)
        FROM quote_daily
        WHERE trade_date > %s::date - make_interval(months => %s) AND trade_date <= %s
        GROUP BY security_id
        """,
        (as_of, months, as_of),
    )
    vol: dict[int, Decimal] = defaultdict(Decimal)
    present: dict[int, set] = defaultdict(set)
    for sid, v, dates in per_sec:
        cvm = sec_company.get(sid)
        if cvm is not None:
            vol[cvm] += v
            present[cvm].update(dates)
    return {
        c: screen.Liquidity(vol[c] / days, Decimal(len(present[c])) / days, days) for c in vol
    }, days


def build_screens(conn: psycopg.Connection, cfg: dict, today: date | None = None) -> dict:
    today = today or date.today()
    p = screen.ScreenParams.from_config(cfg)
    excluded_sectors = set(cfg["screen.excluded_sectors"])
    by_company, ambiguous, unmapped = _company_securities(conn)
    sec_company = {sid: c for c, secs in by_company.items() for sid, _, _ in secs}
    refs = {c: mapping.reference_security(s) for c, s in by_company.items()}
    class_secs = {c: mapping.class_securities(s) for c, s in by_company.items()}
    events = _applied_events(conn)

    sector = {c: s for c, s in conn.execute("SELECT cvm_code, cvm_sector FROM company")}
    sector.update(
        dict(
            conn.execute(
                "SELECT cvm_code, sector FROM company_class_override WHERE sector IS NOT NULL"
            )
        )
    )
    outliers = {
        (c, r) for c, r in conn.execute("SELECT cvm_code, reference_date FROM dividend_outlier")
    }
    released = {
        (c, r)
        for c, r, d in conn.execute("SELECT cvm_code, reference_date, decision FROM outlier_review")
        if d == "include"
    }

    # Todas as versões com fatos; a escolhida em cada data-base depende de received_date.
    rows = conn.execute(
        """
        SELECT a.filing_id, a.cvm_code, a.reference_date, f.version, f.received_date,
               sf.collected_at, a.profit, a.equity, a.jcp, a.dividends, a.dividends_source,
               a.lpa_on, a.lpa_pn, a.shares_on, a.shares_pn
        FROM indicator_annual a
        JOIN filing f ON f.id = a.filing_id
        JOIN source_file sf ON sf.id = f.source_file_id
        ORDER BY a.cvm_code, a.reference_date, f.version
        """
    ).fetchall()

    # Preços de fim de exercício para o valor de mercado (ações da CVM x fechamento da classe).
    wanted = set()
    for r in rows:
        for cls, shares in (("on", r[13]), ("pn", r[14])):
            sid = class_secs.get(r[1], {}).get(cls)
            if shares and sid:
                wanted.add((sid, r[2]))
    prices = _fiscal_year_end_prices(conn, wanted, int(cfg["market.price_lookback_days"]))

    def market_cap(r):
        cvm, ref, s_on, s_pn = r[1], r[2], r[13], r[14]
        if s_on is None or s_pn is None:
            return None
        total = Decimal(0)
        for cls, shares in (("on", s_on), ("pn", s_pn)):
            if shares == 0:
                continue
            sid = class_secs.get(cvm, {}).get(cls)
            price = prices.get((sid, ref)) if sid else None
            if price is None:
                return None
            total += price * shares
        return total if total > 0 else None

    caps = {r[0]: market_cap(r) for r in rows}
    by_cvm: dict[int, list] = defaultdict(list)
    for r in rows:
        by_cvm[r[1]].append(r)

    dates = snapshot_dates(today, int(cfg["screen.snapshot_first_year"]))
    out_result, out_crit = [], []
    status_counts: dict[str, dict[str, int]] = {}
    for as_of in dates:
        liq, _days = _liquidity(conn, as_of, int(cfg["liquidity.months"]), sec_company)
        counts: dict[str, int] = defaultdict(int)
        for cvm, cvm_rows in by_cvm.items():
            # Para cada data-base, a versão mais recente entregue até a data.
            chosen: dict[date, tuple] = {}
            for r in cvm_rows:
                if r[4] <= as_of:
                    chosen[r[2]] = r
            if not chosen:
                continue
            ref_sec = refs.get(cvm)
            years: dict[int, screen.YearData] = {}
            for ref, r in chosen.items():
                lpa = r[11] if (ref_sec is None or ref_sec[0] == "on") else r[12]
                ev = events.get(ref_sec[1], []) if ref_sec else []
                years[ref.year] = screen.YearData(
                    year=ref.year,
                    reference_date=ref,
                    filing_id=r[0],
                    received_date=r[4],
                    collected_at=r[5],
                    profit=r[6],
                    equity=r[7],
                    jcp=r[8],
                    dividends=r[9],
                    dividends_source=r[10],
                    lpa=lpa,
                    market_cap=caps[r[0]],
                    shares=(r[13] + r[14]) if r[13] is not None and r[14] is not None else None,
                    split_factor=corporate.cumulative_factor(ev, r[4], as_of),
                    shares_factor=corporate.cumulative_factor(ev, ref, as_of),
                    outlier=(cvm, ref) in outliers and (cvm, ref) not in released,
                )
            res = screen.evaluate(
                years, liq.get(cvm), p, excluded=sector.get(cvm) in excluded_sectors
            )
            counts[res.status] += 1
            out_result.append((as_of, cvm, res.status, res.data_base, res.collected_at))
            for c in res.criteria:
                out_crit.append(
                    (
                        as_of,
                        cvm,
                        c.name,
                        c.status,
                        c.value,
                        c.threshold,
                        Jsonb(c.detail, dumps=_dumps),
                    )
                )
        status_counts[as_of.isoformat()] = dict(counts)

    with conn.cursor() as cur:
        # Retrato "de hoje" substitui o anterior; fins de ano ficam (e são recalculados).
        cur.execute(
            "DELETE FROM screen_criterion WHERE as_of = ANY(%s)"
            " OR NOT (extract(month FROM as_of) = 12 AND extract(day FROM as_of) = 31)",
            (dates,),
        )
        cur.execute(
            "DELETE FROM screen_result WHERE as_of = ANY(%s)"
            " OR NOT (extract(month FROM as_of) = 12 AND extract(day FROM as_of) = 31)",
            (dates,),
        )
        cur.executemany(
            "INSERT INTO screen_result (as_of, cvm_code, status, data_base, collected_at)"
            " VALUES (%s, %s, %s, %s, %s)",
            out_result,
        )
        cur.executemany(
            "INSERT INTO screen_criterion (as_of, cvm_code, criterion, status, value, threshold,"
            " detail) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            out_crit,
        )
    conn.commit()
    pending_events = conn.execute(
        "SELECT count(*) FROM corporate_event WHERE status = 'suspected'"
    ).fetchone()[0]
    return {
        "snapshots": status_counts,
        "unmapped_tickers_top": sorted(unmapped, key=lambda t: -t[1])[:15],
        "ambiguous_roots": {k: v for k, v in list(ambiguous.items())[:15]},
        "suspected_events_pending": pending_events,
    }


def _dumps(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)
