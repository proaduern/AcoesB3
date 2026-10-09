import { describe, expect, it } from "vitest";
import {
  DCF_GROWTH_FIELD,
  FIELDS,
  buildParams,
  changedFields,
  fieldsFromConfig,
  parseNumber,
  percentText,
} from "./form";
import { CONFIG_KEYS } from "./params";

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

describe("número digitado", () => {
  it("aceita vírgula e ponto; recusa milhar, letras e vazio", () => {
    expect(parseNumber("6")?.toString()).toBe("6");
    expect(parseNumber(" 6,5 ")?.toString()).toBe("6.5");
    expect(parseNumber("6.5")?.toString()).toBe("6.5");
    expect(parseNumber("-2")?.toString()).toBe("-2");
    for (const bad of ["", " ", "abc", "1.234,5", "1e3", "6%", "--1", "6,", ",5", "6,5,1"]) {
      expect(parseNumber(bad), JSON.stringify(bad)).toBeNull();
    }
  });

  it("fração vira percentual sem erro de ponto flutuante", () => {
    expect(percentText(0.06)).toBe("6");
    expect(percentText(0.045)).toBe("4,5");
    expect(percentText("0.12")).toBe("12");
    expect(percentText(0.07)).toBe("7"); // 0,07 × 100 em ponto flutuante daria 7.000000000000001
    expect(percentText(null)).toBe("");
  });
});

describe("campos <-> parâmetros", () => {
  it("todo parâmetro do simulador existe nos campos (ou na tabela K)", () => {
    const ids = new Set(FIELDS.map((f) => `ceiling.${f.id}`));
    for (const k of CONFIG_KEYS) {
      if (k === "ceiling.k_by_methods") continue;
      expect(ids.has(k), k).toBe(true);
    }
  });

  it("ida e volta: o que sai de app_config volta como os mesmos parâmetros", () => {
    const fields = fieldsFromConfig(CONFIG);
    expect(fields.bazin_rate).toBe("6");
    expect(fields.graham_multiplier).toBe("22,5");
    expect(fields.dcf_enabled).toBe("true");
    expect(fields["k:3"]).toBe("2");
    expect(fields[DCF_GROWTH_FIELD]).toBe("");
    const { params, errors } = buildParams(fields);
    expect(errors).toEqual([]);
    expect(params!.bazinRate.toString()).toBe("0.06");
    expect(params!.grahamMultiplier.toString()).toBe("22.5");
    expect(params!.gordonMinSpread.toString()).toBe("0.03");
    expect(params!.dcfYears).toBe(5);
    expect(params!.kByMethods).toEqual({ 3: 2, 4: 3, 5: 3 });
    expect(params!.bandHold.toString()).toBe("1.2");
    expect(params!.dcfGrowth).toBeNull();
  });

  it("percentual digitado vira fração; crescimento informado vira parâmetro", () => {
    const f = { ...fieldsFromConfig(CONFIG), bazin_rate: "8,5", [DCF_GROWTH_FIELD]: "3" };
    const { params } = buildParams(f);
    expect(params!.bazinRate.toString()).toBe("0.085");
    expect(params!.dcfGrowth!.toString()).toBe("0.03");
  });

  it("campo inválido gera mensagem com o nome do campo, nunca um valor padrão", () => {
    const f = { ...fieldsFromConfig(CONFIG), bazin_rate: "abc", dcf_years: "5,5", [DCF_GROWTH_FIELD]: "x" };
    const { params, errors } = buildParams(f);
    expect(params).toBeNull();
    expect(errors.join("|")).toContain("Taxa (dividendo médio ÷ taxa): valor inválido.");
    expect(errors.join("|")).toContain("Anos projetados: use um número inteiro.");
    expect(errors.join("|")).toContain("Crescimento do FCFE informado");
  });

  it("regras de consistência viram erro (taxa zero, faixas fora de ordem, K inválido)", () => {
    const base = fieldsFromConfig(CONFIG);
    expect(buildParams({ ...base, bazin_rate: "0" }).errors[0]).toMatch(/taxa do Bazin/);
    expect(buildParams({ ...base, band_strong: "150" }).errors[0]).toMatch(/faixas/);
    expect(buildParams({ ...base, "k:3": "0" }).errors[0]).toMatch(/Votos exigidos com 3/);
    expect(buildParams({ ...base, "k:4": "1,5" }).errors[0]).toMatch(/Votos exigidos com 4/);
  });

  it("DCF desligado vira parâmetro falso", () => {
    expect(buildParams({ ...fieldsFromConfig(CONFIG), dcf_enabled: "false" }).params!.dcfEnabled).toBe(false);
  });
});

describe("campos alterados", () => {
  it("compara o valor, não a grafia", () => {
    const a = fieldsFromConfig(CONFIG);
    expect(changedFields(a, { ...a, bazin_rate: "6,0" })).toEqual([]);
    expect(changedFields(a, { ...a, bazin_rate: "06" })).toEqual([]);
    expect(changedFields(a, { ...a, bazin_rate: "7" })).toEqual(["bazin_rate"]);
    expect(changedFields(a, { ...a, dcf_enabled: "false" })).toEqual(["dcf_enabled"]);
    expect(changedFields(a, { ...a, [DCF_GROWTH_FIELD]: "2" })).toEqual([DCF_GROWTH_FIELD]);
  });

  it("texto inválido conta como alterado", () => {
    const a = fieldsFromConfig(CONFIG);
    expect(changedFields(a, { ...a, bazin_rate: "x" })).toEqual(["bazin_rate"]);
  });
});
