import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { NO_SCREEN_FILTER, PAGE_SIZE } from "@/lib/screen";
import { createPool } from "./pool";
import { loadPending, loadScreen } from "./screen";

const url = process.env.TEST_DATABASE_URL;
const MIGRATIONS = join(__dirname, "../../../../pipeline/migrations");

describe.skipIf(!url)("filtro da B3 (Postgres de teste)", () => {
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

  it("sem retrato calculado", async () => {
    expect(await loadScreen(pool, NO_SCREEN_FILTER)).toEqual({
      asOf: null,
      counts: {},
      total: 0,
      page: 1,
      pages: 1,
      rows: [],
    });
  });

  it("busca, status, lista, contagens e critérios", async () => {
    await pool.query(`
      INSERT INTO company (cvm_code, cnpj, name, trade_name, cvm_sector, source) VALUES
        (1, '1', 'ALFA ENERGIA S.A.', 'Alfa', 'Energia Elétrica', 'cvm_cad'),
        (2, '2', 'BETA BANCO S.A.', 'Beta', 'Bancos', 'cvm_cad'),
        (3, '3', 'GAMA 100% LTDA', NULL, 'Comércio', 'cvm_cad'),
        (4, '4', 'DELTA S.A.', NULL, NULL, 'cvm_cad')`);
    await pool.query(`INSERT INTO watchlist (cvm_code, role, segment) VALUES (1, 'carteira', 'energia')`);
    await pool.query(`
      INSERT INTO screen_result (as_of, cvm_code, status, data_base, collected_at) VALUES
        ('2025-12-31', 2, 'approved', '2024-12-31', now()),
        ('2026-10-04', 1, 'approved', '2025-12-31', '2026-10-03T12:00:00Z'),
        ('2026-10-04', 2, 'rejected', '2025-12-31', '2026-10-03T12:00:00Z'),
        ('2026-10-04', 3, 'insufficient_history', NULL, NULL),
        ('2026-10-04', 4, 'not_listed', '2020-12-31', NULL)`);
    await pool.query(`
      INSERT INTO screen_criterion (as_of, cvm_code, criterion, status, value, threshold, detail) VALUES
        ('2026-10-04', 2, 'roe_medio', 'fail', 0.08, '> 0.10', '{}'),
        ('2026-10-04', 2, 'liquidez', 'pass', 12500000, 'volume >= 1000000 e presença >= 0.9', '{}'),
        ('2026-10-04', 2, 'dy_medio_liquido', 'unavailable', NULL, '> 0.05', '{"reason": "data"}'),
        ('2026-10-04', 3, 'lucro_positivo', 'unavailable', NULL, '', '{"reason": "history"}'),
        ('2025-12-31', 2, 'roe_medio', 'pass', 0.2, '> 0.10', '{}')`);

    const all = await loadScreen(pool, NO_SCREEN_FILTER);
    expect(all.asOf).toBe("2026-10-04"); // só o retrato mais recente
    expect(all.total).toBe(4);
    expect(all.counts).toEqual({ approved: 1, rejected: 1, insufficient_history: 1, not_listed: 1 });
    // a lista acompanhada vem primeiro, depois por nome
    expect(all.rows.map((r) => r.name)).toEqual([
      "ALFA ENERGIA S.A.",
      "BETA BANCO S.A.",
      "DELTA S.A.",
      "GAMA 100% LTDA",
    ]);
    expect(all.rows[0]).toMatchObject({ role: "carteira", status: "approved", dataBase: "2025-12-31" });
    expect(all.rows[1]).toMatchObject({ role: null, sector: "Bancos" });
    expect(all.rows[2]).toMatchObject({ sector: null, dataBase: "2020-12-31", criteria: [] });

    const beta = all.rows[1]!;
    expect(beta.criteria.map((c) => [c.criterion, c.status, c.value, c.reason]).sort()).toEqual([
      ["dy_medio_liquido", "unavailable", null, "data"],
      ["liquidez", "pass", "12500000.00000000", null],
      ["roe_medio", "fail", "0.08000000", null], // o retrato de fim de ano (0.2) não entra
    ]);

    const rejected = await loadScreen(pool, { ...NO_SCREEN_FILTER, status: "rejected" });
    expect(rejected.rows.map((r) => r.cvmCode)).toEqual([2]);
    expect(rejected.total).toBe(1);
    expect(rejected.counts.approved).toBe(1); // contagens não somem ao filtrar por status

    const lista = await loadScreen(pool, { ...NO_SCREEN_FILTER, onlyWatch: true });
    expect(lista.rows.map((r) => r.cvmCode)).toEqual([1]);

    const busca = await loadScreen(pool, { ...NO_SCREEN_FILTER, q: "banco" });
    expect(busca.rows.map((r) => r.cvmCode)).toEqual([2]);
    const trade = await loadScreen(pool, { ...NO_SCREEN_FILTER, q: "alfa" });
    expect(trade.rows.map((r) => r.cvmCode)).toEqual([1]);
  });

  it("curingas na busca não casam tudo", async () => {
    const pct = await loadScreen(pool, { ...NO_SCREEN_FILTER, q: "%" });
    expect(pct.rows.map((r) => r.cvmCode)).toEqual([3]); // só o nome com "%" literal
    const und = await loadScreen(pool, { ...NO_SCREEN_FILTER, q: "_" });
    expect(und.total).toBe(0);
  });

  it("busca por ticker do FCA (prefixo, sem diferenciar caixa) e mostra os tickers", async () => {
    await pool.query(`INSERT INTO source_file (source, url, sha256, size_bytes) VALUES ('cvm_fca', 'u1', 's', 1)`);
    await pool.query(`
      INSERT INTO filing (doc_type, cvm_code, cnpj, reference_date, version, doc_id, received_date, source_file_id)
      VALUES ('FCA', 2, '2', '2025-12-31', 1, 1, '2026-03-01', 1), ('FCA', 4, '4', '2025-12-31', 1, 2, '2026-03-01', 1)`);
    await pool.query(`
      INSERT INTO company_security (cvm_code, ticker, security_type, filing_id) VALUES
        (2, 'BETA3', 'Ações Ordinárias', 1), (2, 'BETA4', 'Ações Preferenciais', 1), (4, '', 'Ações Ordinárias', 2)`);
    const r = await loadScreen(pool, { ...NO_SCREEN_FILTER, q: "beta4" });
    expect(r.rows.map((x) => x.cvmCode)).toEqual([2]);
    expect(r.rows[0]!.tickers).toEqual(["BETA3", "BETA4"]);
    const prefix = await loadScreen(pool, { ...NO_SCREEN_FILTER, q: "BETA" });
    expect(prefix.rows.map((x) => x.cvmCode)).toEqual([2]);
    const none = await loadScreen(pool, { ...NO_SCREEN_FILTER, q: "DELTA" });
    expect(none.rows[0]!.tickers).toEqual([]); // ticker vazio do FCA não vira "ticker"
  });

  it("paginação: página além do fim é ajustada à última", async () => {
    const values = Array.from({ length: PAGE_SIZE + 5 }, (_, i) => `(${1000 + i}, '${1000 + i}', 'EMPRESA ${String(i).padStart(3, "0")}', 'cvm_cad')`);
    await pool.query(`INSERT INTO company (cvm_code, cnpj, name, source) VALUES ${values.join(",")}`);
    const screens = Array.from({ length: PAGE_SIZE + 5 }, (_, i) => `('2026-10-04', ${1000 + i}, 'rejected')`);
    await pool.query(`INSERT INTO screen_result (as_of, cvm_code, status) VALUES ${screens.join(",")}`);

    const p1 = await loadScreen(pool, { ...NO_SCREEN_FILTER, status: "rejected" });
    expect(p1.total).toBe(PAGE_SIZE + 5 + 1); // + a BETA reprovada
    expect(p1.pages).toBe(2);
    expect(p1.rows).toHaveLength(PAGE_SIZE);
    const p2 = await loadScreen(pool, { ...NO_SCREEN_FILTER, status: "rejected", page: 2 });
    expect(p2.rows).toHaveLength(6);
    const beyond = await loadScreen(pool, { ...NO_SCREEN_FILTER, status: "rejected", page: 50 });
    expect(beyond.page).toBe(2);
    expect(beyond.rows).toHaveLength(6);
    // sem repetir empresa entre páginas
    const ids = new Set([...p1.rows, ...p2.rows].map((r) => r.cvmCode));
    expect(ids.size).toBe(PAGE_SIZE + 6);
  });

  it("pendências: outliers da lista sem decisão, eventos suspeitos e dividendos a lançar", async () => {
    await pool.query(`
      INSERT INTO dividend_outlier (cvm_code, reference_date, total, median, ratio, years_used) VALUES
        (1, '2023-12-31', 900, 300, 3, 5), (1, '2022-12-31', 700, 300, 2.3333, 5),
        (2, '2023-12-31', 800, 100, 8, 5)`);
    await pool.query(`INSERT INTO outlier_review (cvm_code, reference_date, decision) VALUES (1, '2022-12-31', 'include')`);
    await pool.query(`
      INSERT INTO security (ticker, isin, especi, short_name, first_date, last_date)
      VALUES ('ALFA3', 'BRALFA', 'ON NM', 'ALFA', '2010-01-04', '2026-10-02')`);
    await pool.query(`
      INSERT INTO corporate_event (security_id, event_date, factor, status, source) VALUES
        (1, '2024-05-10', 2, 'suspected', 'detected'),
        (1, '2022-03-01', 1.1, 'confirmed', 'detected'),
        (1, '2021-03-01', 0.1, 'auto', 'detected')`);
    await pool.query(`
      INSERT INTO source_file (source, url, sha256, size_bytes) VALUES ('cvm_dfp', 'u2', 's', 1)`);
    await pool.query(`
      INSERT INTO filing (doc_type, cvm_code, cnpj, reference_date, version, doc_id, received_date, source_file_id)
      VALUES ('DFP', 1, '1', '2021-12-31', 1, 10, '2022-03-01', 2), ('DFP', 1, '1', '2022-12-31', 1, 11, '2023-03-01', 2),
             ('DFP', 2, '2', '2021-12-31', 1, 12, '2022-03-01', 2)`);
    await pool.query(`
      INSERT INTO indicator_annual (filing_id, cvm_code, reference_date, notes)
      SELECT id, cvm_code, reference_date, '{"dividends": "DVA zerada depois do último pagamento do FRE"}'::jsonb
      FROM filing WHERE doc_type = 'DFP'`);

    const p = await loadPending(pool);
    expect(p.outliersTotal).toBe(2); // B3 inteira, sem decisão
    expect(p.outliers.map((o) => [o.cvmCode, o.referenceDate])).toEqual([[1, "2023-12-31"]]); // só a lista
    expect(p.eventsTotal).toBe(1); // só o suspeito
    expect(p.events).toMatchObject([{ ticker: "ALFA3", eventDate: "2024-05-10" }]);
    // DVA zerada: só empresa da lista (a 2 não está), com os anos
    expect(p.dividendsToEnter).toEqual([{ cvmCode: 1, name: "ALFA ENERGIA S.A.", years: [2021, 2022] }]);
  });
});
