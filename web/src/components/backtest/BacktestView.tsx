import Link from "next/link";
import { MultiLineChart, type LineSeries } from "@/components/charts/MultiLineChart";
import { Provenance } from "@/components/Provenance";
import { SurvivorshipBanner, UniverseSeal } from "@/components/backtest/Survivorship";
import { DeathBlock, FlowsBlock, MetricsTable, ScenarioTable, TradesTable } from "@/components/backtest/Tables";
import {
  SERIES_SHORT,
  backtestHref,
  rebase,
  runKey,
  yearEnds,
  yearsBetween,
  type BacktestOverview,
  type RunDetail,
  type RunSummary,
  type SeriesKey,
} from "@/lib/backtest";
import { UNAVAILABLE, formatDate, formatDateTime, formatNumber } from "@/lib/format";

const TONES: Record<string, LineSeries["tone"]> = { strategy_net: "s1", idiv: "s2", ibov: "s3", cdi: "s4" };
const CHART_SERIES: SeriesKey[] = ["strategy_net", "idiv", "ibov", "cdi"];

function chartSeries(detail: RunDetail): LineSeries[] {
  return CHART_SERIES.flatMap((k) => {
    const pts = rebase(detail.series[k] ?? []);
    return pts.length >= 2 ? [{ key: k, label: SERIES_SHORT[k], tone: TONES[k] as LineSeries["tone"], points: pts }] : [];
  });
}

function YearTable({ series }: { series: LineSeries[] }) {
  const byYear = series.map((s) => yearEnds(s.points));
  const years = [...new Set(byYear.flatMap((m) => [...m.keys()]))].sort((a, b) => a - b);
  return (
    <div className="tablewrap">
      <table>
        <caption className="sub">Mesmos valores do gráfico no fim de cada ano (início = 100)</caption>
        <thead>
          <tr>
            <th>Ano</th>
            {series.map((s) => (
              <th key={s.key} className="num">{SERIES_SHORT[s.key as SeriesKey]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {years.map((y) => (
            <tr key={y}>
              <td>{y}</td>
              {byYear.map((m, i) => (
                <td key={series[i]!.key} className="num">{m.has(y) ? formatNumber(m.get(y)!.value, 1) : UNAVAILABLE}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ValidationBlock({ ov, run }: { ov: BacktestOverview; run: RunSummary }) {
  const seg = run.metrics.validation;
  if (!seg) return <p>A execução de validação não traz as medidas do período.</p>;
  const years = yearsBetween(seg.start, seg.end);
  const windows = seg.death.windows;
  return (
    <>
      <p className="notice-inline">
        Medida <strong>uma única vez</strong> em {formatDateTime(run.createdAt)}, com o cenário congelado <strong>{run.scenario}</strong>
        {ov.freeze?.note ? ` (“${ov.freeze.note}”)` : ""}. Os parâmetros não podem ser reajustados com base nela; o banco recusa uma segunda medição.
      </p>
      <MetricsTable segment={seg} />
      <DeathBlock segment={seg} run={run} />
      {years < 3.5 && (
        <p className="sub">
          Período curto: {formatNumber(years, 1)} anos (de {formatDate(seg.start)} a {formatDate(seg.end)}), em vez dos 3 reservados na
          especificação. {windows > 0 && `As ${windows} janelas de ${run.windowYears ?? 5} anos que terminam nele se sobrepõem quase por inteiro.`}{" "}
          Leia como indício, não como prova.
        </p>
      )}
    </>
  );
}


/** A tela do backtest sobre dados já lidos (a página só carrega e trata falhas). */
export function BacktestView({
  overview,
  run,
  detail,
  allTrades,
}: {
  overview: BacktestOverview;
  run: RunSummary;
  detail: RunDetail;
  allTrades: boolean;
}) {
  const series = chartSeries(detail);
  const key = runKey(run);
  const keys = [...overview.fits.map((r) => runKey(r)), ...(overview.validation ? [runKey(overview.validation)] : [])];
  const marker = run.kind === "validation" && run.validationStart ? { date: run.validationStart, label: "início da validação" } : null;
  const warnings = run.warnings.filter((w) => w !== run.survivorshipWarning);
  const fitRuns = overview.fits;

  return (
    <main>
      <h1>Backtest</h1>
      <SurvivorshipBanner run={overview.validation ?? run} />

      <section>
        <h2>Validação</h2>
        {overview.validation ? (
          <ValidationBlock ov={overview} run={overview.validation} />
        ) : (
          <p>
            A validação (os últimos anos reservados) ainda não foi medida. Ela só pode ser medida uma vez, com o cenário
            congelado{overview.freeze ? ` (${overview.freeze.scenario})` : ""}.
          </p>
        )}
      </section>

      <section>
        <h2>Ajuste</h2>
        {fitRuns.length === 0 ? (
          <p>Nenhum cenário de ajuste calculado.</p>
        ) : (
          <>
            <p className="sub">
              Período de {formatDate(fitRuns[0]!.startDate)} a {formatDate(fitRuns[0]!.endDate)}, antes da validação. Clique no cenário para ver o gráfico e as
              ordens dele.
            </p>
            <ScenarioTable fits={fitRuns} freeze={overview.freeze} selected={key} />
          </>
        )}
      </section>

      <section>
        <h2>
          {run.kind === "validation" ? `Validação (cenário ${run.scenario}), 2012 em diante` : `Cenário ${run.scenario}`}
          <UniverseSeal />
        </h2>
        <nav className="runs" aria-label="Execução mostrada">
          {keys.map((k) => (
            <Link key={k} href={backtestHref(k)} className={k === key ? "chip active" : "chip"} aria-current={k === key ? "true" : undefined}>
              {k === "validacao" ? "validação" : k}
            </Link>
          ))}
        </nav>
        <p className="sub">
          Níveis reescalados (início = 100): estratégia líquida de custos e impostos, com aporte mensal de {run.contribution ? `R$ ${run.contribution}` : UNAVAILABLE}
          ; índices e CDI investidos 100%. Período de {formatDate(run.startDate)} a {formatDate(run.endDate)}.
        </p>
        <MultiLineChart title={`Backtest ${run.scenario}: níveis reescalados`} series={series} marker={marker} />
        {series.length > 0 && <YearTable series={series} />}
        <h3>Fluxos</h3>
        <FlowsBlock run={run} />
      </section>

      {warnings.length > 0 && (
        <section>
          <h2>Avisos do cálculo</h2>
          <ul>
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2>Universo ({run.companies.length} empresas)</h2>
        <details>
          <summary>Ver as empresas</summary>
          <ul>
            {run.companies.map((c, i) => (
              <li key={`${c.name}-${i}`}>
                {c.name ?? UNAVAILABLE} <span className="sub">({c.segment ?? UNAVAILABLE})</span>
              </li>
            ))}
          </ul>
        </details>
      </section>

      <section>
        <h2>Ordens</h2>
        <TradesTable trades={detail.trades} total={detail.tradesTotal} runKeyValue={key} all={allTrades} />
      </section>

      <Provenance
        source="B3 (COTAHIST, Ibovespa e IDIV), Banco Central (CDI) e CVM Dados Abertos; simulação do pipeline"
        dataBase={run.endDate}
        collectedAt={run.createdAt}
      />
    </main>
  );
}
