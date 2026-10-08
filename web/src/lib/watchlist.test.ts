import { describe, expect, it } from "vitest";
import {
  NO_FILTER,
  filterCompanies,
  filterHref,
  parseFilters,
  segmentsOf,
  situation,
  type ClassRow,
  type WatchCompany,
} from "./watchlist";

const cls = (o: Partial<ClassRow> = {}): ClassRow => ({
  ticker: "AAAA3",
  kind: "on",
  price: "10",
  priceDate: "2026-10-02",
  ceiling: "12",
  ratio: "0.83",
  band: "buy",
  votes: 3,
  kRequired: 3,
  buy: true,
  reason: null,
  ...o,
});

const co = (o: Partial<WatchCompany> = {}): WatchCompany => ({
  cvmCode: 1,
  name: "Alfa",
  role: "carteira",
  segment: "energia",
  plan: "comum",
  ceilingStatus: "ok",
  methodsOk: 5,
  kRequired: 3,
  dataBase: "2025-12-31",
  collectedAt: null,
  screenStatus: "approved",
  screenAsOf: "2026-10-04",
  classes: [cls()],
  ...o,
});

describe("situation", () => {
  it("compra pela regra", () => {
    expect(situation(co(), cls())).toBe("COMPRA");
  });

  it("dados insuficientes nunca é compra, mesmo com buy verdadeiro vindo do banco", () => {
    expect(situation(co({ ceilingStatus: "insufficient" }), cls({ buy: true }))).toBe("Dados insuficientes");
  });

  it("abaixo do teto sem os votos fica na faixa de compra mas não é COMPRA", () => {
    expect(situation(co(), cls({ buy: false, band: "buy" }))).toMatch(/sem os votos/);
  });

  it("faixas acima do teto", () => {
    expect(situation(co(), cls({ buy: false, band: "hold" }))).toBe("Manter");
    expect(situation(co(), cls({ buy: false, band: "expensive" }))).toBe("Cara, avaliar venda");
  });

  it("papel sem teto e empresa sem cálculo", () => {
    expect(situation(co(), cls({ ceiling: null, ratio: null, band: null, buy: false }))).toBe("Sem teto");
    expect(situation(co({ ceilingStatus: null }), cls())).toBe("Sem preço teto calculado");
  });
});

describe("filtros", () => {
  const list = [
    co({ cvmCode: 1, name: "Alfa", role: "carteira", segment: "energia" }),
    co({ cvmCode: 2, name: "Beta", role: "radar", segment: "bancos", classes: [cls({ buy: false })] }),
    co({ cvmCode: 3, name: "Gama", role: "radar", segment: "energia", classes: [] }),
  ];

  it("sem filtro devolve tudo", () => {
    expect(filterCompanies(list, NO_FILTER)).toHaveLength(3);
  });

  it("por papel e por segmento", () => {
    expect(filterCompanies(list, { ...NO_FILTER, role: "radar" }).map((c) => c.name)).toEqual(["Beta", "Gama"]);
    expect(filterCompanies(list, { ...NO_FILTER, segment: "energia" }).map((c) => c.name)).toEqual(["Alfa", "Gama"]);
  });

  it("só compra: mantém só empresas com papel em compra e só esses papéis", () => {
    const r = filterCompanies(list, { ...NO_FILTER, onlyBuy: true });
    expect(r.map((c) => c.name)).toEqual(["Alfa"]);
  });

  it("segmentos únicos e ordenados", () => {
    expect(segmentsOf(list)).toEqual(["bancos", "energia"]);
  });

  it("parâmetros da URL: lixo é ignorado", () => {
    expect(parseFilters({ papel: "xis", segmento: "", compra: "sim" })).toEqual(NO_FILTER);
    expect(parseFilters({ papel: "radar", segmento: "bancos", compra: "1" })).toEqual({
      role: "radar",
      segment: "bancos",
      onlyBuy: true,
    });
    expect(parseFilters({ papel: ["radar"] })).toEqual(NO_FILTER);
  });

  it("links preservam os outros filtros", () => {
    const f = { role: "radar" as const, segment: "bancos", onlyBuy: false };
    expect(filterHref(f, { onlyBuy: true })).toBe("/?papel=radar&segmento=bancos&compra=1");
    expect(filterHref(f, { role: null, segment: null })).toBe("/");
  });
});
