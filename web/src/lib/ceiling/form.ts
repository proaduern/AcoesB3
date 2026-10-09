/**
 * Campos do simulador: o texto que a pessoa digita (vírgula ou ponto, percentuais como "6" para 6%)
 * vira os mesmos parâmetros `ceiling.*` de `app_config`. A conversão passa por `paramsFromConfig`, o
 * caminho já coberto pelo teste de paridade.
 */
import { dec, type Dec } from "./decimal";
import { paramsFromConfig, validateParams, type CeilingParams } from "./params";

export type FieldKind = "percent" | "number" | "int" | "bool";

export interface FieldDef {
  id: string; // chave do campo (a mesma de app_config, sem o prefixo "ceiling.")
  label: string;
  kind: FieldKind;
  group: "bazin" | "graham" | "gordon" | "dcf" | "faixas";
  hint?: string;
}

export const GROUP_LABEL: Record<FieldDef["group"], string> = {
  bazin: "Bazin",
  graham: "Graham",
  gordon: "Gordon",
  dcf: "DCF (FCFE)",
  faixas: "Faixas (preço ÷ teto)",
};

export const FIELDS: FieldDef[] = [
  { id: "bazin_rate", label: "Taxa (dividendo médio ÷ taxa)", kind: "percent", group: "bazin" },
  { id: "graham_multiplier", label: "Multiplicador (22,5 × LPA × VPA)", kind: "number", group: "graham" },
  { id: "gordon_k", label: "Retorno exigido (k)", kind: "percent", group: "gordon" },
  { id: "gordon_g_min", label: "Crescimento mínimo (g)", kind: "percent", group: "gordon" },
  { id: "gordon_g_max", label: "Crescimento máximo (g)", kind: "percent", group: "gordon" },
  {
    id: "gordon_min_spread",
    label: "Spread mínimo k − g (p.p.)",
    kind: "percent",
    group: "gordon",
    hint: "Abaixo disto o método sai do cálculo.",
  },
  { id: "dcf_enabled", label: "Incluir o DCF", kind: "bool", group: "dcf" },
  { id: "dcf_rate", label: "Taxa de desconto", kind: "percent", group: "dcf" },
  { id: "dcf_years", label: "Anos projetados", kind: "int", group: "dcf" },
  { id: "dcf_terminal_growth", label: "Crescimento da perpetuidade", kind: "percent", group: "dcf" },
  { id: "dcf_g_min", label: "Crescimento histórico mínimo", kind: "percent", group: "dcf" },
  { id: "dcf_g_max", label: "Crescimento histórico máximo", kind: "percent", group: "dcf" },
  { id: "band_strong", label: "Compra forte abaixo de", kind: "percent", group: "faixas" },
  { id: "band_buy", label: "Compra abaixo de", kind: "percent", group: "faixas" },
  { id: "band_hold", label: "Manter até (inclusive)", kind: "percent", group: "faixas" },
];

/** Campo extra: crescimento do FCFE informado (vazio = o que o pipeline usou). */
export const DCF_GROWTH_FIELD = "dcf_growth";
export const K_PREFIX = "k:";

export type Fields = Record<string, string>;

const KEY = (id: string) => `ceiling.${id}`;

/** Número digitado: "6", "6,5" ou "6.5". Milhar, letras e vazio são recusados. */
export function parseNumber(text: string): Dec | null {
  const t = text.trim().replace(",", ".");
  return /^-?\d+(\.\d+)?$/.test(t) ? dec(t) : null;
}

/** Fração de `app_config` -> texto de percentual ("0.045" vira "4,5"). */
export function percentText(fraction: unknown): string {
  const d = dec(fraction);
  return d === null ? "" : d.mul(100).toString().replace(".", ",");
}

function plainText(v: unknown): string {
  const d = dec(v);
  return d === null ? "" : d.toString().replace(".", ",");
}

/** Texto inicial de cada campo, a partir de `app_config` (os valores que o pipeline usou). */
export function fieldsFromConfig(cfg: Record<string, unknown>): Fields {
  const out: Fields = {};
  for (const f of FIELDS) {
    const v = cfg[KEY(f.id)];
    out[f.id] = f.kind === "bool" ? String(Boolean(v)) : f.kind === "percent" ? percentText(v) : plainText(v);
  }
  const k = cfg[KEY("k_by_methods")];
  if (k && typeof k === "object" && !Array.isArray(k)) {
    for (const [n, votes] of Object.entries(k as Record<string, unknown>)) out[K_PREFIX + n] = plainText(votes);
  }
  out[DCF_GROWTH_FIELD] = "";
  return out;
}

export interface BuiltParams {
  params: CeilingParams | null;
  errors: string[];
}

/** Texto dos campos -> parâmetros. Qualquer campo inválido vira uma mensagem (e não um valor padrão). */
export function buildParams(fields: Fields): BuiltParams {
  const errors: string[] = [];
  const cfg: Record<string, unknown> = {};
  for (const f of FIELDS) {
    const raw = fields[f.id] ?? "";
    if (f.kind === "bool") {
      cfg[KEY(f.id)] = raw === "true";
      continue;
    }
    const n = parseNumber(raw);
    if (n === null) {
      errors.push(`${f.label}: valor inválido.`);
      continue;
    }
    if (f.kind === "int" && !n.isInteger()) {
      errors.push(`${f.label}: use um número inteiro.`);
      continue;
    }
    cfg[KEY(f.id)] = f.kind === "percent" ? n.div(100).toString() : n.toString();
  }
  const kTable: Record<string, number> = {};
  for (const [id, raw] of Object.entries(fields)) {
    if (!id.startsWith(K_PREFIX)) continue;
    const n = parseNumber(raw);
    if (n === null || !n.isInteger() || n.lt(1)) errors.push(`Votos exigidos com ${id.slice(K_PREFIX.length)} métodos: use um inteiro a partir de 1.`);
    else kTable[id.slice(K_PREFIX.length)] = n.toNumber();
  }
  cfg[KEY("k_by_methods")] = kTable;

  let growth: string | null = null;
  const g = (fields[DCF_GROWTH_FIELD] ?? "").trim();
  if (g !== "") {
    const n = parseNumber(g);
    if (n === null) errors.push("Crescimento do FCFE informado: valor inválido.");
    else growth = n.div(100).toString();
  }
  if (errors.length > 0) return { params: null, errors };
  const params = paramsFromConfig(cfg, growth);
  const problems = validateParams(params);
  return problems.length > 0 ? { params: null, errors: problems } : { params, errors: [] };
}

/** Campos que diferem do texto inicial (o valor numérico, não a grafia: "6" e "6,0" são iguais). */
export function changedFields(initial: Fields, now: Fields): string[] {
  const out: string[] = [];
  for (const id of new Set([...Object.keys(initial), ...Object.keys(now)])) {
    const a = initial[id] ?? "";
    const b = now[id] ?? "";
    if (a === b) continue;
    const na = parseNumber(a);
    const nb = parseNumber(b);
    if (na !== null && nb !== null && na.eq(nb)) continue;
    out.push(id);
  }
  return out;
}

