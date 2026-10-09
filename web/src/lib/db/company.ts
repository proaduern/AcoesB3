import type { Pool } from "pg";
import type {
  CeilingTab,
  CompanyHeader,
  FilterTab,
  MethodRow,
  OriginTab,
  OutlierRow,
  Period,
  PriceTab,
  YearSeries,
} from "@/lib/company";
import { pickTicker } from "@/lib/company";
import type { CriterionRow } from "@/lib/screen";
import { readOnly } from "./readonly";
import { int, iso, str, toClassRow } from "./watchlist";

type Db = Pick<Pool, "connect">;

const LATEST_CEILING = "(SELECT max(as_of) FROM ceiling_result)";

/** Empresa da lista acompanhada, ou nulo (a ficha só existe para a lista). */
export async function loadCompanyHeader(db: Db, cvm: number): Promise<CompanyHeader | null> {
  return readOnly(db, async (c) => {
    const r = await c.query(
      `SELECT co.cvm_code, co.name, co.cnpj, co.cvm_sector, w.role, w.segment
       FROM watchlist w JOIN company co USING (cvm_code) WHERE w.cvm_code = $1`,
      [cvm],
    );
    const row = r.rows[0];
    if (!row) return null;
    const t = await c.query(
      `SELECT DISTINCT ticker FROM ceiling_class WHERE cvm_code = $1 AND as_of = ${LATEST_CEILING} ORDER BY ticker`,
      [cvm],
    );
    return {
      cvmCode: row.cvm_code,
      name: row.name,
      cnpj: row.cnpj,
      sector: str(row.cvm_sector),
      role: row.role,
      segment: row.segment,
      tickers: t.rows.map((x) => x.ticker as string),
    };
  });
}

export async function loadCeilingTab(db: Db, cvm: number): Promise<CeilingTab> {
  return readOnly(db, async (c) => {
    const res = await c.query(
      `SELECT as_of, status, ceiling, methods_ok, k_required, plan, data_base, collected_at
       FROM ceiling_result WHERE cvm_code = $1 AND as_of = ${LATEST_CEILING}`,
      [cvm],
    );
    const r = res.rows[0];
    const asOf = str((await c.query(`SELECT ${LATEST_CEILING} AS as_of`)).rows[0]?.as_of);
    const methods = r
      ? await c.query(
          `SELECT method, status, value, reason, inputs, source, data_base, collected_at
           FROM ceiling_method WHERE cvm_code = $1 AND as_of = $2::date`,
          [cvm, asOf],
        )
      : { rows: [] as Record<string, unknown>[] };
    const classes = r
      ? await c.query(
          `SELECT ticker, kind, price, price_date, ceiling, ratio, band, votes, k_required, buy, reason
           FROM ceiling_class WHERE cvm_code = $1 AND as_of = $2::date ORDER BY ticker`,
          [cvm, asOf],
        )
      : { rows: [] as Record<string, unknown>[] };
    const order = ["bazin", "graham", "gordon", "multiples", "dcf"];
    const rows: MethodRow[] = methods.rows
      .map((m) => ({
        method: m.method as string,
        status: m.status as MethodRow["status"],
        value: str(m.value),
        reason: str(m.reason),
        inputs: (m.inputs ?? {}) as Record<string, unknown>,
        source: m.source as string,
        dataBase: str(m.data_base),
        collectedAt: iso(m.collected_at),
      }))
      .sort((a, b) => order.indexOf(a.method) - order.indexOf(b.method));
    return {
      asOf: r ? asOf : null,
      status: r ? (r.status as CeilingTab["status"]) : null,
      ceiling: r ? str(r.ceiling) : null,
      methodsOk: r ? int(r.methods_ok) : null,
      kRequired: r ? int(r.k_required) : null,
      plan: r ? str(r.plan) : null,
      dataBase: r ? str(r.data_base) : null,
      collectedAt: r ? iso(r.collected_at) : null,
      methods: rows,
      classes: classes.rows.map(toClassRow),
    };
  });
}

const SERIES_FROM: Record<keyof YearSeries, [string, string]> = {
  profit: ["lucro_positivo", "profit"],
  roe: ["roe_medio", "roe"],
  dps: ["queda_dividendo_por_acao", "dps"],
  dy: ["dy_medio_liquido", "dy"],
  payout: ["payout_medio", "payout"],
};

function stringMap(v: unknown): Record<string, string> {
  if (!v || typeof v !== "object" || Array.isArray(v)) return {};
  const out: Record<string, string> = {};
  for (const [k, x] of Object.entries(v as Record<string, unknown>)) {
    if (typeof x === "string" || typeof x === "number") out[k] = String(x);
  }
  return out;
}

/** Critérios do retrato mais recente e as séries anuais que o pipeline gravou no detalhe deles. */
export async function loadFilterTab(db: Db, cvm: number): Promise<FilterTab> {
  return readOnly(db, async (c) => {
    const last = await c.query(
      `SELECT as_of, status, data_base, collected_at FROM screen_result
       WHERE cvm_code = $1 ORDER BY as_of DESC LIMIT 1`,
      [cvm],
    );
    const sr = last.rows[0];
    const empty: YearSeries = { profit: {}, roe: {}, dps: {}, dy: {}, payout: {} };
    const out: FilterTab = {
      asOf: sr ? str(sr.as_of) : null,
      status: sr ? str(sr.status) : null,
      dataBase: sr ? str(sr.data_base) : null,
      collectedAt: sr ? iso(sr.collected_at) : null,
      criteria: [],
      series: empty,
      sources: {},
      outliers: [],
    };
    if (sr) {
      const crit = await c.query(
        `SELECT criterion, status, value, threshold, detail FROM screen_criterion
         WHERE cvm_code = $1 AND as_of = $2::date`,
        [cvm, sr.as_of],
      );
      const detail = new Map<string, Record<string, unknown>>();
      for (const k of crit.rows) {
        const d = (k.detail ?? {}) as Record<string, unknown>;
        detail.set(k.criterion, d);
        out.criteria.push({
          criterion: k.criterion,
          status: k.status,
          value: str(k.value),
          threshold: str(k.threshold),
          reason: typeof d.reason === "string" ? d.reason : null,
        } satisfies CriterionRow);
      }
      for (const [key, [criterion, field]] of Object.entries(SERIES_FROM) as [keyof YearSeries, [string, string]][]) {
        out.series[key] = stringMap(detail.get(criterion)?.[field]);
      }
      out.sources = stringMap(detail.get("queda_dividendo_por_acao")?.sources);
    }
    const o = await c.query(
      `SELECT o.reference_date, o.total, o.median, o.ratio, r.decision
       FROM dividend_outlier o LEFT JOIN outlier_review r USING (cvm_code, reference_date)
       WHERE o.cvm_code = $1 ORDER BY o.reference_date`,
      [cvm],
    );
    out.outliers = o.rows.map(
      (x): OutlierRow => ({
        referenceDate: x.reference_date,
        total: x.total,
        median: x.median,
        ratio: x.ratio,
        decision: x.decision ?? null,
      }),
    );
    return out;
  });
}

/** Fechamento semanal (último pregão da semana) do COTAHIST, sem ajuste, e os eventos societários. */
export async function loadPriceTab(
  db: Db,
  cvm: number,
  tickers: string[],
  wanted: string | null,
  period: Period,
): Promise<PriceTab> {
  const ticker = pickTicker(tickers, wanted);
  const empty: PriceTab = {
    tickers,
    ticker,
    points: [],
    events: [],
    ceiling: null,
    ceilingAsOf: null,
    ceilingFrom: null,
    lastQuoteDate: null,
  };
  if (!ticker) return empty;
  return readOnly(db, async (c) => {
    const sec = await c.query("SELECT id FROM security WHERE ticker = $1 ORDER BY last_date DESC LIMIT 1", [ticker]);
    const id = sec.rows[0]?.id;
    if (!id) return empty;
    const lastQ = await c.query("SELECT max(trade_date) AS d FROM quote_daily WHERE security_id = $1", [id]);
    const lastQuoteDate = str(lastQ.rows[0]?.d);
    if (!lastQuoteDate) return empty;

    const pts = await c.query(
      `SELECT trade_date, close FROM (
         SELECT DISTINCT ON (date_trunc('week', trade_date)) trade_date, close
         FROM quote_daily
         WHERE security_id = $1 AND trade_date > ($2::date - make_interval(years => $3::int))
         ORDER BY date_trunc('week', trade_date), trade_date DESC
       ) w ORDER BY trade_date`,
      [id, lastQuoteDate, period],
    );
    const from = str(pts.rows[0]?.trade_date);
    const ev = await c.query(
      `SELECT event_date, factor, source FROM company_event
       WHERE cvm_code = $1 AND event_date >= $2::date ORDER BY event_date`,
      [cvm, from ?? lastQuoteDate],
    );
    const cl = await c.query(
      `SELECT as_of, ceiling FROM ceiling_class
       WHERE cvm_code = $1 AND ticker = $2 AND as_of = ${LATEST_CEILING}`,
      [cvm, ticker],
    );
    const events = ev.rows.map((e) => ({ date: e.event_date as string, factor: e.factor as string, source: e.source as string }));
    return {
      tickers,
      ticker,
      points: pts.rows.map((p) => ({ date: p.trade_date as string, close: p.close as string })),
      events,
      ceiling: str(cl.rows[0]?.ceiling),
      ceilingAsOf: str(cl.rows[0]?.as_of),
      // O teto está na base de ações de hoje: só é comparável ao preço depois do último evento.
      ceilingFrom: events.length ? (events[events.length - 1] as { date: string }).date : null,
      lastQuoteDate,
    };
  });
}

export async function loadOriginTab(db: Db, cvm: number, tickers: string[]): Promise<OriginTab> {
  return readOnly(db, async (c) => {
    const co = await c.query("SELECT cnpj, cvm_sector FROM company WHERE cvm_code = $1", [cvm]);
    const plan = await c.query(
      `SELECT plan FROM ceiling_result WHERE cvm_code = $1 AND plan IS NOT NULL ORDER BY as_of DESC LIMIT 1`,
      [cvm],
    );
    const ov = await c.query("SELECT sector, plan, note FROM company_class_override WHERE cvm_code = $1", [cvm]);
    const ev = await c.query(
      `SELECT event_date, factor, source, date_basis, event_type, known_from, note
       FROM company_event WHERE cvm_code = $1 ORDER BY event_date DESC, source`,
      [cvm],
    );
    const sus = tickers.length
      ? await c.query(
          `SELECT s.ticker, e.event_date, e.factor, e.status
           FROM corporate_event e JOIN security s ON s.id = e.security_id
           WHERE s.ticker = ANY($1::text[]) AND e.status IN ('suspected', 'rejected')
           ORDER BY e.event_date DESC`,
          [tickers],
        )
      : { rows: [] as Record<string, unknown>[] };
    const divs = await c.query(
      `SELECT DISTINCT ON (a.reference_date) a.reference_date, a.jcp, a.dividends, a.dividends_source,
              sf.collected_at, d.note AS override_note, (d.cvm_code IS NOT NULL) AS manual
       FROM indicator_annual a
       JOIN filing f ON f.id = a.filing_id
       JOIN source_file sf ON sf.id = f.source_file_id
       LEFT JOIN dividend_override d ON d.cvm_code = a.cvm_code AND d.reference_date = a.reference_date
       WHERE a.cvm_code = $1
       ORDER BY a.reference_date DESC, f.version DESC`,
      [cvm],
    );
    return {
      cnpj: co.rows[0]?.cnpj ?? "",
      sector: str(co.rows[0]?.cvm_sector),
      plan: str(plan.rows[0]?.plan),
      override: ov.rows[0]
        ? { sector: str(ov.rows[0].sector), plan: str(ov.rows[0].plan), note: str(ov.rows[0].note) }
        : null,
      events: ev.rows.map((e) => ({
        date: e.event_date,
        factor: e.factor,
        source: e.source,
        dateBasis: e.date_basis,
        eventType: str(e.event_type),
        knownFrom: e.known_from,
        note: str(e.note),
      })),
      suspectedEvents: sus.rows.map((e) => ({
        ticker: e.ticker as string,
        date: e.event_date as string,
        factor: e.factor as string,
        status: e.status as string,
      })),
      dividends: divs.rows.map((d) => ({
        referenceDate: d.reference_date,
        jcp: str(d.jcp),
        dividends: str(d.dividends),
        source: str(d.dividends_source),
        manual: d.manual === true,
        note: str(d.override_note),
        collectedAt: iso(d.collected_at),
      })),
    };
  });
}
