import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { FALLBACK_SURVIVORSHIP, type BacktestOverview, type RunDetail, type RunSummary, type Segment } from "@/lib/backtest";

const WARNING = "Viés de sobrevivência aceito (decisão do usuário): o universo é a lista acompanhada de hoje.";

const stats = (cagr: number, mdd: number, total = 2.5) => ({
  from: "2012-01-02",
  to: "2023-12-29",
  total_return: total,
  cagr,
  volatility: 0.18,
  max_drawdown: mdd,
  drawdown_peak: null,
  drawdown_trough: null,
});
const segment = (cagr: number, start = "2012-01-02", end = "2023-12-29", triggered: boolean | null = false): Segment => ({
  start,
  end,
  series: { strategy_net: stats(cagr, 0.331), strategy_gross: stats(cagr + 0.004, 0.331), idiv: stats(0.099, 0.573), ibov: stats(0.074, 0.468), cdi: stats(0.091, 0) },
  windows: { idiv: { windows: 83, lost: 6, lost_share: 6 / 83 } },
  death: { windows: 24, lost_windows: 2, lost_share: 2 / 24, windows_rule_triggered: false, extra_drawdown: 0.041, drawdown_rule_triggered: false, triggered },
});

const baseRun: RunSummary = {
  id: 1,
  kind: "fit",
  scenario: "dy_5",
  createdAt: "2026-10-08T10:00:00.000Z",
  startDate: "2012-01-02",
  endDate: "2023-12-29",
  contribution: "1000",
  validationStart: "2024-01-01",
  deathLostShare: 0.5,
  deathDrawdownPp: 0.1,
  windowYears: 5,
  metrics: { fit: segment(0.142), flows: { net_invested: "167000.00", net_final_value: "589700.50", net_fees: "389.00", net_taxes: "10700.00", net_dividends: "131500.00", net_trades: 305, net_first_buy: "2015-03-02" } },
  warnings: [WARNING, "Retorno total: os proventos vêm da DVA/FRE.", "56 meses sem compra: o aporte ficou em caixa."],
  survivorshipWarning: WARNING,
  companies: [{ name: "ALFA ENERGIA", segment: "energia" }, { name: "BETA BANCO", segment: "bancos" }],
  freezeId: null,
};
const fit2: RunSummary = { ...baseRun, id: 2, scenario: "aporte_1000", metrics: { fit: segment(0.144) } };
const validation: RunSummary = {
  ...baseRun,
  id: 9,
  kind: "validation",
  endDate: "2025-12-30",
  createdAt: "2026-10-08T22:00:00.000Z",
  freezeId: 1,
  metrics: { fit: segment(0.142), validation: segment(0.154, "2024-01-01", "2025-12-30"), flows: baseRun.metrics.flows },
};

// 24 meses a partir de jul/2023: cobre o início da validação (2024-01-01), como as séries reais (desde 2012)
const monthly = (start: number, growth: number) =>
  Array.from({ length: 24 }, (_, i) => ({
    date: new Date(Date.UTC(2023, 6 + i, 28)).toISOString().slice(0, 10),
    value: start * (1 + growth) ** i,
  }));
const detail: RunDetail = {
  series: { strategy_net: monthly(1, 0.012), strategy_gross: monthly(1, 0.013), idiv: monthly(2000, 0.009), ibov: monthly(60000, 0.007), cdi: monthly(1, 0.009) },
  trades: [{ seq: 4, date: "2025-12-01", ticker: "ALFA3", side: "buy", quantity: "10.000000", price: "9.500000", fee: "0.030000", tax: "0.000000", note: null }],
  tradesTotal: 305,
};

const mocks = vi.hoisted(() => ({ getBacktestOverview: vi.fn(), getRunDetail: vi.fn() }));
vi.mock("@/lib/db/queries", () => mocks);
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: unknown; className?: string; "aria-current"?: "true" | "page" }) => <a href={href} {...rest}>{children as never}</a>,
}));

async function render(q: Record<string, string> = {}) {
  const { default: Page } = await import("./page");
  return renderToStaticMarkup(await Page({ searchParams: Promise.resolve(q) }));
}
const count = (html: string, s: string) => html.split(s).length - 1;
const ov = (o: Partial<BacktestOverview> = {}): BacktestOverview => ({
  fits: [fit2, baseRun],
  validation,
  freeze: { scenario: "dy_5", note: "escolhido pelo usuário", frozenAt: "2026-10-08T21:00:00.000Z" },
  ...o,
});

beforeEach(() => {
  mocks.getBacktestOverview.mockResolvedValue(ov());
  mocks.getRunDetail.mockResolvedValue(detail);
  mocks.getRunDetail.mockClear();
});

describe("tela do backtest: aviso de viés de sobrevivência", () => {
  it("faixa fixa com o texto gravado, sem botão de fechar", async () => {
    const html = await render();
    expect(html).toContain('class="survivorship"');
    expect(html).toContain('role="note"');
    expect(html).toContain(WARNING);
    expect(html).toContain("Atenção: o resultado vale só para o universo de hoje");
    expect(html).not.toMatch(/<button[^>]*>[^<]*(Fechar|Entendi|×)/i);
    expect(html.indexOf('class="survivorship"')).toBeLessThan(html.indexOf("<section>")); // acima de qualquer número
  });

  it("selo 'universo de hoje' ao lado de cada retorno da estratégia e do gráfico", async () => {
    const html = await render();
    // validação: 2 linhas de estratégia; ajuste: 2 cenários; título do gráfico: 1
    expect(count(html, "universo de hoje</span>")).toBe(5);
    const val = html.slice(html.indexOf("<h2>Validação</h2>"), html.indexOf("<h2>Ajuste</h2>"));
    expect(count(val, "universo de hoje</span>")).toBe(2);
    const chartTitle = html.slice(html.indexOf("Validação (cenário dy_5)"), html.indexOf("Validação (cenário dy_5)") + 400);
    expect(chartTitle).toContain("universo de hoje");
    // os índices e o CDI não levam selo
    expect(html).not.toMatch(/IDIV<\/strong><\/td><td class="num">[^<]*<span class="seal"/);
  });

  it("texto padrão quando a execução não grava o aviso: a faixa nunca some", async () => {
    mocks.getBacktestOverview.mockResolvedValue(ov({ validation: { ...validation, survivorshipWarning: null }, fits: [{ ...baseRun, survivorshipWarning: null }] }));
    const html = await render();
    expect(html).toContain(FALLBACK_SURVIVORSHIP);
    expect(html).toContain('class="survivorship"');
  });

  it("a faixa também aparece sem backtest calculado e com o banco fora do ar", async () => {
    mocks.getBacktestOverview.mockResolvedValue({ fits: [], validation: null, freeze: null });
    const none = await render();
    expect(none).toContain("Nenhum backtest calculado");
    expect(none).toContain(FALLBACK_SURVIVORSHIP);
    mocks.getBacktestOverview.mockRejectedValue(new Error("db"));
    const down = await render();
    expect(down).toContain("Dados indisponíveis");
    expect(down).toContain(FALLBACK_SURVIVORSHIP);
  });

  it("o aviso não se repete na lista de avisos do cálculo, mas os outros aparecem", async () => {
    const html = await render();
    const list = html.slice(html.indexOf("Avisos do cálculo"));
    expect(list).not.toContain(WARNING);
    expect(list).toContain("56 meses sem compra");
    expect(list).toContain("os proventos vêm da DVA/FRE");
  });
});

describe("tela do backtest: conteúdo", () => {
  it("validação: medida uma única vez, cenário congelado, medidas e critério de morte com limite", async () => {
    const html = await render();
    expect(html).toContain("uma única vez");
    expect(html).toContain("escolhido pelo usuário");
    expect(html).toContain("15,4%"); // ao ano na validação
    expect(html).toContain("Não acionado");
    expect(html).toContain("mais de 50% das janelas");
    expect(html).toContain("mais de 10,0 p.p.");
    expect(html).toContain("2 de 24 (8,3%)");
    expect(html).toContain("Período curto: 2,0 anos"); // 2024-01-01 a 2025-12-30
    expect(html).toContain("se sobrepõem quase por inteiro");
  });

  it("critério de morte acionado e indisponível ficam explícitos", async () => {
    const seg = segment(0.154, "2024-01-01", "2025-12-30", true);
    seg.death.windows_rule_triggered = true;
    mocks.getBacktestOverview.mockResolvedValue(ov({ validation: { ...validation, metrics: { validation: seg } } }));
    expect(await render()).toContain('class="verdict on">ACIONADO');
    const seg2 = segment(0.154, "2024-01-01", "2025-12-30", null);
    seg2.death = { ...seg2.death, windows: 0, lost_windows: 0, lost_share: null, extra_drawdown: null, windows_rule_triggered: null, drawdown_rule_triggered: null, triggered: null };
    mocks.getBacktestOverview.mockResolvedValue(ov({ validation: { ...validation, metrics: { validation: seg2 } } }));
    const html = await render();
    const val = html.slice(html.indexOf("<h2>Validação</h2>"), html.indexOf("<h2>Ajuste</h2>"));
    expect(val).toContain("Indisponível (faltam janelas");
    expect(val).not.toContain("Não acionado"); // sem dado, nunca "não acionado"
  });

  it("sem validação medida: avisa em vez de inventar", async () => {
    mocks.getBacktestOverview.mockResolvedValue(ov({ validation: null }));
    const html = await render();
    expect(html).toContain("ainda não foi medida");
    expect(html).toContain("congelado (dy_5)");
    expect(html).not.toContain("uma única vez");
  });

  it("ajuste: cenários, congelado marcado, referências e links", async () => {
    const html = await render();
    expect(html).toContain("aporte_1000");
    expect(html).toContain("congelado para a validação");
    expect(html).toContain('href="/backtest?execucao=dy_5"');
    expect(html).toContain("14,2%");
    expect(html).toContain("6 de 83 (7,2%)");
    for (const ref of ["IDIV", "Ibovespa", "CDI"]) expect(html).toContain(ref);
    expect(html).toContain("referência");
  });

  it("gráfico: legenda com as séries, marcador da validação, tabela de fim de ano; nunca R$ 0,00", async () => {
    const html = await render();
    expect(html).toContain('aria-label="Legenda"');
    expect(html).toContain("Estratégia líquida (");
    expect(html).toContain("início da validação");
    expect(html).toContain("viz-line s1");
    expect(html).toContain("viz-line s4");
    expect(html).toContain("Mesmos valores do gráfico no fim de cada ano");
    // nas medidas, dado ausente é "indisponível", nunca zero (o imposto zero de uma ordem é dado real)
    expect(html.slice(0, html.indexOf("<h2>Ordens</h2>"))).not.toContain("R$ 0,00");
  });

  it("execução escolhida por URL carrega o detalhe dela, sem marcador de validação em cenário de ajuste", async () => {
    const html = await render({ execucao: "dy_5" });
    expect(mocks.getRunDetail).toHaveBeenCalledWith(1, false);
    expect(html).toContain("Cenário dy_5");
    expect(html).not.toContain("início da validação");
    await render({ execucao: "validacao", ordens: "todas" });
    expect(mocks.getRunDetail).toHaveBeenLastCalledWith(9, true);
  });

  it("fluxos, universo e ordens", async () => {
    const html = await render();
    expect(html).toContain("R$ 167.000,00");
    expect(html).toContain("R$ 589.700,50");
    expect(html).toContain("02/03/2015");
    expect(html).toContain("Universo (2 empresas)");
    expect(html).toContain("ALFA ENERGIA");
    expect(html).toContain("Mostrando as 1 mais recentes de 305");
    expect(html).toContain("Ver todas");
    expect(html).toContain("Compra");
    expect(html).toContain("Fonte:");
  });

  it("série de índice ausente: o gráfico segue com as outras, sem inventar", async () => {
    mocks.getRunDetail.mockResolvedValue({ ...detail, series: { strategy_net: detail.series.strategy_net, idiv: detail.series.idiv } });
    const html = await render();
    expect(html).toContain("IDIV (");
    expect(html).not.toContain("Ibovespa (");
  });
});
