import type { Pool } from "pg";
import type { Band, ClassRow, Role, WatchCompany, WatchlistData } from "@/lib/watchlist";
import { readOnly } from "./readonly";

type Db = Pick<Pool, "connect">;

export const iso = (v: unknown): string | null => (v instanceof Date ? v.toISOString() : null);
export const str = (v: unknown): string | null => (typeof v === "string" ? v : null);
export const int = (v: unknown): number | null => (typeof v === "number" ? v : null);

/** Linha de `ceiling_class` -> papel da tela (preço e teto como texto, sem perder casas). */
export function toClassRow(k: Record<string, unknown>): ClassRow {
  return {
    ticker: k.ticker as string,
    kind: k.kind as ClassRow["kind"],
    price: k.price as string,
    priceDate: k.price_date as string,
    ceiling: str(k.ceiling),
    ratio: str(k.ratio),
    band: (k.band as Band | null) ?? null,
    votes: int(k.votes),
    kRequired: int(k.k_required),
    buy: k.buy === true,
    reason: str(k.reason),
  };
}

/**
 * Lista acompanhada com o último preço teto. Parte da `watchlist` (não do teto): empresa sem teto
 * calculado continua na lista, marcada como tal, em vez de sumir.
 */
export async function loadWatchlist(db: Db): Promise<WatchlistData> {
  return readOnly(db, async (c) => {
    const last = await c.query("SELECT max(as_of) AS as_of FROM ceiling_result");
    const asOf = str(last.rows[0]?.as_of);

    const companies = await c.query(
      `SELECT w.cvm_code, co.name, w.role, w.segment,
              r.status AS ceiling_status, r.methods_ok, r.k_required, r.plan, r.data_base, r.collected_at,
              s.status AS screen_status, s.as_of AS screen_as_of
       FROM watchlist w
       JOIN company co USING (cvm_code)
       LEFT JOIN ceiling_result r ON r.cvm_code = w.cvm_code AND r.as_of = $1::date
       LEFT JOIN LATERAL (
         SELECT status, as_of FROM screen_result sr
         WHERE sr.cvm_code = w.cvm_code ORDER BY sr.as_of DESC LIMIT 1
       ) s ON true
       ORDER BY (w.role = 'carteira') DESC, w.segment, co.name`,
      [asOf],
    );

    const classes = await c.query(
      `SELECT cvm_code, ticker, kind, price, price_date, ceiling, ratio, band, votes, k_required, buy, reason
       FROM ceiling_class WHERE as_of = $1::date ORDER BY ticker`,
      [asOf],
    );
    const byCvm = new Map<number, ClassRow[]>();
    for (const k of classes.rows) {
      const row = toClassRow(k);
      byCvm.set(k.cvm_code, [...(byCvm.get(k.cvm_code) ?? []), row]);
    }

    const out: WatchCompany[] = companies.rows.map((r) => ({
      cvmCode: r.cvm_code,
      name: r.name,
      role: r.role as Role,
      segment: r.segment,
      plan: str(r.plan),
      ceilingStatus: r.ceiling_status ?? null,
      methodsOk: int(r.methods_ok),
      kRequired: int(r.k_required),
      dataBase: str(r.data_base),
      collectedAt: iso(r.collected_at),
      screenStatus: str(r.screen_status),
      screenAsOf: str(r.screen_as_of),
      classes: byCvm.get(r.cvm_code) ?? [],
    }));
    return { asOf, companies: out };
  });
}
