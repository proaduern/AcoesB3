import type { Pool } from "pg";
import { readOnly } from "./readonly";

/** Procedência de um dado exibido: de onde vem, a que data se refere e quando foi coletado. */
export interface Provenance {
  source: string | null;
  dataBase: string | null; // AAAA-MM-DD
  collectedAt: string | null; // ISO
}

export interface DataFreshness {
  ceilingAsOf: string | null; // data-base do último cálculo do preço teto
  ceilingComputedAt: string | null;
  lastPriceDate: string | null; // último fechamento do COTAHIST usado no teto
  screenAsOf: string | null; // data-base do último retrato do filtro
  provenance: Provenance;
}

type Db = Pick<Pool, "connect">;

const iso = (v: unknown): string | null =>
  v instanceof Date ? v.toISOString() : typeof v === "string" ? v : null;

/** O mais recente de cada cálculo. Tabela vazia = nulo (a tela mostra "indisponível"), nunca zero. */
export async function loadDataFreshness(db: Db): Promise<DataFreshness> {
  const row = await readOnly(db, async (c) => {
    const r = await c.query(`
      WITH last AS (SELECT max(as_of) AS as_of FROM ceiling_result)
      SELECT
        (SELECT as_of FROM last) AS ceiling_as_of,
        (SELECT max(computed_at) FROM ceiling_result WHERE as_of = (SELECT as_of FROM last)) AS ceiling_computed_at,
        (SELECT max(collected_at) FROM ceiling_result WHERE as_of = (SELECT as_of FROM last)) AS collected_at,
        (SELECT max(data_base) FROM ceiling_result WHERE as_of = (SELECT as_of FROM last)) AS data_base,
        (SELECT max(price_date) FROM ceiling_class WHERE as_of = (SELECT as_of FROM last)) AS last_price_date,
        (SELECT max(as_of) FROM screen_result) AS screen_as_of
    `);
    return r.rows[0] as Record<string, unknown>;
  });
  const str = (v: unknown) => (typeof v === "string" ? v : null);
  return {
    ceilingAsOf: str(row.ceiling_as_of),
    ceilingComputedAt: iso(row.ceiling_computed_at),
    lastPriceDate: str(row.last_price_date),
    screenAsOf: str(row.screen_as_of),
    provenance: {
      source: row.ceiling_as_of ? "CVM Dados Abertos (DFP/FRE) e B3 (COTAHIST)" : null,
      dataBase: str(row.data_base),
      collectedAt: iso(row.collected_at),
    },
  };
}
