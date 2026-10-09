import type { Dec } from "./decimal";

export const METHODS = ["bazin", "graham", "gordon", "multiples", "dcf"] as const;
export type MethodName = (typeof METHODS)[number];
export type MethodStatus = "ok" | "excluded" | "unavailable";
export type Band = "strong_buy" | "buy" | "hold" | "expensive";

/** Uma linha de `ceiling_method` como o pipeline gravou. */
export interface StoredMethod {
  method: MethodName;
  status: MethodStatus;
  value: string | null;
  reason: string | null;
  inputs: Record<string, unknown>;
}

/** Um papel de `ceiling_class`. `multiplier` nulo = unit sem composição legível (sem teto). */
export interface StoredClass {
  ticker: string;
  kind: "on" | "pn" | "unit";
  multiplier: number | null;
  price: string;
  reason?: string | null;
}

export interface StoredCompany {
  plan: string | null;
  methods: StoredMethod[];
  classes: StoredClass[];
}

export interface SimMethod {
  method: MethodName;
  status: MethodStatus;
  value: Dec | null; // R$ por ação, na base de ações da data-base
  reason: string | null;
  /** Falso: o valor é o gravado (faltam insumos para refazer, ou o método não depende dos parâmetros). */
  recomputed: boolean;
}

export interface Consolidated {
  status: "ok" | "insufficient";
  ceiling: Dec | null;
  methodsOk: number;
  kRequired: number | null;
}

export interface SimClass {
  ticker: string;
  kind: StoredClass["kind"];
  multiplier: number | null;
  price: Dec;
  ceiling: Dec | null;
  ratio: Dec | null;
  votes: number | null;
  kRequired: number | null;
  band: Band | null;
  buy: boolean;
  reason: string | null;
}

export interface Simulation {
  methods: SimMethod[];
  consolidated: Consolidated;
  classes: SimClass[];
}
