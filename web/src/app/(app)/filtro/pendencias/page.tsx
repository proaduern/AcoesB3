import Link from "next/link";
import { getPending } from "@/lib/db/queries";
import type { Pending } from "@/lib/db/screen";
import { formatBRL, formatDate, formatNumber } from "@/lib/format";

export const dynamic = "force-dynamic";

async function load(): Promise<Pending | null> {
  try {
    return await getPending();
  } catch {
    return null;
  }
}

export default async function PendenciasPage() {
  const p = await load();
  if (!p) {
    return (
      <main>
        <h1>Pendências de revisão</h1>
        <p>Dados indisponíveis: não foi possível ler o banco agora.</p>
      </main>
    );
  }
  return (
    <main>
      <h1>Pendências de revisão</h1>
      <p className="sub">
        A tela só lê o banco: a decisão é registrada por comando (ou pelo workflow no GitHub Actions) e vale no
        próximo `compute`. <Link href="/filtro">← Filtro</Link>
      </p>

      <section>
        <h2>Proventos suspeitos (lista acompanhada): {p.outliers.length}</h2>
        <p className="sub">
          Sem decisão, o ano fica fora do histórico. Na B3 inteira há {p.outliersTotal} pendente(s);
          `acoesb3 review list --priority` mostra os que mudam um resultado.
        </p>
        {p.outliers.length === 0 ? (
          <p>Nenhum.</p>
        ) : (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Empresa</th>
                  <th>Exercício</th>
                  <th className="num">Total</th>
                  <th className="num">Mediana de 5 anos</th>
                  <th className="num">Razão</th>
                  <th>Comando</th>
                </tr>
              </thead>
              <tbody>
                {p.outliers.map((o) => (
                  <tr key={`${o.cvmCode}-${o.referenceDate}`}>
                    <td>{o.name}</td>
                    <td>{formatDate(o.referenceDate)}</td>
                    <td className="num">{formatBRL(o.total, 0)}</td>
                    <td className="num">{formatBRL(o.median, 0)}</td>
                    <td className="num">{formatNumber(o.ratio, 1)}×</td>
                    <td>
                      <code>
                        acoesb3 review outlier --cvm {o.cvmCode} --date {o.referenceDate} --decision include|exclude
                      </code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2>Eventos societários suspeitos: {p.eventsTotal}</h2>
        <p className="sub">Só os eventos confirmados ou automáticos mudam a base de ações. Mostrando os 30 mais recentes.</p>
        {p.events.length === 0 ? (
          <p>Nenhum.</p>
        ) : (
          <div className="tablewrap">
            <table>
              <thead>
                <tr>
                  <th>Papel</th>
                  <th>Data</th>
                  <th className="num">Fator</th>
                  <th>Comando</th>
                </tr>
              </thead>
              <tbody>
                {p.events.map((e) => (
                  <tr key={e.id}>
                    <td>{e.ticker}</td>
                    <td>{formatDate(e.eventDate)}</td>
                    <td className="num">{formatNumber(e.factor, 4)}</td>
                    <td>
                      <code>acoesb3 review event --id {e.id} --decision confirm|reject</code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section>
        <h2>Proventos a lançar à mão (lista acompanhada): {p.dividendsToEnter.length}</h2>
        <p className="sub">Anos de DVA zerada, indisponíveis até o lançamento (não contam como &quot;não pagou&quot;).</p>
        {p.dividendsToEnter.length === 0 ? (
          <p>Nenhum.</p>
        ) : (
          <ul>
            {p.dividendsToEnter.map((d) => (
              <li key={d.cvmCode}>
                {d.name} (CVM {d.cvmCode}): {d.years.join(", ")} —{" "}
                <code>acoesb3 review dividend --cvm {d.cvmCode} --date AAAA-12-31 --jcp 0 --dividends VALOR</code>
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}
