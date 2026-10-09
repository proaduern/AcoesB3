import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import type { Pool } from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { BacktestView } from "@/components/backtest/BacktestView";
import { pickRun } from "@/lib/backtest";
import { TRADES_SHOWN, loadBacktestOverview, loadRunDetail } from "./backtest";
import { createPool } from "./pool";

const url = process.env.TEST_DATABASE_URL;
const MIGRATIONS = join(__dirname, "../../../../pipeline/migrations");

const stats = (cagr: number, mdd: number) => ({
  from: "2012-01-02",
  to: "2023-12-29",
  total_return: 3.5,
  cagr,
  volatility: 0.18,
  max_drawdown: mdd,
  drawdown_peak: "2020-01-02",
  drawdown_trough: "2020-03-23",
});
const segment = (cagr: number) => ({
  start: "2012-01-02",
  end: "2023-12-29",
  series: { strategy_net: stats(cagr, 0.331), idiv: stats(0.099, 0.573), ibov: stats(0.074, 0.468), cdi: stats(0.091, 0) },
  windows: { idiv: { windows: 83, lost: 6, lost_share: 0.0723 } },
  death: { windows: 83, lost_windows: 6, lost_share: 0.0723, windows_rule_triggered: false, extra_drawdown: -0.242, drawdown_rule_triggered: false, triggered: false },
});
const flows = { net_invested: "167000.00", net_final_value: "589700.50", net_fees: "389.00", net_taxes: "10700.00", net_dividends: "131500.00", net_trades: 305, net_first_buy: "2015-03-02" };
const config = (extra: Record<string, unknown> = {}) =>
  JSON.stringify({
    "scenario.contribution": "1000",
    "backtest.validation_start": "2024-01-01",
    "backtest.death_lost_share": 0.5,
    "backtest.death_drawdown_pp": "0.10",
    "backtest.window_years": 5,
    ...extra,
  });

describe.skipIf(!url)("backtest (Postgres de teste)", () => {
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

  it("sem execuções: nada, sem erro", async () => {
    expect(await loadBacktestOverview(pool)).toEqual({ fits: [], validation: null, freeze: null });
  });

  it("última execução de cada cenário, validação, cenário congelado e configuração lida do JSON", async () => {
    const universe = JSON.stringify({
      companies: { "1": { name: "ALFA ENERGIA", segment: "energia" }, "2": { name: "BETA BANCO", segment: "bancos" } },
      survivorship_warning: "Viés de sobrevivência aceito: universo é a lista de hoje.",
    });
    const metricsFit = JSON.stringify({ fit: segment(0.142), flows });
    const insert = (kind: string, scenario: string, hash: string, created: string, cfg: string, uni: string, metrics: string, warnings: string, freeze: number | null) =>
      pool.query(
        `INSERT INTO backtest_run (kind, scenario, freeze_id, cfg_hash, config, start_date, end_date, universe, metrics, warnings, created_at)
         VALUES ($1, $2, $3, $4, $5, '2012-01-02', $6, $7, $8, $9, $10) RETURNING id`,
        [kind, scenario, freeze, hash, cfg, kind === "fit" ? "2023-12-29" : "2025-12-30", uni, metrics, warnings, created],
      );
    await insert("fit", "dy_5", "h1", "2026-10-08T10:00:00Z", config(), universe, metricsFit, JSON.stringify(["aviso 1", "aviso 2"]), null);
    await insert("fit", "aporte_1000", "old", "2026-10-07T10:00:00Z", config(), universe, JSON.stringify({ fit: segment(0.01), flows }), "[]", null);
    await insert("fit", "aporte_1000", "new", "2026-10-08T09:00:00Z", config({ "scenario.contribution": "1000" }), "{}", metricsFit, "[]", null); // sem aviso gravado
    await pool.query(`INSERT INTO backtest_freeze (scenario, cfg_hash, config, note) VALUES ('dy_5', 'h1', '{}', 'escolhido pelo usuário')`);
    await insert(
      "validation",
      "dy_5",
      "h1",
      "2026-10-08T22:00:00Z",
      config(),
      universe,
      JSON.stringify({ fit: segment(0.142), validation: { ...segment(0.154), start: "2024-01-01", end: "2025-12-30" }, flows }),
      JSON.stringify(["aviso da validação"]),
      1,
    );

    const ov = await loadBacktestOverview(pool);
    expect(ov.fits.map((r) => r.scenario)).toEqual(["aporte_1000", "dy_5"]); // um por cenário, por nome
    const aporte = ov.fits[0]!;
    expect(aporte.metrics.fit!.series.strategy_net!.cagr).toBe(0.142); // a mais recente, não a de 0,01
    expect(aporte.survivorshipWarning).toBeNull(); // execução sem o texto: a tela usa o padrão
    expect(aporte.companies).toEqual([]);

    const dy5 = ov.fits[1]!;
    expect(dy5).toMatchObject({
      kind: "fit",
      startDate: "2012-01-02",
      endDate: "2023-12-29",
      contribution: "1000",
      validationStart: "2024-01-01",
      deathLostShare: 0.5,
      deathDrawdownPp: 0.1, // veio como texto no JSON
      windowYears: 5,
      warnings: ["aviso 1", "aviso 2"],
      survivorshipWarning: "Viés de sobrevivência aceito: universo é a lista de hoje.",
      freezeId: null,
    });
    expect(dy5.companies).toEqual([
      { name: "ALFA ENERGIA", segment: "energia" },
      { name: "BETA BANCO", segment: "bancos" },
    ]);
    expect(dy5.createdAt).toBe("2026-10-08T10:00:00.000Z");

    expect(ov.validation).toMatchObject({ kind: "validation", scenario: "dy_5", endDate: "2025-12-30", freezeId: 1, warnings: ["aviso da validação"] });
    expect(ov.validation!.metrics.validation!.start).toBe("2024-01-01");
    expect(ov.validation!.metrics.flows!.net_trades).toBe(305);
    expect(ov.freeze).toMatchObject({ scenario: "dy_5", note: "escolhido pelo usuário" });
    expect(ov.freeze!.frozenAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
  });

  it("configuração ausente ou inválida vira nulo, nunca zero", async () => {
    await pool.query(
      `INSERT INTO backtest_run (kind, scenario, cfg_hash, config, start_date, end_date, universe, metrics, warnings)
       VALUES ('fit', 'sem_config', 'x', '{"backtest.death_lost_share": "abc"}', '2012-01-02', '2023-12-29', '{}', '{}', 'null')`,
    );
    const r = (await loadBacktestOverview(pool)).fits.find((x) => x.scenario === "sem_config")!;
    expect(r).toMatchObject({ contribution: null, validationStart: null, deathLostShare: null, deathDrawdownPp: null, windowYears: null, warnings: [], metrics: {} });
  });

  it("detalhe: séries mensais por nome (só as conhecidas), ordenadas, e as ordens mais recentes primeiro", async () => {
    const id = (await pool.query("SELECT id FROM backtest_run WHERE kind = 'validation'")).rows[0].id as number;
    await pool.query(
      `INSERT INTO backtest_series (run_id, ref_date, series, value) VALUES
         ($1, '2012-02-29', 'strategy_net', 1.01), ($1, '2012-01-31', 'strategy_net', 1.0),
         ($1, '2012-01-31', 'idiv', 2000), ($1, '2012-01-31', 'ibov', 60000), ($1, '2012-01-31', 'cdi', 1.0),
         ($1, '2012-01-31', 'estranha', 5)`,
      [id],
    );
    const values = Array.from({ length: TRADES_SHOWN + 20 }, (_, i) => `(${id}, ${i}, '2015-01-02'::date + ${i}, 'ALFA3', '${i % 2 ? "sell" : "buy"}', 10, 9.5, 0.03, 0, ${i === 0 ? "'primeira compra'" : "NULL"})`);
    await pool.query(`INSERT INTO backtest_trade (run_id, seq, trade_date, ticker, side, quantity, price, fee, tax, note) VALUES ${values.join(",")}`);

    const d = await loadRunDetail(pool, id);
    expect(Object.keys(d.series).sort()).toEqual(["cdi", "ibov", "idiv", "strategy_net"]); // 'estranha' ignorada
    expect(d.series.strategy_net!.map((p) => [p.date, p.value])).toEqual([["2012-01-31", 1], ["2012-02-29", 1.01]]);
    expect(d.tradesTotal).toBe(TRADES_SHOWN + 20);
    expect(d.trades).toHaveLength(TRADES_SHOWN);
    expect(d.trades[0]).toMatchObject({ seq: TRADES_SHOWN + 19, side: "sell" }); // mais recente primeiro
    expect(d.trades[0]!.price).toBe("9.500000"); // texto, sem perder casas
    const all = await loadRunDetail(pool, id, true);
    expect(all.trades).toHaveLength(TRADES_SHOWN + 20);
    expect(all.trades.at(-1)).toMatchObject({ seq: 0, note: "primeira compra" });
  });

  it("detalhe de execução sem séries nem ordens: vazio", async () => {
    const id = (await pool.query("SELECT id FROM backtest_run WHERE scenario = 'sem_config'")).rows[0].id as number;
    expect(await loadRunDetail(pool, id)).toEqual({ series: {}, trades: [], tradesTotal: 0 });
  });

  it("a tela renderiza com o que o banco devolve: aviso gravado, validação medida uma vez, séries e ordens", async () => {
    const ov = await loadBacktestOverview(pool);
    const run = pickRun({}, ov)!;
    expect(run.kind).toBe("validation"); // sem escolha na URL: a validação
    const detail = await loadRunDetail(pool, run.id);
    const html = renderToStaticMarkup(createElement(BacktestView, { overview: ov, run, detail, allTrades: false }));
    expect(html).toContain("Viés de sobrevivência aceito: universo é a lista de hoje."); // texto do banco, não o padrão
    expect(html).toContain("uma única vez");
    expect(html).toContain("escolhido pelo usuário");
    expect(html).toContain("15,4%"); // ao ano na validação
    expect(html).toContain("Não acionado");
    expect(html).toContain("aviso da validação");
    expect(html).toContain("Universo (2 empresas)");
    expect(html).toContain("Mostrando as 50 mais recentes de 70");
    expect(html).toContain("viz-line s1");
  });
});
