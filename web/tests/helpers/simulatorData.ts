/** Monta o que `loadSimulatorData` devolveria, a partir do fixture de paridade (insumos como o pipeline grava). */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { StoredClass, StoredMethod } from "@/lib/ceiling/types";
import type { SimulatorData } from "@/lib/ceiling/view";
import type { ClassRow } from "@/lib/watchlist";

interface Case {
  name: string;
  fixture: string;
  config: Record<string, unknown>;
  classes: { ticker: string; kind: "on" | "unit"; multiplier: number; price: string }[];
  expected: {
    consolidated: { status: "ok" | "insufficient"; ceiling: string | null; methods_ok: number; k_required: number | null };
    classes: { ticker: string; ceiling: string | null; ratio: string | null; votes: number; k_required: number | null; band: ClassRow["band"]; buy: boolean }[];
  };
}
const fx = JSON.parse(readFileSync(join(process.cwd(), "tests/parity/cases.json"), "utf8")) as {
  snapshots: Record<string, { plan: string | null; methods: StoredMethod[] }>;
  cases: Case[];
};

/** Gravado = o que o Python calculou com os parâmetros padrão; `round` imita as 8 casas do banco. */
export function dataFor(fixture: string, round = false): SimulatorData {
  const c = fx.cases.find((x) => x.name === `${fixture}__padrao`)!;
  const snap = fx.snapshots[fixture]!;
  const r8 = (v: string | null) => (v === null || !round ? v : Number(v).toFixed(8));
  const classes: StoredClass[] = c.classes.map((k) => ({ ticker: k.ticker, kind: k.kind, multiplier: k.multiplier, price: k.price, reason: null }));
  return {
    asOf: "2026-10-05",
    dataBase: "2024-12-31",
    collectedAt: null,
    plan: snap.plan,
    config: c.config,
    company: { plan: snap.plan, methods: snap.methods, classes },
    stored: {
      status: c.expected.consolidated.status,
      ceiling: r8(c.expected.consolidated.ceiling),
      methodsOk: c.expected.consolidated.methods_ok,
      kRequired: c.expected.consolidated.k_required,
      classes: c.expected.classes.map((k, i) => ({
        ticker: k.ticker,
        kind: c.classes[i]!.kind,
        price: c.classes[i]!.price,
        priceDate: "2026-10-02",
        ceiling: r8(k.ceiling),
        ratio: r8(k.ratio),
        band: k.band,
        votes: k.votes,
        kRequired: k.k_required,
        buy: k.buy,
        reason: null,
      })),
    },
  };
}

