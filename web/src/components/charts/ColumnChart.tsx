import { barPath, niceTicks, scaleLinear, valueLabelX } from "@/lib/chart";

export interface ColumnPoint {
  label: string; // rótulo do eixo (ano)
  value: number | null; // nulo = sem barra (dado ausente, nunca zero)
  text: string; // valor formatado, para a dica e o rótulo da ponta
  muted?: boolean; // fora das médias (cinza)
  note?: string;
}

const W = 320;
const H = 168;
const M = { l: 46, r: 10, t: 12, b: 22 };

/**
 * Colunas de uma série (um ano por coluna). Marcas finas (≤ 24px), ponta arredondada e base reta,
 * linhas de grade em fio; só o último valor é rotulado. A dica nativa (`<title>`) traz o valor de cada ano.
 */
export function ColumnChart({
  title,
  points,
  yFormat,
}: {
  title: string;
  points: ColumnPoint[];
  yFormat: (n: number) => string;
}) {
  const values = points.map((p) => p.value).filter((v): v is number => v !== null);
  if (values.length === 0) {
    return (
      <figure className="viz">
        <figcaption>{title}</figcaption>
        <p className="sub">indisponível</p>
      </figure>
    );
  }
  const { ticks, domain } = niceTicks(Math.min(0, ...values), Math.max(0, ...values), 3);
  const y = scaleLinear(domain, [H - M.b, M.t]);
  const innerW = W - M.l - M.r;
  const slot = innerW / points.length;
  const bw = Math.min(24, slot * 0.6);
  const lastIdx = points.reduce((acc, p, i) => (p.value !== null ? i : acc), -1);

  return (
    <figure className="viz">
      <figcaption>{title}</figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className={t === 0 ? "viz-axis" : "viz-grid"} />
            <text x={M.l - 6} y={y(t)} className="viz-tick" textAnchor="end" dominantBaseline="middle">
              {yFormat(t)}
            </text>
          </g>
        ))}
        {points.map((p, i) => {
          const cx = M.l + slot * i + slot / 2;
          return (
            <g key={p.label}>
              <title>{`${p.label}: ${p.text}${p.note ? ` (${p.note})` : ""}`}</title>
              <rect x={M.l + slot * i} y={M.t} width={slot} height={H - M.t - M.b} fill="transparent" />
              {p.value !== null && (
                <path d={barPath(cx - bw / 2, bw, y(0), y(p.value))} className={p.muted ? "viz-bar muted" : "viz-bar"} />
              )}
              <text x={cx} y={H - 6} className="viz-tick" textAnchor="middle">
                {p.label}
              </text>
            </g>
          );
        })}
        {lastIdx >= 0 && points[lastIdx]?.value != null && (() => {
          const last = points[lastIdx]!;
          const v = last.value as number;
          const pos = valueLabelX(M.l + slot * lastIdx + slot / 2, last.text, W);
          return (
            <text x={pos.x} y={y(v) + (v >= 0 ? -5 : 12)} className="viz-value" textAnchor={pos.anchor}>
              {last.text}
            </text>
          );
        })()}
      </svg>
    </figure>
  );
}
