import Link from "next/link";
import { PriceChart } from "@/components/charts/PriceChart";
import { Provenance } from "@/components/Provenance";
import { PERIODS, companyHref, type PriceTab } from "@/lib/company";
import { formatDate, formatNumber } from "@/lib/format";

export function PriceSection({ cvm, tab, period }: { cvm: number; tab: PriceTab; period: number }) {
  if (!tab.ticker) return <p>Sem papel com preço teto para mostrar o preço.</p>;
  return (
    <>
      <nav className="filters" aria-label="Papel e período">
        <span>Papel:</span>
        {tab.tickers.map((t) => (
          <Link
            key={t}
            href={companyHref(cvm, { aba: "preco", papel: t, periodo: period as 1 })}
            className={t === tab.ticker ? "chip active" : "chip"}
          >
            {t}
          </Link>
        ))}
        <span>Período:</span>
        {PERIODS.map((p) => (
          <Link
            key={p}
            href={companyHref(cvm, { aba: "preco", papel: tab.ticker, periodo: p })}
            className={p === period ? "chip active" : "chip"}
          >
            {p} {p === 1 ? "ano" : "anos"}
          </Link>
        ))}
      </nav>
      {tab.points.length === 0 ? (
        <p>Cotações indisponíveis para {tab.ticker} neste período.</p>
      ) : (
        <>
          <PriceChart ticker={tab.ticker} points={tab.points} events={tab.events} ceiling={tab.ceiling} ceilingFrom={tab.ceilingFrom} />
          <p className="sub">
            Fechamento semanal (último pregão da semana) do COTAHIST, <strong>sem ajuste por desdobramentos e
            grupamentos</strong>. O teto está na base de ações de hoje; por isso a linha só é desenhada depois do último
            evento societário{tab.ceilingFrom ? ` (${formatDate(tab.ceilingFrom)})` : " do período (não houve evento)"}.
          </p>
          {tab.events.length > 0 && (
            <p className="sub">
              Eventos no período (linhas verticais cinza):{" "}
              {tab.events.map((e) => `${formatDate(e.date)} (fator ${formatNumber(e.factor, 4)})`).join("; ")}.
            </p>
          )}
        </>
      )}
      <Provenance source="B3 (COTAHIST)" dataBase={tab.lastQuoteDate} collectedAt={null} />
    </>
  );
}
