import { dayMs, linePath, niceTicks, scaleLinear, yearTicks } from "@/lib/chart";
import { formatBRL, formatDate, formatNumber } from "@/lib/format";
import type { PriceEvent, PricePoint } from "@/lib/company";

const W = 480;
const H = 250;
const M = { l: 46, r: 12, t: 12, b: 24 };

/**
 * Fechamento do COTAHIST (sem ajuste por desdobramentos) e, se houver, o teto de hoje a partir do último
 * evento societário. Duas séries: legenda sempre presente (identidade nunca só por cor).
 */
export function PriceChart({
  ticker,
  points,
  events,
  ceiling,
  ceilingFrom,
}: {
  ticker: string;
  points: PricePoint[];
  events: PriceEvent[];
  ceiling: string | null;
  ceilingFrom: string | null;
}) {
  const data = points
    .map((p) => ({ date: p.date, t: dayMs(p.date), v: Number(p.close) }))
    .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.v));
  if (data.length < 2) return <p>Sem cotações suficientes para o gráfico.</p>;

  const t0 = data[0]!.t;
  const t1 = data[data.length - 1]!.t;
  const ceilNum = ceiling !== null ? Number(ceiling) : null;
  const ceilStart = ceilingFrom ? Math.max(t0, dayMs(ceilingFrom)) : t0;
  const drawCeiling = ceilNum !== null && Number.isFinite(ceilNum) && ceilStart < t1;

  const ys = data.map((d) => d.v).concat(drawCeiling ? [ceilNum as number] : []);
  const { ticks, domain } = niceTicks(Math.min(...ys), Math.max(...ys), 4);
  const x = scaleLinear([t0, t1], [M.l, W - M.r]);
  const y = scaleLinear(domain, [H - M.b, M.t]);
  const last = data[data.length - 1]!;
  const step = (W - M.l - M.r) / data.length;

  return (
    <figure className="viz wide">
      <ul className="viz-legend" aria-label="Legenda">
        <li>
          <span className="key s1" />
          Fechamento de {ticker} ({formatBRL(last.v)} em {formatDate(last.date)})
        </li>
        {drawCeiling && (
          <li>
            <span className="key s2" />
            Teto de hoje ({formatBRL(ceiling)})
          </li>
        )}
      </ul>
      <div className="vizscroll">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Preço de ${ticker}`}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={M.l} x2={W - M.r} y1={y(t)} y2={y(t)} className="viz-grid" />
            <text x={M.l - 6} y={y(t)} className="viz-tick" textAnchor="end" dominantBaseline="middle">
              {formatNumber(t, 2)}
            </text>
          </g>
        ))}
        {yearTicks(t0, t1).map((t) => (
          <text key={t} x={x(t)} y={H - 6} className="viz-tick" textAnchor="middle">
            {new Date(t).getUTCFullYear()}
          </text>
        ))}
        {events.map((e) => {
          const ex = dayMs(e.date);
          if (!(ex >= t0 && ex <= t1)) return null;
          return (
            <g key={`${e.date}-${e.source}-${e.factor}`}>
              <title>{`Evento societário em ${formatDate(e.date)}: fator ${formatNumber(e.factor, 4)}`}</title>
              <line x1={x(ex)} x2={x(ex)} y1={M.t} y2={H - M.b} className="viz-event" />
            </g>
          );
        })}
        <path d={linePath(data.map((d) => ({ x: x(d.t), y: y(d.v) })))} className="viz-line s1" />
        {drawCeiling && (
          <path d={linePath([{ x: x(ceilStart), y: y(ceilNum as number) }, { x: x(t1), y: y(ceilNum as number) }])} className="viz-line s2" />
        )}
        <circle cx={x(last.t)} cy={y(last.v)} r={4} className="viz-dot s1" />
        {data.map((d) => (
          <g key={d.date}>
            <title>{`${formatDate(d.date)}: ${formatBRL(d.v)}`}</title>
            <rect x={x(d.t) - step / 2} y={M.t} width={step} height={H - M.t - M.b} fill="transparent" />
          </g>
        ))}
      </svg>
      </div>
    </figure>
  );
}
