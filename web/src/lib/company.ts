/** Ficha da empresa: tipos, abas, parâmetros da URL e descrição dos insumos (sem banco). */
import {
  UNAVAILABLE,
  formatBRL,
  formatBRLCompact,
  formatNumber,
  formatPercent,
} from "./format";
import type { ClassRow, Role } from "./watchlist";
import type { CriterionRow } from "./screen";

export const TABS = ["teto", "filtro", "preco", "origem"] as const;
export type Tab = (typeof TABS)[number];
export const TAB_LABEL: Record<Tab, string> = {
  teto: "Preço teto",
  filtro: "Filtro",
  preco: "Preço",
  origem: "Origem dos dados",
};

export const PERIODS = [1, 3, 5, 10] as const;
export type Period = (typeof PERIODS)[number];
export const DEFAULT_PERIOD: Period = 5;

type Params = Record<string, string | string[] | undefined>;
const one = (p: Params, k: string) => (typeof p[k] === "string" ? (p[k] as string) : undefined);

export function parseTab(p: Params): Tab {
  const v = one(p, "aba");
  return (TABS as readonly string[]).includes(v ?? "") ? (v as Tab) : "teto";
}

export function parsePeriod(p: Params): Period {
  const n = Number.parseInt(one(p, "periodo") ?? "", 10);
  return (PERIODS as readonly number[]).includes(n) ? (n as Period) : DEFAULT_PERIOD;
}

/** Só aceita o ticker na forma de papel da B3; o resto é ignorado (o valor vai para uma consulta). */
export function parseTicker(p: Params): string | null {
  const v = one(p, "papel")?.toUpperCase();
  return v && /^[A-Z0-9]{4,6}$/.test(v) ? v : null;
}

export function parseCvm(raw: string): number | null {
  return /^\d{1,7}$/.test(raw) ? Number(raw) : null;
}

export function companyHref(cvm: number, patch: { aba?: Tab; papel?: string | null; periodo?: Period } = {}): string {
  const q = new URLSearchParams();
  if (patch.aba && patch.aba !== "teto") q.set("aba", patch.aba);
  if (patch.papel) q.set("papel", patch.papel);
  if (patch.periodo && patch.periodo !== DEFAULT_PERIOD) q.set("periodo", String(patch.periodo));
  const s = q.toString();
  return s ? `/empresa/${cvm}?${s}` : `/empresa/${cvm}`;
}

// --- Dados da ficha --------------------------------------------------------

export interface CompanyHeader {
  cvmCode: number;
  name: string;
  cnpj: string;
  sector: string | null;
  role: Role;
  segment: string;
  tickers: string[]; // papéis com preço teto
}

export const METHOD_ORDER = ["bazin", "graham", "gordon", "multiples", "dcf"] as const;
export const METHOD_LABEL: Record<string, string> = {
  bazin: "Bazin",
  graham: "Graham",
  gordon: "Gordon",
  multiples: "Múltiplos (P/L ou P/VP)",
  dcf: "DCF (FCFE)",
};
export const METHOD_STATUS_LABEL: Record<string, string> = {
  ok: "Aplicável",
  excluded: "Excluído pela regra",
  unavailable: "Indisponível",
};

export interface MethodRow {
  method: string;
  status: "ok" | "excluded" | "unavailable";
  value: string | null; // R$ por ação, na base de ações da data-base
  reason: string | null;
  inputs: Record<string, unknown>;
  source: string;
  dataBase: string | null;
  collectedAt: string | null;
}

export interface CeilingTab {
  asOf: string | null;
  status: "ok" | "insufficient" | null;
  ceiling: string | null;
  methodsOk: number | null;
  kRequired: number | null;
  plan: string | null;
  dataBase: string | null;
  collectedAt: string | null;
  methods: MethodRow[];
  classes: ClassRow[];
}

export interface YearSeries {
  profit: Record<string, string>; // reais
  roe: Record<string, string>; // fração
  dps: Record<string, string>; // R$ por ação
  dy: Record<string, string>; // fração
  payout: Record<string, string>; // fração
}

export interface OutlierRow {
  referenceDate: string;
  total: string;
  median: string;
  ratio: string;
  decision: "include" | "exclude" | null;
}

export interface FilterTab {
  asOf: string | null;
  status: string | null;
  dataBase: string | null;
  collectedAt: string | null;
  criteria: CriterionRow[];
  series: YearSeries;
  sources: Record<string, string>; // ano -> fonte do provento
  outliers: OutlierRow[];
}

export interface PricePoint {
  date: string;
  close: string;
}
export interface PriceEvent {
  date: string;
  factor: string;
  source: string;
}
export interface PriceTab {
  tickers: string[];
  ticker: string | null;
  points: PricePoint[];
  events: PriceEvent[];
  ceiling: string | null; // teto do papel (R$), na base de ações de hoje
  ceilingAsOf: string | null;
  ceilingFrom: string | null; // a linha só vale a partir daqui (depois do último evento societário)
  lastQuoteDate: string | null;
}

export interface OriginTab {
  cnpj: string;
  sector: string | null;
  plan: string | null;
  override: { sector: string | null; plan: string | null; note: string | null } | null;
  events: {
    date: string;
    factor: string;
    source: string;
    dateBasis: string;
    eventType: string | null;
    knownFrom: string;
    note: string | null;
  }[];
  suspectedEvents: { ticker: string; date: string; factor: string; status: string }[];
  dividends: {
    referenceDate: string;
    jcp: string | null;
    dividends: string | null;
    source: string | null;
    manual: boolean;
    note: string | null;
    collectedAt: string | null;
  }[];
}

// --- Insumos dos métodos ---------------------------------------------------

export interface InputLine {
  label: string;
  value: string;
}

type Fmt = (v: unknown) => string;
const asNum = (v: unknown): string | number | null =>
  typeof v === "string" || typeof v === "number" ? v : null;

const pct: Fmt = (v) => formatPercent(asNum(v), 2);
const brl: Fmt = (v) => formatBRL(asNum(v));
const brlCompact: Fmt = (v) => formatBRLCompact(asNum(v));
const num: Fmt = (v) => formatNumber(asNum(v), 2);
const int: Fmt = (v) => formatNumber(asNum(v), 0);
const text: Fmt = (v) => (typeof v === "string" ? v : v == null ? UNAVAILABLE : String(v));
const years: Fmt = (v) => (Array.isArray(v) ? (v.length ? v.join(", ") : "nenhum") : text(v));

function yearMap(f: Fmt): Fmt {
  return (v) => {
    if (!v || typeof v !== "object" || Array.isArray(v)) return text(v);
    const entries = Object.entries(v as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b));
    return entries.length ? entries.map(([y, x]) => `${y}: ${f(x)}`).join(" · ") : "nenhum";
  };
}

const growthFmt: Fmt = (v) => {
  const g = v as { first?: unknown; last?: unknown; first_year?: unknown; last_year?: unknown } | null;
  if (!g || typeof g !== "object") return text(v);
  if ("first" in g) {
    return `${brlCompact(g.first)} (${text(g.first_year)}) → ${brlCompact(g.last)} (${text(g.last_year)})`;
  }
  return JSON.stringify(v);
};

const KEYS: Record<string, [string, Fmt]> = {
  dps_net: ["Dividendo líquido por ação, por ano", yearMap(brl)],
  mean: ["Dividendo médio líquido por ação", brl],
  rate: ["Taxa", pct],
  outlier_years: ["Anos de outlier (fora da média)", years],
  missing_years: ["Anos faltando", years],
  g_raw: ["Crescimento histórico (sem limite)", pct],
  g: ["Crescimento usado", pct],
  k: ["Retorno exigido (k)", pct],
  d1: ["Dividendo do próximo ano (D1)", brl],
  growth: ["Dividendo total bruto, pontas da janela", growthFmt],
  lpa: ["LPA por ano", yearMap(brl)],
  lpa_mean: ["LPA médio", brl],
  vpa: ["VPA", brl],
  vpa_year: ["Exercício do VPA", text],
  multiplier: ["Multiplicador de Graham", num],
  ratios: ["Múltiplo por ano", yearMap(num)],
  median: ["Múltiplo mediano", num],
  kind: ["Tipo de múltiplo", text],
  skipped: ["Anos fora da mediana", yearMap(text)],
  valid_years: ["Anos válidos", int],
  fcfe: ["FCFE por ano", yearMap(brlCompact)],
  base: ["FCFE base (média)", brlCompact],
  base_years: ["Anos da base", years],
  growth_source: ["Origem do crescimento", text],
  terminal_growth: ["Perpetuidade", pct],
  years: ["Anos projetados", int],
  pv_projection: ["Valor presente da projeção", brlCompact],
  pv_terminal: ["Valor presente da perpetuidade", brlCompact],
  equity_value: ["Valor total das ações", brlCompact],
  why: ["Motivo por ano", yearMap(text)],
  plan: ["Plano de contas", text],
};

// Detalhe longo do DCF: fica no comando `acoesb3 ceilings list --dcf`, não na ficha.
const HIDDEN = new Set(["fcfe_detail"]);

/** Insumos gravados em `ceiling_method.inputs`, em português e no formato de cada um. */
export function describeInputs(inputs: Record<string, unknown>): InputLine[] {
  const lines: InputLine[] = [];
  for (const [key, value] of Object.entries(inputs)) {
    if (HIDDEN.has(key) || value === null || value === undefined) continue;
    const known = KEYS[key];
    if (known) lines.push({ label: known[0], value: known[1](value) });
    else lines.push({ label: key, value: typeof value === "object" ? JSON.stringify(value) : String(value) });
  }
  return lines;
}

/** Tickers de uma ficha: o escolhido na URL se existir na lista, senão o primeiro. */
export function pickTicker(tickers: string[], wanted: string | null): string | null {
  if (wanted && tickers.includes(wanted)) return wanted;
  return tickers[0] ?? null;
}

/** Anos presentes em qualquer série, em ordem crescente. */
export function seriesYears(s: YearSeries): number[] {
  const set = new Set<number>();
  for (const m of Object.values(s)) for (const y of Object.keys(m)) set.add(Number(y));
  return [...set].filter(Number.isFinite).sort((a, b) => a - b);
}
