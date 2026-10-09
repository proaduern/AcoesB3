import Link from "next/link";
import { UniverseSeal } from "@/components/backtest/Survivorship";
import {
  SERIES_LABEL,
  SERIES_ORDER,
  backtestHref,
  deathRules,
  deathVerdict,
  lostWindowsText,
  runKey,
  type Freeze,
  type RunSummary,
  type Segment,
  type SeriesKey,
  type TradeRow,
} from "@/lib/backtest";
import { UNAVAILABLE, formatBRL, formatDate, formatNumber, formatPercent } from "@/lib/format";

const isStrategy = (k: SeriesKey) => k === "strategy_net" || k === "strategy_gross";

/** Medidas de cada série no período; o selo marca as linhas da estratégia. */
export function MetricsTable({ segment }: { segment: Segment }) {
  return (
    <div className="tablewrap">
      <table>
        <caption className="sub">
          Período de {formatDate(segment.start)} a {formatDate(segment.end)}. Retornos ponderados no tempo (o aporte não distorce).
        </caption>
        <thead>
          <tr>
            <th>Série</th>
            <th className="num">Retorno no período</th>
            <th className="num">Ao ano</th>
            <th className="num">Queda máxima</th>
            <th className="num">Volatilidade</th>
          </tr>
        </thead>
        <tbody>
          {SERIES_ORDER.map((k) => {
            const s = segment.series[k];
            return (
              <tr key={k} className={k === "strategy_net" ? "selected" : undefined}>
                <td>
                  <strong>{SERIES_LABEL[k]}</strong>
                </td>
                <td className="num">
                  {formatPercent(s?.total_return, 1)}
                  {isStrategy(k) && s && <UniverseSeal />}
                </td>
                <td className="num">{formatPercent(s?.cagr, 1)}</td>
                <td className="num">{formatPercent(s?.max_drawdown, 1)}</td>
                <td className="num">{formatPercent(s?.volatility, 1)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Critério de morte: o veredito e cada regra com o valor e o limite configurado. */
export function DeathBlock({ segment, run }: { segment: Segment; run: RunSummary }) {
  const verdict = deathVerdict(segment.death);
  return (
    <div>
      <p>
        Critério de morte (contra o IDIV):{" "}
        <span className={segment.death.triggered ? "verdict on" : "verdict"}>{verdict}</span>
      </p>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Regra</th>
              <th className="num">Estratégia</th>
              <th>Aciona quando</th>
              <th>Resultado</th>
            </tr>
          </thead>
          <tbody>
            {deathRules(segment.death, run).map((r) => (
              <tr key={r.label}>
                <td>{r.label}</td>
                <td className="num">{r.value}</td>
                <td>{r.limit}</td>
                <td>{r.triggered === null ? "Indisponível" : r.triggered ? "Acionada" : "Não acionada"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Cenários do ajuste lado a lado, com os índices de referência do mesmo período. */
export function ScenarioTable({ fits, freeze, selected }: { fits: RunSummary[]; freeze: Freeze | null; selected: string | null }) {
  const ref = fits.find((r) => r.metrics.fit)?.metrics.fit;
  return (
    <div className="tablewrap">
      <table>
        <thead>
          <tr>
            <th>Cenário</th>
            <th className="num">Aporte mensal</th>
            <th className="num">Líquido ao ano</th>
            <th className="num">Bruto ao ano</th>
            <th className="num">Queda máxima</th>
            <th>Janelas perdidas para o IDIV</th>
            <th>Critério de morte</th>
          </tr>
        </thead>
        <tbody>
          {fits.map((r) => {
            const seg = r.metrics.fit;
            const key = runKey(r);
            const frozen = freeze?.scenario === r.scenario;
            return (
              <tr key={r.id} className={[frozen ? "frozen" : "", selected === key ? "selected" : ""].join(" ").trim() || undefined}>
                <td>
                  <Link href={backtestHref(key)}>
                    <strong>{r.scenario}</strong>
                  </Link>
                  {frozen && <div className="sub">congelado para a validação</div>}
                </td>
                <td className="num">{formatBRL(r.contribution, 0)}</td>
                <td className="num">
                  {formatPercent(seg?.series.strategy_net?.cagr, 1)}
                  {seg && <UniverseSeal />}
                </td>
                <td className="num">{formatPercent(seg?.series.strategy_gross?.cagr, 1)}</td>
                <td className="num">{formatPercent(seg?.series.strategy_net?.max_drawdown, 1)}</td>
                <td>{lostWindowsText(seg?.windows.idiv)}</td>
                <td>{seg ? deathVerdict(seg.death) : UNAVAILABLE}</td>
              </tr>
            );
          })}
          {ref &&
            (["idiv", "ibov", "cdi"] as const).map((k) => (
              <tr key={k}>
                <td>
                  <strong>{SERIES_LABEL[k]}</strong>
                  <div className="sub">referência</div>
                </td>
                <td className="num">—</td>
                <td className="num">{formatPercent(ref.series[k]?.cagr, 1)}</td>
                <td className="num">—</td>
                <td className="num">{formatPercent(ref.series[k]?.max_drawdown, 1)}</td>
                <td>—</td>
                <td>—</td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}

/** Aportes, valor final, custos e proventos da execução mostrada. */
export function FlowsBlock({ run }: { run: RunSummary }) {
  const f = run.metrics.flows;
  if (!f) return null;
  const rows: [string, string][] = [
    ["Total aportado", formatBRL(f.net_invested == null ? null : String(f.net_invested))],
    ["Valor final (líquido de impostos e taxas)", formatBRL(f.net_final_value == null ? null : String(f.net_final_value))],
    ["Valor final bruto", formatBRL(f.gross_final_value == null ? null : String(f.gross_final_value))],
    ["Proventos recebidos", formatBRL(f.net_dividends == null ? null : String(f.net_dividends))],
    ["Imposto pago", formatBRL(f.net_taxes == null ? null : String(f.net_taxes))],
    ["Taxas da B3", formatBRL(f.net_fees == null ? null : String(f.net_fees))],
    ["Ordens", f.net_trades == null ? UNAVAILABLE : formatNumber(f.net_trades, 0)],
    ["Primeira compra", formatDate(f.net_first_buy)],
  ];
  return (
    <dl className="inputs bt-grid">
      {rows.map(([k, v]) => (
        <div key={k}>
          <dt>{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

export function TradesTable({ trades, total, runKeyValue, all }: { trades: TradeRow[]; total: number; runKeyValue: string; all: boolean }) {
  if (total === 0) return <p>Nenhuma ordem nesta execução.</p>;
  return (
    <>
      <p className="sub">
        {all || trades.length >= total ? `Todas as ${total} ordens` : `Mostrando as ${trades.length} mais recentes de ${total}`}, da mais recente para a mais antiga.{" "}
        {!all && trades.length < total && <Link href={backtestHref(runKeyValue, true)}>Ver todas</Link>}
      </p>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Data</th>
              <th>Papel</th>
              <th>Lado</th>
              <th className="num">Quantidade</th>
              <th className="num">Preço</th>
              <th className="num">Taxa</th>
              <th className="num">Imposto</th>
              <th>Nota</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.seq}>
                <td>{formatDate(t.date)}</td>
                <td>{t.ticker}</td>
                <td>{t.side === "buy" ? "Compra" : "Venda"}</td>
                <td className="num">{formatNumber(t.quantity, Number.isInteger(Number(t.quantity)) ? 0 : 4)}</td>
                <td className="num">{formatBRL(t.price)}</td>
                <td className="num">{formatBRL(t.fee)}</td>
                <td className="num">{formatBRL(t.tax)}</td>
                <td>{t.note ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
