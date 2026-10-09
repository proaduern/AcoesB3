import { describe, expect, it } from "vitest";
import { barPath, dayMs, linePath, niceTicks, scaleLinear, valueLabelX, yearTicks } from "./chart";

describe("scaleLinear", () => {
  it("mapeia o domínio no intervalo, inclusive invertido (y de SVG)", () => {
    const y = scaleLinear([0, 100], [200, 0]);
    expect(y(0)).toBe(200);
    expect(y(100)).toBe(0);
    expect(y(25)).toBe(150);
  });
  it("domínio de largura zero cai no meio", () => {
    expect(scaleLinear([5, 5], [0, 10])(5)).toBe(5);
  });
});

describe("niceTicks", () => {
  it("números redondos que cobrem os dados", () => {
    const t = niceTicks(0, 87, 4);
    expect(t.ticks).toEqual([0, 25, 50, 75, 100]);
    expect(t.domain).toEqual([0, 100]);
  });
  it("com negativos, inclui o zero", () => {
    const t = niceTicks(-0.05, 0.18, 4);
    expect(t.ticks).toContain(0);
    expect(t.domain[0]).toBeLessThanOrEqual(-0.05);
    expect(t.domain[1]).toBeGreaterThanOrEqual(0.18);
  });
  it("valores iguais ou não finitos não quebram", () => {
    expect(niceTicks(0, 0).domain).toEqual([0, 1]);
    expect(niceTicks(5, 5).domain[1]).toBeGreaterThanOrEqual(5);
    expect(niceTicks(Number.NaN, 1).ticks).toEqual([0]);
  });
});

describe("barPath", () => {
  it("positivo: base reta embaixo, ponta arredondada em cima", () => {
    const p = barPath(10, 20, 100, 40, 4);
    expect(p.startsWith("M10,100V44")).toBe(true);
    expect(p).toContain("Q10,40 14,40");
  });
  it("negativo desce da base; altura zero não desenha", () => {
    expect(barPath(10, 20, 100, 130, 4)).toContain("V126");
    expect(barPath(10, 20, 100, 100)).toBe("");
  });
  it("raio limitado à metade da largura e à altura", () => {
    expect(barPath(0, 4, 10, 9, 4)).toContain("Q0,9 1,9");
  });
});

describe("tempo", () => {
  it("dayMs sem fuso e inválido = NaN", () => {
    expect(dayMs("2026-10-08")).toBe(Date.UTC(2026, 9, 8));
    expect(Number.isNaN(dayMs("lixo"))).toBe(true);
  });
  it("marcas de ano dentro do intervalo, espaçadas", () => {
    const t = yearTicks(dayMs("2021-03-10"), dayMs("2026-10-08"), 6);
    expect(t.map((ms) => new Date(ms).getUTCFullYear())).toEqual([2022, 2023, 2024, 2025, 2026]);
    const sparse = yearTicks(dayMs("2010-01-04"), dayMs("2026-10-08"), 4);
    expect(sparse.length).toBeLessThanOrEqual(4);
  });
  it("linePath", () => {
    expect(linePath([{ x: 0, y: 1 }, { x: 2.123, y: 3 }])).toBe("M0,1L2.12,3");
    expect(linePath([])).toBe("");
  });
});

describe("valueLabelX", () => {
  it("centraliza quando cabe e encosta na borda quando não cabe", () => {
    expect(valueLabelX(100, "R$ 0,85", 320)).toEqual({ x: 100, anchor: "middle" });
    expect(valueLabelX(306, "R$ 2,35 bi", 320)).toEqual({ x: 318, anchor: "end" });
  });
});
