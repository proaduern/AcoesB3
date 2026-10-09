import {
  CRITERION_LABEL,
  CRITERION_ORDER,
  formatCriterionValue,
  formatThreshold,
  reasonText,
  type CriterionRow,
} from "@/lib/screen";

const RESULT: Record<CriterionRow["status"], string> = {
  pass: "Passou",
  fail: "Reprovou",
  unavailable: "Indisponível",
};

/** Critérios do filtro com valor, limite e resultado; usada no filtro da B3 e na ficha. */
export function CriteriaTable({ criteria, className = "inner" }: { criteria: CriterionRow[]; className?: string }) {
  if (criteria.length === 0) return <p className="sub">Sem critérios avaliados neste status.</p>;
  const rank = (n: string) => {
    const i = (CRITERION_ORDER as readonly string[]).indexOf(n);
    return i === -1 ? 99 : i;
  };
  const sorted = [...criteria].sort((a, b) => rank(a.criterion) - rank(b.criterion));
  return (
    <table className={className}>
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
              {RESULT[c.status]}
              {c.status === "unavailable" && reasonText(c.reason) && <div className="sub">{reasonText(c.reason)}</div>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
