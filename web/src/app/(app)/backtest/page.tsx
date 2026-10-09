import { SurvivorshipBanner } from "@/components/backtest/Survivorship";
import { BacktestView } from "@/components/backtest/BacktestView";
import { pickRun } from "@/lib/backtest";
import { getBacktestOverview, getRunDetail } from "@/lib/db/queries";

export const dynamic = "force-dynamic";

async function load(params: Record<string, string | string[] | undefined>) {
  try {
    const overview = await getBacktestOverview();
    const run = pickRun(params, overview);
    const detail = run ? await getRunDetail(run.id, params.ordens === "todas") : null;
    return { overview, run, detail };
  } catch {
    return null;
  }
}

export default async function BacktestPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const data = await load(params);

  if (!data) {
    return (
      <main>
        <h1>Backtest</h1>
        <SurvivorshipBanner run={null} />
        <p>Dados indisponíveis: não foi possível ler o banco agora.</p>
      </main>
    );
  }
  const { overview, run, detail } = data;
  if (!run || !detail) {
    return (
      <main>
        <h1>Backtest</h1>
        <SurvivorshipBanner run={null} />
        <p>Nenhum backtest calculado: rode `acoesb3 backtest benchmarks` e `acoesb3 backtest run` (workflow backtest).</p>
      </main>
    );
  }
  return <BacktestView overview={overview} run={run} detail={detail} allTrades={params.ordens === "todas"} />;
}
