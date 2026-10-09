/** Geometria dos gráficos SVG (sem React, sem banco): escalas, marcas e eixos. */

export function scaleLinear(domain: [number, number], range: [number, number]) {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const span = d1 - d0;
  return (v: number) => (span === 0 ? (r0 + r1) / 2 : r0 + ((v - d0) / span) * (r1 - r0));
}

/** Marcas "redondas" (1, 2, 2,5, 5 × 10ⁿ) que cobrem [min, max]; devolve o novo domínio e os ticks. */
export function niceTicks(min: number, max: number, count = 4): { ticks: number[]; domain: [number, number] } {
  if (!Number.isFinite(min) || !Number.isFinite(max)) return { ticks: [0], domain: [0, 1] };
  if (min === max) {
    if (min === 0) return { ticks: [0, 1], domain: [0, 1] };
    max = min > 0 ? min * 2 : 0;
    min = min > 0 ? 0 : min * 2;
  }
  const raw = (max - min) / Math.max(1, count);
  const pow = 10 ** Math.floor(Math.log10(raw));
  const f = raw / pow;
  const step = (f <= 1 ? 1 : f <= 2 ? 2 : f <= 2.5 ? 2.5 : f <= 5 ? 5 : 10) * pow;
  const lo = Math.floor(min / step + 1e-9) * step;
  const hi = Math.ceil(max / step - 1e-9) * step;
  const ticks: number[] = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
  return { ticks, domain: [ticks[0] as number, ticks[ticks.length - 1] as number] };
}

/** Coluna a partir da linha-base: ponta de dados arredondada (r) e base reta (especificação do dataviz). */
export function barPath(x: number, w: number, yBase: number, yEnd: number, r = 4): string {
  const h = Math.abs(yEnd - yBase);
  if (h === 0) return "";
  const rr = Math.min(r, w / 2, h);
  const x2 = x + w;
  const f = (n: number) => Number(n.toFixed(2));
  if (yEnd < yBase) {
    // positivo: sobe da base
    return `M${f(x)},${f(yBase)}V${f(yEnd + rr)}Q${f(x)},${f(yEnd)} ${f(x + rr)},${f(yEnd)}H${f(x2 - rr)}Q${f(x2)},${f(yEnd)} ${f(x2)},${f(yEnd + rr)}V${f(yBase)}Z`;
  }
  // negativo: desce da base
  return `M${f(x)},${f(yBase)}V${f(yEnd - rr)}Q${f(x)},${f(yEnd)} ${f(x + rr)},${f(yEnd)}H${f(x2 - rr)}Q${f(x2)},${f(yEnd)} ${f(x2)},${f(yEnd - rr)}V${f(yBase)}Z`;
}

export function linePath(points: { x: number; y: number }[]): string {
  return points
    .map((p, i) => `${i === 0 ? "M" : "L"}${Number(p.x.toFixed(2))},${Number(p.y.toFixed(2))}`)
    .join("");
}

/** `AAAA-MM-DD` -> milissegundos UTC, sem fuso local. */
export function dayMs(date: string): number {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(date);
  if (!m) return Number.NaN;
  return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
}

/** 1º de janeiro de cada ano dentro do intervalo, para o eixo do tempo. */
export function yearTicks(fromMs: number, toMs: number, maxTicks = 6): number[] {
  const y0 = new Date(fromMs).getUTCFullYear() + 1;
  const y1 = new Date(toMs).getUTCFullYear();
  const years: number[] = [];
  for (let y = y0; y <= y1; y++) years.push(y);
  const every = Math.max(1, Math.ceil(years.length / maxTicks));
  return years.filter((_, i) => i % every === 0).map((y) => Date.UTC(y, 0, 1));
}

/** Posição e âncora de um rótulo de valor para que ele nunca passe da borda direita do gráfico. */
export function valueLabelX(cx: number, text: string, width: number, charWidth = 6.4): { x: number; anchor: "middle" | "end" } {
  const half = (text.length * charWidth) / 2;
  if (cx + half <= width - 2) return { x: cx, anchor: "middle" };
  return { x: width - 2, anchor: "end" };
}
