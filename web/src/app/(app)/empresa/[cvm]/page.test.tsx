import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CeilingTab, CompanyHeader, FilterTab, OriginTab, PriceTab } from "@/lib/company";

const header: CompanyHeader = {
  cvmCode: 1,
  name: "ALFA ENERGIA S.A.",
  cnpj: "11.111.111/0001-11",
  sector: "Energia Elétrica",
  role: "carteira",
  segment: "energia",
  tickers: ["ALFA3", "ALFA4"],
};

const ceiling: CeilingTab = {
  asOf: "2026-10-05",
  status: "ok",
  ceiling: "11.00000000",
  methodsOk: 3,
  kRequired: 2,
  plan: "comum",
  dataBase: "2025-12-31",
  collectedAt: "2026-10-04T23:30:00.000Z",
  methods: [
    { method: "bazin", status: "ok", value: "10.00000000", reason: null, inputs: { mean: "0.60", rate: "0.06" }, source: "CVM DFP", dataBase: "2025-12-31", collectedAt: null },
    { method: "graham", status: "excluded", value: null, reason: "LPA ou VPA não positivo", inputs: {}, source: "CVM DFP", dataBase: null, collectedAt: null },
    { method: "dcf", status: "unavailable", value: null, reason: "crescimento histórico indisponível", inputs: {}, source: "CVM DFC", dataBase: null, collectedAt: null },
  ],
  classes: [
    { ticker: "ALFA3", kind: "on", price: "9.900000", priceDate: "2026-10-02", ceiling: "11.00000000", ratio: "0.90000000", band: "buy", votes: 2, kRequired: 2, buy: true, reason: null },
    { ticker: "ALFA11", kind: "unit", price: "31.000000", priceDate: "2026-10-02", ceiling: null, ratio: null, band: null, votes: null, kRequired: null, buy: false, reason: "composição ilegível" },
  ],
};

const filter: FilterTab = {
  asOf: "2026-10-04",
  status: "approved",
  dataBase: "2025-12-31",
  collectedAt: null,
  criteria: [{ criterion: "roe_medio", status: "pass", value: "0.15", threshold: "> 0.10", reason: null }],
  series: {
    profit: { "2024": "1000000000", "2025": "1200000000" },
    roe: { "2024": "0.14", "2025": "0.16" },
    dps: { "2024": "0.55", "2025": "0.65" },
    dy: {},
    payout: { "2025": "0.52" },
  },
  sources: { "2024": "dva", "2025": "manual" },
  outliers: [{ referenceDate: "2024-12-31", total: "900000000", median: "300000000", ratio: "3", decision: null }],
};

const price: PriceTab = {
  tickers: ["ALFA3", "ALFA4"],
  ticker: "ALFA3",
  points: [
    { date: "2026-09-18", close: "8.500000" },
    { date: "2026-09-25", close: "9.200000" },
    { date: "2026-10-02", close: "9.900000" },
  ],
  events: [{ date: "2026-09-22", factor: "1.40000000", source: "cotahist" }],
  ceiling: "11.00000000",
  ceilingAsOf: "2026-10-05",
  ceilingFrom: "2026-09-22",
  lastQuoteDate: "2026-10-02",
};

const origin: OriginTab = {
  cnpj: "11.111.111/0001-11",
  sector: "Energia Elétrica",
  plan: "comum",
  override: { sector: null, plan: "seguradora", note: "DVA de seguradora" },
  events: [{ date: "2019-06-03", factor: "2.00000000", source: "fre", dateBasis: "approval", eventType: "Desdobramento", knownFrom: "2019-06-10", note: null }],
  suspectedEvents: [{ ticker: "ALFA3", date: "2024-05-10", factor: "2.00000000", status: "suspected" }],
  dividends: [{ referenceDate: "2025-12-31", jcp: "10000000", dividends: "100000000", source: "manual", manual: true, note: "RI da empresa", collectedAt: "2026-10-01T10:00:00.000Z" }],
};

const mocks = vi.hoisted(() => ({
  getCompanyHeader: vi.fn(),
  getCeilingTab: vi.fn(),
  getFilterTab: vi.fn(),
  getPriceTab: vi.fn(),
  getOriginTab: vi.fn(),
  notFound: vi.fn(() => {
    throw new Error("NEXT_NOT_FOUND");
  }),
}));
vi.mock("@/lib/db/queries", () => mocks);
vi.mock("next/navigation", () => ({ notFound: mocks.notFound }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: unknown; className?: string; "aria-current"?: "page" }) => (
    <a href={href} {...rest}>{children as never}</a>
  ),
}));

async function render(cvm: string, q: Record<string, string> = {}) {
  const { default: Page } = await import("./page");
  return renderToStaticMarkup(await Page({ params: Promise.resolve({ cvm }), searchParams: Promise.resolve(q) }));
}

beforeEach(() => {
  mocks.getCompanyHeader.mockResolvedValue(header);
  mocks.getCeilingTab.mockResolvedValue(ceiling);
  mocks.getFilterTab.mockResolvedValue(filter);
  mocks.getPriceTab.mockResolvedValue(price);
  mocks.getOriginTab.mockResolvedValue(origin);
  mocks.notFound.mockClear();
});

describe("ficha da empresa", () => {
  it("cabeçalho e abas", async () => {
    const html = await render("1");
    expect(html).toContain("ALFA ENERGIA S.A.");
    expect(html).toContain("Papéis: ALFA3, ALFA4");
    for (const t of ["Preço teto", "Filtro", "Preço", "Origem dos dados"]) expect(html).toContain(t);
    expect(html).toContain('aria-current="page"');
  });

  it("aba Preço teto: consolidado, métodos com motivo e insumos, papel sem teto com motivo", async () => {
    const html = await render("1");
    expect(html).toContain("R$ 11,00 por ação");
    expect(html).toContain("COMPRA");
    expect(html).toContain("Bazin");
    expect(html).toContain("Excluído pela regra");
    expect(html).toContain("LPA ou VPA não positivo");
    expect(html).toContain("crescimento histórico indisponível");
    expect(html).toContain("Dividendo médio líquido por ação");
    expect(html).toContain("composição ilegível");
    expect(html).toContain("Fonte:");
    expect(html).not.toContain("R$ 0,00");
  });

  it("empresa sem cálculo: aviso, sem tabelas vazias", async () => {
    mocks.getCeilingTab.mockResolvedValue({ ...ceiling, asOf: null, status: null, ceiling: null, methods: [], classes: [] });
    expect(await render("1")).toContain("Sem preço teto calculado");
  });

  it("aba Filtro: critérios, gráficos com título, tabela com indisponível e outlier pendente em cinza", async () => {
    const html = await render("1", { aba: "filtro" });
    expect(html).toContain("Aprovada");
    expect(html).toContain("ROE médio de 5 anos");
    expect(html).toContain('aria-label="Lucro do controlador (R$)"');
    expect(html).toContain("viz-bar muted"); // 2024: outlier pendente
    expect(html).toContain("outlier pendente (fora das médias)");
    expect(html).toContain("Cinza = ano de outlier fora das médias");
    expect(html).toContain("indisponível"); // DY sem série
    expect(html).toContain("manual");
    expect(html).not.toContain("0,0%");
  });

  it("aba Preço: gráfico com legenda das duas séries, seletor de papel/período e aviso sobre ajuste", async () => {
    const html = await render("1", { aba: "preco", papel: "ALFA3", periodo: "3" });
    expect(mocks.getPriceTab).toHaveBeenCalledWith(1, ["ALFA3", "ALFA4"], "ALFA3", 3);
    expect(html).toContain("Fechamento de ALFA3 (R$ 9,90 em 02/10/2026)");
    expect(html).toContain("Teto de hoje (R$ 11,00)");
    expect(html).toContain("sem ajuste por desdobramentos");
    expect(html).toContain("22/09/2026");
    expect(html).toContain("3 anos");
    expect(html).toContain("viz-line s2");
  });

  it("aba Preço sem teto do papel: só uma série e sem legenda do teto", async () => {
    mocks.getPriceTab.mockResolvedValue({ ...price, ceiling: null, ceilingFrom: null });
    const html = await render("1", { aba: "preco" });
    expect(html).not.toContain("Teto de hoje");
    expect(html).not.toContain("viz-line s2");
  });

  it("aba Origem: reclassificação, eventos, suspeitos e provento lançado à mão", async () => {
    const html = await render("1", { aba: "origem" });
    expect(html).toContain("plano: seguradora");
    expect(html).toContain("data de aprovação (não a de efeito)");
    expect(html).toContain("suspeito, aguarda revisão");
    expect(html).toContain("lançado à mão: RI da empresa");
  });

  it("empresa fora da lista ou código inválido = não encontrada", async () => {
    mocks.getCompanyHeader.mockResolvedValue(null);
    await expect(render("2")).rejects.toThrow("NEXT_NOT_FOUND");
    await expect(render("abc")).rejects.toThrow("NEXT_NOT_FOUND");
    expect(mocks.getCeilingTab).not.toHaveBeenCalled();
  });

  it("banco fora do ar: aviso, não erro", async () => {
    mocks.getCeilingTab.mockRejectedValue(new Error("db"));
    expect(await render("1")).toContain("Dados indisponíveis");
    mocks.getCompanyHeader.mockRejectedValue(new Error("db"));
    expect(await render("1")).toContain("Dados indisponíveis");
  });
});
