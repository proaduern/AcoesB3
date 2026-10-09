/**
 * Paridade com `pipeline/acoesb3/ceiling.py`: o fixture (`web/tests/parity/cases.json`) é gerado pelo
 * Python (`acoesb3 ceilings parity-export`). Cada caso traz o que o pipeline gravou com os parâmetros
 * padrão (snapshot) e o que o Python calcula, a partir dos dados brutos, com outros parâmetros
 * (expected). O simulador, só com o snapshot, tem de chegar ao mesmo resultado.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { D, dec, paramsFromConfig, simulate, type Dec, type StoredCompany } from "./index";

interface Case {
  name: string;
  fixture: string;
  config: Record<string, unknown>;
  dcf_growth: string | null;
  classes: { ticker: string; kind: "on" | "pn" | "unit"; multiplier: number; price: string }[];
  expected: {
    methods: { method: string; status: string; value: string | null; reason: string | null }[];
    consolidated: { status: string; ceiling: string | null; methods_ok: number; k_required: number | null };
    classes: {
      ticker: string;
      ceiling: string | null;
      ratio: string | null;
      votes: number;
      k_required: number | null;
      band: string | null;
      buy: boolean;
    }[];
  };
}
interface Fixture {
  header: { version: number };
  snapshots: Record<string, { plan: string | null; methods: StoredCompany["methods"] }>;
  cases: Case[];
}

const fixture = JSON.parse(readFileSync(join(__dirname, "../../../tests/parity/cases.json"), "utf8")) as Fixture;

/** Valores iguais até 1e-9 relativo (o Python e o decimal.js têm 28 dígitos; o resto é arredondamento). */
function close(got: Dec | null, want: string | null, label: string) {
  if (want === null) {
    expect(got, label).toBeNull();
    return;
  }
  expect(got, label).not.toBeNull();
  const w = new D(want);
  const tol = D.max(new D(1), w.abs()).mul("1e-9");
  expect((got as Dec).minus(w).abs().lte(tol), `${label}: ${got?.toString()} ≠ ${want}`).toBe(true);
}

describe("paridade com ceiling.py", () => {
  it("o fixture existe, é da versão esperada e tem casos", () => {
    expect(fixture.header.version).toBe(1);
    expect(fixture.cases.length).toBeGreaterThan(100);
  });

  it.each(fixture.cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    const snap = fixture.snapshots[c.fixture];
    expect(snap, `snapshot ${c.fixture}`).toBeDefined();
    const company: StoredCompany = { plan: snap!.plan, methods: snap!.methods, classes: c.classes };
    const sim = simulate(company, paramsFromConfig(c.config, c.dcf_growth));

    expect(sim.methods.map((m) => [m.method, m.status])).toEqual(
      c.expected.methods.map((m) => [m.method, m.status]),
    );
    c.expected.methods.forEach((want, i) => {
      const got = sim.methods[i]!;
      close(got.value, want.value, `${want.method}.valor`);
      expect(got.reason, `${want.method}.motivo`).toBe(want.reason);
    });

    const cons = c.expected.consolidated;
    expect(sim.consolidated.status).toBe(cons.status);
    expect(sim.consolidated.methodsOk).toBe(cons.methods_ok);
    expect(sim.consolidated.kRequired).toBe(cons.k_required);
    close(sim.consolidated.ceiling, cons.ceiling, "teto");

    expect(sim.classes.map((k) => k.ticker)).toEqual(c.expected.classes.map((k) => k.ticker));
    c.expected.classes.forEach((want, i) => {
      const got = sim.classes[i]!;
      close(got.ceiling, want.ceiling, `${want.ticker}.teto`);
      close(got.ratio, want.ratio, `${want.ticker}.razão`);
      expect(got.votes, `${want.ticker}.votos`).toBe(want.votes);
      expect(got.kRequired, `${want.ticker}.K`).toBe(want.k_required);
      expect(got.band, `${want.ticker}.faixa`).toBe(want.band);
      expect(got.buy, `${want.ticker}.compra`).toBe(want.buy);
    });
  });

  it("os métodos refeitos de verdade (e não só repassados) cobrem os 5 métodos", () => {
    const recomputed = new Set<string>();
    for (const c of fixture.cases) {
      const snap = fixture.snapshots[c.fixture]!;
      const sim = simulate({ plan: snap.plan, methods: snap.methods, classes: c.classes }, paramsFromConfig(c.config, c.dcf_growth));
      for (const m of sim.methods) if (m.recomputed && m.status === "ok") recomputed.add(m.method);
    }
    expect([...recomputed].sort()).toEqual(["bazin", "dcf", "gordon", "graham", "multiples"]);
  });

  it("com os parâmetros padrão o simulador reproduz o valor gravado de cada método", () => {
    for (const c of fixture.cases.filter((x) => x.name.endsWith("__padrao"))) {
      const snap = fixture.snapshots[c.fixture]!;
      const sim = simulate({ plan: snap.plan, methods: snap.methods, classes: [] }, paramsFromConfig(c.config, null));
      snap.methods.forEach((stored, i) => {
        const got = sim.methods[i]!;
        expect(got.status, c.name).toBe(stored.status);
        close(got.value, stored.status === "ok" ? stored.value : null, `${c.name}.${stored.method}`);
      });
    }
  });

  it("dec lê o texto do Python e do Postgres", () => {
    expect(dec("1E+1")?.toString()).toBe("10");
    expect(dec("0.0600000000000000")?.toString()).toBe("0.06");
    expect(dec("")).toBeNull();
    expect(dec("x")).toBeNull();
    expect(dec(null)).toBeNull();
  });
});
