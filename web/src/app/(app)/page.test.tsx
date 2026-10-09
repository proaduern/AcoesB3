import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ClassRow, WatchCompany, WatchlistData } from "@/lib/watchlist";

const cls = (o: Partial<ClassRow>): ClassRow => ({
  ticker: "AAAA3",
  kind: "on",
  price: "9.900000",
  priceDate: "2026-10-02",
  ceiling: "11.00000000",
  ratio: "0.90000000",
  band: "buy",
  votes: 3,
  kRequired: 3,
  buy: true,
  reason: null,
  ...o,
});
const co = (o: Partial<WatchCompany>): WatchCompany => ({
  cvmCode: 1,
  name: "Alfa Energia",
  role: "carteira",
  segment: "energia",
  plan: "comum",
  ceilingStatus: "ok",
  methodsOk: 5,
  kRequired: 3,
  dataBase: "2025-12-31",
  collectedAt: "2026-10-04T23:30:00.000Z",
  screenStatus: "approved",
  screenAsOf: "2026-10-04",
  classes: [cls({})],
  ...o,
});

const data: WatchlistData = {
  asOf: "2026-10-05",
  companies: [
    co({}),
    co({
      cvmCode: 2,
      name: "Gama Radar",
      role: "radar",
      ceilingStatus: "insufficient",
      methodsOk: 2,
      kRequired: null,
      screenStatus: null,
      classes: [
        cls({ ticker: "GAMA3", buy: false, votes: 1, kRequired: null, ceiling: "8.00000000", ratio: "1.20000000", band: "hold" }),
        cls({ ticker: "GAMA11", kind: "unit", buy: false, votes: null, kRequired: null, ceiling: null, ratio: null, band: null, reason: "composição ilegível" }),
      ],
    }),
    co({ cvmCode: 3, name: "Delta Sem Teto", role: "radar", ceilingStatus: null, dataBase: null, collectedAt: null, classes: [] }),
  ],
};

vi.mock("@/lib/db/queries", () => ({ getWatchlist: vi.fn(async () => data) }));
vi.mock("next/link", () => ({
  default: ({ href, children, className }: { href: string; children: unknown; className?: string }) => (
    <a href={href} className={className}>{children as never}</a>
  ),
}));

describe("página da lista acompanhada", () => {
  it("mostra compra, dados insuficientes e sem teto, e nunca zero para dado ausente", async () => {
    const { default: Home } = await import("./page");
    const html = renderToStaticMarkup(await Home({ searchParams: Promise.resolve({}) }));

    expect(html).toContain("Carteira");
    expect(html).toContain("Radar");
    expect(html).toContain("COMPRA");
    expect(html).toContain("R$ 9,90");
    expect(html).toContain("90%");
    expect(html).toContain("3/3");
    expect(html).toContain("Dados insuficientes");
    expect(html).toContain("composição ilegível");
    expect(html).toContain("Sem preço teto calculado");
    expect(html).toContain("indisponível");
    expect(html).not.toContain("R$ 0,00");
    expect(html).not.toContain("0/0");
    expect(html).toContain("31/12/2025"); // exercício
    expect(html).toContain("Fonte:"); // procedência
  });

  it("filtro 'só compra' esconde quem não é compra", async () => {
    const { default: Home } = await import("./page");
    const html = renderToStaticMarkup(await Home({ searchParams: Promise.resolve({ compra: "1" }) }));
    expect(html).toContain("Alfa Energia");
    expect(html).not.toContain("Gama Radar");
    expect(html).not.toContain("Delta Sem Teto");
  });
});
