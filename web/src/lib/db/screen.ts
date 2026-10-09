import type { Pool } from "pg";
import {
  PAGE_SIZE,
  escapeLike,
  isStatus,
  totalPages,
  type CriterionRow,
  type ScreenFilters,
  type ScreenRow,
  type ScreenStatus,
} from "@/lib/screen";
import { readOnly } from "./readonly";

type Db = Pick<Pool, "connect">;

export interface ScreenPage {
  asOf: string | null; // retrato mais recente
  counts: Partial<Record<ScreenStatus, number>>; // por status, com a busca e a lista aplicadas
  total: number; // empresas com os filtros (incluindo o status)
  page: number;
  pages: number;
  rows: ScreenRow[];
}

const str = (v: unknown): string | null => (typeof v === "string" ? v : null);

/** Retrato mais recente do filtro, com busca por nome ou ticker, status, lista e paginação. */
export async function loadScreen(db: Db, f: ScreenFilters): Promise<ScreenPage> {
  return readOnly(db, async (c) => {
    const last = await c.query("SELECT max(as_of) AS as_of FROM screen_result");
    const asOf = str(last.rows[0]?.as_of);
    if (!asOf) return { asOf: null, counts: {}, total: 0, page: 1, pages: 1, rows: [] };

    const pattern = f.q ? `%${escapeLike(f.q)}%` : null;
    // Parâmetros: $1 data, $2 padrão de busca (nulo = sem busca), $3 só a lista
    const base = `
      FROM screen_result r
      JOIN company co USING (cvm_code)
      LEFT JOIN watchlist w USING (cvm_code)
      LEFT JOIN (
        SELECT cvm_code, array_agg(DISTINCT ticker ORDER BY ticker) AS tickers
        FROM company_security WHERE ticker IS NOT NULL AND ticker <> '' GROUP BY cvm_code
      ) t USING (cvm_code)
      WHERE r.as_of = $1::date
        AND ($2::text IS NULL OR co.name ILIKE $2 OR co.trade_name ILIKE $2
             OR EXISTS (SELECT 1 FROM unnest(t.tickers) x WHERE x ILIKE $2))
        AND (NOT $3::boolean OR w.cvm_code IS NOT NULL)`;
    const args = [asOf, pattern, f.onlyWatch];

    const countRows = await c.query(
      `SELECT r.status, count(*)::int AS n ${base} GROUP BY r.status`,
      args,
    );
    const counts: Partial<Record<ScreenStatus, number>> = {};
    for (const r of countRows.rows) {
      const st: unknown = r.status;
      if (isStatus(st)) counts[st] = r.n as number;
    }
    const total = f.status ? (counts[f.status] ?? 0) : Object.values(counts).reduce((a, b) => a + b, 0);
    const pages = totalPages(total);
    const page = Math.min(f.page, pages);

    const rowsRes = await c.query(
      `SELECT r.cvm_code, co.name, co.cvm_sector, r.status, r.data_base, r.collected_at, w.role,
              coalesce(t.tickers, '{}') AS tickers
       ${base} AND ($4::text IS NULL OR r.status = $4)
       ORDER BY (w.cvm_code IS NULL), co.name, r.cvm_code
       LIMIT ${PAGE_SIZE} OFFSET $5`,
      [...args, f.status, (page - 1) * PAGE_SIZE],
    );

    const codes = rowsRes.rows.map((r) => r.cvm_code as number);
    const crit = codes.length
      ? await c.query(
          `SELECT cvm_code, criterion, status, value, threshold, detail->>'reason' AS reason
           FROM screen_criterion WHERE as_of = $1::date AND cvm_code = ANY($2::int[])`,
          [asOf, codes],
        )
      : { rows: [] as Record<string, unknown>[] };
    const byCvm = new Map<number, CriterionRow[]>();
    for (const k of crit.rows) {
      const row: CriterionRow = {
        criterion: k.criterion as string,
        status: k.status as CriterionRow["status"],
        value: str(k.value),
        threshold: str(k.threshold),
        reason: str(k.reason),
      };
      byCvm.set(k.cvm_code as number, [...(byCvm.get(k.cvm_code as number) ?? []), row]);
    }

    const rows: ScreenRow[] = rowsRes.rows.map((r) => ({
      cvmCode: r.cvm_code,
      name: r.name,
      sector: str(r.cvm_sector),
      tickers: r.tickers,
      status: r.status,
      dataBase: str(r.data_base),
      collectedAt: r.collected_at instanceof Date ? r.collected_at.toISOString() : null,
      role: r.role ?? null,
      criteria: byCvm.get(r.cvm_code) ?? [],
    }));
    return { asOf, counts, total, page, pages, rows };
  });
}

export interface PendingOutlier {
  cvmCode: number;
  name: string;
  referenceDate: string;
  total: string;
  median: string;
  ratio: string;
}
export interface PendingEvent {
  id: number;
  ticker: string;
  eventDate: string;
  factor: string;
}
export interface PendingDividend {
  cvmCode: number;
  name: string;
  years: number[];
}
export interface Pending {
  outliersTotal: number; // B3 inteira
  outliers: PendingOutlier[]; // lista acompanhada, sem decisão
  eventsTotal: number;
  events: PendingEvent[];
  dividendsToEnter: PendingDividend[]; // lista acompanhada
}

/** Pendências de revisão manual. A revisão em si segue por comando (tela somente leitura). */
export async function loadPending(db: Db): Promise<Pending> {
  return readOnly(db, async (c) => {
    const total = await c.query(
      `SELECT count(*)::int AS n FROM dividend_outlier o
       LEFT JOIN outlier_review r USING (cvm_code, reference_date) WHERE r.decision IS NULL`,
    );
    const outliers = await c.query(
      `SELECT o.cvm_code, co.name, o.reference_date, o.total, o.median, o.ratio
       FROM dividend_outlier o
       JOIN watchlist w USING (cvm_code) JOIN company co USING (cvm_code)
       LEFT JOIN outlier_review r USING (cvm_code, reference_date)
       WHERE r.decision IS NULL ORDER BY o.ratio DESC, o.cvm_code, o.reference_date`,
    );
    const evTotal = await c.query(
      "SELECT count(*)::int AS n FROM corporate_event WHERE status = 'suspected'",
    );
    const events = await c.query(
      `SELECT e.id, s.ticker, e.event_date, e.factor
       FROM corporate_event e JOIN security s ON s.id = e.security_id
       WHERE e.status = 'suspected' ORDER BY e.event_date DESC, e.id LIMIT 30`,
    );
    const divs = await c.query(
      `SELECT a.cvm_code, co.name, array_agg(extract(year FROM a.reference_date)::int ORDER BY a.reference_date) AS years
       FROM indicator_annual a JOIN watchlist w USING (cvm_code) JOIN company co USING (cvm_code)
       WHERE a.notes->>'dividends' LIKE 'DVA zerada%'
       GROUP BY a.cvm_code, co.name ORDER BY co.name`,
    );
    return {
      outliersTotal: total.rows[0].n,
      outliers: outliers.rows.map((r) => ({
        cvmCode: r.cvm_code,
        name: r.name,
        referenceDate: r.reference_date,
        total: r.total,
        median: r.median,
        ratio: r.ratio,
      })),
      eventsTotal: evTotal.rows[0].n,
      events: events.rows.map((r) => ({
        id: r.id,
        ticker: r.ticker,
        eventDate: r.event_date,
        factor: r.factor,
      })),
      dividendsToEnter: divs.rows.map((r) => ({ cvmCode: r.cvm_code, name: r.name, years: r.years })),
    };
  });
}
