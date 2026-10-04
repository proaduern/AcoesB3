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
    to_enter = [
        (cvm, name, sorted(y.year for y in years))
        for cvm, name, years in conn.execute(
            """
            SELECT a.cvm_code, coalesce(c.name, '(sem cadastro)'), array_agg(a.reference_date)
            FROM indicator_annual a LEFT JOIN company c USING (cvm_code)
            WHERE a.notes->>'dividends' LIKE 'DVA zerada%%'
            GROUP BY 1, 2 ORDER BY 2, 1
            """
        )
    ]
    return {"outliers": outliers, "events": events, "dividends_to_enter": to_enter}


def source_check(dva, fre, low=Decimal("0.9"), high=Decimal("1.1")) -> str:
    """Compara o total da DVA com o do FRE no ano do outlier."""
    if dva is None and fre is None:
        return "sem fonte"
    if dva is None or fre is None:
        return "só " + ("DVA" if fre is None else "FRE")
    if dva <= 0 or fre <= 0:
        return "divergem"
    return "concordam" if low <= fre / dva <= high else "divergem"


HINTS = {
    "concordam": "duas fontes iguais: pagamento real; decida include/exclude",
    "divergem": "fontes diferentes: provável erro de dado ou de escala; confira e lance o valor",
    "só DVA": "uma fonte só: confirme no release antes de decidir",
    "só FRE": "uma fonte só: confirme no release antes de decidir",
    "sem fonte": "sem total de proventos para conferir",
}


def priority(conn: psycopg.Connection) -> list[tuple]:
    """Outliers sem decisão que mudam um resultado: empresas líquidas (critério de liquidez
    aprovado) já aprovadas, ou sem payout/DY por causa de outliers ou prejuízos. Aprovadas
    primeiro, depois por volume negociado. Usa o retrato mais recente de cada empresa."""
    rows = conn.execute(
        """
        WITH latest AS (
            SELECT DISTINCT ON (cvm_code) cvm_code, as_of, status
            FROM screen_result ORDER BY cvm_code, as_of DESC
        )
        SELECT o.cvm_code, c.name, o.reference_date, o.total, o.median, o.ratio,
               CASE WHEN a.jcp IS NOT NULL THEN a.jcp + a.dividends END AS dva,
               CASE WHEN a.fre_jcp IS NOT NULL THEN a.fre_jcp + a.fre_dividends END AS fre,
               l.status, liq.value
        FROM dividend_outlier o
        JOIN company c USING (cvm_code)
        JOIN latest l USING (cvm_code)
        JOIN screen_criterion liq ON liq.as_of = l.as_of AND liq.cvm_code = o.cvm_code
             AND liq.criterion = 'liquidez' AND liq.status = 'pass'
        LEFT JOIN indicator_annual a ON a.cvm_code = o.cvm_code
             AND a.reference_date = o.reference_date
        LEFT JOIN outlier_review r ON r.cvm_code = o.cvm_code
             AND r.reference_date = o.reference_date
        WHERE r.decision IS NULL
          AND l.status IN ('approved', 'rejected', 'insufficient_data')
          AND (l.status = 'approved' OR EXISTS (
                SELECT 1 FROM screen_criterion k
                WHERE k.as_of = l.as_of AND k.cvm_code = o.cvm_code
                  AND k.status = 'unavailable' AND k.detail->>'reason' = 'outliers_or_losses'))
        ORDER BY (l.status = 'approved') DESC, liq.value DESC NULLS LAST, o.ratio DESC
        """
    ).fetchall()
    return [(*r[:8], r[8], source_check(r[6], r[7])) for r in rows]


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
