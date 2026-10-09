/** Tipos, rótulos e regras puras da lista acompanhada (sem banco). */

export type Role = "carteira" | "radar";
export type Band = "strong_buy" | "buy" | "hold" | "expensive";

export const BAND_LABEL: Record<Band, string> = {
  strong_buy: "Compra forte",
  buy: "Compra",
  hold: "Manter",
  expensive: "Cara, avaliar venda",
};

export const ROLE_LABEL: Record<Role, string> = { carteira: "Carteira", radar: "Radar" };

export const SCREEN_LABEL: Record<string, string> = {
  approved: "Aprovada",
  rejected: "Reprovada",
  insufficient_history: "Histórico insuficiente",
  insufficient_data: "Dados insuficientes",
  excluded: "Fora do universo",
  stale: "Dados desatualizados",
  not_listed: "Sem papel mapeado",
};

export interface ClassRow {
  ticker: string;
  kind: "on" | "pn" | "unit";
  price: string;
  priceDate: string;
  ceiling: string | null;
  ratio: string | null;
  band: Band | null;
  votes: number | null;
  kRequired: number | null;
  buy: boolean;
  reason: string | null; // por que este papel está sem teto
}

export interface WatchCompany {
  cvmCode: number;
  name: string;
  role: Role;
  segment: string;
  plan: string | null;
  ceilingStatus: "ok" | "insufficient" | null; // nulo = sem preço teto calculado
  methodsOk: number | null;
  kRequired: number | null;
  dataBase: string | null; // último exercício usado
  collectedAt: string | null;
  screenStatus: string | null;
  screenAsOf: string | null;
  classes: ClassRow[];
}

export interface WatchlistData {
  asOf: string | null; // data do último cálculo do preço teto
  companies: WatchCompany[];
}

export interface Filters {
  role: Role | null;
  segment: string | null;
  onlyBuy: boolean;
}

export const NO_FILTER: Filters = { role: null, segment: null, onlyBuy: false };

/** Lê os filtros dos parâmetros da URL; valor desconhecido é ignorado (não filtra por lixo). */
export function parseFilters(params: Record<string, string | string[] | undefined>): Filters {
  const one = (k: string) => {
    const v = params[k];
    return typeof v === "string" ? v : undefined;
  };
  const role = one("papel");
  return {
    role: role === "carteira" || role === "radar" ? role : null,
    segment: one("segmento") || null,
    onlyBuy: one("compra") === "1",
  };
}

/** Aplica os filtros; "só compra" mantém a empresa só com os papéis em compra. */
export function filterCompanies(companies: WatchCompany[], f: Filters): WatchCompany[] {
  return companies
    .filter((c) => (f.role ? c.role === f.role : true))
    .filter((c) => (f.segment ? c.segment === f.segment : true))
    .map((c) => (f.onlyBuy ? { ...c, classes: c.classes.filter((k) => k.buy) } : c))
    .filter((c) => (f.onlyBuy ? c.classes.length > 0 : true));
}

export function segmentsOf(companies: WatchCompany[]): string[] {
  return [...new Set(companies.map((c) => c.segment))].sort((a, b) => a.localeCompare(b, "pt-BR"));
}

/** Link com os filtros trocados (um parâmetro por vez; vazio remove). */
export function filterHref(f: Filters, patch: Partial<Filters>): string {
  const n = { ...f, ...patch };
  const q = new URLSearchParams();
  if (n.role) q.set("papel", n.role);
  if (n.segment) q.set("segmento", n.segment);
  if (n.onlyBuy) q.set("compra", "1");
  const s = q.toString();
  return s ? `/?${s}` : "/";
}

/** Situação em texto: nunca só cor. Sem teto, com poucos métodos ou compra pela regra. */
export function situation(c: Pick<WatchCompany, "ceilingStatus">, k: ClassRow): string {
  if (c.ceilingStatus === null) return "Sem preço teto calculado";
  if (k.ceiling === null) return "Sem teto";
  if (c.ceilingStatus === "insufficient") return "Dados insuficientes";
  if (k.buy) return "COMPRA";
  if (k.band === "strong_buy" || k.band === "buy") return "Abaixo do teto, sem os votos exigidos";
  return k.band ? BAND_LABEL[k.band] : "Sem teto";
}
