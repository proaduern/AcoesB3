"""Carga no banco: cadastro CVM, DFP/ITR/FCA e COTAHIST."""

from __future__ import annotations

import logging
from datetime import date

import psycopg

from . import cotahist, cvm, fre
from .db import get_config
from .http import download

log = logging.getLogger(__name__)


def load_cad(conn: psycopg.Connection, force: bool = False) -> dict:
    d = download(conn, "cvm_cad", cvm.CAD_URL, force=force)
    if d is None:
        raise RuntimeError(f"cadastro CVM não encontrado: {cvm.CAD_URL}")
    if d.content is None:
        return {"skipped": "sem mudança"}
    rows = cvm.parse_cad(d.content)
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO company (cvm_code, cnpj, name, trade_name, cvm_sector, status, status_since,
                                 registered_at, canceled_at, cancel_reason, category, source,
                                 updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'cvm_cad', now())
            ON CONFLICT (cvm_code) DO UPDATE SET
                cnpj = EXCLUDED.cnpj, name = EXCLUDED.name, trade_name = EXCLUDED.trade_name,
                cvm_sector = EXCLUDED.cvm_sector, status = EXCLUDED.status,
                status_since = EXCLUDED.status_since, registered_at = EXCLUDED.registered_at,
                canceled_at = EXCLUDED.canceled_at, cancel_reason = EXCLUDED.cancel_reason,
                category = EXCLUDED.category, source = EXCLUDED.source, updated_at = now()
            """,
            [
                (
                    r.cvm_code,
                    r.cnpj,
                    r.name,
                    r.trade_name,
                    r.cvm_sector,
                    r.status,
                    r.status_since,
                    r.registered_at,
                    r.canceled_at,
                    r.cancel_reason,
                    r.category,
                )
                for r in rows
            ],
        )
    conn.commit()
    return {"companies": len(rows)}


def _upsert_filings(conn, rows: list[cvm.IndexRow], source_file_id: int) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO filing (doc_type, cvm_code, cnpj, reference_date, version, doc_id,
                                received_date, link, source_file_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (doc_type, cvm_code, reference_date, version) DO UPDATE SET
                doc_id = EXCLUDED.doc_id, received_date = EXCLUDED.received_date,
                link = EXCLUDED.link, cnpj = EXCLUDED.cnpj
            """,
            [
                (
                    r.doc_type,
                    r.cvm_code,
                    r.cnpj,
                    r.reference_date,
                    r.version,
                    r.doc_id,
                    r.received_date,
                    r.link,
                    source_file_id,
                )
                for r in rows
            ],
        )


def _account_rules(conn) -> list[cvm.AccountRule]:
    return [
        cvm.AccountRule(s, c, ch)
        for s, c, ch in conn.execute("SELECT statement, code, include_children FROM cvm_account")
    ]


def load_doc_year(conn: psycopg.Connection, doc_type: str, year: int, force: bool = False) -> dict:
    """Carrega um zip anual de DFP, ITR, FCA ou FRE. Idempotente."""
    if doc_type == "FRE":
        return load_fre_year(conn, year, force)
    url = cvm.doc_url(doc_type, year)
    d = download(conn, f"cvm_{doc_type.lower()}", url, force=force)
    if d is None:
        return {"skipped": "arquivo inexistente"}
    if d.content is None:
        return {"skipped": "sem mudança"}
    members = cvm.ZipMembers(d.content)
    prefix = f"{doc_type.lower()}_cia_aberta_"
    index = cvm.parse_index(members[f"{prefix}{year}.csv"])
    wrong = {r.doc_type for r in index} - {doc_type}
    if wrong:
        raise ValueError(f"índice {url} traz CATEG_DOC inesperado: {wrong}")
    _upsert_filings(conn, index, d.source_file_id)
    result = {"filings": len(index)}
    if doc_type == "FCA":
        result.update(_load_fca_securities(conn, members[f"{prefix}valor_mobiliario_{year}.csv"]))
    else:
        result.update(_load_statements(conn, doc_type, year, members))
    conn.commit()
    return result


def load_fre_year(conn: psycopg.Connection, year: int, force: bool = False) -> dict:
    """Zip anual do FRE: índice, capital social, desdobramentos e proventos por classe.

    Os zips de 2025 em diante não trazem desdobramento nem dividendos (layout novo): o arquivo
    ausente é registrado no resultado, não é erro.
    """
    url = cvm.doc_url("FRE", year)
    d = download(conn, "cvm_fre", url, force=force)
    if d is None:
        return {"skipped": "arquivo inexistente"}
    if d.content is None:
        return {"skipped": "sem mudança"}
    members = cvm.ZipMembers(d.content)
    index = fre.parse_index(members[fre.member("", year)])
    _upsert_filings(conn, index, d.source_file_id)
    bounds = fre.Bounds(
        int(get_config(conn, "fre.min_year")), int(get_config(conn, "fre.max_future_days"))
    )
    by_doc = {
        doc_id: (fid, received)
        for fid, doc_id, received in conn.execute(
            "SELECT id, doc_id, received_date FROM filing"
            " WHERE doc_type = 'FRE' AND doc_id = ANY(%s)",
            ([r.doc_id for r in index],),
        )
    }
    filing_ids = sorted(fid for fid, _ in by_doc.values())
    result: dict = {"filings": len(index), "absent_files": [], "orphan_doc_ids": []}
    with_data: set[int] = set()
    with conn.cursor() as cur:
        for table in ("fre_capital", "fre_split", "fre_dividend"):
            cur.execute(f"DELETE FROM {table} WHERE filing_id = ANY(%s)", (filing_ids,))

    def locate(doc_id: int):
        if doc_id not in by_doc:
            result["orphan_doc_ids"].append(doc_id)
            return None
        return by_doc[doc_id]

    cap_name = fre.member("capital_social", year)
    if cap_name in members:
        capital = []
        for r in fre.parse_capital(members[cap_name]):
            hit = locate(r.doc_id)
            if hit:
                fid, received = hit
                capital.append(
                    (
                        fid,
                        r.capital_type,
                        bounds.ok(r.approved_on, received),
                        r.common,
                        r.preferred,
                        r.total,
                    )
                )
                with_data.add(fid)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO fre_capital (filing_id, capital_type, approved_on, shares_common,"
                " shares_pref, shares_total) VALUES (%s, %s, %s, %s, %s, %s)",
                capital,
            )
        result["capital"] = len(capital)
    else:
        result["absent_files"].append(cap_name)

    split_name = fre.member("capital_social_desdobramento", year)
    if split_name in members:
        splits, bad_dates = [], 0
        for r in fre.parse_splits(members[split_name]):
            hit = locate(r.doc_id)
            if hit:
                fid, received = hit
                when = bounds.ok(r.approved_on, received)
                bad_dates += r.approved_on is not None and when is None
                splits.append(
                    (fid, r.event_type, when, r.total_before, r.total_after, r.common_before,
                     r.common_after, r.pref_before, r.pref_after)
                )  # fmt: skip
                with_data.add(fid)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO fre_split (filing_id, event_type, approved_on, total_before,"
                " total_after, common_before, common_after, pref_before, pref_after)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                splits,
            )
        result["splits"] = len(splits)
        result["splits_invalid_dates"] = bad_dates
    else:
        result["absent_files"].append(split_name)

    div_name = fre.member("distribuicao_dividendos_classe_acao", year)
    if div_name in members:
        parsed, skipped = fre.parse_dividends(members[div_name])
        dividends = []
        for r in parsed:
            hit = locate(r.doc_id)
            if hit:
                fid, received = hit
                dividends.append(
                    (fid, r.exercise_start, r.exercise_end, r.share_type, r.share_class, r.kind,
                     r.amount, bounds.ok(r.paid_on, received))
                )  # fmt: skip
                with_data.add(fid)
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO fre_dividend (filing_id, exercise_start, exercise_end, share_type,"
                " share_class, kind, amount, paid_on) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                dividends,
            )
        result["dividends"] = len(dividends)
        result["dividends_skipped"] = skipped
    else:
        result["absent_files"].append(div_name)

    with conn.cursor() as cur:
        cur.execute("UPDATE filing SET has_lines = true WHERE id = ANY(%s)", (sorted(with_data),))
    result["orphan_doc_ids"] = sorted(set(result["orphan_doc_ids"]))
    conn.commit()
    return result


def _filing_ids(conn, doc_type: str, year_rows) -> dict:
    keys = {(r.cvm_code, r.reference_date, r.version) for r in year_rows}
    if not keys:
        return {}
    ids = {}
    for fid, code, ref, ver in conn.execute(
        "SELECT id, cvm_code, reference_date, version FROM filing "
        "WHERE doc_type = %s AND cvm_code = ANY(%s)",
        (doc_type, list({k[0] for k in keys})),
    ):
        if (code, ref, ver) in keys:
            ids[(code, ref, ver)] = fid
    return ids


def _load_statements(conn, doc_type: str, year: int, members: cvm.ZipMembers) -> dict:
    rules = _account_rules(conn)
    per_share = get_config(conn, "cvm.per_share_prefixes")
    prefix = f"{doc_type.lower()}_cia_aberta_"
    lines: list[cvm.Line] = []
    for statement in cvm.STATEMENTS:
        for scope, consolidated in (("con", True), ("ind", False)):
            name = f"{prefix}{statement}_{scope}_{year}.csv"
            if name not in members:
                raise ValueError(f"arquivo esperado ausente no zip: {name}")
            parsed = cvm.parse_statement(members[name], statement, consolidated, rules, per_share)
            lines.extend(parsed)
    lines, identical_dups, conflicts = cvm.dedupe(lines)
    if conflicts:
        log.warning(
            "%s %d: contas com valores conflitantes (ignoradas): %s", doc_type, year, conflicts[:5]
        )
    lines = cvm.choose_scope(lines)
    ids = _filing_ids(conn, doc_type, lines)
    # Documento fora do índice não tem data de entrega: fica de fora, mas registrado.
    orphan = sorted({(x.cvm_code, x.reference_date, x.version) for x in lines} - ids.keys())
    if orphan:
        log.warning("%s %d: documentos fora do índice: %s", doc_type, year, orphan)
        lines = [x for x in lines if (x.cvm_code, x.reference_date, x.version) in ids]
    filing_ids = sorted(set(ids.values()))
    with conn.cursor() as cur:
        cur.execute("DELETE FROM financial_line WHERE filing_id = ANY(%s)", (filing_ids,))
        with cur.copy(
            "COPY financial_line (filing_id, statement, consolidated, account_code, period_start,"
            " period_end, value, source_scale, description) FROM STDIN"
        ) as copy:
            for x in lines:
                copy.write_row(
                    (
                        ids[(x.cvm_code, x.reference_date, x.version)],
                        x.statement,
                        x.consolidated,
                        x.account_code,
                        x.period_start,
                        x.period_end,
                        x.value,
                        x.source_scale,
                        x.description,
                    )
                )
        cur.execute("UPDATE filing SET has_lines = true WHERE id = ANY(%s)", (filing_ids,))
    # composicao_capital não existe nos zips antigos (ex.: DFP 2010): dado indisponível.
    shares_name = f"{prefix}composicao_capital_{year}.csv"
    shares = (
        _load_share_counts(conn, doc_type, members[shares_name])
        if shares_name in members
        else "arquivo ausente no zip"
    )
    return {
        "lines": len(lines),
        "filings_with_lines": len(filing_ids),
        "share_counts": shares,
        "orphan_docs": [[c, r.isoformat(), v] for c, r, v in orphan],
        "identical_duplicates": identical_dups,
        "conflicting_keys": [[str(v) for v in k] for k in conflicts],
    }


def _load_share_counts(conn, doc_type: str, raw: bytes) -> int:
    rows = cvm.parse_share_counts(raw)
    ids = {
        (cnpj, ref, ver): fid
        for fid, cnpj, ref, ver in conn.execute(
            "SELECT id, cnpj, reference_date, version FROM filing"
            " WHERE doc_type = %s AND cnpj = ANY(%s)",
            (doc_type, list({r.cnpj for r in rows})),
        )
    }
    data = [
        (
            ids[(r.cnpj, r.reference_date, r.version)],
            r.common,
            r.preferred,
            r.total,
            r.treasury_common,
            r.treasury_preferred,
            r.treasury_total,
        )
        for r in rows
        if (r.cnpj, r.reference_date, r.version) in ids
    ]
    if len(data) != len(rows):
        log.warning("composicao_capital: %d linhas sem documento no índice", len(rows) - len(data))
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO share_count (filing_id, common, preferred, total, treasury_common,
                                     treasury_preferred, treasury_total)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (filing_id) DO UPDATE SET common = EXCLUDED.common,
                preferred = EXCLUDED.preferred, total = EXCLUDED.total,
                treasury_common = EXCLUDED.treasury_common,
                treasury_preferred = EXCLUDED.treasury_preferred,
                treasury_total = EXCLUDED.treasury_total
            """,
            data,
        )
    return len(data)


def _load_fca_securities(conn, raw: bytes) -> dict:
    rows = cvm.parse_fca_securities(raw)
    by_doc = {
        doc_id: (fid, code)
        for fid, doc_id, code in conn.execute(
            "SELECT id, doc_id, cvm_code FROM filing WHERE doc_type = 'FCA' AND doc_id = ANY(%s)",
            (list({r.doc_id for r in rows}),),
        )
    }
    # Documento fora do índice não tem data de entrega: fica de fora, mas registrado.
    missing = sorted({r.doc_id for r in rows} - by_doc.keys())
    if missing:
        log.warning("FCA valor_mobiliario: ID_Documento fora do índice: %s", missing)
    rows = [r for r in rows if r.doc_id in by_doc]
    filing_ids = sorted({by_doc[r.doc_id][0] for r in rows})
    with conn.cursor() as cur:
        cur.execute("DELETE FROM company_security WHERE filing_id = ANY(%s)", (filing_ids,))
        cur.executemany(
            """
            INSERT INTO company_security (cvm_code, ticker, security_type, preferred_class,
                unit_composition, market, segment, trading_start, trading_end, filing_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    by_doc[r.doc_id][1],
                    r.ticker,
                    r.security_type,
                    r.preferred_class,
                    r.unit_composition,
                    r.market,
                    r.segment,
                    r.trading_start,
                    r.trading_end,
                    by_doc[r.doc_id][0],
                )
                for r in rows
            ],
        )
        cur.execute("UPDATE filing SET has_lines = true WHERE id = ANY(%s)", (filing_ids,))
    return {"securities": len(rows), "orphan_doc_ids": missing}


# --- COTAHIST ---------------------------------------------------------------

COTAHIST_BASE = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"


def cotahist_year_url(year: int) -> str:
    return f"{COTAHIST_BASE}/COTAHIST_A{year}.ZIP"


def cotahist_day_url(day: date) -> str:
    return f"{COTAHIST_BASE}/COTAHIST_D{day:%d%m%Y}.ZIP"


def load_cotahist(conn: psycopg.Connection, url: str, force: bool = False) -> dict:
    d = download(conn, "b3_cotahist", url, force=force)
    if d is None:
        return {"skipped": "arquivo inexistente"}
    if d.content is None:
        return {"skipped": "sem mudança"}
    codbdi = set(get_config(conn, "cotahist.codbdi"))
    markets = set(get_config(conn, "cotahist.market_types"))
    isin_types = set(get_config(conn, "cotahist.isin_types"))
    quotes = list(cotahist.select_quotes(cotahist.iter_zip(d.content), codbdi, markets, isin_types))
    if not quotes:
        return {"quotes": 0}
    sec_ids = _upsert_securities(conn, quotes)
    with conn.cursor() as cur:
        cur.execute(
            "CREATE TEMP TABLE tmp_quote (LIKE quote_daily INCLUDING DEFAULTS) ON COMMIT DROP"
        )
        with cur.copy(
            "COPY tmp_quote (security_id, trade_date, open, high, low, avg, close, trades,"
            " quantity, volume, distribution, source_file_id) FROM STDIN"
        ) as copy:
            for q in quotes:
                f = q.quote_factor
                copy.write_row(
                    (
                        sec_ids[(q.ticker, q.isin)],
                        q.trade_date,
                        q.open / f,
                        q.high / f,
                        q.low / f,
                        q.avg / f,
                        q.close / f,
                        q.trades,
                        q.quantity,
                        q.volume,
                        q.distribution,
                        d.source_file_id,
                    )
                )
        cur.execute(
            """
            INSERT INTO quote_daily SELECT * FROM tmp_quote
            ON CONFLICT (security_id, trade_date) DO UPDATE SET
                open = EXCLUDED.open, high = EXCLUDED.high, low = EXCLUDED.low, avg = EXCLUDED.avg,
                close = EXCLUDED.close, trades = EXCLUDED.trades, quantity = EXCLUDED.quantity,
                volume = EXCLUDED.volume, distribution = EXCLUDED.distribution,
                source_file_id = EXCLUDED.source_file_id
            """
        )
    conn.commit()
    return {"quotes": len(quotes), "securities": len(sec_ids)}


def _upsert_securities(conn, quotes: list[cotahist.Quote]) -> dict[tuple[str, str], int]:
    agg: dict[tuple[str, str], list] = {}
    for q in quotes:
        key = (q.ticker, q.isin)
        cur = agg.get(key)
        if cur is None:
            agg[key] = [q.especi, q.short_name, q.trade_date, q.trade_date]
        else:
            if q.trade_date >= cur[3]:
                cur[0], cur[1], cur[3] = q.especi, q.short_name, q.trade_date
            cur[2] = min(cur[2], q.trade_date)
    ids: dict[tuple[str, str], int] = {}
    with conn.cursor() as cur:
        for (ticker, isin), (especi, name, first, last) in agg.items():
            row = cur.execute(
                """
                INSERT INTO security (ticker, isin, especi, short_name, first_date, last_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, isin) DO UPDATE SET
                    especi = CASE WHEN EXCLUDED.last_date >= security.last_date
                                  THEN EXCLUDED.especi ELSE security.especi END,
                    short_name = CASE WHEN EXCLUDED.last_date >= security.last_date
                                      THEN EXCLUDED.short_name ELSE security.short_name END,
                    first_date = LEAST(security.first_date, EXCLUDED.first_date),
                    last_date = GREATEST(security.last_date, EXCLUDED.last_date)
                RETURNING id
                """,
                (ticker, isin, especi, name, first, last),
            ).fetchone()
            ids[(ticker, isin)] = row[0]
    return ids


def size_report(conn: psycopg.Connection) -> dict:
    total = conn.execute("SELECT pg_database_size(current_database())").fetchone()[0]
    tables = conn.execute(
        """
        SELECT relname, pg_total_relation_size(c.oid), c.reltuples::bigint
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
        ORDER BY 2 DESC
        """
    ).fetchall()
    return {"database_bytes": total, "tables": [list(t) for t in tables]}
