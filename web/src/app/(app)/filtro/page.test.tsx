import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { Pending, ScreenPage } from "@/lib/db/screen";

const page: ScreenPage = {
  asOf: "2026-10-04",
  counts: { approved: 1, rejected: 2, not_listed: 1 },
  total: 3,
  page: 1,
  pages: 1,
  rows: [
    {
      cvmCode: 1,
      name: "ALFA ENERGIA S.A.",
      sector: "Energia Elétrica",
      tickers: ["ALFA3", "ALFA4"],
      status: "rejected",
      dataBase: "2025-12-31",
      collectedAt: "2026-10-03T12:00:00.000Z",
      role: "carteira",
      criteria: [
        { criterion: "roe_medio", status: "fail", value: "0.08", threshold: "> 0.10", reason: null },
        { criterion: "dy_medio_liquido", status: "unavailable", value: null, threshold: "> 0.05", reason: "data" },
        { criterion: "liquidez", status: "pass", value: "12500000", threshold: "volume >= 1000000", reason: null },
      ],
    },
    {
      cvmCode: 4,
      name: "DELTA S.A.",
      sector: null,
      tickers: [],
      status: "not_listed",
      dataBase: null,
      collectedAt: null,
      role: null,
      criteria: [],
    },
  ],
};

const pending: Pending = {
  outliersTotal: 12,
  outliers: [{ cvmCode: 1, name: "ALFA ENERGIA S.A.", referenceDate: "2023-12-31", total: "900000000", median: "300000000", ratio: "3.0000" }],
  eventsTotal: 1,
  events: [{ id: 7, ticker: "ALFA3", eventDate: "2024-05-10", factor: "2.00000000" }],
  dividendsToEnter: [{ cvmCode: 1, name: "ALFA ENERGIA S.A.", years: [2021, 2022] }],
};

vi.mock("@/lib/db/queries", () => ({
  getScreen: vi.fn(async () => page),
  getPending: vi.fn(async () => pending),
}));
vi.mock("next/link", () => ({
  default: ({ href, children, className }: { href: string; children: unknown; className?: string }) => (
    <a href={href} className={className}>{children as never}</a>
  ),
}));

describe("página do filtro", () => {
  it("mostra status, critérios com valor formatado e nunca zero para dado ausente", async () => {
    const { default: FiltroPage } = await import("./page");
    const html = renderToStaticMarkup(await FiltroPage({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("ALFA3, ALFA4");
    expect(html).toContain("Reprovada");
    expect(html).toContain("Na lista: Carteira");
    expect(html).toContain("Reprovou: ROE médio de 5 anos");
    expect(html).toContain("Indisponível: DY médio líquido de 5 anos");
    expect(html).toContain("8,0%"); // ROE 0.08 como percentual
    expect(html).toContain("R$ 12,50 mi");
    expect(html).toContain("&gt; 0,10"); // limite com vírgula
    expect(html).toContain("falta dado em algum ano da janela");
    expect(html).toContain("sem ticker no FCA");
    expect(html).toContain("Sem papel mapeado");
    expect(html).toContain("Reprovada (2)"); // contagem por status no chip
    expect(html).toContain("/filtro/pendencias");
    expect(html).toContain("Fonte:");
    expect(html).not.toContain("R$ 0,00");
  });
});

describe("página de pendências", () => {
  it("mostra os comandos e deixa claro que a tela só lê", async () => {
    const { default: Pendencias } = await import("./pendencias/page");
    const html = renderToStaticMarkup(await Pendencias());
    expect(html).toContain("só lê o banco");
    expect(html).toContain("acoesb3 review outlier --cvm 1 --date 2023-12-31");
    expect(html).toContain("acoesb3 review event --id 7");
    expect(html).toContain("ALFA ENERGIA S.A. (CVM 1): 2021, 2022");
    expect(html).toContain("12 pendente(s)");
    expect(html).toContain("3,0×");
  });
});
