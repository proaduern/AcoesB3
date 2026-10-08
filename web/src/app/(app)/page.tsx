import Link from "next/link";
import { Provenance } from "@/components/Provenance";
import type { WatchlistData } from "@/lib/watchlist";
import { getWatchlist } from "@/lib/db/queries";
import { formatBRL, formatDate, formatPercent, UNAVAILABLE } from "@/lib/format";
import {
  BAND_LABEL,
  ROLE_LABEL,
  SCREEN_LABEL,
  filterCompanies,
  filterHref,
  parseFilters,
  segmentsOf,
  situation,
  type Filters,
  type Role,
  type WatchCompany,
} from "@/lib/watchlist";

export const dynamic = "force-dynamic";

async function load(): Promise<WatchlistData | null> {
  try {
    return await getWatchlist();
  } catch {
    return null;
  }
}

function Chip({ href, active, children }: { href: string; active: boolean; children: string }) {
  return (
    <Link href={href} className={active ? "chip active" : "chip"} aria-current={active ? "true" : undefined}>
      {children}
    </Link>
  );
}

function Table({ role, companies }: { role: Role; companies: WatchCompany[] }) {
  if (companies.length === 0) return null;
  return (
    <section>
      <h2>{ROLE_LABEL[role]}</h2>
      <div className="tablewrap">
        <table>
          <thead>
            <tr>
              <th>Papel</th>
              <th>Segmento</th>
              <th className="num">Preço</th>
              <th className="num">Teto</th>
              <th className="num">Preço ÷ teto</th>
              <th>Faixa</th>
              <th className="num">Votos</th>
              <th>Situação</th>
              <th>Filtro</th>
              <th>Exercício</th>
            </tr>
          </thead>
          <tbody>
            {companies.map((c) => {
              const rows = c.classes.length > 0 ? c.classes : [null];
              return rows.map((k, i) => (
                <tr key={`${c.cvmCode}-${k?.ticker ?? "x"}`} className={k?.buy ? "buy" : undefined}>
                  <td>
                    <strong>{k?.ticker ?? UNAVAILABLE}</strong>
                    <div className="sub">{i === 0 ? c.name : ""}</div>
                  </td>
                  <td>{c.segment}</td>
                  <td className="num">
                    {k ? formatBRL(k.price) : UNAVAILABLE}
                    {k && <div className="sub">{formatDate(k.priceDate)}</div>}
                  </td>
                  <td className="num">{k ? formatBRL(k.ceiling) : UNAVAILABLE}</td>
                  <td className="num">{k ? formatPercent(k.ratio, 0) : UNAVAILABLE}</td>
                  <td>{k?.band ? BAND_LABEL[k.band] : UNAVAILABLE}</td>
                  <td className="num">
                    {k && k.votes !== null && k.kRequired !== null
                      ? `${k.votes}/${k.kRequired}`
                      : UNAVAILABLE}
                  </td>
                  <td>
                    {k ? situation(c, k) : "Sem preço teto calculado"}
                    {k?.reason && <div className="sub">{k.reason}</div>}
                    {c.ceilingStatus === "insufficient" && (
                      <div className="sub">{c.methodsOk ?? 0} método(s) aplicável(is)</div>
                    )}
                  </td>
                  <td>{c.screenStatus ? (SCREEN_LABEL[c.screenStatus] ?? c.screenStatus) : UNAVAILABLE}</td>
                  <td>{formatDate(c.dataBase)}</td>
                </tr>
              ));
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const filters: Filters = parseFilters(await searchParams);
  const data = await load();

  if (!data) {
    return (
      <main>
        <h1>Lista acompanhada</h1>
        <p>Dados indisponíveis: não foi possível ler o banco agora.</p>
      </main>
    );
  }
  if (data.asOf === null || data.companies.length === 0) {
    return (
      <main>
        <h1>Lista acompanhada</h1>
        <p>
          {data.companies.length === 0
            ? "A lista acompanhada está vazia (acoesb3 watch add)."
            : "Nenhum preço teto calculado: rode `acoesb3 compute --step ceilings` (workflow compute)."}
        </p>
      </main>
    );
  }

  const shown = filterCompanies(data.companies, filters);
  const latestCollected = data.companies.map((c) => c.collectedAt).filter((v): v is string => !!v).sort().at(-1);
  const latestBase = data.companies.map((c) => c.dataBase).filter((v): v is string => !!v).sort().at(-1);

  return (
    <main>
      <h1>Lista acompanhada</h1>
      <p className="sub">
        Preço teto de {formatDate(data.asOf)}. Preço atual = último fechamento do COTAHIST (não é cotação intradiária).
      </p>

      <nav className="filters" aria-label="Filtros">
        <span>Papel:</span>
        <Chip href={filterHref(filters, { role: null })} active={filters.role === null}>Todos</Chip>
        <Chip href={filterHref(filters, { role: "carteira" })} active={filters.role === "carteira"}>Carteira</Chip>
        <Chip href={filterHref(filters, { role: "radar" })} active={filters.role === "radar"}>Radar</Chip>
        <span>Segmento:</span>
        <Chip href={filterHref(filters, { segment: null })} active={filters.segment === null}>Todos</Chip>
        {segmentsOf(data.companies).map((s) => (
          <Chip key={s} href={filterHref(filters, { segment: s })} active={filters.segment === s}>
            {s}
          </Chip>
        ))}
        <Chip href={filterHref(filters, { onlyBuy: !filters.onlyBuy })} active={filters.onlyBuy}>
          Só compra
        </Chip>
      </nav>

      {shown.length === 0 && <p>Nenhuma empresa com estes filtros.</p>}
      <Table role="carteira" companies={shown.filter((c) => c.role === "carteira")} />
      <Table role="radar" companies={shown.filter((c) => c.role === "radar")} />

      <Provenance
        source="CVM Dados Abertos (DFP/FRE) e B3 (COTAHIST); cálculo do pipeline"
        dataBase={latestBase ?? null}
        collectedAt={latestCollected ?? null}
      />
    </main>
  );
}
