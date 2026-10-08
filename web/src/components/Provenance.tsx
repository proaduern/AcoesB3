import { formatDate, formatDateTime } from "@/lib/format";
import type { Provenance as ProvenanceData } from "@/lib/db/core";

/** Fonte, data-base e data de coleta de um dado (seção 10 da especificação). Ausente = "indisponível". */
export function Provenance({ source, dataBase, collectedAt }: ProvenanceData) {
  return (
    <small className="provenance">
      Fonte: {source ?? "indisponível"} · data-base: {formatDate(dataBase)} · coletado em:{" "}
      {formatDateTime(collectedAt)}
    </small>
  );
}
