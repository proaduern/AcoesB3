/** Tela do backtest: tipos do que o pipeline grava, rótulos e regras puras (sem banco e sem React). */
import { UNAVAILABLE, formatNumber, formatPercent } from "./format";

/**
 * Aviso padrão, usado **só** quando a execução não traz o texto (`universe.survivorship_warning`).
 * O texto oficial vem do banco; a faixa nunca some por falta dele.
 */
export const FALLBACK_SURVIVORSHIP =
  "Viés de sobrevivência: o universo do backtest é a lista acompanhada de hoje; empresas canceladas ou que " +
  "nunca entraram na lista não aparecem, e isso tende a favorecer o resultado.";

export const SERIES_ORDER = ["strategy_net", "strategy_gross", "idiv", "ibov", "cdi"] as const;
export type SeriesKey = (typeof SERIES_ORDER)[number];

export const SERIES_LABEL: Record<SeriesKey, string> = {
  strategy_net: "Estratégia (líquida de custos e impostos)",
  strategy_gross: "Estratégia bruta",
  idiv: "IDIV",
  ibov: "Ibovespa",
  cdi: "CDI",
};

/** Rótulos curtos para a legenda do gráfico e os cabeçalhos da tabela por ano. */
export const SERIES_SHORT: Record<SeriesKey, string> = {
  strategy_net: "Estratégia líquida",
  strategy_gross: "Estratégia bruta",
  idiv: "IDIV",
  ibov: "Ibovespa",
  cdi: "CDI",
};

export interface SeriesStats {
  from: string;
  to: string;
  total_return: number | null;
  cagr: number | null;
  volatility: number | null;
  max_drawdown: number | null; // fração positiva (0,35 = queda de 35%)
  drawdown_peak: string | null;
  drawdown_trough: string | null;
}

export interface WindowStats {
  windows: number;
  lost: number;
  lost_share: number | null;
}

export interface Death {
  windows: number;
  lost_windows: number;
  lost_share: number | null;
  windows_rule_triggered: boolean | null;
  extra_drawdown: number | null;
  drawdown_rule_triggered: boolean | null;
  triggered: boolean | null;
}

export interface Segment {
  start: string;
  end: string;
  series: Partial<Record<SeriesKey, SeriesStats | null>>;
  windows: Record<string, WindowStats>;
  death: Death;
}

export interface Flows {
  net_invested?: string | number | null;
  net_final_value?: string | number | null;
  net_fees?: string | number | null;
  net_taxes?: string | number | null;
  net_dividends?: string | number | null;
  net_trades?: number | null;
  net_first_buy?: string | null;
  gross_final_value?: string | number | null;
}

export interface RunMetrics {
  fit?: Segment;
  validation?: Segment;
  flows?: Flows;
}

export interface RunSummary {
  id: number;
  kind: "fit" | "validation";
  scenario: string;
  createdAt: string;
  startDate: string;
  endDate: string;
  contribution: string | null;
  validationStart: string | null;
  deathLostShare: number | null; // limite configurado (fração)
  deathDrawdownPp: number | null; // limite configurado (fração)
  windowYears: number | null;
  metrics: RunMetrics;
  warnings: string[];
  survivorshipWarning: string | null;
  companies: { name: string | null; segment: string | null }[];
  freezeId: number | null;
}

export interface Freeze {
  scenario: string;
  note: string | null;
  frozenAt: string;
}

export interface BacktestOverview {
  fits: RunSummary[]; // última execução de ajuste de cada cenário
  validation: RunSummary | null;
  freeze: Freeze | null;
}

export interface TradeRow {
  seq: number;
  date: string;
  ticker: string;
  side: "buy" | "sell";
  quantity: string;
  price: string;
  fee: string;
  tax: string;
  note: string | null;
}

export interface SeriesPoint {
  date: string;
  value: number;
}

export interface RunDetail {
  series: Partial<Record<SeriesKey, SeriesPoint[]>>;
  trades: TradeRow[];
  tradesTotal: number;
}

/** O texto do aviso: o gravado na execução, ou o padrão quando falta. Nunca vazio. */
export function survivorshipText(run: Pick<RunSummary, "survivorshipWarning"> | null): string {
  const t = run?.survivorshipWarning?.trim();
  return t ? t : FALLBACK_SURVIVORSHIP;
}

// --- Seleção da execução mostrada -----------------------------------------------------------

export const VALIDATION_KEY = "validacao";

type Params = Record<string, string | string[] | undefined>;

/** Execução do gráfico: `?execucao=validacao` ou o nome de um cenário; o resto cai no padrão. */
export function pickRun(params: Params, ov: BacktestOverview): RunSummary | null {
  const v = typeof params.execucao === "string" ? params.execucao : undefined;
  if (v === VALIDATION_KEY && ov.validation) return ov.validation;
  const byName = ov.fits.find((r) => r.scenario === v);
  if (byName) return byName;
  if (ov.validation) return ov.validation;
  const frozen = ov.freeze ? ov.fits.find((r) => r.scenario === ov.freeze?.scenario) : undefined;
  return frozen ?? ov.fits[0] ?? null;
}

export const runKey = (r: RunSummary): string => (r.kind === "validation" ? VALIDATION_KEY : r.scenario);

export function backtestHref(key: string | null, allTrades = false): string {
  const q = new URLSearchParams();
  if (key) q.set("execucao", key);
  if (allTrades) q.set("ordens", "todas");
  const s = q.toString();
  return s ? `/backtest?${s}` : "/backtest";
}

// --- Gráfico: níveis reescalados --------------------------------------------------------------

/** Níveis reescalados para 100 na primeira data da série (cada série tem sua unidade: cota, pontos, CDI). */
export function rebase(points: SeriesPoint[]): SeriesPoint[] {
  const first = points.find((p) => Number.isFinite(p.value) && p.value > 0);
  if (!first) return [];
  return points.filter((p) => Number.isFinite(p.value)).map((p) => ({ date: p.date, value: (p.value / first.value) * 100 }));
}

/** Último ponto de cada ano (a tabela equivalente ao gráfico). */
export function yearEnds(points: SeriesPoint[]): Map<number, SeriesPoint> {
  const out = new Map<number, SeriesPoint>();
  for (const p of points) out.set(Number(p.date.slice(0, 4)), p); // pontos em ordem de data: o último vence
  return out;
}

// --- Texto de medidas ------------------------------------------------------------------------

export const pp = (fraction: number | null | undefined): string =>
  fraction === null || fraction === undefined ? UNAVAILABLE : `${formatNumber(fraction * 100, 1)} p.p.`;

export function lostWindowsText(w: WindowStats | undefined): string {
  if (!w || w.windows === 0) return UNAVAILABLE;
  return `${w.lost} de ${w.windows} (${formatPercent(w.lost_share, 1)})`;
}

export interface DeathRule {
  label: string;
  value: string;
  limit: string;
  triggered: boolean | null;
}

export function deathRules(d: Death, run: Pick<RunSummary, "deathLostShare" | "deathDrawdownPp" | "windowYears">): DeathRule[] {
  const yrs = run.windowYears ?? 5;
  return [
    {
      label: `Janelas móveis de ${yrs} anos perdidas para o IDIV`,
      value: d.windows === 0 ? UNAVAILABLE : `${d.lost_windows} de ${d.windows} (${formatPercent(d.lost_share, 1)})`,
      limit: run.deathLostShare === null ? UNAVAILABLE : `mais de ${formatPercent(run.deathLostShare, 0)} das janelas`,
      triggered: d.windows_rule_triggered,
    },
    {
      label: "Queda máxima da estratégia além da do IDIV",
      value: pp(d.extra_drawdown),
      limit: run.deathDrawdownPp === null ? UNAVAILABLE : `mais de ${pp(run.deathDrawdownPp)}`,
      triggered: d.drawdown_rule_triggered,
    },
  ];
}

export function deathVerdict(d: Death): string {
  if (d.triggered === null) return "Indisponível (faltam janelas ou queda máxima para comparar)";
  return d.triggered ? "ACIONADO" : "Não acionado";
}

/** Anos (com decimais) entre duas datas ISO, para avisar de período curto. */
export function yearsBetween(a: string, b: string): number {
  const ms = Date.UTC(+b.slice(0, 4), +b.slice(5, 7) - 1, +b.slice(8, 10)) - Date.UTC(+a.slice(0, 4), +a.slice(5, 7) - 1, +a.slice(8, 10));
  return ms / (365.25 * 864e5);
}
