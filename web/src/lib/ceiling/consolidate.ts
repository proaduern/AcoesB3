/** Mediana, votos (K), faixas e situação de cada papel. Espelha `consolidate`, `k_for`, `band_for` e `value_class`. */
import { D, dec, type Dec } from "./decimal";
import type { CeilingParams } from "./params";
import type { Band, Consolidated, SimClass, SimMethod, StoredClass } from "./types";

/** Votos exigidos para `n` métodos; nulo com menos que o mínimo configurado. */
export function kFor(n: number, p: CeilingParams): number | null {
  const keys = Object.keys(p.kByMethods).map(Number);
  if (keys.length === 0 || n < Math.min(...keys)) return null;
  const key = Math.max(...keys.filter((m) => m <= n));
  return p.kByMethods[key] ?? null;
}

export function median(values: Dec[]): Dec {
  const v = [...values].sort((a, b) => a.cmp(b));
  const mid = Math.floor(v.length / 2);
  return v.length % 2 === 1 ? (v[mid] as Dec) : (v[mid - 1] as Dec).plus(v[mid] as Dec).div(2);
}

export function consolidate(methods: SimMethod[], p: CeilingParams): Consolidated {
  const values = methods.filter((m) => m.status === "ok" && m.value !== null).map((m) => m.value as Dec);
  const k = kFor(values.length, p);
  return {
    status: k !== null ? "ok" : "insufficient",
    ceiling: values.length > 0 ? median(values) : null,
    methodsOk: values.length,
    kRequired: k,
  };
}

/** Preço ÷ teto: abaixo da faixa forte, compra, manter (até o limite, inclusive) ou cara. */
export function bandFor(ratio: Dec, p: CeilingParams): Band {
  if (ratio.lt(p.bandStrong)) return "strong_buy";
  if (ratio.lt(p.bandBuy)) return "buy";
  if (ratio.lte(p.bandHold)) return "hold";
  return "expensive";
}

/**
 * Teto e situação de um papel. "Compra" = preço abaixo do teto (mediana) **e** abaixo do teto de pelo
 * menos K métodos; com poucos métodos nunca é compra. Unit sem composição legível não tem teto.
 */
export function valueClass(
  c: StoredClass,
  price: Dec,
  methods: SimMethod[],
  cons: Consolidated,
  p: CeilingParams,
): SimClass {
  const base = { ticker: c.ticker, kind: c.kind, multiplier: c.multiplier, price };
  if (c.multiplier === null) {
    return { ...base, ceiling: null, ratio: null, votes: null, kRequired: null, band: null, buy: false, reason: c.reason ?? "sem composição legível" };
  }
  const mult = new D(c.multiplier);
  const ceiling = cons.ceiling !== null ? cons.ceiling.mul(mult) : null;
  const ratio = ceiling !== null && !ceiling.isZero() ? price.div(ceiling) : null;
  const votes = methods.filter((m) => m.status === "ok" && m.value !== null && price.lt((m.value as Dec).mul(mult))).length;
  const buy =
    cons.status === "ok" && ceiling !== null && price.lt(ceiling) && cons.kRequired !== null && votes >= cons.kRequired;
  return {
    ...base,
    ceiling,
    ratio,
    votes,
    kRequired: cons.kRequired,
    band: ratio !== null ? bandFor(ratio, p) : null,
    buy,
    reason: null,
  };
}

/** Preço em texto (ou número) para Decimal; inválido = nulo. */
export const parsePrice = (v: unknown): Dec | null => {
  const d = dec(v);
  return d !== null && d.gt(0) ? d : null;
};
