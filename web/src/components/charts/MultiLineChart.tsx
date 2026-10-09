import { dayMs, linePath, niceTicks, scaleLinear, yearTicks } from "@/lib/chart";
import { formatDate, formatNumber } from "@/lib/format";

export interface LineSeries {
  key: string;
  label: string;
  tone: "s1" | "s2" | "s3" | "s4";
  points: { date: string; value: number }[];
}

const W = 640;
const H = 300;
const M = { l: 44, r: 12, t: 14, b: 24 };

/**
 * Linhas de níveis reescalados (início = 100) no mesmo eixo, com legenda sempre presente (a identidade
 * nunca depende só da cor) e o valor final de cada série. Um marcador vertical opcional (início da validação).
 * A dica nativa de cada mês lista todas as séries.
 */
export function MultiLineChart({
  title,
  series,
  marker,
}: {
  title: string;
  series: LineSeries[];
  marker?: { date: string; label: string } | null;
}) {
  const drawn = series
    .map((s) => ({ ...s, pts: s.points.map((p) => ({ t: dayMs(p.date), v: p.value, date: p.date })).filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v)) }))
    .filter((s) => s.pts.length >= 2);
  if (drawn.length === 0) return <p>Sem séries suficientes para o gráfico.</p>;

  const all = drawn.flatMap((s) => s.pts);
  const t0 = Math.min(...all.map((p) => p.t));
  const t1 = Math.max(...all.map((p) => p.t));
  const { ticks, domain } = niceTicks(Math.min(...all.map((p) => p.v)), Math.max(...all.map((p) => p.v)), 4);
  const x = scaleLinear([t0, t1], [M.l, W - M.r]);
  const y = scaleLinear(domain, [H - M.b, M.t]);

  // Dica por mês: junta o valor de cada série na mesma data.
  const dates = [...new Set(all.map((p) => p.date))].sort();
  const byDate = new Map(drawn.map((s) => [s.key, new Map(s.pts.map((p) => [p.date, p.v]))] as const));
  const step = (W - M.l - M.r) / Math.max(1, dates.length);
  const markerMs = marker ? dayMs(marker.date) : Number.NaN;

  return (
    <figure className="viz wide bt">
      <ul className="viz-legend" aria-label="Legenda">
        {drawn.map((s) => (
          <li key={s.key}>
            <span className={`key ${s.tone}`} />
            {s.label} ({formatNumber(s.pts[s.pts.length - 1]!.v, 0)})
          </li>
        ))}
      </ul>
      <div className="vizscroll">
        <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={title}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="viz-grid" />
              <text x={M.l - 6} y={y(t)} className="viz-tick" textAnchor="end" dominantBaseline="middle">
                {formatNumber(t, 0)}
              </text>
            </g>
          ))}
          {yearTicks(t0, t1).map((t) => (
            <text key={t} x={x(t)} y={H - 6} className="viz-tick" textAnchor="middle">
              {new Date(t).getUTCFullYear()}
            </text>
          ))}
          {marker && markerMs >= t0 && markerMs <= t1 && (
            <g>
              <title>{`${marker.label}: ${formatDate(marker.date)}`}</title>
              <line x1={x(markerMs)} x2={x(markerMs)} y1={M.t} y2={H - M.b} className="viz-event" />
              <text x={x(markerMs) - 4} y={M.t + 10} className="viz-tick" textAnchor="end">
                {marker.label}
              </text>
            </g>
          )}
          {drawn.map((s) => (
            <path key={s.key} d={linePath(s.pts.map((p) => ({ x: x(p.t), y: y(p.v) })))} className={`viz-line ${s.tone}`} />
          ))}
          {dates.map((d) => (
            <g key={d}>
              <title>
                {`${formatDate(d)} — ` +
                  drawn.map((s) => `${s.label.split(" (")[0]}: ${byDate.get(s.key)?.has(d) ? formatNumber(byDate.get(s.key)!.get(d), 1) : "indisponível"}`).join(" · ")}
              </title>
              <rect x={x(dayMs(d)) - step / 2} y={M.t} width={step} height={H - M.t - M.b} fill="transparent" />
            </g>
          ))}
        </svg>
      </div>
    </figure>
  );
}
