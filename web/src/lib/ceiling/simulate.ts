import { consolidate, parsePrice, valueClass } from "./consolidate";
import { D, type Dec } from "./decimal";
import * as methods from "./methods";
import type { CeilingParams } from "./params";
import { METHODS, type SimMethod, type Simulation, type StoredCompany, type StoredMethod } from "./types";

function run(m: StoredMethod, p: CeilingParams): SimMethod {
  switch (m.method) {
    case "bazin":
      return methods.bazin(m, p);
    case "gordon":
      return methods.gordon(m, p);
    case "graham":
      return methods.graham(m, p);
    case "multiples":
      return methods.multiples(m);
    case "dcf":
      return methods.dcf(m, p);
  }
}

/**
 * Refaz o preço teto de uma empresa com os parâmetros dados. `prices` troca o preço de papéis pelo
 * ticker (o resto usa o preço gravado). Sem alterar nada, devolve o que o pipeline gravou.
 */
export function simulate(
  company: StoredCompany,
  p: CeilingParams,
  prices: Record<string, string | number> = {},
): Simulation {
  const stored = [...company.methods]
    .filter((m) => p.dcfEnabled || m.method !== "dcf") // método desligado não entra, como no pipeline
    .sort((a, b) => METHODS.indexOf(a.method) - METHODS.indexOf(b.method));
  const sims = stored.map((m) => run(m, p));
  const cons = consolidate(sims, p);
  const classes = company.classes.map((c) => {
    const price: Dec = parsePrice(prices[c.ticker]) ?? parsePrice(c.price) ?? new D(0);
    return valueClass(c, price, sims, cons, p);
  });
  return { methods: sims, consolidated: cons, classes };
}
