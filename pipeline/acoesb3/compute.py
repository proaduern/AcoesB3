"""Fase 2 no banco: fatos anuais, outliers, eventos societários e retratos do filtro."""

from __future__ import annotations

import itertools
import json
import logging
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import psycopg
from psycopg.types.json import Jsonb

from . import ceiling, corporate, fcfe, indicators, mapping, screen
from . import shares as shares_mod

log = logging.getLogger(__name__)


def load_config(conn: psycopg.Connection) -> dict:
    return {k: v for k, v in conn.execute("SELECT key, value FROM app_config")}


# --- 1. Fatos anuais --------------------------------------------------------


def _fre_dividends(conn, cfg: dict) -> dict[tuple[int, date], tuple]:
    """(cvm_code, fim do exercício) -> (JCP, outros proventos, entrega do documento do FRE).

    Vale o documento mais recente que traz o exercício (os FRE de anos seguidos se sobrepõem).
    Valores em R$, somados por espécie e classe de ação (o total da empresa)."""
    jcp_kinds = set(cfg["fre.jcp_kinds"])
    best: dict[tuple[int, date], tuple[date, int]] = {}
    sums: dict[tuple[int, date, int], list[Decimal]] = defaultdict(lambda: [Decimal(0), Decimal(0)])
    for cvm, end, fid, received, kind, amount in conn.execute(
        """
        SELECT f.cvm_code, d.exercise_end, f.id, f.received_date, d.kind, sum(d.amount)
        FROM fre_dividend d JOIN filing f ON f.id = d.filing_id
        GROUP BY 1, 2, 3, 4, 5
        """
    ):
        key = (cvm, end)
        if key not in best or (received, fid) > best[key]:
            best[key] = (received, fid)
        sums[(cvm, end, fid)][0 if kind in jcp_kinds else 1] += amount
    return {key: (*sums[(key[0], key[1], fid)], received) for key, (received, fid) in best.items()}


def build_annual(conn: psycopg.Connection, cfg: dict | None = None) -> dict:
    """Um registro de indicator_annual por versão de DFP com contas. Idempotente."""
    cfg = cfg or load_config(conn)
    fre_div = _fre_dividends(conn, cfg)
    scale = (
        Decimal(str(cfg["fre.scale_mismatch_min"])),
        Decimal(str(cfg["fre.scale_mismatch_max"])),
    )
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
    stmts = sorted({s for s, _ in indicators.NEEDED})
    codes = sorted({c for _, c in indicators.NEEDED})
    facts: list[tuple] = []
    with conn.cursor(name="annual_lines") as cur:
        cur.execute(
            """
            SELECT fl.filing_id, fl.statement, fl.account_code, fl.value, fl.consolidated,
                   fl.description
            FROM financial_line fl JOIN filing f ON f.id = fl.filing_id
            WHERE f.doc_type = 'DFP' AND f.has_lines AND fl.period_end = f.reference_date
              AND ((fl.statement = ANY(%s) AND fl.account_code = ANY(%s))
                   OR (fl.statement = 'BPP' AND fl.account_code ~ '^2\\.[0-9]{2}(\\.[0-9]{2})?$'))
            ORDER BY fl.filing_id
            """,
            (stmts, codes),
        )
        seen: set[int] = set()
        for fid, grp in itertools.groupby(cur, key=lambda r: r[0]):
            grp = list(grp)
            lines = {(s, c): v for _, s, c, v, _, _ in grp if indicators.wanted_line(s, c)}
            labels = {c: d for _, s, c, _, _, d in grp if s == "BPP" and d}
            scope = grp[0][4]  # uma carga grava um só escopo por documento
            facts.append(
                _annual_fact(
                    fid, filings, lines, shares, forced, overrides, scope, fre_div, scale, labels
                )
            )
            seen.add(fid)
    # DFP com contas mas sem nenhuma das linhas lidas: registrar tudo como indisponível.
    for fid in filings.keys() - seen:
        facts.append(
            _annual_fact(fid, filings, {}, shares, forced, overrides, None, fre_div, scale)
        )
    suspect = _apply_zero_dividend_rule(facts)
    rows = [_to_row(f) for f in facts]
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO indicator_annual (filing_id, cvm_code, reference_date, plan, profit, equity,
                jcp, dividends, dividends_source, lpa_on, lpa_pn, shares_on, shares_pn, notes,
                fre_jcp, fre_dividends, fre_available_from, computed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            ON CONFLICT (filing_id) DO UPDATE SET plan = EXCLUDED.plan, profit = EXCLUDED.profit,
                equity = EXCLUDED.equity, jcp = EXCLUDED.jcp, dividends = EXCLUDED.dividends,
                dividends_source = EXCLUDED.dividends_source, lpa_on = EXCLUDED.lpa_on,
                lpa_pn = EXCLUDED.lpa_pn, shares_on = EXCLUDED.shares_on,
                shares_pn = EXCLUDED.shares_pn, notes = EXCLUDED.notes,
                fre_jcp = EXCLUDED.fre_jcp, fre_dividends = EXCLUDED.fre_dividends,
                fre_available_from = EXCLUDED.fre_available_from, computed_at = now()
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
    return {
        "annual_rows": len(rows),
        "plans": dict(plans),
        "unavailable": missing,
        "with_fre_dividends": sum(1 for r in rows if r[14] is not None),
        "dva_zero_suspect_years": suspect,
    }


def _annual_fact(
    fid, filings, lines, shares, forced, overrides, consolidated, fre_div, scale, labels=None
):  # fmt: skip
    cvm, ref = filings[fid]
    a = indicators.extract_annual(
        lines, shares.get(fid), forced.get(cvm), overrides.get((cvm, ref)), consolidated, labels
    )
    a.notes["scope"] = {True: "consolidada", False: "individual", None: "sem demonstrações"}[
        consolidated
    ]
    fre = fre_div.get((cvm, ref), (None, None, None))
    if (
        a.dividends_source == "dva"
        and a.jcp is not None
        and fre[0] is not None
        and indicators.scale_mismatch(a.jcp + a.dividends, fre[0] + fre[1], *scale)
    ):
        a.jcp = a.dividends = a.dividends_source = None
        fre = (None, None, None)
        a.notes["dividends"] = "FRE e DVA divergem por ~1000x: escala incerta, ano indisponível"
    return (fid, cvm, ref, a, fre)


def _apply_zero_dividend_rule(facts: list[tuple]) -> int:
    """DVA zerada depois de o FRE mostrar pagamentos: indisponível (ver indicators)."""
    by_company: dict[int, list] = defaultdict(list)
    for _fid, cvm, ref, a, fre in facts:
        total = a.jcp + a.dividends if a.jcp is not None and a.dividends is not None else None
        fre_total = fre[0] + fre[1] if fre[0] is not None else None
        by_company[cvm].append((ref, total, fre_total, a.dividends_source))
    flagged = {
        cvm: indicators.suspect_zero_years(sorted(y, key=lambda t: t[0]))
        for cvm, y in by_company.items()
    }
    n = 0
    for _fid, cvm, ref, a, _fre in facts:
        if ref in flagged.get(cvm, ()):
            a.jcp = a.dividends = a.dividends_source = None
            a.notes["dividends"] = (
                "DVA zerada depois de o FRE mostrar pagamentos: indisponível, lançar à mão"
            )
            n += 1
    return n


def _to_row(fact):
    fid, cvm, ref, a, fre = fact
    return (
        fid, cvm, ref, a.plan, a.profit, a.equity, a.jcp, a.dividends, a.dividends_source,
        a.lpa_on, a.lpa_pn, a.shares_on, a.shares_pn, Jsonb(a.notes), *fre,
    )  # fmt: skip


# --- 2. Outliers ------------------------------------------------------------


def _best_annual(conn, prefer: str = "fre") -> dict[tuple[int, date], tuple]:
    """Versão mais recente de cada (empresa, data-base) com fatos anuais, com os proventos
    já escolhidos (manual > FRE > DVA), sem olhar a data de entrega."""
    best: dict[tuple[int, date], tuple] = {}
    for cvm, ref, ver, jcp, div, src, fjcp, fdiv in conn.execute(
        """
        SELECT a.cvm_code, a.reference_date, f.version, a.jcp, a.dividends, a.dividends_source,
               a.fre_jcp, a.fre_dividends
        FROM indicator_annual a JOIN filing f ON f.id = a.filing_id
        ORDER BY a.cvm_code, a.reference_date, f.version
        """
    ):
        j, d, _ = indicators.choose_dividends(jcp, div, src, fjcp, fdiv, None, prefer=prefer)
        best[(cvm, ref)] = (ver, j, d)
    return best


def build_outliers(conn: psycopg.Connection, cfg: dict) -> dict:
    p = screen.ScreenParams.from_config(cfg)
    best = _best_annual(conn, cfg["dividends.preferred_source"])
    by_company: dict[int, dict[int, Decimal]] = defaultdict(dict)
    for (cvm, ref), (_ver, jcp, div) in best.items():
        if jcp is not None and div is not None:
            by_company[cvm][ref.year] = jcp + div
    refs = {(c, r.year): r for (c, r) in best}
    rows = []
    for cvm, totals in by_company.items():
        found = screen.find_outliers(
            totals,
            p.outlier_multiple,
            p.outlier_median_years,
            p.outlier_min_history,
            Decimal(str(cfg["outlier.persistence"])),
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


def _share_snapshots(conn) -> dict[int, list]:
    """cvm_code -> retratos do capital social do FRE (um por documento)."""
    capital_rows: dict[int, list] = defaultdict(list)
    for fid, cvm, received, ctype, approved, common, pref in conn.execute(
        """
        SELECT f.id, f.cvm_code, f.received_date, c.capital_type, c.approved_on,
               c.shares_common, c.shares_pref
        FROM fre_capital c JOIN filing f ON f.id = c.filing_id
        """
    ):
        capital_rows[cvm].append((fid, received, ctype, approved, common, pref))
    return {c: shares_mod.snapshots_from_capital(r) for c, r in capital_rows.items()}


def detect_events(conn: psycopg.Connection, cfg: dict) -> dict:
    sp = split_params(cfg)
    by_company, _, _, _ = _company_securities(conn, cfg)
    sec_company = {sid: c for c, secs in by_company.items() for sid, _, _ in secs}
    snapshots = _share_snapshots(conn)
    snap_tol = Decimal(str(cfg["events.snapshot_tolerance"]))
    confirmed = 0
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
                status = e.status
                cvm = sec_company.get(sid)
                if (
                    status == "suspected"
                    and cvm is not None
                    and shares_mod.confirmed_by_snapshots(
                        snapshots.get(cvm, []), e.event_date, e.factor, snap_tol
                    )
                ):
                    status = "auto"  # a contagem de ações do FRE cresceu pelo mesmo fator
                    confirmed += 1
                found.append(
                    (sid, e.event_date, e.factor, e.observed_ratio, e.dismes_changed, status)
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
    return {
        "securities_scanned": n_sec,
        "events": counts,
        "confirmed_by_fre_shares": confirmed,
    }


# --- 4. Retratos do filtro --------------------------------------------------


def snapshot_dates(today: date, first_year: int) -> list[date]:
    ends = [date(y, 12, 31) for y in range(first_year, today.year + 1)]
    return sorted({d for d in ends if d < today} | {today})


def _company_securities(conn, cfg: dict | None = None):
    """cvm_code -> [(security_id, ticker, volume total)], raízes ambíguas, papéis sem empresa e o
    que o mapeamento automático por nome resolveu (raiz -> (cvm_code, motivo))."""
    cfg = cfg or load_config(conn)
    fca = [
        (t, c)
        for t, c in conn.execute(
            "SELECT DISTINCT ticker, cvm_code FROM company_security WHERE ticker IS NOT NULL"
        )
    ]
    over = dict(conn.execute("SELECT ticker_root, cvm_code FROM ticker_company_override"))
    root_map, ambiguous = mapping.build_root_map(fca, over)
    secs = conn.execute(
        "SELECT s.id, s.ticker, s.short_name, coalesce(sum(q.volume), 0) FROM security s"
        " LEFT JOIN quote_daily q ON q.security_id = s.id GROUP BY s.id, s.ticker, s.short_name"
    ).fetchall()
    unmapped_names: dict[str, list[str]] = defaultdict(list)
    for _sid, ticker, short, _vol in secs:
        root = mapping.ticker_root(ticker)
        if root and root not in root_map and root not in ambiguous and short:
            unmapped_names[root].append(short)
    companies = [
        (c, [n, t]) for c, n, t in conn.execute("SELECT cvm_code, name, trade_name FROM company")
    ]
    auto = mapping.auto_map_roots(
        unmapped_names,
        companies,
        float(cfg["mapping.auto_min_ratio"]),
        int(cfg["mapping.auto_min_prefix"]),
    )
    root_map = {**{r: c for r, (c, _) in auto.items()}, **root_map}
    by_company: dict[int, list] = defaultdict(list)
    unmapped = []
    for sid, ticker, _short, vol in secs:
        root = mapping.ticker_root(ticker)
        cvm = root_map.get(root) if root else None
        if cvm is None:
            unmapped.append((ticker, float(vol)))
        else:
            by_company[cvm].append((sid, ticker, float(vol)))
    return by_company, ambiguous, unmapped, auto


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


def build_company_events(conn: psycopg.Connection, cfg: dict) -> dict:
    """Eventos por empresa: fator do FRE, data de efeito do COTAHIST (corporate.merge_events)."""
    window = int(cfg["events.match_window_days"])
    tol = Decimal(str(cfg["events.match_tolerance"]))
    dedupe = int(cfg["events.dedupe_days"])
    by_company, _, _, _ = _company_securities(conn, cfg)
    sec_company = {sid: c for c, secs in by_company.items() for sid, _, _ in secs}
    fre_events: dict[int, list] = defaultdict(list)
    for cvm, approved, before, after, received, kind in conn.execute(
        """
        SELECT f.cvm_code, s.approved_on, s.total_before, s.total_after, f.received_date,
               s.event_type
        FROM fre_split s JOIN filing f ON f.id = s.filing_id
        WHERE s.approved_on IS NOT NULL AND s.total_before > 0 AND s.total_after > 0
        """
    ):
        fre_events[cvm].append(
            corporate.FreEvent(
                approved, Decimal(after) / Decimal(before), received, kind, before, after
            )
        )
    price_events: dict[int, list] = defaultdict(list)
    for sid, d, factor, status, source in conn.execute(
        "SELECT security_id, event_date, factor, status, source FROM corporate_event"
        " WHERE status <> 'rejected'"
    ):
        cvm = sec_company.get(sid)
        if cvm is not None:
            kind = "manual" if source == "manual" else status
            price_events[cvm].append(corporate.PriceEvent(d, factor, kind))
    coverage = dict(
        conn.execute(
            """
            SELECT f.cvm_code, max(f.received_date) FROM filing f
            WHERE f.doc_type = 'FRE' AND (
                EXISTS (SELECT 1 FROM fre_dividend d WHERE d.filing_id = f.id)
                OR EXISTS (SELECT 1 FROM fre_split s WHERE s.filing_id = f.id))
            GROUP BY 1
            """
        )
    )
    out, dropped = [], []
    for cvm in set(fre_events) | set(price_events):
        merged, drop = corporate.merge_events(
            fre_events.get(cvm, []),
            price_events.get(cvm, []),
            coverage.get(cvm),
            window,
            tol,
            dedupe,
        )
        out += [
            (
                cvm,
                e.event_date,
                e.factor,
                e.source,
                e.date_basis,
                e.known_from,
                e.event_type,
                e.shares_before,
                e.shares_after,
            )  # fmt: skip
            for e in merged
        ]
        dropped += [(cvm, e.event_date.isoformat(), float(e.factor)) for e in drop]
    with conn.cursor() as cur:
        cur.execute("DELETE FROM company_event")
        cur.executemany(
            "INSERT INTO company_event (cvm_code, event_date, factor, source, date_basis,"
            " known_from, event_type, shares_before, shares_after)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            out,
        )
    conn.commit()
    by_kind: dict[str, int] = defaultdict(int)
    for row in out:
        by_kind[f"{row[3]}/{row[4]}"] += 1
    raw_fre = sum(len(v) for v in fre_events.values())
    return {
        "fre_events_raw": raw_fre,
        "fre_events_unique": sum(
            len(corporate.dedupe_fre(v, dedupe, Decimal("0.005"))) for v in fre_events.values()
        ),
        "company_events": dict(by_kind),
        "price_events_dropped_vs_fre": len(dropped),
        "dropped_sample": sorted(dropped)[:10],
    }


@dataclass
class _YearsContext:
    """Dados carregados uma vez para montar os exercícios (YearData) de qualquer empresa em
    qualquer data-base: usado pelo filtro (todas as empresas) e pelo preço teto (lista)."""

    cfg: dict
    gap: int
    by_company: dict
    class_secs: dict
    sec_company: dict
    ambiguous: dict
    unmapped: list
    auto: dict
    sector: dict
    outliers: set
    released: set
    snapshots: dict
    events: dict
    by_cvm: dict
    prices: dict

    def market_cap(self, cvm, ref, on, pn):
        total = Decimal(0)
        for cls, qty in (("on", on), ("pn", pn)):
            if qty == 0:
                continue
            price = next(
                (
                    self.prices[(sid, ref)]
                    for sid in self.class_secs.get(cvm, {}).get(cls, [])
                    if (sid, ref) in self.prices
                ),
                None,
            )
            if price is None:
                return None
            total += price * qty
        return total if total > 0 else None


def _load_years_context(
    conn: psycopg.Connection, cfg: dict, only: set[int] | None = None
) -> _YearsContext:
    """Carrega o necessário para ``_years_at``. ``only``: restringe às empresas dadas (o preço
    teto roda só na lista acompanhada); None = todas."""
    by_company, ambiguous, unmapped, auto = _company_securities(conn, cfg)
    sec_company = {sid: c for c, secs in by_company.items() for sid, _, _ in secs}
    class_secs = {c: mapping.class_securities(s) for c, s in by_company.items()}

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

    # Ações do FRE (retratos por documento) e eventos por empresa.
    snapshots = _share_snapshots(conn)
    events: dict[int, list] = defaultdict(list)
    for cvm, d, factor, known, before, after in conn.execute(
        "SELECT cvm_code, event_date, factor, known_from, shares_before, shares_after"
        " FROM company_event ORDER BY event_date"
    ):
        events[cvm].append((d, factor, before, after, known))

    # Todas as versões com fatos; a escolhida em cada data-base depende de received_date.
    rows = conn.execute(
        """
        SELECT a.filing_id, a.cvm_code, a.reference_date, f.version, f.received_date,
               sf.collected_at, a.profit, a.equity, a.jcp, a.dividends, a.dividends_source,
               a.fre_jcp, a.fre_dividends, a.fre_available_from, a.plan
        FROM indicator_annual a
        JOIN filing f ON f.id = a.filing_id
        JOIN source_file sf ON sf.id = f.source_file_id
        WHERE %s::int[] IS NULL OR a.cvm_code = ANY(%s)
        ORDER BY a.cvm_code, a.reference_date, f.version
        """,
        (list(only) if only is not None else None,) * 2,
    ).fetchall()

    # Preços de fim de exercício para o valor de mercado (ações do FRE x fechamento da classe).
    wanted = {
        (sid, r[2]) for r in rows for sids in class_secs.get(r[1], {}).values() for sid in sids
    }
    prices = _fiscal_year_end_prices(conn, wanted, int(cfg["market.price_lookback_days"]))

    by_cvm: dict[int, list] = defaultdict(list)
    for r in rows:
        by_cvm[r[1]].append(r)
    return _YearsContext(
        cfg=cfg,
        gap=int(cfg["shares.max_snapshot_gap_days"]),
        by_company=by_company,
        class_secs=class_secs,
        sec_company=sec_company,
        ambiguous=ambiguous,
        unmapped=unmapped,
        auto=auto,
        sector=sector,
        outliers=outliers,
        released=released,
        snapshots=snapshots,
        events=events,
        by_cvm=by_cvm,
        prices=prices,
    )


def _years_at(ctx: _YearsContext, cvm: int, as_of: date) -> tuple[dict, dict]:
    """Exercícios de uma empresa conhecidos em ``as_of`` (versão mais recente entregue até a
    data, proventos escolhidos pela regra de fonte). Devolve (ano -> YearData, ano -> plano)."""
    chosen: dict[date, tuple] = {}
    for r in ctx.by_cvm.get(cvm, []):
        if r[4] <= as_of:
            chosen[r[2]] = r
    known_full = [(d, f, b, a) for d, f, b, a, known in ctx.events.get(cvm, []) if known <= as_of]
    known_events = [(d, f) for d, f, _, _ in known_full]
    years: dict[int, screen.YearData] = {}
    plans: dict[int, str | None] = {}
    for ref, r in chosen.items():
        jcp, div, source = indicators.choose_dividends(
            r[8], r[9], r[10], r[11], r[12], r[13], as_of,
            prefer=ctx.cfg["dividends.preferred_source"],
        )  # fmt: skip
        found = shares_mod.shares_at(ctx.snapshots.get(cvm, []), known_full, ref, as_of, ctx.gap)
        qty = (found[0] + found[1]) if found else None
        years[ref.year] = screen.YearData(
            year=ref.year,
            reference_date=ref,
            filing_id=r[0],
            received_date=r[4],
            collected_at=r[5],
            profit=r[6],
            equity=r[7],
            jcp=jcp,
            dividends=div,
            dividends_source=source,
            market_cap=ctx.market_cap(cvm, ref, found[0], found[1]) if found else None,
            shares=qty,
            shares_factor=corporate.cumulative_factor(known_events, ref, as_of),
            outlier=(cvm, ref) in ctx.outliers and (cvm, ref) not in ctx.released,
        )
        plans[ref.year] = r[14]
    return years, plans


def build_screens(conn: psycopg.Connection, cfg: dict, today: date | None = None) -> dict:
    today = today or date.today()
    p = screen.ScreenParams.from_config(cfg)
    excluded_sectors = set(cfg["screen.excluded_sectors"])
    ctx = _load_years_context(conn, cfg)

    dates = snapshot_dates(today, int(cfg["screen.snapshot_first_year"]))
    out_result, out_crit = [], []
    status_counts: dict[str, dict[str, int]] = {}
    for as_of in dates:
        liq, _days = _liquidity(conn, as_of, int(cfg["liquidity.months"]), ctx.sec_company)
        counts: dict[str, int] = defaultdict(int)
        for cvm in ctx.by_cvm:
            years, _plans = _years_at(ctx, cvm, as_of)
            if not years:
                continue
            res = screen.evaluate(
                years,
                liq.get(cvm),
                p,
                excluded=ctx.sector.get(cvm) in excluded_sectors,
                as_of=as_of,
                listed=cvm in ctx.by_company,
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
        "auto_mapped_roots": {r: [c, why] for r, (c, why) in sorted(ctx.auto.items())},
        "unmapped_tickers_top": sorted(ctx.unmapped, key=lambda t: -t[1])[:15],
        "ambiguous_roots": {k: v for k, v in list(ctx.ambiguous.items())[:15]},
        "suspected_events_pending": pending_events,
    }


# --- 5. Preço teto (lista acompanhada) ---------------------------------------

CEILING_SOURCES = {
    "bazin": "CVM DFP (proventos) + FRE (ações e eventos)",
    "graham": "CVM DFP (lucro, PL) + FRE (ações e eventos)",
    "gordon": "CVM DFP (proventos) + FRE (ações e eventos)",
    "multiples": "CVM DFP (lucro, PL) + FRE (ações) + B3 COTAHIST (fechamento de fim de exercício)",
    "dcf": "CVM DFP (DFC: caixa operacional, investimento e financiamento) + FRE (ações)",
}


def _load_fcfe(conn, filing_ids: list[int], rules: fcfe.FcfeRules) -> dict[int, fcfe.Fcfe]:
    """filing_id -> FCFE do exercício, a partir das contas do DFC (6.01, 6.02.xx, 6.03.xx)."""
    lines: dict[int, list] = defaultdict(list)
    for fid, code, desc, value in conn.execute(
        """
        SELECT filing_id, account_code, description, value FROM financial_line
        WHERE filing_id = ANY(%s) AND statement IN ('DFC_MI', 'DFC_MD')
          AND account_code ~ '^6\\.0[123](\\.[0-9]{2})?$'
        """,
        (filing_ids,),
    ):
        lines[fid].append((code, desc or "", value))
    return {fid: fcfe.compute_fcfe(ls, rules) for fid, ls in lines.items()}


def _latest_prices(conn, sids: list[int], as_of: date, max_age: int) -> dict[int, tuple]:
    """security_id -> (data, fechamento): último pregão até ``as_of`` dentro de ``max_age`` dias."""
    if not sids:
        return {}
    return {
        sid: (d, close)
        for sid, d, close in conn.execute(
            """
            SELECT t.sec, q.trade_date, q.close
            FROM unnest(%s::int[]) AS t(sec)
            JOIN LATERAL (
                SELECT trade_date, close FROM quote_daily
                WHERE security_id = t.sec AND trade_date <= %s
                  AND trade_date > %s::date - %s::int
                ORDER BY trade_date DESC LIMIT 1) q ON true
            """,
            (sids, as_of, as_of, max_age),
        )
    }


def _unit_compositions(conn, as_of: date) -> dict[str, str]:
    """ticker -> composição da unit no FCA mais recente entregue até ``as_of`` (\"1 ON / 2 PN\")."""
    return dict(
        conn.execute(
            """
            SELECT DISTINCT ON (cs.ticker) cs.ticker, cs.unit_composition
            FROM company_security cs JOIN filing f ON f.id = cs.filing_id
            WHERE cs.ticker IS NOT NULL AND cs.unit_composition IS NOT NULL
              AND f.received_date <= %s
            ORDER BY cs.ticker, f.received_date DESC, f.version DESC
            """,
            (as_of,),
        )
    )


def build_ceilings(conn: psycopg.Connection, cfg: dict, as_of: date | None = None) -> dict:
    """Preço teto da lista acompanhada na data ``as_of`` (padrão: hoje). Só usa DFP entregues até
    a data e o último fechamento até ela. Substitui o resultado da mesma data; as outras ficam."""
    as_of = as_of or date.today()
    p = ceiling.CeilingParams.from_config(cfg)
    watch = [r[0] for r in conn.execute("SELECT cvm_code FROM watchlist ORDER BY cvm_code")]
    if not watch:
        return {"as_of": as_of, "companies": 0, "warning": "lista acompanhada vazia"}
    ctx = _load_years_context(conn, cfg, only=set(watch))
    sids = [sid for c in watch for sid, _t, _v in ctx.by_company.get(c, [])]
    prices = _latest_prices(conn, sids, as_of, p.price_max_age_days)
    compositions = _unit_compositions(conn, as_of)
    rules = fcfe.FcfeRules.from_config(cfg)
    growth = dict(conn.execute("SELECT cvm_code, growth FROM dcf_growth_override"))

    method_rows, result_rows, class_rows = [], [], []
    summary: dict[str, dict] = {}
    for cvm in watch:
        years, plans = _years_at(ctx, cvm, as_of)
        last = max(years) if years else None
        plan = plans.get(last) if last else None
        by_filing = _load_fcfe(conn, [y.filing_id for y in years.values()], rules) if years else {}
        by_year = {y: by_filing[v.filing_id] for y, v in years.items() if v.filing_id in by_filing}
        methods = ceiling.evaluate_methods(years, plan, p, by_year, growth.get(cvm))
        cons = ceiling.consolidate(methods, p)
        data_base = years[last].reference_date if last else None
        collected = max((y.collected_at for y in years.values() if y.collected_at), default=None)
        for m in methods:
            method_rows.append(
                (
                    as_of,
                    cvm,
                    m.method,
                    m.status,
                    m.value,
                    m.reason,
                    Jsonb(m.inputs, dumps=_dumps),
                    CEILING_SOURCES[m.method],
                    data_base,
                    collected,
                )  # fmt: skip
            )
        result_rows.append(
            (as_of, cvm, cons.status, cons.methods_ok, cons.k_required, cons.ceiling, plan,
             data_base, collected)
        )  # fmt: skip
        listed = []
        for sid, ticker, _vol in sorted(ctx.by_company.get(cvm, []), key=lambda t: t[1]):
            if sid not in prices:
                continue  # sem fechamento recente: papel sem negociação ou ticker antigo
            price_date, price = prices[sid]
            kind = mapping.ticker_class(ticker)
            mult, reason = 1, None
            if kind == "other":
                kind = "unit"
                mult = ceiling.parse_unit_composition(compositions.get(ticker))
                if mult is None:
                    reason = "composição da unit indisponível no FCA"
            if mult is None:
                class_rows.append(
                    (as_of, cvm, ticker, kind, None, price, price_date, None, None, None, None,
                     None, False, reason)
                )  # fmt: skip
                continue
            v = ceiling.value_class(ticker, kind, mult, price, price_date, methods, cons, p)
            class_rows.append(
                (as_of, cvm, ticker, kind, mult, price, price_date, v.ceiling, v.ratio, v.band,
                 v.votes, v.k_required, v.buy, None)
            )  # fmt: skip
            listed.append(ticker)
        summary[str(cvm)] = {
            "status": cons.status,
            "methods_ok": cons.methods_ok,
            "tickers": listed,
        }

    with conn.cursor() as cur:
        for table in ("ceiling_method", "ceiling_result", "ceiling_class"):
            cur.execute(f"DELETE FROM {table} WHERE as_of = %s", (as_of,))
        cur.executemany(
            "INSERT INTO ceiling_method (as_of, cvm_code, method, status, value, reason, inputs,"
            " source, data_base, collected_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            method_rows,
        )
        cur.executemany(
            "INSERT INTO ceiling_result (as_of, cvm_code, status, methods_ok, k_required, ceiling,"
            " plan, data_base, collected_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            result_rows,
        )
        cur.executemany(
            "INSERT INTO ceiling_class (as_of, cvm_code, ticker, kind, multiplier, price,"
            " price_date, ceiling, ratio, band, votes, k_required, buy, reason)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            class_rows,
        )
    conn.commit()
    by_status: dict[str, int] = defaultdict(int)
    for r in result_rows:
        by_status[r[2]] += 1
    return {
        "as_of": as_of,
        "companies": len(watch),
        "by_status": dict(by_status),
        "tickers_valued": sum(1 for r in class_rows if r[7] is not None),
        "tickers_without_ceiling": [r[2] for r in class_rows if r[7] is None],
        "buy": [r[2] for r in class_rows if r[12]],
    }


def _dumps(obj) -> str:
    return json.dumps(obj, default=str, ensure_ascii=False)
