/** Regras puras da tela do filtro (sem banco): rótulos, parâmetros da URL e formatação de critérios. */
import { formatBRLCompact, formatNumber, formatPercent, UNAVAILABLE } from "./format";

export const STATUS_ORDER = [
  "approved",
  "rejected",
  "insufficient_history",
  "insufficient_data",
  "stale",
  "not_listed",
  "excluded",
] as const;
export type ScreenStatus = (typeof STATUS_ORDER)[number];

export const STATUS_LABEL: Record<ScreenStatus, string> = {
  approved: "Aprovada",
  rejected: "Reprovada",
  insufficient_history: "Histórico insuficiente",
  insufficient_data: "Dados insuficientes",
  stale: "Dados desatualizados",
  not_listed: "Sem papel mapeado",
  excluded: "Fora do universo",
};

export const CRITERION_ORDER = [
  "lucro_positivo",
  "roe_medio",
  "proventos_todos_os_anos",
  "dy_medio_liquido",
  "payout_medio",
  "queda_dividendo_por_acao",
  "liquidez",
] as const;

export const CRITERION_LABEL: Record<string, string> = {
  lucro_positivo: "Lucro positivo",
  roe_medio: "ROE médio de 5 anos",
  proventos_todos_os_anos: "Proventos em todos os anos",
  dy_medio_liquido: "DY médio líquido de 5 anos",
  payout_medio: "Payout médio",
  queda_dividendo_por_acao: "Quedas do dividendo por ação",
  liquidez: "Liquidez",
};

export const REASON_LABEL: Record<string, string> = {
  data: "falta dado em algum ano da janela",
  history: "menos anos de DFP que a janela",
  no_security: "sem papel negociado no COTAHIST",
  outliers: "anos válidos insuficientes depois de tirar os outliers",
};

export interface CriterionRow {
  criterion: string;
  status: "pass" | "fail" | "unavailable";
  value: string | null;
  threshold: string | null;
  reason: string | null;
}

export interface ScreenRow {
  cvmCode: number;
  name: string;
  sector: string | null;
  tickers: string[];
  status: ScreenStatus;
  dataBase: string | null;
  collectedAt: string | null;
  role: "carteira" | "radar" | null; // nulo = fora da lista acompanhada
  criteria: CriterionRow[];
}

export const PAGE_SIZE = 50;

export interface ScreenFilters {
  status: ScreenStatus | null;
  q: string | null;
  onlyWatch: boolean;
  page: number; // a partir de 1
}

export const NO_SCREEN_FILTER: ScreenFilters = { status: null, q: null, onlyWatch: false, page: 1 };

export function isStatus(v: unknown): v is ScreenStatus {
  return typeof v === "string" && (STATUS_ORDER as readonly string[]).includes(v);
}

export function parseScreenFilters(
  params: Record<string, string | string[] | undefined>,
): ScreenFilters {
  const one = (k: string) => (typeof params[k] === "string" ? (params[k] as string) : undefined);
  const q = one("q")?.trim().slice(0, 60);
  const page = Number.parseInt(one("pagina") ?? "1", 10);
  return {
    status: isStatus(one("status")) ? (one("status") as ScreenStatus) : null,
    q: q ? q : null,
    onlyWatch: one("lista") === "1",
    page: Number.isInteger(page) && page >= 1 && page <= 10_000 ? page : 1,
  };
}

/** Link com os filtros trocados; mudar qualquer filtro volta à página 1. */
export function screenHref(f: ScreenFilters, patch: Partial<ScreenFilters>): string {
  const n = { ...f, page: 1, ...patch };
  const q = new URLSearchParams();
  if (n.status) q.set("status", n.status);
  if (n.q) q.set("q", n.q);
  if (n.onlyWatch) q.set("lista", "1");
  if (n.page > 1) q.set("pagina", String(n.page));
  const s = q.toString();
  return s ? `/filtro?${s}` : "/filtro";
}

/** Escapa `%`, `_` e `\` para uso em ILIKE: a busca é por texto, não por padrão. */
export function escapeLike(q: string): string {
  return q.replace(/[\\%_]/g, (c) => `\\${c}`);
}

const COUNT_UNIT: Record<string, [string, string]> = {
  lucro_positivo: ["ano", "anos"],
  proventos_todos_os_anos: ["ano", "anos"],
  queda_dividendo_por_acao: ["queda", "quedas"],
};

/** Valor do critério no formato dele: contagem, percentual (fração no banco) ou volume em reais. */
export function formatCriterionValue(name: string, value: string | null): string {
  if (value === null) return UNAVAILABLE;
  if (name in COUNT_UNIT) {
    const [one, many] = COUNT_UNIT[name] as [string, string];
    const n = formatNumber(value, 0);
    return n === UNAVAILABLE ? n : `${n} ${n === "1" ? one : many}`;
  }
  if (name === "liquidez") return formatBRLCompact(value);
  return formatPercent(value, 1); // roe_medio, dy_medio_liquido, payout_medio
}

/** O limite vem como texto do pipeline (`> 0.10`); só troca o ponto decimal por vírgula. */
export function formatThreshold(t: string | null): string {
  return t ? t.replace(/(\d)\.(\d)/g, "$1,$2") : UNAVAILABLE;
}

export function reasonText(reason: string | null): string | null {
  if (!reason) return null;
  return REASON_LABEL[reason] ?? reason;
}

/** Critérios que reprovaram ou ficaram indisponíveis, na ordem canônica. */
export function problemCriteria(criteria: CriterionRow[]): { failed: string[]; unavailable: string[] } {
  const rank = (n: string) => {
    const i = (CRITERION_ORDER as readonly string[]).indexOf(n);
    return i === -1 ? 99 : i;
  };
  const sorted = [...criteria].sort((a, b) => rank(a.criterion) - rank(b.criterion));
  const label = (c: CriterionRow) => CRITERION_LABEL[c.criterion] ?? c.criterion;
  return {
    failed: sorted.filter((c) => c.status === "fail").map(label),
    unavailable: sorted.filter((c) => c.status === "unavailable").map(label),
  };
}

export function totalPages(total: number): number {
  return Math.max(1, Math.ceil(total / PAGE_SIZE));
}
