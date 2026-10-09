import { describe, expect, it } from "vitest";
import {
  FALLBACK_SURVIVORSHIP,
  backtestHref,
  deathRules,
  deathVerdict,
  lostWindowsText,
  pickRun,
  pp,
  rebase,
  runKey,
  survivorshipText,
  yearEnds,
  yearsBetween,
  type BacktestOverview,
  type Death,
  type RunSummary,
} from "./backtest";

const run = (o: Partial<RunSummary>): RunSummary => ({
  id: 1,
  kind: "fit",
  scenario: "aporte_1000",
  createdAt: "2026-10-08T12:00:00.000Z",
  startDate: "2012-01-02",
  endDate: "2023-12-29",
  contribution: "1000",
  validationStart: "2024-01-01",
  deathLostShare: 0.5,
  deathDrawdownPp: 0.1,
  windowYears: 5,
  metrics: {},
  warnings: [],
  survivorshipWarning: null,
  companies: [],
  freezeId: null,
  ...o,
});

const death = (o: Partial<Death> = {}): Death => ({
  windows: 24,
  lost_windows: 2,
  lost_share: 2 / 24,
  windows_rule_triggered: false,
  extra_drawdown: 0.041,
  drawdown_rule_triggered: false,
  triggered: false,
  ...o,
});

describe("aviso de viés de sobrevivência", () => {
  it("usa o texto gravado na execução", () => {
    expect(survivorshipText(run({ survivorshipWarning: "  Aviso gravado.  " }))).toBe("Aviso gravado.");
  });

  it("nunca fica vazio: texto ausente, em branco ou sem execução cai no padrão", () => {
    for (const r of [run({ survivorshipWarning: null }), run({ survivorshipWarning: "" }), run({ survivorshipWarning: "   " }), null]) {
      expect(survivorshipText(r)).toBe(FALLBACK_SURVIVORSHIP);
    }
    expect(FALLBACK_SURVIVORSHIP).toMatch(/lista acompanhada de hoje/);
    expect(FALLBACK_SURVIVORSHIP).toMatch(/favorecer o resultado/);
  });
});

describe("execução escolhida", () => {
  const fits = [run({ id: 1, scenario: "aporte_1000" }), run({ id: 2, scenario: "dy_5" }), run({ id: 3, scenario: "dy_7" })];
  const validation = run({ id: 9, kind: "validation", scenario: "dy_5" });
  const base: BacktestOverview = { fits, validation: null, freeze: null };

  it("sem escolha: a validação se existe; senão o cenário congelado; senão o primeiro", () => {
    expect(pickRun({}, { ...base, validation })!.id).toBe(9);
    expect(pickRun({}, { ...base, freeze: { scenario: "dy_7", note: null, frozenAt: "x" } })!.id).toBe(3);
    expect(pickRun({}, base)!.id).toBe(1);
    expect(pickRun({}, { fits: [], validation: null, freeze: null })).toBeNull();
  });

  it("escolha por URL: cenário ou validação; lixo cai no padrão", () => {
    const ov = { ...base, validation };
    expect(pickRun({ execucao: "dy_7" }, ov)!.id).toBe(3);
    expect(pickRun({ execucao: "validacao" }, ov)!.id).toBe(9);
    expect(pickRun({ execucao: "nao_existe" }, ov)!.id).toBe(9);
    expect(pickRun({ execucao: "validacao" }, base)!.id).toBe(1); // sem validação medida
    expect(pickRun({ execucao: ["dy_7"] }, base)!.id).toBe(1);
  });

  it("chaves e links", () => {
    expect(runKey(validation)).toBe("validacao");
    expect(runKey(fits[1]!)).toBe("dy_5");
    expect(backtestHref(null)).toBe("/backtest");
    expect(backtestHref("dy_5", true)).toBe("/backtest?execucao=dy_5&ordens=todas");
  });
});

describe("gráfico", () => {
  it("reescala para 100 na primeira data válida; ignora nulo e não numérico", () => {
    const r = rebase([
      { date: "2012-01-31", value: 0 },
      { date: "2012-02-29", value: 2000 },
      { date: "2012-03-30", value: 2200 },
      { date: "2012-04-30", value: Number.NaN },
      { date: "2012-05-31", value: 1000 },
    ]);
    expect(r.map((p) => p.date)).toEqual(["2012-01-31", "2012-02-29", "2012-03-30", "2012-05-31"]);
    [0, 100, 110, 50].forEach((want, i) => expect(r[i]!.value).toBeCloseTo(want, 9));
    expect(rebase([])).toEqual([]);
    expect(rebase([{ date: "2012-01-31", value: -1 }])).toEqual([]);
  });

  it("último ponto de cada ano", () => {
    const m = yearEnds([
      { date: "2012-06-29", value: 1 },
      { date: "2012-12-28", value: 2 },
      { date: "2013-03-29", value: 3 },
    ]);
    expect([...m.entries()].map(([y, p]) => [y, p.value])).toEqual([[2012, 2], [2013, 3]]);
  });

  it("anos entre datas", () => {
    expect(yearsBetween("2024-01-01", "2025-12-31")).toBeCloseTo(2, 1);
    expect(yearsBetween("2012-01-01", "2024-01-01")).toBeCloseTo(12, 1);
  });
});

describe("critério de morte", () => {
  it("veredito: acionado, não acionado e indisponível (nunca 'não acionado' sem dado)", () => {
    expect(deathVerdict(death({ triggered: false }))).toBe("Não acionado");
    expect(deathVerdict(death({ triggered: true }))).toBe("ACIONADO");
    expect(deathVerdict(death({ triggered: null }))).toMatch(/^Indisponível/);
  });

  it("regras com valor e limite configurado", () => {
    const [w, d] = deathRules(death(), run({}));
    expect(w).toMatchObject({ value: "2 de 24 (8,3%)", limit: "mais de 50% das janelas", triggered: false });
    expect(w!.label).toContain("5 anos");
    expect(d).toMatchObject({ value: "4,1 p.p.", limit: "mais de 10,0 p.p.", triggered: false });
  });

  it("sem janelas ou sem queda para comparar: indisponível, não zero", () => {
    const [w, d] = deathRules(death({ windows: 0, lost_windows: 0, lost_share: null, extra_drawdown: null, windows_rule_triggered: null, drawdown_rule_triggered: null, triggered: null }), run({}));
    expect(w!.value).toBe("indisponível");
    expect(d!.value).toBe("indisponível");
    expect(lostWindowsText(undefined)).toBe("indisponível");
    expect(lostWindowsText({ windows: 0, lost: 0, lost_share: null })).toBe("indisponível");
    expect(lostWindowsText({ windows: 83, lost: 6, lost_share: 6 / 83 })).toBe("6 de 83 (7,2%)");
  });

  it("limite ausente na configuração: indisponível", () => {
    const [w, d] = deathRules(death(), run({ deathLostShare: null, deathDrawdownPp: null }));
    expect(w!.limit).toBe("indisponível");
    expect(d!.limit).toBe("indisponível");
  });

  it("pontos percentuais", () => {
    expect(pp(0.041)).toBe("4,1 p.p.");
    expect(pp(-0.02)).toBe("-2,0 p.p.");
    expect(pp(null)).toBe("indisponível");
  });
});
