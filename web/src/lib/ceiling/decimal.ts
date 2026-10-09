import Decimal from "decimal.js";

/**
 * Aritmética do simulador: 28 dígitos e arredondamento par, como o `Decimal` do Python
 * (`ceiling.py`). Uma cópia própria, para não alterar a configuração global usada na formatação.
 */
export const D = Decimal.clone({
  precision: 28,
  rounding: Decimal.ROUND_HALF_EVEN,
  toExpNeg: -1_000_000,
  toExpPos: 1_000_000,
});
export type Dec = InstanceType<typeof D>;

/** Número em texto (como o Postgres e o Python gravam), número ou nulo; qualquer outra coisa = nulo. */
export function dec(v: unknown): Dec | null {
  if (typeof v !== "string" && typeof v !== "number") return null;
  if (typeof v === "string" && v.trim() === "") return null;
  try {
    const d = new D(v);
    return d.isFinite() ? d : null;
  } catch {
    return null;
  }
}
