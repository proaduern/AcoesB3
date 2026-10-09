import type { Pool } from "pg";
import {
  SERIES_ORDER,
  type BacktestOverview,
  type Freeze,
  type RunDetail,
  type RunMetrics,
  type RunSummary,
  type SeriesKey,
  type TradeRow,
} from "@/lib/backtest";
import { readOnly } from "./readonly";
import { iso, str } from "./watchlist";

type Db = Pick<Pool, "connect">;

export const TRADES_SHOWN = 50;
export const TRADES_MAX = 2000;

const RUN_COLUMNS =
  "id, kind, scenario, created_at, start_date, end_date, config, universe, metrics, warnings, freeze_id";

/** Número gravado em JSON (número ou texto); inválido = nulo, nunca zero. */
function jsonNumber(v: unknown): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "" && Number.isFinite(Number(v))) return Number(v);
  return null;
}

function toRun(r: Record<string, unknown>): RunSummary {
  const config = (r.config ?? {}) as Record<string, unknown>;
  const universe = (r.universe ?? {}) as { companies?: Record<string, { name?: string | null; segment?: string | null }>; survivorship_warning?: unknown };
  const companies = Object.values(universe.companies ?? {}).map((c) => ({ name: c?.name ?? null, segment: c?.segment ?? null }));
  const warnings = Array.isArray(r.warnings) ? (r.warnings as unknown[]).filter((w): w is string => typeof w === "string") : [];
  return {
    id: r.id as number,
    kind: r.kind as RunSummary["kind"],
    scenario: r.scenario as string,
    createdAt: iso(r.created_at) ?? "",
    startDate: r.start_date as string,
    endDate: r.end_date as string,
    contribution: typeof config["scenario.contribution"] === "string" ? (config["scenario.contribution"] as string) : null,
    validationStart: typeof config["backtest.validation_start"] === "string" ? (config["backtest.validation_start"] as string) : null,
    deathLostShare: jsonNumber(config["backtest.death_lost_share"]),
    deathDrawdownPp: jsonNumber(config["backtest.death_drawdown_pp"]),
    windowYears: jsonNumber(config["backtest.window_years"]),
    metrics: (r.metrics ?? {}) as RunMetrics,
    warnings,
    survivorshipWarning: typeof universe.survivorship_warning === "string" ? universe.survivorship_warning : null,
    companies,
    freezeId: typeof r.freeze_id === "number" ? r.freeze_id : null,
  };
}

/** Última execução de ajuste de cada cenário, a validação (se já medida) e o cenário congelado. */
export async function loadBacktestOverview(db: Db): Promise<BacktestOverview> {
  return readOnly(db, async (c) => {
    const fits = await c.query(
      `SELECT DISTINCT ON (scenario) ${RUN_COLUMNS} FROM backtest_run WHERE kind = 'fit'
       ORDER BY scenario, created_at DESC, id DESC`,
    );
    const val = await c.query(`SELECT ${RUN_COLUMNS} FROM backtest_run WHERE kind = 'validation' ORDER BY id DESC LIMIT 1`);
    const fz = await c.query("SELECT scenario, note, frozen_at FROM backtest_freeze ORDER BY id DESC LIMIT 1");
    const freeze: Freeze | null = fz.rows[0]
      ? { scenario: fz.rows[0].scenario, note: str(fz.rows[0].note), frozenAt: iso(fz.rows[0].frozen_at) ?? "" }
      : null;
    return { fits: fits.rows.map(toRun), validation: val.rows[0] ? toRun(val.rows[0]) : null, freeze };
  });
}

/** Séries mensais (níveis) e as ordens mais recentes de uma execução. */
export async function loadRunDetail(db: Db, runId: number, allTrades = false): Promise<RunDetail> {
  return readOnly(db, async (c) => {
    const s = await c.query("SELECT series, ref_date, value FROM backtest_series WHERE run_id = $1 ORDER BY ref_date", [runId]);
    const series: RunDetail["series"] = {};
    for (const r of s.rows) {
      const key = r.series as SeriesKey;
      if (!(SERIES_ORDER as readonly string[]).includes(key)) continue;
      const v = Number(r.value);
      if (!Number.isFinite(v)) continue;
      (series[key] ??= []).push({ date: r.ref_date as string, value: v });
    }
    const total = await c.query("SELECT count(*)::int AS n FROM backtest_trade WHERE run_id = $1", [runId]);
    const t = await c.query(
      `SELECT seq, trade_date, ticker, side, quantity, price, fee, tax, note
       FROM backtest_trade WHERE run_id = $1 ORDER BY seq DESC LIMIT $2`,
      [runId, allTrades ? TRADES_MAX : TRADES_SHOWN],
    );
    const trades: TradeRow[] = t.rows.map((r) => ({
      seq: r.seq,
      date: r.trade_date,
      ticker: r.ticker,
      side: r.side,
      quantity: r.quantity,
      price: r.price,
      fee: r.fee,
      tax: r.tax,
      note: str(r.note),
    }));
    return { series, trades, tradesTotal: total.rows[0].n };
  });
}
