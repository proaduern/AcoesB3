import { Provenance } from "@/components/Provenance";
import {
  METHOD_LABEL,
  METHOD_STATUS_LABEL,
  describeInputs,
  type CeilingTab,
} from "@/lib/company";
import { UNAVAILABLE, formatBRL, formatDate, formatPercent } from "@/lib/format";
import { BAND_LABEL, situation } from "@/lib/watchlist";

export function CeilingSection({ tab }: { tab: CeilingTab }) {
  if (!tab.asOf || tab.status === null) {
    return <p>Sem preço teto calculado para esta empresa: rode `acoesb3 compute --step ceilings`.</p>;
  }
  return (
    <>
      <p>
        <strong>Teto consolidado (mediana dos métodos): {formatBRL(tab.ceiling)} por ação</strong>
        <span className="sub">
          {" "}
          · {tab.methodsOk ?? 0} método(s) aplicável(is) · votos exigidos (K):{" "}
          {tab.kRequired ?? "n/a"}
          {tab.status === "insufficient" && " · dados insuficientes: o teto aparece, mas nunca é compra"}
        </span>
      </p>
      <p className="sub">
        Cálculo de {formatDate(tab.asOf)}. Valores por ação na base de ações dessa data; o mesmo valor vale para todas as
        classes e a unit soma as ações da composição.
      </p>

      <h2>Papéis</h2>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Papel</th>
              <th className="num">Preço</th>
              <th className="num">Teto</th>
              <th className="num">Preço ÷ teto</th>
              <th>Faixa</th>
              <th className="num">Votos</th>
              <th>Situação</th>
            </tr>
          </thead>
          <tbody>
            {tab.classes.map((k) => (
              <tr key={k.ticker} className={k.buy ? "buy" : undefined}>
                <td>
                  <strong>{k.ticker}</strong>
                  <div className="sub">{k.kind === "unit" ? "unit" : k.kind.toUpperCase()}</div>
                </td>
                <td className="num">
                  {formatBRL(k.price)}
                  <div className="sub">{formatDate(k.priceDate)}</div>
                </td>
                <td className="num">{formatBRL(k.ceiling)}</td>
                <td className="num">{formatPercent(k.ratio, 0)}</td>
                <td>{k.band ? BAND_LABEL[k.band] : UNAVAILABLE}</td>
                <td className="num">
                  {k.votes !== null && k.kRequired !== null ? `${k.votes}/${k.kRequired}` : UNAVAILABLE}
                </td>
                <td>
                  {situation({ ceilingStatus: tab.status }, k)}
                  {k.reason && <div className="sub">{k.reason}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <h2>Métodos</h2>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Método</th>
              <th>Situação</th>
              <th className="num">Teto por ação</th>
              <th>Detalhe</th>
            </tr>
          </thead>
          <tbody>
            {tab.methods.map((m) => {
              const lines = describeInputs(m.inputs);
              return (
                <tr key={m.method}>
                  <td>
                    <strong>{METHOD_LABEL[m.method] ?? m.method}</strong>
                  </td>
                  <td>
                    {METHOD_STATUS_LABEL[m.status] ?? m.status}
                    {m.reason && <div className="sub">{m.reason}</div>}
                  </td>
                  <td className="num">{m.status === "ok" ? formatBRL(m.value) : UNAVAILABLE}</td>
                  <td>
                    {lines.length > 0 ? (
                      <details>
                        <summary>Insumos</summary>
                        <dl className="inputs">
                          {lines.map((l) => (
                            <div key={l.label}>
                              <dt>{l.label}</dt>
                              <dd>{l.value}</dd>
                            </div>
                          ))}
                        </dl>
                        <Provenance source={m.source} dataBase={m.dataBase} collectedAt={m.collectedAt} />
                      </details>
                    ) : (
                      <Provenance source={m.source} dataBase={m.dataBase} collectedAt={m.collectedAt} />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Provenance
        source="CVM Dados Abertos (DFP/FRE) e B3 (COTAHIST); cálculo do pipeline"
        dataBase={tab.dataBase}
        collectedAt={tab.collectedAt}
      />
    </>
  );
}
