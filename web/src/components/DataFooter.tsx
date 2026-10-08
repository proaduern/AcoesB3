import type { DataFreshness } from "@/lib/db/core";
import { getDataFreshness } from "@/lib/db/queries";
import { formatDate, formatDateTime } from "@/lib/format";
import { Provenance } from "./Provenance";

async function tryFreshness(): Promise<DataFreshness | null> {
  try {
    return await getDataFreshness();
  } catch {
    return null;
  }
}

/** Rodapé de toda tela: data do cálculo e do último fechamento. Banco fora do ar = aviso, não erro. */
export async function DataFooter() {
  const f = await tryFreshness();
  if (!f) {
    return (
      <footer className="datafooter">Dados indisponíveis: não foi possível ler o banco agora.</footer>
    );
  }
  return (
    <footer className="datafooter">
      <div>
        Preço teto calculado para {formatDate(f.ceilingAsOf)} (em {formatDateTime(f.ceilingComputedAt)}) ·
        último fechamento: {formatDate(f.lastPriceDate)} · filtro: {formatDate(f.screenAsOf)}
      </div>
      <Provenance {...f.provenance} />
    </footer>
  );
}
