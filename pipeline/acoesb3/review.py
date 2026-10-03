"""Revisão manual: outliers de proventos, eventos societários e correções por empresa.

Até a tela existir (fase 5), a revisão é feita por estes comandos. Depois de qualquer
alteração, rode ``acoesb3 compute`` para refletir nos retratos do filtro.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import psycopg


def pending(conn: psycopg.Connection) -> dict:
    outliers = conn.execute(
        """
        SELECT o.cvm_code, c.name, o.reference_date, o.total, o.median, o.ratio, r.decision
        FROM dividend_outlier o
        JOIN company c USING (cvm_code)
        LEFT JOIN outlier_review r USING (cvm_code, reference_date)
        ORDER BY (r.decision IS NOT NULL), o.ratio DESC
        """
    ).fetchall()
    events = conn.execute(
        """
        SELECT e.id, s.ticker, e.event_date, e.factor, e.observed_ratio, e.dismes_changed, e.status
        FROM corporate_event e JOIN security s ON s.id = e.security_id
        WHERE e.status IN ('suspected', 'auto')
        ORDER BY (e.status = 'auto'), e.event_date DESC
        """
    ).fetchall()
    return {"outliers": outliers, "events": events}


def decide_outlier(conn, cvm_code: int, reference_date: date, decision: str, note: str | None):
    if decision == "reset":
        conn.execute(
            "DELETE FROM outlier_review WHERE cvm_code = %s AND reference_date = %s",
            (cvm_code, reference_date),
        )
    else:
        if not conn.execute(
            "SELECT 1 FROM dividend_outlier WHERE cvm_code = %s AND reference_date = %s",
            (cvm_code, reference_date),
        ).fetchone():
            raise ValueError("não há outlier detectado para essa empresa e data-base")
        conn.execute(
            """
            INSERT INTO outlier_review (cvm_code, reference_date, decision, note)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (cvm_code, reference_date) DO UPDATE SET
                decision = EXCLUDED.decision, note = EXCLUDED.note, decided_at = now()
            """,
            (cvm_code, reference_date, decision, note),
        )
    conn.commit()


def decide_event(conn, event_id: int, decision: str):
    """confirm / reject / reset. Reset devolve o evento detectado a 'suspected' (o próximo
    ``compute`` reclassifica) e apaga evento manual."""
    if decision == "reset":
        conn.execute("DELETE FROM corporate_event WHERE id = %s AND source = 'manual'", (event_id,))
        conn.execute(
            "UPDATE corporate_event SET status = 'suspected' WHERE id = %s AND source = 'detected'",
            (event_id,),
        )
    else:
        status = {"confirm": "confirmed", "reject": "rejected"}[decision]
        cur = conn.execute(
            "UPDATE corporate_event SET status = %s WHERE id = %s", (status, event_id)
        )
        if cur.rowcount == 0:
            raise ValueError(f"evento {event_id} não existe")
    conn.commit()


def add_event(conn, ticker: str, event_date: date, factor: Decimal, note: str | None):
    """Evento informado à mão (ex.: bonificação pequena que a detecção não pega)."""
    rows = conn.execute("SELECT id FROM security WHERE ticker = %s", (ticker,)).fetchall()
    if len(rows) != 1:
        raise ValueError(f"ticker {ticker}: {len(rows)} papéis encontrados (esperado 1)")
    conn.execute(
        """
        INSERT INTO corporate_event (security_id, event_date, factor, status, source, note)
        VALUES (%s, %s, %s, 'confirmed', 'manual', %s)
        ON CONFLICT (security_id, event_date) DO UPDATE SET factor = EXCLUDED.factor,
            status = 'confirmed', source = 'manual', note = EXCLUDED.note
        """,
        (rows[0][0], event_date, factor, note),
    )
    conn.commit()


def set_dividends(
    conn, cvm_code: int, reference_date: date, jcp: Decimal, dividends: Decimal, source: str,
    note: str | None,
):  # fmt: skip
    """Proventos do exercício (R$) que substituem a DVA nesse ano. Valores brutos, em reais."""
    if not conn.execute(
        "SELECT 1 FROM filing WHERE doc_type = 'DFP' AND cvm_code = %s AND reference_date = %s",
        (cvm_code, reference_date),
    ).fetchone():
        raise ValueError("não há DFP dessa empresa nessa data-base")
    conn.execute(
        """
        INSERT INTO dividend_override (cvm_code, reference_date, jcp, dividends, source, note)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (cvm_code, reference_date) DO UPDATE SET jcp = EXCLUDED.jcp,
            dividends = EXCLUDED.dividends, source = EXCLUDED.source, note = EXCLUDED.note,
            set_at = now()
        """,
        (cvm_code, reference_date, jcp, dividends, source, note),
    )
    conn.commit()


def clear_dividends(conn, cvm_code: int, reference_date: date):
    conn.execute(
        "DELETE FROM dividend_override WHERE cvm_code = %s AND reference_date = %s",
        (cvm_code, reference_date),
    )
    conn.commit()


def set_class(conn, cvm_code: int, sector: str | None, plan: str | None, note: str | None):
    conn.execute(
        """
        INSERT INTO company_class_override (cvm_code, sector, plan, note) VALUES (%s, %s, %s, %s)
        ON CONFLICT (cvm_code) DO UPDATE SET sector = EXCLUDED.sector, plan = EXCLUDED.plan,
            note = EXCLUDED.note, set_at = now()
        """,
        (cvm_code, sector, plan, note),
    )
    conn.commit()


def set_ticker_root(conn, root: str, cvm_code: int, note: str | None):
    conn.execute(
        """
        INSERT INTO ticker_company_override (ticker_root, cvm_code, note) VALUES (%s, %s, %s)
        ON CONFLICT (ticker_root) DO UPDATE SET cvm_code = EXCLUDED.cvm_code,
            note = EXCLUDED.note, set_at = now()
        """,
        (root.upper(), cvm_code, note),
    )
    conn.commit()
