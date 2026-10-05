"""Lista de empresas acompanhadas (carteira e radar) e busca de candidatas ao radar.

O cálculo do filtro roda em toda a B3; a lista restringe revisão, preço teto e alertas.
"""

from __future__ import annotations

import unicodedata

import psycopg

from .db import get_config

ROLES = ("carteira", "radar")


def _fold(text: str | None) -> str:
    t = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def find(conn: psycopg.Connection, text: str) -> list[tuple]:
    """Empresas cujo nome contém ``text`` (sem acento), com o último status do filtro."""
    rows = conn.execute(
        """
        SELECT c.cvm_code, c.name, c.status, coalesce(o.sector, c.cvm_sector), s.status, s.as_of
        FROM company c
        LEFT JOIN company_class_override o USING (cvm_code)
        LEFT JOIN LATERAL (SELECT status, as_of FROM screen_result r WHERE r.cvm_code = c.cvm_code
                           ORDER BY as_of DESC LIMIT 1) s ON true
        """
    ).fetchall()
    needle = _fold(text)
    return [r for r in rows if needle in _fold(r[1])]


def add(conn: psycopg.Connection, cvm_code: int, role: str, segment: str, note: str | None):
    if role not in ROLES:
        raise ValueError(f"role deve ser um de {ROLES}")
    if not conn.execute("SELECT 1 FROM company WHERE cvm_code = %s", (cvm_code,)).fetchone():
        raise ValueError(f"empresa {cvm_code} não existe")
    conn.execute(
        """
        INSERT INTO watchlist (cvm_code, role, segment, note) VALUES (%s, %s, %s, %s)
        ON CONFLICT (cvm_code) DO UPDATE SET role = EXCLUDED.role, segment = EXCLUDED.segment,
            note = EXCLUDED.note
        """,
        (cvm_code, role, segment, note),
    )
    conn.commit()


def remove(conn: psycopg.Connection, cvm_code: int):
    conn.execute("DELETE FROM watchlist WHERE cvm_code = %s", (cvm_code,))
    conn.commit()


def listing(conn: psycopg.Connection) -> list[tuple]:
    return conn.execute(
        """
        SELECT w.role, w.segment, w.cvm_code, c.name, s.status
        FROM watchlist w JOIN company c USING (cvm_code)
        LEFT JOIN LATERAL (SELECT status FROM screen_result r WHERE r.cvm_code = w.cvm_code
                           ORDER BY as_of DESC LIMIT 1) s ON true
        ORDER BY w.role, w.segment, c.name
        """
    ).fetchall()


def candidates(conn: psycopg.Connection, per_segment: int = 6) -> dict[str, list[tuple]]:
    """Por segmento, empresas fora da lista, listadas e líquidas, melhores primeiro:
    aprovadas, depois as que falham em menos critérios. Cada linha traz o status, os critérios
    que falham ou ficam indisponíveis e o volume negociado."""
    segments = get_config(conn, "watch.segments")
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (cvm_code) cvm_code, as_of, status
            FROM screen_result ORDER BY cvm_code, as_of DESC
        )
        SELECT c.cvm_code, c.name, coalesce(o.sector, c.cvm_sector), l.status,
               (SELECT value FROM screen_criterion k WHERE k.as_of = l.as_of
                  AND k.cvm_code = c.cvm_code AND k.criterion = 'liquidez'),
               coalesce((SELECT string_agg(k.criterion || ':' || k.status, ', '
                                           ORDER BY k.criterion)
                         FROM screen_criterion k WHERE k.as_of = l.as_of
                           AND k.cvm_code = c.cvm_code AND k.status <> 'pass'), ''),
               (SELECT count(*) FROM screen_criterion k WHERE k.as_of = l.as_of
                  AND k.cvm_code = c.cvm_code AND k.status = 'fail')
        FROM company c
        JOIN latest l USING (cvm_code)
        LEFT JOIN company_class_override o USING (cvm_code)
        WHERE l.status IN ('approved', 'rejected', 'insufficient_history', 'insufficient_data')
          AND NOT EXISTS (SELECT 1 FROM watchlist w WHERE w.cvm_code = c.cvm_code)
          AND EXISTS (SELECT 1 FROM screen_criterion k WHERE k.as_of = l.as_of
                      AND k.cvm_code = c.cvm_code AND k.criterion = 'liquidez'
                      AND k.status = 'pass')
        """
    ).fetchall()
    out: dict[str, list[tuple]] = {}
    for seg, needles in segments.items():
        hits = [r for r in rows if any(n in _fold(r[2]) for n in needles)]
        order = {"approved": 0, "rejected": 1, "insufficient_data": 2, "insufficient_history": 3}
        hits.sort(key=lambda r: (order[r[3]], r[6], -(r[4] or 0)))
        out[seg] = hits[:per_segment]
    return out


def explain(conn: psycopg.Connection, cvm_code: int) -> dict:
    """Dados por trás do último retrato de uma empresa: critérios, fatos anuais e eventos."""
    as_of = conn.execute(
        "SELECT max(as_of) FROM screen_result WHERE cvm_code = %s", (cvm_code,)
    ).fetchone()[0]
    criteria = conn.execute(
        "SELECT criterion, status, value, threshold, detail FROM screen_criterion"
        " WHERE cvm_code = %s AND as_of = %s ORDER BY criterion",
        (cvm_code, as_of),
    ).fetchall()
    annual = conn.execute(
        """
        SELECT reference_date, jcp + dividends, fre_jcp + fre_dividends, dividends_source,
               shares_on, shares_pn, notes->>'dividends'
        FROM indicator_annual WHERE cvm_code = %s ORDER BY reference_date
        """,
        (cvm_code,),
    ).fetchall()
    events = conn.execute(
        "SELECT event_date, factor, source, date_basis, event_type, shares_before, shares_after"
        " FROM company_event WHERE cvm_code = %s ORDER BY event_date",
        (cvm_code,),
    ).fetchall()
    return {"as_of": as_of, "criteria": criteria, "annual": annual, "events": events}


def ceilings(conn: psycopg.Connection, cvm_codes: list[int] | None = None) -> dict:
    """Último preço teto da lista (ou das empresas pedidas): consolidação, métodos e papéis."""
    as_of = conn.execute("SELECT max(as_of) FROM ceiling_result").fetchone()[0]
    if as_of is None:
        return {"as_of": None, "companies": []}
    filt = "AND r.cvm_code = ANY(%s)" if cvm_codes else ""
    args = (as_of, cvm_codes) if cvm_codes else (as_of,)
    out = []
    for cvm, name, status, n_ok, k, ceil_, plan, data_base in conn.execute(
        f"""
        SELECT r.cvm_code, c.name, r.status, r.methods_ok, r.k_required, r.ceiling, r.plan,
               r.data_base
        FROM ceiling_result r JOIN company c USING (cvm_code)
        WHERE r.as_of = %s {filt} ORDER BY c.name
        """,
        args,
    ).fetchall():
        methods = conn.execute(
            "SELECT method, status, value, reason, inputs FROM ceiling_method"
            " WHERE as_of = %s AND cvm_code = %s ORDER BY method",
            (as_of, cvm),
        ).fetchall()
        classes = conn.execute(
            "SELECT ticker, kind, price, price_date, ceiling, ratio, band, votes, k_required, buy,"
            " reason FROM ceiling_class WHERE as_of = %s AND cvm_code = %s ORDER BY ticker",
            (as_of, cvm),
        ).fetchall()
        out.append(
            {
                "cvm": cvm,
                "name": name,
                "status": status,
                "methods_ok": n_ok,
                "k": k,
                "ceiling": ceil_,
                "plan": plan,
                "data_base": data_base,
                "methods": methods,
                "classes": classes,
            }
        )
    return {"as_of": as_of, "companies": out}
