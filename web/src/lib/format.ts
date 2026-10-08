import Decimal from "decimal.js";

/** Texto para dado ausente. Dado ausente nunca vira zero nem valor anterior (CLAUDE.md, seção 10). */
export const UNAVAILABLE = "indisponível";

export type Numeric = string | number | Decimal | null | undefined;

/** Aceita o `numeric` do Postgres (texto) ou número; vazio, nulo e não finito = indisponível. */
function toDecimal(v: Numeric): Decimal | null {
  if (v === null || v === undefined) return null;
  if (typeof v === "string" && v.trim() === "") return null;
  try {
    const d = new Decimal(v);
    return d.isFinite() ? d : null;
  } catch {
    return null;
  }
}

const groupFormat = (digits: number) =>
  new Intl.NumberFormat("pt-BR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

function plain(d: Decimal, digits: number): string {
  return groupFormat(digits).format(Number(d.toDecimalPlaces(digits, Decimal.ROUND_HALF_UP)));
}

export function formatNumber(v: Numeric, digits = 2): string {
  const d = toDecimal(v);
  return d ? plain(d, digits) : UNAVAILABLE;
}

export function formatBRL(v: Numeric, digits = 2): string {
  const d = toDecimal(v);
  if (!d) return UNAVAILABLE;
  const body = `R$ ${plain(d.abs(), digits)}`;
  return d.isNegative() && !d.toDecimalPlaces(digits).isZero() ? `-${body}` : body;
}

const COMPACT: [number, string][] = [
  [1e12, "tri"],
  [1e9, "bi"],
  [1e6, "mi"],
];

/** Valor em reais por extenso curto: 41085000000 -> "R$ 41,09 bi". Abaixo de 1 mi, valor inteiro. */
export function formatBRLCompact(v: Numeric): string {
  const d = toDecimal(v);
  if (!d) return UNAVAILABLE;
  const abs = d.abs();
  for (const [limit, label] of COMPACT) {
    if (abs.gte(limit)) {
      const sign = d.isNegative() ? "-" : "";
      return `${sign}R$ ${plain(abs.div(limit), 2)} ${label}`;
    }
  }
  return formatBRL(d.toString(), 2);
}

/** Fração em percentual: 0.142 -> "14,2%". */
export function formatPercent(fraction: Numeric, digits = 1): string {
  const d = toDecimal(fraction);
  return d ? `${plain(d.mul(100), digits)}%` : UNAVAILABLE;
}

/** Data `AAAA-MM-DD` (ou ISO) -> `DD/MM/AAAA`, sem passar por Date (sem deslocamento de fuso). */
export function formatDate(v: string | null | undefined): string {
  const m = typeof v === "string" ? /^(\d{4})-(\d{2})-(\d{2})/.exec(v) : null;
  return m ? `${m[3]}/${m[2]}/${m[1]}` : UNAVAILABLE;
}

/** Instante ISO -> `DD/MM/AAAA HH:MM` no horário de Brasília. */
export function formatDateTime(v: string | null | undefined): string {
  if (!v) return UNAVAILABLE;
  const t = new Date(v);
  if (Number.isNaN(t.getTime())) return UNAVAILABLE;
  const parts = new Intl.DateTimeFormat("pt-BR", {
    timeZone: "America/Sao_Paulo",
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(t);
  const g = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${g("day")}/${g("month")}/${g("year")} ${g("hour")}:${g("minute")}`;
}

const SCALE_FACTOR = { UNIDADE: 1, MIL: 1000 } as const;
export type Escala = keyof typeof SCALE_FACTOR;

/**
 * ESCALA_MOEDA da CVM, explícita. Os valores do banco **já estão em reais** (o pipeline converte em
 * `cvm.scale_value`), então a tela nunca reescala: use isto só para dado cru com a escala conhecida.
 * Escala desconhecida é erro, como no Python.
 */
export function toReais(value: string, escala: string): string {
  if (!(escala in SCALE_FACTOR)) throw new Error(`ESCALA_MOEDA desconhecida: ${escala}`);
  return new Decimal(value).mul(SCALE_FACTOR[escala as Escala]).toString();
}
