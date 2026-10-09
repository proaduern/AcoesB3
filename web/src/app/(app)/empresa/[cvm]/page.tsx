import Link from "next/link";
import { notFound } from "next/navigation";
import { CeilingSection } from "@/components/company/CeilingSection";
import { FilterSection } from "@/components/company/FilterSection";
import { OriginSection } from "@/components/company/OriginSection";
import { PriceSection } from "@/components/company/PriceSection";
import { Simulator } from "@/components/company/Simulator";
import {
  TABS,
  TAB_LABEL,
  companyHref,
  parseCvm,
  parsePeriod,
  parseTab,
  parseTicker,
  type CeilingTab,
  type CompanyHeader,
  type FilterTab,
  type OriginTab,
  type Period,
  type PriceTab,
  type Tab,
} from "@/lib/company";
import {
  getCeilingTab,
  getCompanyHeader,
  getFilterTab,
  getOriginTab,
  getPriceTab,
  getSimulatorData,
} from "@/lib/db/queries";
import type { SimulatorData } from "@/lib/ceiling/view";
import { ROLE_LABEL } from "@/lib/watchlist";

export const dynamic = "force-dynamic";

async function header(cvm: number): Promise<CompanyHeader | null | "error"> {
  try {
    return await getCompanyHeader(cvm);
  } catch {
    return "error";
  }
}

type TabData =
  | { tab: "teto"; d: CeilingTab }
  | { tab: "simulador"; d: SimulatorData | null }
  | { tab: "filtro"; d: FilterTab }
  | { tab: "preco"; d: PriceTab }
  | { tab: "origem"; d: OriginTab };

/** Lê só a aba pedida. Falha do banco = nulo (a página mostra o aviso). */
async function loadTab(
  cvm: number,
  tab: Tab,
  h: CompanyHeader,
  wanted: string | null,
  period: Period,
): Promise<TabData | null> {
  try {
    if (tab === "teto") return { tab, d: await getCeilingTab(cvm) };
    if (tab === "simulador") return { tab, d: await getSimulatorData(cvm) };
    if (tab === "filtro") return { tab, d: await getFilterTab(cvm) };
    if (tab === "preco") return { tab, d: await getPriceTab(cvm, h.tickers, wanted, period) };
    return { tab, d: await getOriginTab(cvm, h.tickers) };
  } catch {
    return null;
  }
}

export default async function CompanyPage({
  params,
  searchParams,
}: {
  params: Promise<{ cvm: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const cvm = parseCvm((await params).cvm);
  if (cvm === null) notFound();
  const q = await searchParams;
  const tab = parseTab(q);

  const h = await header(cvm);
  if (h === null) notFound(); // fora da lista acompanhada: a ficha só existe para a lista
  if (h === "error") {
    return (
      <main>
        <h1>Empresa</h1>
        <p>Dados indisponíveis: não foi possível ler o banco agora.</p>
        <Link href="/">← Lista</Link>
      </main>
    );
  }

  const period = parsePeriod(q);
  const data = await loadTab(cvm, tab, h, parseTicker(q), period);
  let body: React.ReactNode;
  if (!data) body = <p>Dados indisponíveis: não foi possível ler o banco agora.</p>;
  else if (data.tab === "teto") body = <CeilingSection tab={data.d} />;
  else if (data.tab === "simulador")
    body = data.d ? (
      <Simulator data={data.d} />
    ) : (
      <p>Sem preço teto calculado para esta empresa: rode `acoesb3 compute --step ceilings`.</p>
    );
  else if (data.tab === "filtro") body = <FilterSection tab={data.d} />;
  else if (data.tab === "preco") body = <PriceSection cvm={cvm} period={period} tab={data.d} />;
  else body = <OriginSection tab={data.d} />;

  return (
    <main>
      <p className="sub">
        <Link href="/">← Lista acompanhada</Link>
      </p>
      <h1>{h.name}</h1>
      <p className="meta">
        <span>{ROLE_LABEL[h.role]}</span>
        <span>Segmento: {h.segment}</span>
        {h.sector && <span>Setor CVM: {h.sector}</span>}
        <span>Papéis: {h.tickers.length ? h.tickers.join(", ") : "sem preço teto"}</span>
        <span>CVM {h.cvmCode}</span>
      </p>
      <nav className="tabs" aria-label="Abas da ficha">
        {TABS.map((t) => (
          <Link key={t} href={companyHref(cvm, { aba: t })} aria-current={t === tab ? "page" : undefined}>
            {TAB_LABEL[t]}
          </Link>
        ))}
      </nav>
      {body}
    </main>
  );
}
