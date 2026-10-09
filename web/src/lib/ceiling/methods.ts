/**
 * Os 5 métodos refeitos a partir dos insumos gravados em `ceiling_method.inputs`.
 * Espelha `pipeline/acoesb3/ceiling.py` função a função (mesmos motivos, mesma ordem de verificações);
 * qualquer mudança lá exige mudar aqui e regerar o fixture de paridade.
 *
 * Quando faltam os insumos para refazer (método excluído pelo plano de contas, indisponível por falta
 * de dado, linha gravada antes de o pipeline guardar o divisor por ação), devolve o valor gravado,
 * marcado com `recomputed: false`: nunca inventa um valor.
 */
import { D, dec, type Dec } from "./decimal";
import type { CeilingParams } from "./params";
import type { SimMethod, StoredMethod } from "./types";

const kept = (m: StoredMethod): SimMethod => ({
  method: m.method,
  status: m.status,
  value: m.status === "ok" ? dec(m.value) : null,
  reason: m.reason,
  recomputed: false,
});

const ok = (m: StoredMethod, value: Dec): SimMethod => ({
  method: m.method,
  status: "ok",
  value,
  reason: null,
  recomputed: true,
});

const no = (m: StoredMethod, status: "excluded" | "unavailable", reason: string): SimMethod => ({
  method: m.method,
  status,
  value: null,
  reason,
  recomputed: true,
});

const clamp = (v: Dec, lo: Dec, hi: Dec): Dec => minOf(maxOf(v, lo), hi);
const maxOf = (a: Dec, b: Dec): Dec => (a.gte(b) ? a : b);
const minOf = (a: Dec, b: Dec): Dec => (a.lte(b) ? a : b);

/** Bazin: dividendo médio líquido por ação ÷ taxa. */
export function bazin(m: StoredMethod, p: CeilingParams): SimMethod {
  const mean = dec(m.inputs.mean);
  if (mean === null) return kept(m);
  if (mean.lte(0)) return no(m, "unavailable", "dividendo médio líquido não positivo");
  return ok(m, mean.div(p.bazinRate));
}

/** Gordon: D1 ÷ (k − g), com g = crescimento histórico limitado a [g_min, g_max]. */
export function gordon(m: StoredMethod, p: CeilingParams): SimMethod {
  const mean = dec(m.inputs.mean);
  const gRaw = dec(m.inputs.g_raw);
  if (mean === null || gRaw === null) return kept(m);
  const g = clamp(gRaw, p.gordonGMin, p.gordonGMax);
  const spread = p.gordonK.minus(g);
  if (spread.lt(p.gordonMinSpread)) return no(m, "excluded", "k − g abaixo do mínimo");
  const d1 = mean.mul(new D(1).plus(g));
  if (d1.lte(0)) return no(m, "unavailable", "dividendo médio líquido não positivo");
  return ok(m, d1.div(spread));
}

/** Graham: √(multiplicador × LPA médio × VPA). */
export function graham(m: StoredMethod, p: CeilingParams): SimMethod {
  const lpa = dec(m.inputs.lpa_mean);
  const vpa = dec(m.inputs.vpa);
  if (lpa === null || vpa === null) return kept(m);
  if (lpa.lte(0) || vpa.lte(0)) return no(m, "excluded", "LPA ou VPA não positivo");
  return ok(m, p.grahamMultiplier.mul(lpa).mul(vpa).sqrt());
}

/** Múltiplos: P/L mediano × LPA médio (ou P/VP mediano × VPA em banco e seguradora). Sem parâmetros. */
export function multiples(m: StoredMethod): SimMethod {
  const median = dec(m.inputs.median);
  const base = m.inputs.kind === "P/VP" ? dec(m.inputs.vpa) : m.inputs.kind === "P/L" ? dec(m.inputs.lpa_mean) : null;
  if (median === null || base === null) return kept(m);
  if (base.lte(0)) return no(m, "excluded", "LPA ou VPA não positivo");
  return ok(m, median.mul(base));
}

const INFORMED = "informado para a empresa";

/** DCF (FCFE): base × crescimento por `dcfYears` anos, mais a perpetuidade, por ação. */
export function dcf(m: StoredMethod, p: CeilingParams): SimMethod {
  const base = dec(m.inputs.base);
  if (base === null) return kept(m);
  if (base.lte(0)) return no(m, "unavailable", "FCFE médio não positivo");
  const shares = dec(m.inputs.shares);
  const factor = dec(m.inputs.shares_factor);
  if (shares === null || factor === null || shares.lte(0)) return kept(m);

  let g: Dec | null;
  if (p.dcfGrowth !== null) g = p.dcfGrowth;
  else if (m.inputs.growth_source === INFORMED) g = dec(m.inputs.g);
  else {
    const gRaw = dec(m.inputs.g_raw);
    g = gRaw === null ? null : clamp(gRaw, p.dcfGMin, p.dcfGMax);
  }
  if (g === null) return kept(m); // crescimento histórico indisponível: pede o crescimento da empresa

  const k = p.dcfRate;
  const gt = p.dcfTerminalGrowth;
  if (k.lte(gt)) return no(m, "excluded", "taxa de desconto não supera a perpetuidade");

  const one = new D(1);
  let flow = base;
  let pv = new D(0);
  for (let i = 1; i <= p.dcfYears; i++) {
    flow = flow.mul(one.plus(g));
    pv = pv.plus(flow.div(one.plus(k).pow(i)));
  }
  const terminal = flow.mul(one.plus(gt)).div(k.minus(gt)).div(one.plus(k).pow(p.dcfYears));
  const total = pv.plus(terminal);
  return ok(m, total.div(shares).div(factor));
}
