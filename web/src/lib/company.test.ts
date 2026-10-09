import { describe, expect, it } from "vitest";
import {
  companyHref,
  describeInputs,
  parseCvm,
  parsePeriod,
  parseTab,
  parseTicker,
  pickTicker,
  seriesYears,
} from "./company";

describe("parâmetros da URL", () => {
  it("aba e período inválidos caem no padrão", () => {
    expect(parseTab({})).toBe("teto");
    expect(parseTab({ aba: "xis" })).toBe("teto");
    expect(parseTab({ aba: "origem" })).toBe("origem");
    expect(parseTab({ aba: ["filtro"] })).toBe("teto");
    expect(parsePeriod({})).toBe(5);
    expect(parsePeriod({ periodo: "3" })).toBe(3);
    expect(parsePeriod({ periodo: "7" })).toBe(5);
    expect(parsePeriod({ periodo: "abc" })).toBe(5);
  });

  it("ticker só no formato de papel da B3 (vai para a consulta)", () => {
    expect(parseTicker({ papel: "alfa3" })).toBe("ALFA3");
    expect(parseTicker({ papel: "ALFA11" })).toBe("ALFA11");
    expect(parseTicker({ papel: "A'; DROP TABLE x;--" })).toBeNull();
    expect(parseTicker({ papel: "AB" })).toBeNull();
    expect(parseTicker({})).toBeNull();
  });

  it("código CVM só com dígitos", () => {
    expect(parseCvm("5410")).toBe(5410);
    expect(parseCvm("5410abc")).toBeNull();
    expect(parseCvm("-1")).toBeNull();
    expect(parseCvm("")).toBeNull();
    expect(parseCvm("12345678")).toBeNull();
  });

  it("links omitem os padrões", () => {
    expect(companyHref(7)).toBe("/empresa/7");
    expect(companyHref(7, { aba: "teto", periodo: 5 })).toBe("/empresa/7");
    expect(companyHref(7, { aba: "preco", papel: "ALFA3", periodo: 10 })).toBe("/empresa/7?aba=preco&papel=ALFA3&periodo=10");
  });

  it("papel escolhido só vale se for da empresa", () => {
    expect(pickTicker(["A3", "A4"], "A4")).toBe("A4");
    expect(pickTicker(["A3", "A4"], "ZZ")).toBe("A3");
    expect(pickTicker([], "A4")).toBeNull();
  });

  it("anos de todas as séries, ordenados e sem repetir", () => {
    expect(
      seriesYears({ profit: { "2024": "1" }, roe: { "2023": "1", "2024": "1" }, dps: {}, dy: {}, payout: { "2025": "1" } }),
    ).toEqual([2023, 2024, 2025]);
  });
});

describe("describeInputs", () => {
  it("Bazin: dividendos por ano, taxa e média", () => {
    const l = describeInputs({
      dps_net: { "2025": "0.65", "2024": "0.55" },
      outlier_years: [2023],
      mean: "0.60",
      rate: "0.06",
    });
    expect(l).toEqual([
      { label: "Dividendo líquido por ação, por ano", value: "2024: R$ 0,55 · 2025: R$ 0,65" },
      { label: "Anos de outlier (fora da média)", value: "2023" },
      { label: "Dividendo médio líquido por ação", value: "R$ 0,60" },
      { label: "Taxa", value: "6,00%" },
    ]);
  });

  it("Gordon: crescimento, spread e pontas do dividendo total", () => {
    const l = describeInputs({
      g_raw: "0.0823",
      g: "0.05",
      k: "0.12",
      growth: { first: "1000000000", last: "1470000000", first_year: 2021, last_year: 2025 },
      d1: "0.63",
    });
    const by = Object.fromEntries(l.map((x) => [x.label, x.value]));
    expect(by["Crescimento histórico (sem limite)"]).toBe("8,23%");
    expect(by["Crescimento usado"]).toBe("5,00%");
    expect(by["Dividendo total bruto, pontas da janela"]).toBe("R$ 1,00 bi (2021) → R$ 1,47 bi (2025)");
    expect(by["Dividendo do próximo ano (D1)"]).toBe("R$ 0,63");
  });

  it("anos vazios e listas vazias não viram zero", () => {
    expect(describeInputs({ outlier_years: [] })).toEqual([{ label: "Anos de outlier (fora da média)", value: "nenhum" }]);
    expect(describeInputs({ dps_net: {} })).toEqual([{ label: "Dividendo líquido por ação, por ano", value: "nenhum" }]);
  });

  it("valor ausente ou nulo é omitido; detalhe do DCF fica de fora", () => {
    expect(describeInputs({ mean: null, fcfe_detail: { 2024: {} }, base: "100000000" })).toEqual([
      { label: "FCFE base (média)", value: "R$ 100,00 mi" },
    ]);
  });

  it("múltiplos: P/L por ano e anos descartados com motivo", () => {
    const l = describeInputs({ ratios: { "2024": "9.5", "2025": "10.25" }, skipped: { "2020": "prejuízo" }, kind: "P/L", median: "9.875" });
    const by = Object.fromEntries(l.map((x) => [x.label, x.value]));
    expect(by["Múltiplo por ano"]).toBe("2024: 9,50 · 2025: 10,25");
    expect(by["Anos fora da mediana"]).toBe("2020: prejuízo");
    expect(by["Tipo de múltiplo"]).toBe("P/L");
  });

  it("chave desconhecida aparece como veio, não some", () => {
    expect(describeInputs({ novo_campo: 3, outro: { a: 1 } })).toEqual([
      { label: "novo_campo", value: "3" },
      { label: "outro", value: '{"a":1}' },
    ]);
  });

  it("valor de dado com formato errado vira indisponível, não zero", () => {
    expect(describeInputs({ mean: "abc" })).toEqual([{ label: "Dividendo médio líquido por ação", value: "indisponível" }]);
  });
});
