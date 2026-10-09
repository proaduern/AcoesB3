import { Provenance } from "@/components/Provenance";
import type { OriginTab } from "@/lib/company";
import { UNAVAILABLE, formatBRLCompact, formatDate, formatNumber } from "@/lib/format";

const SOURCE: Record<string, string> = {
  fre: "FRE (CVM)",
  cotahist: "Salto de preço (COTAHIST)",
  manual: "Informado à mão",
  dva: "DVA (CVM)",
};
const DATE_BASIS: Record<string, string> = {
  cotahist: "data do salto de preço",
  approval: "data de aprovação (não a de efeito)",
};
const EVENT_STATUS: Record<string, string> = { suspected: "suspeito, aguarda revisão", rejected: "rejeitado" };

export function OriginSection({ tab }: { tab: OriginTab }) {
  const lastCollected = tab.dividends.map((d) => d.collectedAt).filter((v): v is string => !!v).sort().at(-1) ?? null;
  return (
    <>
      <h2>Cadastro</h2>
      <dl className="inputs">
        <div><dt>CNPJ</dt><dd>{tab.cnpj || UNAVAILABLE}</dd></div>
        <div><dt>Setor declarado à CVM</dt><dd>{tab.sector ?? UNAVAILABLE}</dd></div>
        <div><dt>Plano de contas</dt><dd>{tab.plan ?? "não identificado"}</dd></div>
        <div>
          <dt>Reclassificação manual</dt>
          <dd>
            {tab.override
              ? `${tab.override.sector ? `setor: ${tab.override.sector}; ` : ""}${tab.override.plan ? `plano: ${tab.override.plan}` : ""}${tab.override.note ? ` — ${tab.override.note}` : ""}`
              : "nenhuma"}
          </dd>
        </div>
      </dl>

      <h2>Eventos societários</h2>
      {tab.events.length === 0 ? (
        <p>Nenhum evento aplicado.</p>
      ) : (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Data</th>
                <th className="num">Fator</th>
                <th>Origem</th>
                <th>Tipo</th>
                <th>Base da data</th>
                <th>Conhecido desde</th>
              </tr>
            </thead>
            <tbody>
              {tab.events.map((e) => (
                <tr key={`${e.date}-${e.source}-${e.factor}`}>
                  <td>{formatDate(e.date)}</td>
                  <td className="num">{formatNumber(e.factor, 4)}</td>
                  <td>{SOURCE[e.source] ?? e.source}</td>
                  <td>{e.eventType ?? UNAVAILABLE}</td>
                  <td>{DATE_BASIS[e.dateBasis] ?? e.dateBasis}</td>
                  <td>{formatDate(e.knownFrom)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {tab.suspectedEvents.length > 0 && (
        <>
          <p className="sub">Saltos de preço detectados que não foram aplicados:</p>
          <ul>
            {tab.suspectedEvents.map((e) => (
              <li key={`${e.ticker}-${e.date}-${e.status}`}>
                {e.ticker}, {formatDate(e.date)}, fator {formatNumber(e.factor, 4)}: {EVENT_STATUS[e.status] ?? e.status}
              </li>
            ))}
          </ul>
        </>
      )}

      <h2>Proventos por exercício</h2>
      <p className="sub">Total declarado no exercício (DVA da DFP; FRE ou lançamento manual quando a DVA falta). Valores em reais.</p>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Exercício</th>
              <th className="num">JCP</th>
              <th className="num">Dividendos</th>
              <th>Fonte</th>
            </tr>
          </thead>
          <tbody>
            {tab.dividends.map((d) => (
              <tr key={d.referenceDate}>
                <td>{formatDate(d.referenceDate)}</td>
                <td className="num">{formatBRLCompact(d.jcp)}</td>
                <td className="num">{formatBRLCompact(d.dividends)}</td>
                <td>
                  {d.source ? (SOURCE[d.source] ?? d.source) : UNAVAILABLE}
                  {d.manual && <div className="sub">lançado à mão{d.note ? `: ${d.note}` : ""}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Provenance source="CVM Dados Abertos (DFP, FRE, FCA)" dataBase={tab.dividends[0]?.referenceDate ?? null} collectedAt={lastCollected} />
    </>
  );
}
