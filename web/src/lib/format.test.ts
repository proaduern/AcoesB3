import { describe, expect, it } from "vitest";
import {
  UNAVAILABLE,
  formatBRL,
  formatBRLCompact,
  formatDate,
  formatDateTime,
  formatNumber,
  formatPercent,
  toReais,
} from "./format";

describe("dado ausente nunca vira zero", () => {
  it.each([null, undefined, "", "  ", "abc", "NaN", "Infinity", Number.NaN])(
    "%j -> indisponível",
    (v) => {
      expect(formatBRL(v as never)).toBe(UNAVAILABLE);
      expect(formatBRLCompact(v as never)).toBe(UNAVAILABLE);
      expect(formatPercent(v as never)).toBe(UNAVAILABLE);
      expect(formatNumber(v as never)).toBe(UNAVAILABLE);
    },
  );

  it("zero de verdade continua zero", () => {
    expect(formatBRL("0")).toBe("R$ 0,00");
    expect(formatPercent(0)).toBe("0,0%");
  });

  it("datas ausentes ou inválidas", () => {
    expect(formatDate(null)).toBe(UNAVAILABLE);
    expect(formatDate("lixo")).toBe(UNAVAILABLE);
    expect(formatDateTime(undefined)).toBe(UNAVAILABLE);
    expect(formatDateTime("lixo")).toBe(UNAVAILABLE);
  });
});

describe("formatos pt-BR", () => {
  it("reais", () => {
    expect(formatBRL("1234.5")).toBe("R$ 1.234,50");
    expect(formatBRL("-9.999")).toBe("-R$ 10,00");
    expect(formatBRL("-0.001")).toBe("R$ 0,00");
    expect(formatBRL("24.5", 0)).toBe("R$ 25");
  });

  it("arredonda sem erro de binário (meio para cima)", () => {
    expect(formatBRL("1.005")).toBe("R$ 1,01");
    expect(formatPercent("0.1425", 1)).toBe("14,3%");
  });

  it("percentual", () => {
    expect(formatPercent("0.142")).toBe("14,2%");
    expect(formatPercent(1.2, 0)).toBe("120%");
  });

  it("data sem deslocamento de fuso", () => {
    expect(formatDate("2026-10-08")).toBe("08/10/2026");
    expect(formatDate("2026-01-01T00:00:00.000Z")).toBe("01/01/2026");
  });

  it("instante no horário de Brasília", () => {
    expect(formatDateTime("2026-10-08T22:53:00Z")).toBe("08/10/2026 19:53");
    expect(formatDateTime("2026-01-01T02:00:00Z")).toBe("31/12/2025 23:00");
  });
});

describe("ESCALA_MOEDA", () => {
  it("o valor do banco já está em reais: R$ 41,085 bi aparece como 41,09 bi, sem reescalar", () => {
    expect(formatBRLCompact("41085000000")).toBe("R$ 41,09 bi");
  });

  it("ler em mil como se fosse reais erraria por 1000x (o contrário do que o banco guarda)", () => {
    expect(formatBRLCompact("41085000")).toBe("R$ 41,09 mi");
    expect(formatBRLCompact(toReais("41085000", "MIL"))).toBe("R$ 41,09 bi");
  });

  it("toReais: UNIDADE não muda, MIL multiplica por 1000", () => {
    expect(toReais("6042593", "UNIDADE")).toBe("6042593");
    expect(toReais("6042593", "MIL")).toBe("6042593000");
    expect(toReais("1.5", "MIL")).toBe("1500");
  });

  it("escala desconhecida é erro", () => {
    expect(() => toReais("1", "MILHAO")).toThrow(/ESCALA_MOEDA desconhecida/);
    expect(() => toReais("1", "")).toThrow();
  });

  it("faixas do formato curto", () => {
    expect(formatBRLCompact("999999")).toBe("R$ 999.999,00");
    expect(formatBRLCompact("1000000")).toBe("R$ 1,00 mi");
    expect(formatBRLCompact("2500000000000")).toBe("R$ 2,50 tri");
    expect(formatBRLCompact("-3000000000")).toBe("-R$ 3,00 bi");
  });
});
