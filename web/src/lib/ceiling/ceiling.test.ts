/** Números conferidos à mão (os mesmos de `pipeline/tests/test_ceiling.py`) e os casos de borda do simulador. */
import { describe, expect, it } from "vitest";
import {
  D,
  bandFor,
  consolidate,
  kFor,
  median,
  methods,
  paramsFromConfig,
  simulate,
  validateParams,
  type CeilingParams,
  type SimMethod,
  type StoredCompany,
  type StoredMethod,
} from "./index";

const CONFIG = {
  "ceiling.bazin_rate": 0.06,
  "ceiling.graham_multiplier": 22.5,
  "ceiling.gordon_k": 0.12,
  "ceiling.gordon_g_min": 0,
  "ceiling.gordon_g_max": 0.05,
  "ceiling.gordon_min_spread": 0.03,
  "ceiling.dcf_enabled": true,
  "ceiling.dcf_rate": 0.12,
  "ceiling.dcf_years": 5,
  "ceiling.dcf_terminal_growth": 0.04,
  "ceiling.dcf_g_min": 0,
  "ceiling.dcf_g_max": 0.05,
  "ceiling.k_by_methods": { "3": 2, "4": 3, "5": 3 },
  "ceiling.band_strong": 0.8,
  "ceiling.band_buy": 1.0,
  "ceiling.band_hold": 1.2,
};
const P = paramsFromConfig(CONFIG);
const withP = (o: Partial<CeilingParams>): CeilingParams => ({ ...P, ...o });

const stored = (method: StoredMethod["method"], inputs: Record<string, unknown>, status: StoredMethod["status"] = "ok", value: string | null = null, reason: string | null = null): StoredMethod => ({
  method,
  status,
  value,
  reason,
  inputs,
});
const val = (m: SimMethod) => m.value?.toString();

describe("métodos, com números conferidos à mão", () => {
  it("Bazin: R$ 0,60 de dividendo médio ÷ 6% = R$ 10", () => {
    const m = methods.bazin(stored("bazin", { mean: "0.6" }), P);
    expect([m.status, val(m), m.recomputed]).toEqual(["ok", "10", true]);
    expect(val(methods.bazin(stored("bazin", { mean: "0.6" }), withP({ bazinRate: new D("0.08") })))).toBe("7.5");
  });

  it("Bazin: média não positiva fica indisponível, nunca zero", () => {
    const m = methods.bazin(stored("bazin", { mean: "0" }), P);
    expect([m.status, m.value, m.reason]).toEqual(["unavailable", null, "dividendo médio líquido não positivo"]);
  });

  it("Graham: √(22,5 × 2 × 8) = 18,973665961010276", () => {
    const m = methods.graham(stored("graham", { lpa_mean: "2", vpa: "8" }), P);
    expect(m.value!.sub("18.97366596101027598").abs().lt("1e-12")).toBe(true);
    // multiplicador 15: √(15 × 16) = √240
    expect(methods.graham(stored("graham", { lpa_mean: "2", vpa: "8" }), withP({ grahamMultiplier: new D(15) })).value!.sub(new D(240).sqrt()).abs().lt("1e-12")).toBe(true);
  });

  it("Graham: LPA ou VPA não positivo exclui; banco (sem insumos) fica como gravado", () => {
    expect(methods.graham(stored("graham", { lpa_mean: "-1", vpa: "8" }, "excluded"), P).reason).toBe("LPA ou VPA não positivo");
    const bank = methods.graham(stored("graham", { plan: "banco" }, "excluded", null, "banco ou seguradora"), P);
    expect([bank.status, bank.reason, bank.recomputed]).toEqual(["excluded", "banco ou seguradora", false]);
  });

  it("Gordon: g limitado a 5%, D1 = 0,6 × 1,05, spread 7 p.p.", () => {
    const m = methods.gordon(stored("gordon", { mean: "0.6", g_raw: "0.0941" }), P);
    expect(m.value!.sub(new D("0.63").div("0.07")).abs().lt("1e-12")).toBe(true);
  });

  it("Gordon: k − g abaixo do mínimo exclui, e volta a valer com outro k", () => {
    const inputs = { mean: "0.6", g_raw: "0.0941" };
    const low = methods.gordon(stored("gordon", inputs), withP({ gordonK: new D("0.07") }));
    expect([low.status, low.reason]).toEqual(["excluded", "k − g abaixo do mínimo"]);
    const back = methods.gordon(stored("gordon", inputs, "excluded", null, "k − g abaixo do mínimo"), P);
    expect(back.status).toBe("ok");
  });

  it("Gordon: spread exatamente no mínimo ainda vale (a regra é estritamente menor)", () => {
    const m = methods.gordon(stored("gordon", { mean: "1", g_raw: "0.09" }), withP({ gordonK: new D("0.08"), gordonGMax: new D("0.05") }));
    expect(m.status).toBe("ok"); // k − g = 0,08 − 0,05 = 0,03 = mínimo
  });

  it("Múltiplos: mediana × base; P/VP usa o VPA; sem tipo fica como gravado", () => {
    expect(val(methods.multiples(stored("multiples", { median: "11", kind: "P/L", lpa_mean: "2" })))).toBe("22");
    expect(val(methods.multiples(stored("multiples", { median: "1.2", kind: "P/VP", vpa: "10" })))).toBe("12");
    expect(methods.multiples(stored("multiples", { median: "11" }, "unavailable", null, "x")).recomputed).toBe(false);
    expect(methods.multiples(stored("multiples", { median: "11", kind: "P/L", lpa_mean: "-1" }, "excluded")).status).toBe("excluded");
  });

  const dcfInputs = { base: "1000", g_raw: "0", growth_source: "histórico do FCFE", shares: "1000", shares_factor: "1" };

  it("DCF: fluxo constante de 1.000 por 1.000 ações = R$ 10,98 por ação", () => {
    const m = methods.dcf(stored("dcf", dcfInputs), P);
    expect(m.value!.sub("10.981325326").abs().lt("1e-6")).toBe(true);
  });

  it("DCF: fator de ações da data-base divide o valor", () => {
    const m = methods.dcf(stored("dcf", { ...dcfInputs, shares_factor: "2" }), P);
    expect(m.value!.sub(new D("10.981325326").div(2)).abs().lt("1e-6")).toBe(true);
  });

  it("DCF: crescimento informado vale sem o teto do histórico; o da tela vence o gravado", () => {
    const base = methods.dcf(stored("dcf", { ...dcfInputs, g_raw: "0.2" }), P); // limitado a 5%
    const informed = methods.dcf(stored("dcf", { ...dcfInputs, g_raw: "0.2" }), withP({ dcfGrowth: new D("0.10") }));
    expect(informed.value!.gt(base.value!)).toBe(true);
    const fromStore = methods.dcf(stored("dcf", { ...dcfInputs, growth_source: "informado para a empresa", g: "0.02" }), P);
    const sameFromParam = methods.dcf(stored("dcf", dcfInputs), withP({ dcfGrowth: new D("0.02") }));
    expect(fromStore.value!.eq(sameFromParam.value!)).toBe(true);
  });

  it("DCF: sem crescimento histórico fica como gravado; a tela pode informar o crescimento", () => {
    const noGrowth = { base: "700", shares: "1000", shares_factor: "1" };
    const asStored = stored("dcf", noGrowth, "unavailable", null, "crescimento histórico indisponível: informe o crescimento da empresa");
    expect(methods.dcf(asStored, P).recomputed).toBe(false);
    expect(methods.dcf(asStored, withP({ dcfGrowth: new D("0.02") })).status).toBe("ok");
  });

  it("DCF: taxa não supera a perpetuidade exclui; FCFE médio não positivo é indisponível", () => {
    expect(methods.dcf(stored("dcf", dcfInputs), withP({ dcfRate: new D("0.04") })).reason).toBe("taxa de desconto não supera a perpetuidade");
    expect(methods.dcf(stored("dcf", { ...dcfInputs, base: "-5" }), P).reason).toBe("FCFE médio não positivo");
  });

  it("DCF gravado antes de o pipeline guardar o divisor por ação não é recalculado", () => {
    const legacy = stored("dcf", { base: "1000", g_raw: "0", growth_source: "histórico do FCFE" }, "ok", "10.98");
    const m = methods.dcf(legacy, withP({ dcfRate: new D("0.10") }));
    expect([m.recomputed, val(m)]).toEqual([false, "10.98"]); // o valor gravado, sem fingir que refez
  });
});

describe("consolidação, votos e faixas", () => {
  const ok = (v: string): SimMethod => ({ method: "bazin", status: "ok", value: new D(v), reason: null, recomputed: true });
  const off: SimMethod = { method: "graham", status: "unavailable", value: null, reason: "x", recomputed: true };

  it("mediana: ímpar pega o do meio; par tira a média dos dois do meio", () => {
    expect(median([new D(14), new D(10), new D(12)]).toString()).toBe("12");
    expect(median([new D(16), new D(10), new D(12), new D(14)]).toString()).toBe("13");
  });

  it("K por quantidade de métodos e menos que o mínimo = dados insuficientes", () => {
    expect([2, 3, 4, 5, 6].map((n) => kFor(n, P))).toEqual([null, 2, 3, 3, 3]);
    const cons = consolidate([ok("10"), ok("12"), off], P);
    expect(cons).toMatchObject({ status: "insufficient", methodsOk: 2, kRequired: null });
    expect(cons.ceiling!.toString()).toBe("11"); // o teto aparece, mas nunca é compra
  });

  it("nenhum método aplicável: sem teto, sem zero", () => {
    expect(consolidate([off], P)).toMatchObject({ status: "insufficient", ceiling: null, methodsOk: 0 });
  });

  it("faixas nas fronteiras: 80% é compra, 100% é manter, 120% ainda é manter", () => {
    const b = (r: string) => bandFor(new D(r), P);
    expect([b("0.79999"), b("0.8"), b("0.99999"), b("1"), b("1.2"), b("1.20001")]).toEqual([
      "strong_buy", "buy", "buy", "hold", "hold", "expensive",
    ]);
  });
});

describe("simulate", () => {
  const company: StoredCompany = {
    plan: "comum",
    methods: [
      stored("bazin", { mean: "0.6" }),
      stored("graham", { lpa_mean: "2", vpa: "8" }),
      stored("gordon", { mean: "0.6", g_raw: "0.0941" }),
      stored("dcf", { base: "1000", g_raw: "0", growth_source: "histórico do FCFE", shares: "1000", shares_factor: "1" }),
    ],
    classes: [
      { ticker: "ALFA3", kind: "on", multiplier: 1, price: "9" },
      { ticker: "ALFA11", kind: "unit", multiplier: 3, price: "30" },
      { ticker: "ALFA9", kind: "unit", multiplier: null, price: "30", reason: "composição ilegível" },
    ],
  };

  it("troca o preço de um papel sem mexer nos outros", () => {
    const a = simulate(company, P);
    const b = simulate(company, P, { ALFA3: "20" });
    expect(a.classes[0]!.price.toString()).toBe("9");
    expect(b.classes[0]!.price.toString()).toBe("20");
    expect(b.classes[1]!.price.toString()).toBe("30");
    expect(b.classes[0]!.buy).toBe(false);
    expect(b.classes[0]!.band).toBe("expensive");
  });

  it("preço inválido na tela cai no preço gravado", () => {
    expect(simulate(company, P, { ALFA3: "abc" }).classes[0]!.price.toString()).toBe("9");
    expect(simulate(company, P, { ALFA3: "-1" }).classes[0]!.price.toString()).toBe("9");
  });

  it("unit sem composição legível não tem teto nem compra, com o motivo", () => {
    const k = simulate(company, P).classes[2]!;
    expect([k.ceiling, k.ratio, k.band, k.buy, k.reason]).toEqual([null, null, null, false, "composição ilegível"]);
  });

  it("unit soma as ações da composição: teto, votos e preço na mesma escala", () => {
    const s = simulate(company, P);
    expect(s.classes[1]!.ceiling!.eq(s.consolidated.ceiling!.mul(3))).toBe(true);
  });

  it("DCF desligado sai da lista e da mediana", () => {
    const s = simulate(company, withP({ dcfEnabled: false }));
    expect(s.methods.map((m) => m.method)).toEqual(["bazin", "graham", "gordon"]);
    expect(s.consolidated.methodsOk).toBe(3);
  });

  it("métodos saem na ordem fixa, não na do banco", () => {
    const shuffled = { ...company, methods: [...company.methods].reverse() };
    expect(simulate(shuffled, P).methods.map((m) => m.method)).toEqual(["bazin", "graham", "gordon", "dcf"]);
  });

  it("não altera os dados de entrada", () => {
    const before = JSON.stringify(company);
    simulate(company, withP({ bazinRate: new D("0.1") }), { ALFA3: "1" });
    expect(JSON.stringify(company)).toBe(before);
  });
});

describe("parâmetros", () => {
  it("lê o formato de app_config (JSON) e o crescimento informado", () => {
    const p = paramsFromConfig(CONFIG, "0.03");
    expect(p.bazinRate.toString()).toBe("0.06");
    expect(p.kByMethods).toEqual({ 3: 2, 4: 3, 5: 3 });
    expect(p.dcfGrowth!.toString()).toBe("0.03");
    expect(paramsFromConfig(CONFIG).dcfGrowth).toBeNull();
  });

  it("parâmetro ausente ou inválido é erro explícito, não padrão escondido", () => {
    const rest: Record<string, unknown> = { ...CONFIG };
    delete rest["ceiling.gordon_k"];
    expect(() => paramsFromConfig(rest)).toThrow(/ceiling.gordon_k/);
    expect(() => paramsFromConfig({ ...CONFIG, "ceiling.bazin_rate": "abc" })).toThrow(/ceiling.bazin_rate/);
    expect(() => paramsFromConfig({ ...CONFIG, "ceiling.k_by_methods": [1] })).toThrow();
    expect(() => paramsFromConfig(CONFIG, "abc")).toThrow(/crescimento do DCF/);
  });

  it("validação aponta o que quebraria o cálculo", () => {
    expect(validateParams(P)).toEqual([]);
    expect(validateParams(withP({ bazinRate: new D(0) }))).toHaveLength(1);
    expect(validateParams(withP({ dcfYears: 0 }))).toHaveLength(1);
    expect(validateParams(withP({ gordonGMin: new D("0.06") }))).toHaveLength(1);
    expect(validateParams(withP({ bandStrong: new D(2) }))).toHaveLength(1);
    expect(validateParams(withP({ kByMethods: {} }))).toHaveLength(1);
  });
});
