import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { loadDataFreshness } from "./core";
import { createPool } from "./pool";
import { readOnly } from "./readonly";

const url = process.env.TEST_DATABASE_URL;
const MIGRATIONS = join(__dirname, "../../../../pipeline/migrations");

describe.skipIf(!url)("camada de leitura (Postgres de teste)", () => {
  let pool: Pool;

  beforeAll(async () => {
    pool = createPool(url as string);
    // Mesmo esquema do pipeline: as migrações são a fonte da verdade.
    await pool.query("DROP SCHEMA public CASCADE; CREATE SCHEMA public");
    for (const f of readdirSync(MIGRATIONS).filter((n) => n.endsWith(".sql")).sort()) {
      await pool.query(readFileSync(join(MIGRATIONS, f), "utf8"));
    }
  });

  afterAll(async () => {
    await pool?.end();
  });

  it("banco sem cálculo: tudo nulo (indisponível), nunca zero", async () => {
    const f = await loadDataFreshness(pool);
    expect(f).toEqual({
      ceilingAsOf: null,
      ceilingComputedAt: null,
      lastPriceDate: null,
      screenAsOf: null,
      provenance: { source: null, dataBase: null, collectedAt: null },
    });
  });

  it("devolve o cálculo mais recente, datas como texto e procedência", async () => {
    await pool.query(`
      INSERT INTO ceiling_result (as_of, cvm_code, status, methods_ok, k_required, ceiling, data_base, collected_at)
      VALUES ('2026-09-30', 1, 'ok', 4, 3, 10, '2025-12-31', '2026-09-29T12:00:00Z'),
             ('2026-10-05', 1, 'ok', 5, 3, 11, '2025-12-31', '2026-10-04T23:30:00Z'),
             ('2026-10-05', 2, 'insufficient', 2, NULL, NULL, '2024-12-31', '2026-10-03T10:00:00Z')`);
    await pool.query(`
      INSERT INTO ceiling_class (as_of, cvm_code, ticker, kind, multiplier, price, price_date)
      VALUES ('2026-10-05', 1, 'AAAA3', 'on', 1, 9.5, '2026-10-02'),
             ('2026-10-05', 1, 'AAAA4', 'pn', 1, 9.9, '2026-10-01')`);
    await pool.query(`
      INSERT INTO screen_result (as_of, cvm_code, status) VALUES ('2026-10-04', 1, 'approved')`);

    const f = await loadDataFreshness(pool);
    expect(f.ceilingAsOf).toBe("2026-10-05"); // texto puro, sem deslocamento de fuso
    expect(f.lastPriceDate).toBe("2026-10-02");
    expect(f.screenAsOf).toBe("2026-10-04");
    expect(f.ceilingComputedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(f.provenance.dataBase).toBe("2025-12-31"); // o mais recente entre as empresas do cálculo
    expect(f.provenance.collectedAt).toBe("2026-10-04T23:30:00.000Z");
    expect(f.provenance.source).toMatch(/CVM/);
  });

  it("numeric chega como texto, sem perder precisão", async () => {
    const r = await readOnly(pool, (c) =>
      c.query("SELECT ceiling FROM ceiling_result WHERE as_of = '2026-10-05' AND cvm_code = 1"),
    );
    expect(r.rows[0].ceiling).toBe("11.00000000");
  });

  it("transação somente leitura: escrita falha e nada é gravado", async () => {
    await expect(
      readOnly(pool, (c) => c.query("INSERT INTO app_config (key, value) VALUES ('x', '1')")),
    ).rejects.toThrow(/read-only transaction/);
    await expect(
      readOnly(pool, (c) => c.query("UPDATE ceiling_result SET ceiling = 0")),
    ).rejects.toThrow(/read-only transaction/);
    await expect(readOnly(pool, (c) => c.query("DROP TABLE watchlist"))).rejects.toThrow(
      /read-only transaction/,
    );
    const after = await pool.query("SELECT count(*)::int AS n FROM app_config WHERE key = 'x'");
    expect(after.rows[0].n).toBe(0);
  });

  it("a conexão volta ao pool limpa depois do erro", async () => {
    const r = await readOnly(pool, (c) => c.query("SELECT 1 AS ok"));
    expect(r.rows[0].ok).toBe(1);
  });
});
