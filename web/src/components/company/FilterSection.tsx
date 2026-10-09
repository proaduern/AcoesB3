import { ColumnChart, type ColumnPoint } from "@/components/charts/ColumnChart";
import { CriteriaTable } from "@/components/CriteriaTable";
import { Provenance } from "@/components/Provenance";
import { seriesYears, type FilterTab, type OutlierRow } from "@/lib/company";
import { UNAVAILABLE, formatBRL, formatBRLCompact, formatDate, formatPercent } from "@/lib/format";
import { STATUS_LABEL, isStatus } from "@/lib/screen";

/** Situação de cada ano de provento suspeito: sem decisão fica fora das médias. */
export function outlierByYear(outliers: OutlierRow[]): Map<number, { excluded: boolean; label: string }> {
  const m = new Map<number, { excluded: boolean; label: string }>();
  for (const o of outliers) {
    const year = Number(o.referenceDate.slice(0, 4));
    if (o.decision === "include") m.set(year, { excluded: false, label: "outlier liberado (dentro das médias)" });
    else if (o.decision === "exclude") m.set(year, { excluded: true, label: "outlier excluído" });
    else m.set(year, { excluded: true, label: "outlier pendente (fora das médias)" });
  }
  return m;
}

function points(
  values: Record<string, string>,
  out: Map<number, { excluded: boolean; label: string }>,
  fmt: (v: string) => string,
  num: (v: string) => number,
): ColumnPoint[] {
  return Object.keys(values)
    .map(Number)
    .sort((a, b) => a - b)
    .map((year) => {
      const raw = values[String(year)] as string;
      const o = out.get(year);
      return { label: String(year), value: num(raw), text: fmt(raw), muted: o?.excluded, note: o?.label };
    });
}

const compactAxis = (n: number) => formatBRLCompact(n).replace("R$ ", "");
const pctAxis = (n: number) => formatPercent(n, 0);
const brlAxis = (n: number) => formatBRL(n, 2).replace("R$ ", "");

export function FilterSection({ tab }: { tab: FilterTab }) {
  if (!tab.asOf) {
    return <p>Nenhum retrato do filtro para esta empresa: rode `acoesb3 compute --step screens`.</p>;
  }
  const out = outlierByYear(tab.outliers);
  const s = tab.series;
  const years = seriesYears(s);
  const hasMuted = [...out.values()].some((o) => o.excluded);
  const n = (v: string) => Number(v);
  const cell = (m: Record<string, string>, y: number, f: (v: string) => string) =>
    m[String(y)] === undefined ? UNAVAILABLE : f(m[String(y)] as string);

  return (
    <>
      <p>
        Status do retrato de {formatDate(tab.asOf)}:{" "}
        <strong>{tab.status && isStatus(tab.status) ? STATUS_LABEL[tab.status] : (tab.status ?? UNAVAILABLE)}</strong>
      </p>
      <CriteriaTable criteria={tab.criteria} className="" />

      <h2>Histórico anual</h2>
      <p className="sub">
        Valores gravados pelo pipeline no detalhe de cada critério (janela do critério). Ano sem barra = indisponível.
        {hasMuted && (
          <>
            {" "}
            <span className="viz-key-muted" />
            Cinza = ano de outlier fora das médias.
          </>
        )}
      </p>
      <div className="charts">
        <ColumnChart title="Lucro do controlador (R$)" yFormat={compactAxis} points={points(s.profit, out, (v) => formatBRLCompact(v), n)} />
        <ColumnChart title="ROE" yFormat={pctAxis} points={points(s.roe, out, (v) => formatPercent(v, 1), n)} />
        <ColumnChart title="Dividendo por ação (R$)" yFormat={brlAxis} points={points(s.dps, out, (v) => formatBRL(v), n)} />
        <ColumnChart title="Dividend yield líquido" yFormat={pctAxis} points={points(s.dy, out, (v) => formatPercent(v, 1), n)} />
        <ColumnChart title="Payout" yFormat={pctAxis} points={points(s.payout, out, (v) => formatPercent(v, 0), n)} />
      </div>

      <div className="tablewrap">
        <table>
          <caption className="sub">Mesmos valores dos gráficos, em tabela</caption>
          <thead>
            <tr>
              <th>Exercício</th>
              <th className="num">Lucro</th>
              <th className="num">ROE</th>
              <th className="num">Dividendo por ação</th>
              <th className="num">DY líquido</th>
              <th className="num">Payout</th>
              <th>Fonte do provento</th>
              <th>Outlier</th>
            </tr>
          </thead>
          <tbody>
            {[...years].reverse().map((y) => (
              <tr key={y}>
                <td>{y}</td>
                <td className="num">{cell(s.profit, y, (v) => formatBRLCompact(v))}</td>
                <td className="num">{cell(s.roe, y, (v) => formatPercent(v, 1))}</td>
                <td className="num">{cell(s.dps, y, (v) => formatBRL(v))}</td>
                <td className="num">{cell(s.dy, y, (v) => formatPercent(v, 1))}</td>
                <td className="num">{cell(s.payout, y, (v) => formatPercent(v, 0))}</td>
                <td className="nowrap">{tab.sources[String(y)] ?? UNAVAILABLE}</td>
                <td className="nowrap">{out.get(y)?.label ?? ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {tab.outliers.length > 0 && (
        <>
          <h2>Proventos suspeitos</h2>
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Exercício</th>
                  <th className="num">Total</th>
                  <th className="num">Mediana de 5 anos</th>
                  <th>Decisão</th>
                </tr>
              </thead>
              <tbody>
                {tab.outliers.map((o) => (
                  <tr key={o.referenceDate}>
                    <td>{formatDate(o.referenceDate)}</td>
                    <td className="num">{formatBRLCompact(o.total)}</td>
                    <td className="num">{formatBRLCompact(o.median)}</td>
                    <td>{outlierByYear([o]).get(Number(o.referenceDate.slice(0, 4)))?.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <Provenance source="CVM Dados Abertos (DFP, FRE) e B3 (COTAHIST)" dataBase={tab.dataBase} collectedAt={tab.collectedAt} />
    </>
  );
}
