/** Visão do simulador sobre empresas reais do fixture de paridade (insumos como o pipeline grava). */
import { describe, expect, it } from "vitest";
import { dataFor } from "../../../tests/helpers/simulatorData";
import { fieldsFromConfig } from "./form";
import { computeView, initialState, trimZeros, type SimState, type SimulatorData } from "./view";

const withField = (data: SimulatorData, patch: Record<string, string>): SimState => {
  const s = initialState(data);
  return { ...s, fields: { ...s.fields, ...patch } };
};

describe("trimZeros", () => {
  it("só tira zeros depois da vírgula", () => {
    expect(trimZeros("10.500000")).toBe("10.5");
    expect(trimZeros("100.000000")).toBe("100");
    expect(trimZeros("100")).toBe("100");
    expect(trimZeros("0.010000")).toBe("0.01");
    expect(trimZeros("20")).toBe("20");
  });
});

describe("sem alterar nada", () => {
  it.each(["comum_completo", "banco", "ano_de_outlier", "dois_metodos_dados_insuficientes", "dcf_pede_crescimento"])(
    "%s: o resultado é idêntico ao gravado",
    (name) => {
      const data = dataFor(name);
      const v = computeView(data, initialState(data));
      expect(v.errors).toEqual([]);
      expect(v.changed).toBe(false);
      expect(v.changedFields).toEqual([]);
      expect(v.methods.every((m) => !m.changed)).toBe(true);
      expect(v.classes.every((k) => !k.changed)).toBe(true);
    },
  );

  it("o gravado no banco tem 8 casas: arredondar o gravado não conta como mudança", () => {
    const data = dataFor("comum_completo", true);
    expect(computeView(data, initialState(data)).changed).toBe(false);
  });

  it("o preço inicial é o gravado, sem zeros sobrando (100 continua 100)", () => {
    const data = dataFor("comum_completo");
    data.company.classes[0]!.price = "100.000000";
    expect(initialState(data).prices[data.company.classes[0]!.ticker]).toBe("100");
  });
});

describe("alterando parâmetros", () => {
  const data = dataFor("comum_completo");

  it("taxa do Bazin: só o Bazin muda, e o consolidado acompanha", () => {
    const v = computeView(data, withField(data, { bazin_rate: "8" }));
    expect(v.errors).toEqual([]);
    expect(v.changedFields).toEqual(["bazin_rate"]);
    expect(v.methods.filter((m) => m.changed).map((m) => m.method)).toEqual(["bazin"]);
    const bazin = v.methods.find((m) => m.method === "bazin")!;
    expect(Number(bazin.sim.value!.toString())).toBeLessThan(Number(bazin.storedValue));
    expect(v.changed).toBe(true);
  });

  it("DCF desligado: sai da conta e aparece como removido, não some", () => {
    const v = computeView(data, withField(data, { dcf_enabled: "false" }));
    const dcf = v.methods.find((m) => m.method === "dcf")!;
    expect(dcf.sim.reason).toBe("desligado na simulação");
    expect(dcf.changed).toBe(true);
    expect(v.consolidated!.methodsOk).toBe(4);
    expect(v.sim!.methods.map((m) => m.method)).not.toContain("dcf");
  });

  it("tabela de K alterada muda a compra sem mexer nos tetos", () => {
    const base = computeView(data, initialState(data));
    const v = computeView(data, withField(data, { "k:5": "5" }));
    expect(v.consolidated!.ceiling!.eq(base.consolidated!.ceiling!)).toBe(true);
    expect(v.consolidated!.kRequired).toBe(5);
    expect(v.classes.some((k) => k.stored?.buy && !k.sim.buy)).toBe(true);
  });

  it("DCF sem crescimento histórico ganha valor ao informar o crescimento", () => {
    const d = dataFor("dcf_pede_crescimento");
    const before = computeView(d, initialState(d)).methods.find((m) => m.method === "dcf")!;
    expect(before.sim.status).toBe("unavailable");
    const after = computeView(d, withField(d, { dcf_growth: "3" })).methods.find((m) => m.method === "dcf")!;
    expect(after.sim.status).toBe("ok");
    expect(after.changed).toBe(true);
    expect(after.storedStatus).toBe("unavailable");
  });

  it("com dois métodos aplicáveis continua sem K (dados insuficientes)", () => {
    const d = dataFor("dois_metodos_dados_insuficientes");
    const v = computeView(d, withField(d, { bazin_rate: "5" }));
    expect(v.consolidated!.status).toBe("insufficient");
    expect(v.classes.every((k) => !k.sim.buy)).toBe(true);
  });
});

describe("alterando o preço", () => {
  const data = dataFor("comum_completo");
  const ticker = data.company.classes[0]!.ticker;

  it("preço alto leva à faixa cara e tira a compra; só o papel alterado muda", () => {
    const s = initialState(data);
    const v = computeView(data, { ...s, prices: { ...s.prices, [ticker]: "9999,50" } });
    expect(v.errors).toEqual([]);
    const k = v.classes.find((x) => x.ticker === ticker)!;
    expect(k.sim.band).toBe("expensive");
    expect(k.sim.buy).toBe(false);
    expect(k.changed).toBe(true);
    expect(v.classes.filter((x) => x.changed).map((x) => x.ticker)).toEqual([ticker]);
    expect(v.consolidated!.changed).toBe(false); // o preço não muda o teto
  });

  it("preço inválido ou zero é erro explícito (com a mensagem certa), não o preço gravado", () => {
    const s = initialState(data);
    const cases: [string, string][] = [
      ["abc", "valor inválido"],
      ["1.234,5", "valor inválido"],
      ["-5", "valor inválido"],
      ["0", "precisa ser maior que zero"],
      ["0,00", "precisa ser maior que zero"],
    ];
    for (const [bad, message] of cases) {
      const v = computeView(data, { ...s, prices: { ...s.prices, [ticker]: bad } });
      expect(v.errors, bad).toEqual([`Preço de ${ticker}: ${message}.`]);
      expect(v.sim).toBeNull();
    }
  });

  it("preço em branco usa o gravado", () => {
    const s = initialState(data);
    const v = computeView(data, { ...s, prices: { ...s.prices, [ticker]: "" } });
    expect(v.errors).toEqual([]);
    expect(v.changed).toBe(false);
  });
});

describe("campos inválidos", () => {
  const data = dataFor("comum_completo");

  it("não calcula com campo inválido e diz qual", () => {
    const v = computeView(data, withField(data, { gordon_k: "doze" }));
    expect(v.sim).toBeNull();
    expect(v.methods).toEqual([]);
    expect(v.errors.join(" ")).toContain("Retorno exigido (k)");
    expect(v.changedFields).toEqual(["gordon_k"]);
  });

  it("fieldsFromConfig reproduz os parâmetros do pipeline (nada alterado)", () => {
    const s = initialState(data);
    expect(s.fields).toEqual(fieldsFromConfig(data.config));
  });
});
