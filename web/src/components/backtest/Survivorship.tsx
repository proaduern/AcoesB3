import { survivorshipText, type RunSummary } from "@/lib/backtest";

/**
 * Aviso fixo do viés de sobrevivência: sem botão de fechar e sempre presente (texto padrão se a execução
 * não trouxer o dela). Fica no topo e acompanha a rolagem em telas largas.
 */
export function SurvivorshipBanner({ run }: { run: Pick<RunSummary, "survivorshipWarning"> | null }) {
  return (
    <div className="survivorship" role="note" aria-label="Aviso: viés de sobrevivência">
      <strong>Atenção: o resultado vale só para o universo de hoje</strong>
      {survivorshipText(run)}
    </div>
  );
}

/** Selo ao lado de cada retorno da estratégia: o aviso acompanha o número. */
export function UniverseSeal() {
  return (
    <span
      className="seal"
      title="Universo de hoje: a lista acompanhada atual, sem empresas canceladas. Tende a favorecer o resultado."
    >
      universo de hoje
    </span>
  );
}
