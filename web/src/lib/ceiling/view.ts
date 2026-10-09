/**
 * Visão do simulador: o que está gravado ao lado do que sai com os campos digitados. Sem React e sem
 * banco, para ser testada direto; o componente só desenha.
 */
import { situation, type ClassRow } from "@/lib/watchlist";
import { D, dec, type Dec } from "./decimal";
import { buildParams, changedFields, DCF_GROWTH_FIELD, fieldsFromConfig, type Fields } from "./form";
import { simulate } from "./simulate";
import type { MethodName, MethodStatus, SimClass, SimMethod, Simulation, StoredCompany } from "./types";

/** Tudo o que a tela precisa do servidor: o gravado e os parâmetros que o pipeline usou. */
export interface SimulatorData {
  asOf: string;
  dataBase: string | null;
  collectedAt: string | null;
  plan: string | null;
  config: Record<string, unknown>; // app_config (ceiling.*)
  company: StoredCompany; // métodos com insumos e papéis com multiplicador
  stored: {
    status: "ok" | "insufficient";
    ceiling: string | null;
    methodsOk: number;
    kRequired: number | null;
    classes: ClassRow[]; // ceiling_class como gravado
  };
}

export interface SimState {
  fields: Fields;
  prices: Record<string, string>; // ticker -> texto digitado
}

/** "10.500000" -> "10.5", "100.000000" -> "100", "100" -> "100" (só zeros depois da vírgula). */
export function trimZeros(s: string): string {
  return s.includes(".") ? s.replace(/0+$/, "").replace(/\.$/, "") : s;
}

export function initialState(data: SimulatorData): SimState {
  const prices: Record<string, string> = {};
  for (const c of data.company.classes) prices[c.ticker] = trimZeros(c.price).replace(".", ",");
  return { fields: fieldsFromConfig(data.config), prices };
}

export interface MethodView {
  method: MethodName;
  storedStatus: MethodStatus | null;
  storedValue: string | null;
  sim: SimMethod;
  changed: boolean;
}

export interface ClassView {
  ticker: string;
  kind: SimClass["kind"];
  multiplier: number | null;
  stored: ClassRow | null;
  simRow: ClassRow;
  sim: SimClass;
  storedSituation: string;
  simSituation: string;
  changed: boolean;
}

export interface View {
  errors: string[]; // vazio quando os campos são válidos
  changedFields: string[];
  changed: boolean; // o resultado difere do gravado
  sim: Simulation | null;
  methods: MethodView[];
  consolidated: {
    stored: SimulatorData["stored"];
    ceiling: Dec | null;
    methodsOk: number;
    kRequired: number | null;
    status: "ok" | "insufficient";
    changed: boolean;
  } | null;
  classes: ClassView[];
}

/** Os valores gravados têm 8 casas (numeric(24,8)): diferença até 2e-8 não é mudança. */
const TOL = new D("2e-8");
function differs(a: Dec | null, b: Dec | null): boolean {
  if (a === null || b === null) return a !== b;
  return a.minus(b).abs().gt(TOL);
}

/** Texto de preço digitado -> Decimal; vazio ou inválido = nulo (a simulação usa o gravado). */
function priceOf(text: string | undefined): string | undefined {
  if (text === undefined) return undefined;
  const t = text.trim().replace(",", ".");
  return /^\d+(\.\d+)?$/.test(t) ? t : undefined;
}

export function asClassRow(k: SimClass, buyOverride?: boolean): ClassRow {
  return {
    ticker: k.ticker,
    kind: k.kind,
    price: k.price.toString(),
    priceDate: "",
    ceiling: k.ceiling?.toString() ?? null,
    ratio: k.ratio?.toString() ?? null,
    band: k.band,
    votes: k.votes,
    kRequired: k.kRequired,
    buy: buyOverride ?? k.buy,
    reason: k.reason,
  };
}

export function computeView(data: SimulatorData, state: SimState): View {
  const empty: View = { errors: [], changedFields: [], changed: false, sim: null, methods: [], consolidated: null, classes: [] };
  const built = buildParams(state.fields);
  const initial = initialState(data);
  const touched = changedFields(initial.fields, state.fields);
  if (built.params === null) return { ...empty, errors: built.errors, changedFields: touched };

  const prices: Record<string, string> = {};
  const priceErrors: string[] = [];
  for (const c of data.company.classes) {
    const typed = state.prices[c.ticker] ?? "";
    const ok = priceOf(typed);
    if (typed.trim() !== "" && ok === undefined) priceErrors.push(`Preço de ${c.ticker}: valor inválido.`);
    else if (ok !== undefined && new D(ok).gt(0)) prices[c.ticker] = ok;
    else if (typed.trim() !== "") priceErrors.push(`Preço de ${c.ticker}: precisa ser maior que zero.`);
  }
  if (priceErrors.length > 0) return { ...empty, errors: priceErrors, changedFields: touched };

  const sim = simulate(data.company, built.params, prices);
  const storedByMethod = new Map(data.company.methods.map((m) => [m.method, m]));

  const methods: MethodView[] = sim.methods.map((m) => {
    const st = storedByMethod.get(m.method);
    const storedValue = st?.status === "ok" ? st.value : null;
    return {
      method: m.method,
      storedStatus: st?.status ?? null,
      storedValue,
      sim: m,
      changed: (st?.status ?? null) !== m.status || differs(dec(storedValue), m.value),
    };
  });
  // Método gravado que o DCF desligado tirou da conta: aparece como removido, não some sem aviso.
  for (const st of data.company.methods) {
    if (!sim.methods.some((m) => m.method === st.method)) {
      methods.push({
        method: st.method,
        storedStatus: st.status,
        storedValue: st.status === "ok" ? st.value : null,
        sim: { method: st.method, status: "excluded", value: null, reason: "desligado na simulação", recomputed: true },
        changed: true,
      });
    }
  }

  const storedRows = new Map(data.stored.classes.map((k) => [k.ticker, k]));
  const classes: ClassView[] = sim.classes.map((k) => {
    const stored = storedRows.get(k.ticker) ?? null;
    const simRow = asClassRow(k);
    const consStatus = { ceilingStatus: sim.consolidated.status };
    const storedSituation = stored ? situation({ ceilingStatus: data.stored.status }, stored) : "indisponível";
    const simSituation = situation(consStatus, simRow);
    const changed =
      !stored ||
      differs(dec(stored.ceiling), k.ceiling) ||
      differs(dec(stored.ratio), k.ratio) ||
      stored.band !== k.band ||
      stored.buy !== k.buy ||
      differs(dec(stored.price), k.price);
    return { ticker: k.ticker, kind: k.kind, multiplier: k.multiplier, stored, simRow, sim: k, storedSituation, simSituation, changed };
  });

  const consChanged =
    differs(dec(data.stored.ceiling), sim.consolidated.ceiling) ||
    data.stored.status !== sim.consolidated.status ||
    data.stored.kRequired !== sim.consolidated.kRequired ||
    data.stored.methodsOk !== sim.consolidated.methodsOk;

  return {
    errors: [],
    changedFields: touched,
    changed: consChanged || methods.some((m) => m.changed) || classes.some((c) => c.changed),
    sim,
    methods,
    consolidated: {
      stored: data.stored,
      ceiling: sim.consolidated.ceiling,
      methodsOk: sim.consolidated.methodsOk,
      kRequired: sim.consolidated.kRequired,
      status: sim.consolidated.status,
      changed: consChanged,
    },
    classes,
  };
}

export { DCF_GROWTH_FIELD };
