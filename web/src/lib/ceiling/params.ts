import { dec, type Dec } from "./decimal";

/**
 * Parâmetros que o simulador pode alterar: os que agem sobre os insumos já gravados. Janelas de
 * exercícios, alíquotas e mínimos de anos mudam *quais* exercícios entram nas médias e exigem os dados
 * brutos, então não estão aqui. Os nomes de `app_config` são os mesmos do pipeline (`ceiling.*`).
 */
export interface CeilingParams {
  bazinRate: Dec;
  grahamMultiplier: Dec;
  gordonK: Dec;
  gordonGMin: Dec;
  gordonGMax: Dec;
  gordonMinSpread: Dec;
  dcfEnabled: boolean;
  dcfRate: Dec;
  dcfYears: number;
  dcfTerminalGrowth: Dec;
  dcfGMin: Dec;
  dcfGMax: Dec;
  /** Crescimento do FCFE informado; nulo = o que o pipeline usou (histórico limitado ou o da empresa). */
  dcfGrowth: Dec | null;
  /** Votos exigidos por quantidade de métodos aplicáveis (`ceiling.k_by_methods`). */
  kByMethods: Record<number, number>;
  bandStrong: Dec;
  bandBuy: Dec;
  bandHold: Dec;
}

export const CONFIG_KEYS = [
  "ceiling.bazin_rate",
  "ceiling.graham_multiplier",
  "ceiling.gordon_k",
  "ceiling.gordon_g_min",
  "ceiling.gordon_g_max",
  "ceiling.gordon_min_spread",
  "ceiling.dcf_enabled",
  "ceiling.dcf_rate",
  "ceiling.dcf_years",
  "ceiling.dcf_terminal_growth",
  "ceiling.dcf_g_min",
  "ceiling.dcf_g_max",
  "ceiling.k_by_methods",
  "ceiling.band_strong",
  "ceiling.band_buy",
  "ceiling.band_hold",
] as const;

function need(cfg: Record<string, unknown>, key: string): unknown {
  if (!(key in cfg) || cfg[key] === null || cfg[key] === undefined) {
    throw new Error(`parâmetro ausente em app_config: ${key}`);
  }
  return cfg[key];
}

function num(cfg: Record<string, unknown>, key: string): Dec {
  const v = need(cfg, key);
  const d = typeof v === "string" || typeof v === "number" ? dec(v) : null;
  if (d === null) throw new Error(`parâmetro inválido em app_config: ${key}`);
  return d;
}

/** Lê os parâmetros de um mapa no formato de `app_config` (chave -> valor JSON). */
export function paramsFromConfig(
  cfg: Record<string, unknown>,
  dcfGrowth: string | number | null = null,
): CeilingParams {
  const kRaw = need(cfg, "ceiling.k_by_methods");
  if (typeof kRaw !== "object" || Array.isArray(kRaw)) throw new Error("ceiling.k_by_methods inválido");
  const kByMethods: Record<number, number> = {};
  for (const [n, k] of Object.entries(kRaw as Record<string, unknown>)) {
    kByMethods[Number(n)] = Number(k);
  }
  const years = Number(need(cfg, "ceiling.dcf_years"));
  const growth = dcfGrowth === null ? null : dec(dcfGrowth);
  if (dcfGrowth !== null && growth === null) throw new Error("crescimento do DCF informado é inválido");
  return {
    bazinRate: num(cfg, "ceiling.bazin_rate"),
    grahamMultiplier: num(cfg, "ceiling.graham_multiplier"),
    gordonK: num(cfg, "ceiling.gordon_k"),
    gordonGMin: num(cfg, "ceiling.gordon_g_min"),
    gordonGMax: num(cfg, "ceiling.gordon_g_max"),
    gordonMinSpread: num(cfg, "ceiling.gordon_min_spread"),
    dcfEnabled: Boolean(need(cfg, "ceiling.dcf_enabled")),
    dcfRate: num(cfg, "ceiling.dcf_rate"),
    dcfYears: years,
    dcfTerminalGrowth: num(cfg, "ceiling.dcf_terminal_growth"),
    dcfGMin: num(cfg, "ceiling.dcf_g_min"),
    dcfGMax: num(cfg, "ceiling.dcf_g_max"),
    dcfGrowth: growth,
    kByMethods,
    bandStrong: num(cfg, "ceiling.band_strong"),
    bandBuy: num(cfg, "ceiling.band_buy"),
    bandHold: num(cfg, "ceiling.band_hold"),
  };
}

/** Problemas que fariam o cálculo dividir por zero ou perder o sentido (texto para a tela). */
export function validateParams(p: CeilingParams): string[] {
  const errors: string[] = [];
  if (!p.bazinRate.gt(0)) errors.push("A taxa do Bazin precisa ser maior que zero.");
  if (p.grahamMultiplier.lt(0)) errors.push("O multiplicador de Graham não pode ser negativo.");
  if (!p.gordonK.gt(0)) errors.push("O retorno exigido (k) do Gordon precisa ser maior que zero.");
  if (p.gordonGMin.gt(p.gordonGMax)) errors.push("O crescimento mínimo do Gordon passa do máximo.");
  if (p.dcfGMin.gt(p.dcfGMax)) errors.push("O crescimento mínimo do DCF passa do máximo.");
  if (!Number.isInteger(p.dcfYears) || p.dcfYears < 1 || p.dcfYears > 50) {
    errors.push("Os anos projetados do DCF precisam ser um inteiro de 1 a 50.");
  }
  if (!p.dcfRate.gt(-1)) errors.push("A taxa de desconto do DCF precisa ser maior que -100%.");
  if (Object.keys(p.kByMethods).length === 0) errors.push("A tabela de votos (K) está vazia.");
  if (!(p.bandStrong.lte(p.bandBuy) && p.bandBuy.lte(p.bandHold))) {
    errors.push("As faixas precisam estar em ordem: compra forte ≤ compra ≤ manter.");
  }
  return errors;
}
