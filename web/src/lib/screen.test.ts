import { describe, expect, it } from "vitest";
import {
  NO_SCREEN_FILTER,
  escapeLike,
  formatCriterionValue,
  formatThreshold,
  parseScreenFilters,
  problemCriteria,
  reasonText,
  screenHref,
  totalPages,
  type CriterionRow,
} from "./screen";

const crit = (criterion: string, status: CriterionRow["status"]): CriterionRow => ({
  criterion,
  status,
  value: null,
  threshold: null,
  reason: null,
});

describe("parâmetros da URL", () => {
  it("valores inválidos são ignorados", () => {
    expect(parseScreenFilters({ status: "xis", q: "   ", pagina: "0", lista: "sim" })).toEqual(NO_SCREEN_FILTER);
    expect(parseScreenFilters({ pagina: "abc" }).page).toBe(1);
    expect(parseScreenFilters({ pagina: "-3" }).page).toBe(1);
    expect(parseScreenFilters({ pagina: "99999999" }).page).toBe(1);
    expect(parseScreenFilters({ status: ["approved"] }).status).toBeNull();
  });

  it("lê status, busca, lista e página", () => {
    expect(parseScreenFilters({ status: "rejected", q: " itaú ", lista: "1", pagina: "3" })).toEqual({
      status: "rejected",
      q: "itaú",
      onlyWatch: true,
      page: 3,
    });
  });

  it("trunca busca longa", () => {
    expect(parseScreenFilters({ q: "a".repeat(200) }).q).toHaveLength(60);
  });

  it("mudar filtro volta à página 1; mudar página preserva os filtros", () => {
    const f = { status: "rejected" as const, q: "banco", onlyWatch: false, page: 4 };
    expect(screenHref(f, { status: null })).toBe("/filtro?q=banco");
    expect(screenHref(f, { page: 5 })).toBe("/filtro?status=rejected&q=banco&pagina=5");
    expect(screenHref(NO_SCREEN_FILTER, {})).toBe("/filtro");
  });
});

describe("busca por texto", () => {
  it("escapa curingas do LIKE", () => {
    expect(escapeLike("100%_a\\b")).toBe("100\\%\\_a\\\\b");
    expect(escapeLike("itau")).toBe("itau");
  });
});

describe("valor dos critérios", () => {
  it("contagens", () => {
    expect(formatCriterionValue("lucro_positivo", "9")).toBe("9 anos");
    expect(formatCriterionValue("proventos_todos_os_anos", "1")).toBe("1 ano");
    expect(formatCriterionValue("queda_dividendo_por_acao", "3.0000")).toBe("3 quedas");
    expect(formatCriterionValue("queda_dividendo_por_acao", "0")).toBe("0 quedas");
  });

  it("frações viram percentual; liquidez vira reais", () => {
    expect(formatCriterionValue("roe_medio", "0.1523")).toBe("15,2%");
    expect(formatCriterionValue("dy_medio_liquido", "0.05")).toBe("5,0%");
    expect(formatCriterionValue("payout_medio", "0.4")).toBe("40,0%");
    expect(formatCriterionValue("liquidez", "12500000")).toBe("R$ 12,50 mi");
  });

  it("sem valor = indisponível, nunca zero", () => {
    for (const n of ["lucro_positivo", "roe_medio", "liquidez", "queda_dividendo_por_acao"]) {
      expect(formatCriterionValue(n, null)).toBe("indisponível");
    }
  });

  it("limite com vírgula decimal e motivo em português", () => {
    expect(formatThreshold("> 0.10")).toBe("> 0,10");
    expect(formatThreshold("volume >= 1000000 e presença >= 0.9")).toBe("volume >= 1000000 e presença >= 0,9");
    expect(formatThreshold(null)).toBe("indisponível");
    expect(reasonText("data")).toMatch(/falta dado/);
    expect(reasonText("novo_motivo")).toBe("novo_motivo");
    expect(reasonText(null)).toBeNull();
  });
});

describe("problemas", () => {
  it("separa reprovados de indisponíveis, na ordem canônica", () => {
    const r = problemCriteria([
      crit("liquidez", "fail"),
      crit("dy_medio_liquido", "unavailable"),
      crit("lucro_positivo", "fail"),
      crit("roe_medio", "pass"),
    ]);
    expect(r.failed).toEqual(["Lucro positivo", "Liquidez"]);
    expect(r.unavailable).toEqual(["DY médio líquido de 5 anos"]);
  });
});

describe("paginação", () => {
  it("total de páginas", () => {
    expect(totalPages(0)).toBe(1);
    expect(totalPages(50)).toBe(1);
    expect(totalPages(51)).toBe(2);
    expect(totalPages(1234)).toBe(25);
  });
});
