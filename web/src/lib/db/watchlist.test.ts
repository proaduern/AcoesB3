import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createPool } from "./pool";
import { loadWatchlist } from "./watchlist";

const url = process.env.TEST_DATABASE_URL;
const MIGRATIONS = join(__dirname, "../../../../pipeline/migrations");

describe.skipIf(!url)("lista acompanhada (Postgres de teste)", () => {
  let pool: Pool;

  beforeAll(async () => {
    pool = createPool(url as string);
    await pool.query("DROP SCHEMA public CASCADE; CREATE SCHEMA public");
    for (const f of readdirSync(MIGRATIONS).filter((n) => n.endsWith(".sql")).sort()) {
      await pool.query(readFileSync(join(MIGRATIONS, f), "utf8"));
    }
  });

  afterAll(async () => {
    await pool?.end();
  });

  it("lista vazia e sem cálculo", async () => {
    expect(await loadWatchlist(pool)).toEqual({ asOf: null, companies: [] });
  });

  it("junta lista, teto, papéis e último retrato do filtro", async () => {
    await pool.query(`
      INSERT INTO company (cvm_code, cnpj, name, source) VALUES
        (1, '1', 'Alfa Energia', 'cvm_cad'), (2, '2', 'Beta Banco', 'cvm_cad'),
        (3, '3', 'Gama Radar', 'cvm_cad'), (4, '4', 'Delta Sem Teto', 'cvm_cad')`);
    await pool.query(`
      INSERT INTO watchlist (cvm_code, role, segment) VALUES
        (1, 'carteira', 'energia'), (2, 'carteira', 'bancos'), (3, 'radar', 'energia'), (4, 'radar', 'bancos')`);
    await pool.query(`
      INSERT INTO ceiling_result (as_of, cvm_code, status, methods_ok, k_required, ceiling, plan, data_base, collected_at)
      VALUES ('2026-09-30', 1, 'ok', 4, 3, 99, 'comum', '2024-12-31', '2026-09-29T12:00:00Z'),
             ('2026-10-05', 1, 'ok', 5, 3, 11, 'comum', '2025-12-31', '2026-10-04T23:30:00Z'),
             ('2026-10-05', 2, 'ok', 3, 2, 30, 'banco', '2025-12-31', '2026-10-04T23:30:00Z'),
             ('2026-10-05', 3, 'insufficient', 2, NULL, 8, 'comum', '2025-12-31', '2026-10-04T23:30:00Z')`);
    await pool.query(`
      INSERT INTO ceiling_class (as_of, cvm_code, ticker, kind, multiplier, price, price_date, ceiling, ratio, band, votes, k_required, buy, reason)
      VALUES ('2026-10-05', 1, 'ALFA4', 'pn', 1, 9.9, '2026-10-02', 11, 0.9, 'buy', 3, 3, true, NULL),
             ('2026-10-05', 1, 'ALFA3', 'on', 1, 10.5, '2026-10-02', 11, 0.954545, 'buy', 2, 3, false, NULL),
             ('2026-10-05', 1, 'ALFA11', 'unit', NULL, 31, '2026-10-02', NULL, NULL, NULL, NULL, NULL, false, 'composição ilegível'),
             ('2026-10-05', 2, 'BETA3', 'on', 1, 40, '2026-10-02', 30, 1.333333, 'expensive', 0, 2, false, NULL),
             ('2026-09-30', 1, 'VELHO3', 'on', 1, 1, '2026-09-30', 1, 1, 'hold', 1, 3, false, NULL)`);
    await pool.query(`
      INSERT INTO screen_result (as_of, cvm_code, status) VALUES
        ('2025-12-31', 1, 'rejected'), ('2026-10-04', 1, 'approved'), ('2026-10-04', 2, 'stale')`);

    const w = await loadWatchlist(pool);
    expect(w.asOf).toBe("2026-10-05");
    // carteira antes do radar; dentro do papel, por segmento e nome
    expect(w.companies.map((c) => c.name)).toEqual([
      "Beta Banco",
      "Alfa Energia",
      "Delta Sem Teto",
      "Gama Radar",
    ]);

    const alfa = w.companies.find((c) => c.cvmCode === 1)!;
    expect(alfa).toMatchObject({
      role: "carteira",
      segment: "energia",
      ceilingStatus: "ok",
      methodsOk: 5,
      kRequired: 3,
      dataBase: "2025-12-31",
      screenStatus: "approved", // o retrato mais recente, não o de fim de ano
      screenAsOf: "2026-10-04",
      collectedAt: "2026-10-04T23:30:00.000Z",
    });
    // só os papéis do último cálculo; ordenados por ticker; velho (outra data) fica de fora
    expect(alfa.classes.map((k) => k.ticker)).toEqual(["ALFA11", "ALFA3", "ALFA4"]);
    const unit = alfa.classes[0]!;
    expect(unit).toMatchObject({ ceiling: null, ratio: null, band: null, votes: null, reason: "composição ilegível" });
    const pn = alfa.classes[2]!;
    expect(pn).toMatchObject({ buy: true, band: "buy", votes: 3, kRequired: 3, priceDate: "2026-10-02" });
    expect(pn.price).toBe("9.900000"); // texto: sem perder casas

    const gama = w.companies.find((c) => c.cvmCode === 3)!;
    expect(gama.ceilingStatus).toBe("insufficient");
    expect(gama.kRequired).toBeNull();
    expect(gama.screenStatus).toBeNull(); // sem retrato = indisponível, não "reprovada"
  });

  it("empresa da lista sem cálculo continua na lista, marcada como sem teto", async () => {
    const w = await loadWatchlist(pool);
    const delta = w.companies.find((c) => c.cvmCode === 4)!;
    expect(delta.ceilingStatus).toBeNull();
    expect(delta.dataBase).toBeNull();
    expect(delta.classes).toEqual([]);
  });
});
