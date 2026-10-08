import Link from "next/link";
import { Provenance } from "@/components/Provenance";
import { getScreen } from "@/lib/db/queries";
import type { ScreenPage } from "@/lib/db/screen";
import { formatDate, UNAVAILABLE } from "@/lib/format";
import { ROLE_LABEL } from "@/lib/watchlist";
import {
  CRITERION_LABEL,
  CRITERION_ORDER,
  STATUS_LABEL,
  STATUS_ORDER,
  formatCriterionValue,
  formatThreshold,
  parseScreenFilters,
  problemCriteria,
  reasonText,
  screenHref,
  type CriterionRow,
  type ScreenFilters,
  type ScreenRow,
} from "@/lib/screen";

export const dynamic = "force-dynamic";

async function load(f: ScreenFilters): Promise<ScreenPage | null> {
  try {
    return await getScreen(f);
  } catch {
    return null;
  }
}

const CRITERION_STATUS: Record<CriterionRow["status"], string> = {
  pass: "Passou",
  fail: "Reprovou",
  unavailable: "Indisponível",
};

function Criteria({ row }: { row: ScreenRow }) {
  if (row.criteria.length === 0) {
    return <p className="sub">Sem critérios avaliados neste status.</p>;
  }
  const rank = (n: string) => {
    const i = (CRITERION_ORDER as readonly string[]).indexOf(n);
    return i === -1 ? 99 : i;
  };
  const sorted = [...row.criteria].sort((a, b) => rank(a.criterion) - rank(b.criterion));
  return (
    <table className="inner">
      <thead>
        <tr>
          <th>Critério</th>
          <th className="num">Valor</th>
          <th>Limite</th>
          <th>Resultado</th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((c) => (
          <tr key={c.criterion}>
            <td>{CRITERION_LABEL[c.criterion] ?? c.criterion}</td>
            <td className="num">{formatCriterionValue(c.criterion, c.value)}</td>
            <td>{formatThreshold(c.threshold)}</td>
            <td>
              {CRITERION_STATUS[c.status]}
              {c.status === "unavailable" && reasonText(c.reason) && (
                <div className="sub">{reasonText(c.reason)}</div>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Row({ row }: { row: ScreenRow }) {
  const { failed, unavailable } = problemCriteria(row.criteria);
  return (
    <tr>
      <td>
        <strong>{row.name}</strong>
        <div className="sub">{row.tickers.length ? row.tickers.join(", ") : "sem ticker no FCA"}</div>
      </td>
      <td>{row.sector ?? UNAVAILABLE}</td>
      <td>
        {STATUS_LABEL[row.status]}
        {row.role && <div className="sub">Na lista: {ROLE_LABEL[row.role]}</div>}
      </td>
      <td>
        {failed.length > 0 && <div>Reprovou: {failed.join("; ")}</div>}
        {unavailable.length > 0 && <div className="sub">Indisponível: {unavailable.join("; ")}</div>}
        {failed.length === 0 && unavailable.length === 0 && row.criteria.length > 0 && "Todos passaram"}
        {row.criteria.length === 0 && "—"}
        {row.criteria.length > 0 && (
          <details>
            <summary>Critérios</summary>
            <Criteria row={row} />
          </details>
        )}
      </td>
      <td>{formatDate(row.dataBase)}</td>
    </tr>
  );
}

export default async function FiltroPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const f = parseScreenFilters(await searchParams);
  const data = await load(f);

  if (!data) {
    return (
      <main>
        <h1>Filtro</h1>
        <p>Dados indisponíveis: não foi possível ler o banco agora.</p>
      </main>
    );
  }
  if (!data.asOf) {
    return (
      <main>
        <h1>Filtro</h1>
        <p>Nenhum retrato do filtro calculado: rode `acoesb3 compute --step screens`.</p>
      </main>
    );
  }

  const collected = data.rows.map((r) => r.collectedAt).filter((v): v is string => !!v).sort().at(-1);
  const base = data.rows.map((r) => r.dataBase).filter((v): v is string => !!v).sort().at(-1);

  return (
    <main>
      <h1>Filtro da B3</h1>
      <p className="sub">
        Retrato de {formatDate(data.asOf)}. O filtro é calculado para a B3 inteira; o trabalho (preço teto, revisão)
        vale só para a lista acompanhada. <Link href="/filtro/pendencias">Pendências de revisão</Link>
      </p>

      <form className="search" action="/filtro" method="get">
        <input type="search" name="q" defaultValue={f.q ?? ""} placeholder="Nome ou ticker" aria-label="Buscar por nome ou ticker" />
        {f.status && <input type="hidden" name="status" value={f.status} />}
        {f.onlyWatch && <input type="hidden" name="lista" value="1" />}
        <button type="submit">Buscar</button>
        {f.q && <Link href={screenHref(f, { q: null })}>limpar</Link>}
      </form>

      <nav className="filters" aria-label="Filtros">
        <span>Status:</span>
        <Link href={screenHref(f, { status: null })} className={f.status === null ? "chip active" : "chip"}>
          Todos
        </Link>
        {STATUS_ORDER.map((s) => (
          <Link key={s} href={screenHref(f, { status: s })} className={f.status === s ? "chip active" : "chip"}>
            {STATUS_LABEL[s]} ({data.counts[s] ?? 0})
          </Link>
        ))}
        <Link href={screenHref(f, { onlyWatch: !f.onlyWatch })} className={f.onlyWatch ? "chip active" : "chip"}>
          Só a lista acompanhada
        </Link>
      </nav>

      <p className="sub">
        {data.total} empresa(s) · página {data.page} de {data.pages}
      </p>
      {data.rows.length === 0 ? (
        <p>Nenhuma empresa com estes filtros.</p>
      ) : (
        <div className="tablewrap">
          <table>
            <thead>
              <tr>
                <th>Empresa</th>
                <th>Setor (CVM)</th>
                <th>Status</th>
                <th>Critérios</th>
                <th>Exercício</th>
              </tr>
            </thead>
            <tbody>
              {data.rows.map((r) => (
                <Row key={r.cvmCode} row={r} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <nav className="pager" aria-label="Páginas">
        {data.page > 1 && <Link href={screenHref(f, { page: data.page - 1 })}>← Anterior</Link>}
        {data.page < data.pages && <Link href={screenHref(f, { page: data.page + 1 })}>Próxima →</Link>}
      </nav>

      <Provenance source="CVM Dados Abertos (DFP/FRE) e B3 (COTAHIST); cálculo do pipeline" dataBase={base ?? null} collectedAt={collected ?? null} />
    </main>
  );
}
