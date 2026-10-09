import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import type { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import {
  loadCeilingTab,
  loadCompanyHeader,
  loadFilterTab,
  loadOriginTab,
  loadPriceTab,
} from "./company";
import { createPool } from "./pool";

const url = process.env.TEST_DATABASE_URL;
const MIGRATIONS = join(__dirname, "../../../../pipeline/migrations");

describe.skipIf(!url)("ficha da empresa (Postgres de teste)", () => {
  let pool: Pool;

  beforeAll(async () => {
    pool = createPool(url as string);
    await pool.query("DROP SCHEMA public CASCADE; CREATE SCHEMA public");
    for (const f of readdirSync(MIGRATIONS).filter((n) => n.endsWith(".sql")).sort()) {
      await pool.query(readFileSync(join(MIGRATIONS, f), "utf8"));
    }
    await pool.query(`
      INSERT INTO company (cvm_code, cnpj, name, cvm_sector, source) VALUES
        (1, '11.111.111/0001-11', 'ALFA ENERGIA S.A.', 'Energia Elétrica', 'cvm_cad'),
        (2, '22.222.222/0001-22', 'BETA FORA DA LISTA', 'Bancos', 'cvm_cad')`);
    await pool.query(`INSERT INTO watchlist (cvm_code, role, segment) VALUES (1, 'carteira', 'energia')`);

    // preço teto: dois cálculos; só o último vale
    await pool.query(`
      INSERT INTO ceiling_result (as_of, cvm_code, status, methods_ok, k_required, ceiling, plan, data_base, collected_at) VALUES
        ('2026-09-30', 1, 'ok', 4, 3, 99, 'comum', '2024-12-31', '2026-09-29T12:00:00Z'),
        ('2026-10-05', 1, 'ok', 3, 2, 11, 'comum', '2025-12-31', '2026-10-04T23:30:00Z')`);
    await pool.query(`
      INSERT INTO ceiling_method (as_of, cvm_code, method, status, value, reason, inputs, source, data_base, collected_at) VALUES
        ('2026-10-05', 1, 'dcf', 'unavailable', NULL, 'crescimento histórico indisponível', '{"fcfe": {"2024": "100000000"}}', 'CVM DFC', '2025-12-31', '2026-10-04T23:30:00Z'),
        ('2026-10-05', 1, 'bazin', 'ok', 10, NULL, '{"mean": "0.60", "rate": "0.06", "dps_net": {"2024": "0.55", "2025": "0.65"}}', 'CVM DFP', '2025-12-31', '2026-10-04T23:30:00Z'),
        ('2026-10-05', 1, 'graham', 'excluded', NULL, 'LPA ou VPA não positivo', '{}', 'CVM DFP', '2025-12-31', NULL),
        ('2026-09-30', 1, 'bazin', 'ok', 99, NULL, '{}', 'CVM DFP', '2024-12-31', NULL)`);
    await pool.query(`
      INSERT INTO ceiling_class (as_of, cvm_code, ticker, kind, multiplier, price, price_date, ceiling, ratio, band, votes, k_required, buy) VALUES
        ('2026-10-05', 1, 'ALFA3', 'on', 1, 9.9, '2026-10-02', 11, 0.9, 'buy', 2, 2, true),
        ('2026-10-05', 1, 'ALFA4', 'pn', 1, 9.0, '2026-10-02', 11, 0.818182, 'buy', 2, 2, true)`);

    // filtro
    await pool.query(`INSERT INTO screen_result (as_of, cvm_code, status, data_base, collected_at) VALUES
        ('2025-12-31', 1, 'rejected', '2024-12-31', NULL), ('2026-10-04', 1, 'approved', '2025-12-31', '2026-10-03T12:00:00Z')`);
    await pool.query(`
      INSERT INTO screen_criterion (as_of, cvm_code, criterion, status, value, threshold, detail) VALUES
        ('2026-10-04', 1, 'lucro_positivo', 'pass', 10, '>= 8 de 10 anos', '{"profit": {"2024": "1000000000", "2025": "1200000000"}}'),
        ('2026-10-04', 1, 'roe_medio', 'pass', 0.15, '> 0.10', '{"roe": {"2024": "0.14", "2025": "0.16"}}'),
        ('2026-10-04', 1, 'queda_dividendo_por_acao', 'pass', 2, '<= 4', '{"dps": {"2024": "0.55", "2025": "0.65"}, "sources": {"2024": "dva", "2025": "manual"}}'),
        ('2026-10-04', 1, 'dy_medio_liquido', 'unavailable', NULL, '> 0.05', '{"reason": "data"}'),
        ('2026-10-04', 1, 'payout_medio', 'pass', 0.5, 'entre 0.25 e 1', '{"payout": {"2025": "0.52"}}'),
        ('2025-12-31', 1, 'roe_medio', 'fail', 0.01, '> 0.10', '{"roe": {"2020": "0.01"}}')`);
    await pool.query(`
      INSERT INTO dividend_outlier (cvm_code, reference_date, total, median, ratio, years_used) VALUES
        (1, '2024-12-31', 900, 300, 3, 5), (1, '2023-12-31', 700, 300, 2.3333, 5)`);
    await pool.query(`INSERT INTO outlier_review (cvm_code, reference_date, decision) VALUES (1, '2023-12-31', 'include')`);

    // preço: semana a semana
    await pool.query(`INSERT INTO source_file (source, url, sha256, size_bytes) VALUES ('b3_cotahist', 'u', 's', 1)`);
    await pool.query(`INSERT INTO security (ticker, isin, especi, short_name, first_date, last_date) VALUES
        ('ALFA3', 'BRALFA3', 'ON NM', 'ALFA', '2010-01-04', '2026-10-02'),
        ('ALFA3', 'BROLD3', 'ON', 'ALFA VELHA', '2005-01-03', '2012-01-02')`);
    const day = (d: string, close: number, sec = 1) =>
      `(${sec}, '${d}', ${close}, ${close}, ${close}, ${close}, ${close}, 1, 1, 1, 0, 1)`;
    const days = [
      ["2020-01-06", 5],
      ["2026-09-14", 8], ["2026-09-15", 8.1], ["2026-09-18", 8.5],
      ["2026-09-21", 9], ["2026-09-25", 9.2],
      ["2026-09-28", 9.5], ["2026-10-02", 9.9],
    ] as const;
    await pool.query(
      `INSERT INTO quote_daily (security_id, trade_date, open, high, low, avg, close, trades, quantity, volume, distribution, source_file_id) VALUES ${days
        .map(([d, c]) => day(d, c))
        .join(",")}`,
    );
    await pool.query(`INSERT INTO company_event (cvm_code, event_date, factor, source, date_basis, known_from, event_type) VALUES
        (1, '2019-06-03', 2, 'fre', 'cotahist', '2019-06-10', 'Desdobramento'),
        (1, '2026-09-22', 1.4, 'cotahist', 'cotahist', '2026-09-23', NULL)`);

    // origem
    await pool.query(`INSERT INTO company_class_override (cvm_code, sector, plan, note) VALUES (1, NULL, 'seguradora', 'DVA de seguradora')`);
    await pool.query(`INSERT INTO source_file (source, url, sha256, size_bytes, collected_at) VALUES ('cvm_dfp', 'u2', 's', 1, '2026-10-01T10:00:00Z')`);
    await pool.query(`
      INSERT INTO filing (doc_type, cvm_code, cnpj, reference_date, version, doc_id, received_date, source_file_id, has_lines) VALUES
        ('DFP', 1, '1', '2024-12-31', 1, 10, '2025-03-01', 2, true),
        ('DFP', 1, '1', '2024-12-31', 2, 11, '2025-04-01', 2, true),
        ('DFP', 1, '1', '2025-12-31', 1, 12, '2026-03-01', 2, true)`);
    await pool.query(`
      INSERT INTO indicator_annual (filing_id, cvm_code, reference_date, jcp, dividends, dividends_source)
      SELECT id, cvm_code, reference_date, 10 * version, 100 * version, CASE WHEN reference_date = '2025-12-31' THEN 'manual' ELSE 'dva' END
      FROM filing WHERE doc_type = 'DFP'`);
    await pool.query(`INSERT INTO dividend_override (cvm_code, reference_date, jcp, dividends, source, note) VALUES (1, '2025-12-31', 10, 100, 'manual', 'RI da empresa')`);
    await pool.query(`INSERT INTO corporate_event (security_id, event_date, factor, status, source) VALUES
        (1, '2024-05-10', 2, 'suspected', 'detected'), (1, '2023-05-10', 2, 'confirmed', 'detected'), (1, '2022-05-10', 2, 'rejected', 'detected')`);
  });

  afterAll(async () => {
    await pool?.end();
  });

  it("cabeçalho: só empresa da lista, com os papéis do teto", async () => {
    const h = await loadCompanyHeader(pool, 1);
    expect(h).toEqual({
      cvmCode: 1,
      name: "ALFA ENERGIA S.A.",
      cnpj: "11.111.111/0001-11",
      sector: "Energia Elétrica",
      role: "carteira",
      segment: "energia",
      tickers: ["ALFA3", "ALFA4"],
    });
    expect(await loadCompanyHeader(pool, 2)).toBeNull(); // existe, mas fora da lista
    expect(await loadCompanyHeader(pool, 999)).toBeNull();
  });

  it("preço teto: último cálculo, métodos na ordem e papéis", async () => {
    const t = await loadCeilingTab(pool, 1);
    expect(t).toMatchObject({
      asOf: "2026-10-05",
      status: "ok",
      ceiling: "11.00000000",
      methodsOk: 3,
      kRequired: 2,
      plan: "comum",
      dataBase: "2025-12-31",
      collectedAt: "2026-10-04T23:30:00.000Z",
    });
    expect(t.methods.map((m) => m.method)).toEqual(["bazin", "graham", "dcf"]);
    expect(t.methods[0]).toMatchObject({ status: "ok", value: "10.00000000", reason: null });
    expect(t.methods[0]!.inputs).toMatchObject({ rate: "0.06" });
    expect(t.methods[1]).toMatchObject({ status: "excluded", value: null, collectedAt: null });
    expect(t.methods[2]).toMatchObject({ status: "unavailable", reason: "crescimento histórico indisponível" });
    expect(t.classes.map((k) => k.ticker)).toEqual(["ALFA3", "ALFA4"]);
  });

  it("preço teto de empresa sem cálculo: vazio, não erro", async () => {
    const t = await loadCeilingTab(pool, 2);
    expect(t).toMatchObject({ asOf: null, status: null, ceiling: null, methods: [], classes: [] });
  });

  it("filtro: retrato mais recente, séries anuais do detalhe e outliers com decisão", async () => {
    const f = await loadFilterTab(pool, 1);
    expect(f).toMatchObject({ asOf: "2026-10-04", status: "approved", dataBase: "2025-12-31" });
    expect(f.criteria).toHaveLength(5); // o retrato de fim de ano não entra
    expect(f.series.roe).toEqual({ "2024": "0.14", "2025": "0.16" }); // sem o 2020 do outro retrato
    expect(f.series.profit["2025"]).toBe("1200000000");
    expect(f.series.dps).toEqual({ "2024": "0.55", "2025": "0.65" });
    expect(f.series.dy).toEqual({}); // critério indisponível: sem série, não zero
    expect(f.series.payout).toEqual({ "2025": "0.52" });
    expect(f.sources).toEqual({ "2024": "dva", "2025": "manual" });
    expect(f.criteria.find((c) => c.criterion === "dy_medio_liquido")).toMatchObject({
      status: "unavailable",
      reason: "data",
      value: null,
    });
    expect(f.outliers.map((o) => [o.referenceDate, o.decision])).toEqual([
      ["2023-12-31", "include"],
      ["2024-12-31", null],
    ]);
  });

  it("filtro de empresa sem retrato", async () => {
    const f = await loadFilterTab(pool, 2);
    expect(f).toMatchObject({ asOf: null, status: null, criteria: [], outliers: [] });
    expect(f.series).toEqual({ profit: {}, roe: {}, dps: {}, dy: {}, payout: {} });
  });

  it("preço: fechamento semanal, só o papel vigente, janela e linha do teto depois do último evento", async () => {
    const p = await loadPriceTab(pool, 1, ["ALFA3", "ALFA4"], "ALFA3", 1);
    expect(p.ticker).toBe("ALFA3");
    expect(p.lastQuoteDate).toBe("2026-10-02");
    // 2020 fica fora da janela de 1 ano; um ponto por semana, o último pregão dela
    expect(p.points.map((x) => x.date)).toEqual(["2026-09-18", "2026-09-25", "2026-10-02"]);
    expect(p.points[2]!.close).toBe("9.900000");
    expect(p.events.map((e) => e.date)).toEqual(["2026-09-22"]); // o de 2019 fica fora da janela
    expect(p.ceiling).toBe("11.00000000");
    expect(p.ceilingFrom).toBe("2026-09-22");
  });

  it("preço: janela maior inclui o evento antigo; papel inválido cai no primeiro; sem cotação = vazio", async () => {
    const wide = await loadPriceTab(pool, 1, ["ALFA3", "ALFA4"], "XXXX9", 10);
    expect(wide.ticker).toBe("ALFA3");
    expect(wide.points.map((x) => x.date)[0]).toBe("2020-01-06");
    // eventos só dentro do período com cotação: o de 2019 é anterior ao 1º pregão (2020-01-06)
    expect(wide.events.map((e) => e.date)).toEqual(["2026-09-22"]);
    const noQuotes = await loadPriceTab(pool, 1, ["ALFA3", "ALFA4"], "ALFA4", 5);
    expect(noQuotes).toMatchObject({ ticker: "ALFA4", points: [], ceiling: null });
    const none = await loadPriceTab(pool, 1, [], null, 5);
    expect(none).toMatchObject({ ticker: null, points: [] });
  });

  it("origem: reclassificação, eventos, suspeitos e proventos (última versão, fonte manual)", async () => {
    const o = await loadOriginTab(pool, 1, ["ALFA3"]);
    expect(o).toMatchObject({ cnpj: "11.111.111/0001-11", sector: "Energia Elétrica", plan: "comum" });
    expect(o.override).toEqual({ sector: null, plan: "seguradora", note: "DVA de seguradora" });
    expect(o.events.map((e) => [e.date, e.source])).toEqual([
      ["2026-09-22", "cotahist"],
      ["2019-06-03", "fre"],
    ]);
    expect(o.suspectedEvents.map((e) => e.status)).toEqual(["suspected", "rejected"]); // confirmado não é pendência
    // uma linha por exercício, na última versão (v2 de 2024: 20 e 200)
    expect(o.dividends.map((d) => [d.referenceDate, d.jcp, d.dividends, d.source, d.manual])).toEqual([
      ["2025-12-31", "10.000000", "100.000000", "manual", true],
      ["2024-12-31", "20.000000", "200.000000", "dva", false],
    ]);
    expect(o.dividends[0]!.note).toBe("RI da empresa");
    expect(o.dividends[0]!.collectedAt).toBe("2026-10-01T10:00:00.000Z");
  });
});
