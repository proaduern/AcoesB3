"use client";

import { useMemo, useState } from "react";
import {
  DCF_GROWTH_FIELD,
  FIELDS,
  GROUP_LABEL,
  K_PREFIX,
  type FieldDef,
} from "@/lib/ceiling/form";
import { METHODS } from "@/lib/ceiling/types";
import { computeView, initialState, type SimState, type SimulatorData } from "@/lib/ceiling/view";
import { METHOD_LABEL, METHOD_STATUS_LABEL } from "@/lib/company";
import { UNAVAILABLE, formatBRL, formatDate, formatPercent } from "@/lib/format";
import { BAND_LABEL } from "@/lib/watchlist";

const GROUPS: FieldDef["group"][] = ["bazin", "graham", "gordon", "dcf", "faixas"];

/**
 * Simulador do preço teto de uma empresa: o que o pipeline gravou ao lado do que sai com outros
 * parâmetros e preços. Nada é gravado; o cálculo é o mesmo de `ceiling.py` (teste de paridade).
 */
export function Simulator({ data, initial }: { data: SimulatorData; initial?: Partial<SimState> }) {
  const base = useMemo(() => initialState(data), [data]);
  const [state, setState] = useState<SimState>({
    fields: { ...base.fields, ...initial?.fields },
    prices: { ...base.prices, ...initial?.prices },
  });
  const view = useMemo(() => computeView(data, state), [data, state]);
  const touched = new Set(view.changedFields);
  const kIds = Object.keys(base.fields)
    .filter((id) => id.startsWith(K_PREFIX))
    .sort((a, b) => Number(a.slice(K_PREFIX.length)) - Number(b.slice(K_PREFIX.length)));

  const setField = (id: string, value: string) => setState((s) => ({ ...s, fields: { ...s.fields, [id]: value } }));
  const setPrice = (ticker: string, value: string) => setState((s) => ({ ...s, prices: { ...s.prices, [ticker]: value } }));
  const reset = () => setState(initialState(data));
  const anyChange = view.changedFields.length > 0 || Object.keys(state.prices).some((t) => state.prices[t] !== base.prices[t]);

  const field = (f: FieldDef) => {
    const changed = touched.has(f.id);
    const inputId = `sim-${f.id}`;
    return (
      <div key={f.id} className={changed ? "field changed" : "field"}>
        {f.kind === "bool" ? (
          <label htmlFor={inputId}>
            <input
              id={inputId}
              type="checkbox"
              checked={state.fields[f.id] === "true"}
              onChange={(e) => setField(f.id, String(e.target.checked))}
            />{" "}
            {f.label}
          </label>
        ) : (
          <>
            <label htmlFor={inputId}>{f.label}</label>
            <span className="inputwrap">
              <input
                id={inputId}
                inputMode="decimal"
                autoComplete="off"
                value={state.fields[f.id] ?? ""}
                onChange={(e) => setField(f.id, e.target.value)}
                aria-invalid={view.errors.some((m) => m.startsWith(f.label)) || undefined}
              />
              {f.kind === "percent" && <span aria-hidden="true">%</span>}
            </span>
          </>
        )}
        {changed && <span className="tag">alterado</span>}
        {f.hint && <span className="sub">{f.hint}</span>}
      </div>
    );
  };

  const cons = view.consolidated;
  return (
    <section className="sim">
      <p className="notice" role="note">
        Simulação: nada é gravado e o resultado não é o preço teto oficial. Usa os insumos do cálculo de{" "}
        {formatDate(data.asOf)} (último exercício: {formatDate(data.dataBase)}); só os parâmetros e o preço mudam. Janelas
        de exercícios e alíquotas continuam as do pipeline.
      </p>

      <div className="sim-grid">
        <form className="sim-form" onSubmit={(e) => e.preventDefault()} aria-label="Parâmetros da simulação">
          {GROUPS.map((g) => (
            <fieldset key={g}>
              <legend>{GROUP_LABEL[g]}</legend>
              {FIELDS.filter((f) => f.group === g).map(field)}
              {g === "dcf" && (
                <div className={touched.has(DCF_GROWTH_FIELD) ? "field changed" : "field"}>
                  <label htmlFor="sim-dcf-growth">Crescimento do FCFE informado</label>
                  <span className="inputwrap">
                    <input
                      id="sim-dcf-growth"
                      inputMode="decimal"
                      autoComplete="off"
                      placeholder="o do pipeline"
                      value={state.fields[DCF_GROWTH_FIELD] ?? ""}
                      onChange={(e) => setField(DCF_GROWTH_FIELD, e.target.value)}
                    />
                    <span aria-hidden="true">%</span>
                  </span>
                  {touched.has(DCF_GROWTH_FIELD) && <span className="tag">alterado</span>}
                  <span className="sub">Vazio mantém o crescimento que o pipeline usou. Informado vale sem o teto do histórico.</span>
                </div>
              )}
            </fieldset>
          ))}
          <fieldset>
            <legend>Votos exigidos (K)</legend>
            {kIds.map((id) => (
              <div key={id} className={touched.has(id) ? "field changed" : "field"}>
                <label htmlFor={`sim-${id}`}>Com {id.slice(K_PREFIX.length)} métodos aplicáveis</label>
                <span className="inputwrap">
                  <input
                    id={`sim-${id}`}
                    inputMode="numeric"
                    autoComplete="off"
                    value={state.fields[id] ?? ""}
                    onChange={(e) => setField(id, e.target.value)}
                  />
                </span>
                {touched.has(id) && <span className="tag">alterado</span>}
              </div>
            ))}
            <span className="sub">Com menos métodos que o menor valor: dados insuficientes, nunca compra.</span>
          </fieldset>
          <button type="button" onClick={reset} disabled={!anyChange}>
            Voltar aos valores gravados
          </button>
        </form>

        <div className="sim-out" aria-live="polite">
          {view.errors.length > 0 && (
            <div role="alert" className="errors">
              <strong>Corrija para ver o resultado:</strong>
              <ul>
                {view.errors.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </div>
          )}

          {cons && view.sim && (
            <>
              <p className="headline">
                <strong>Teto consolidado: {formatBRL(cons.ceiling?.toString())} por ação</strong>
                {cons.changed && <span className="tag">alterado</span>}
                <span className="sub">
                  {" "}
                  · gravado: {formatBRL(cons.stored.ceiling)} · {cons.methodsOk} método(s) aplicável(is) · votos exigidos (K):{" "}
                  {cons.kRequired ?? "n/a"}
                  {cons.status === "insufficient" && " · dados insuficientes: nunca é compra"}
                </span>
              </p>
              {!view.changed && <p className="sub">Com os valores atuais o resultado é idêntico ao gravado.</p>}

              <h3>Métodos</h3>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th>Método</th>
                      <th className="num">Gravado</th>
                      <th className="num">Simulado</th>
                      <th>Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...view.methods]
                      .sort((a, b) => METHODS.indexOf(a.method) - METHODS.indexOf(b.method))
                      .map((m) => (
                        <tr key={m.method}>
                          <td>
                            <strong>{METHOD_LABEL[m.method] ?? m.method}</strong>
                          </td>
                          <td className="num">
                            {m.storedStatus === "ok" ? formatBRL(m.storedValue) : (METHOD_STATUS_LABEL[m.storedStatus ?? ""] ?? UNAVAILABLE)}
                          </td>
                          <td className="num">{m.sim.status === "ok" ? formatBRL(m.sim.value?.toString()) : UNAVAILABLE}</td>
                          <td>
                            {METHOD_STATUS_LABEL[m.sim.status]}
                            {m.changed && <span className="tag">alterado</span>}
                            {m.sim.reason && <div className="sub">{m.sim.reason}</div>}
                            {!m.sim.recomputed && (
                              <div className="sub">
                                valor gravado: faltam insumos para refazer
                                {m.method === "dcf" && m.storedStatus === "ok" ? " (rode compute --step ceilings)" : ""}
                              </div>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              <h3>Papéis</h3>
              <div className="tablewrap">
                <table>
                  <thead>
                    <tr>
                      <th>Papel</th>
                      <th className="num">Preço (R$)</th>
                      <th className="num">Teto</th>
                      <th className="num">Preço ÷ teto</th>
                      <th>Faixa</th>
                      <th className="num">Votos</th>
                      <th>Situação</th>
                    </tr>
                  </thead>
                  <tbody>
                    {view.classes.map((k) => (
                      <tr key={k.ticker} className={k.sim.buy ? "buy" : undefined}>
                        <td>
                          <strong>{k.ticker}</strong>
                          <div className="sub">{k.kind === "unit" ? `unit (${k.multiplier ?? "?"} ações)` : k.kind.toUpperCase()}</div>
                        </td>
                        <td className="num">
                          <input
                            className="price"
                            aria-label={`Preço de ${k.ticker}`}
                            inputMode="decimal"
                            autoComplete="off"
                            value={state.prices[k.ticker] ?? ""}
                            onChange={(e) => setPrice(k.ticker, e.target.value)}
                          />
                          <div className="sub">gravado: {formatBRL(k.stored?.price)}</div>
                        </td>
                        <td className="num">
                          {formatBRL(k.sim.ceiling?.toString())}
                          <div className="sub">gravado: {formatBRL(k.stored?.ceiling)}</div>
                        </td>
                        <td className="num">
                          {formatPercent(k.sim.ratio?.toString(), 1)}
                          <div className="sub">gravado: {formatPercent(k.stored?.ratio, 1)}</div>
                        </td>
                        <td>{k.sim.band ? BAND_LABEL[k.sim.band] : UNAVAILABLE}</td>
                        <td className="num">
                          {k.sim.votes !== null && k.sim.kRequired !== null ? `${k.sim.votes}/${k.sim.kRequired}` : UNAVAILABLE}
                        </td>
                        <td>
                          {k.simSituation}
                          {k.changed && <span className="tag">alterado</span>}
                          {k.changed && <div className="sub">gravado: {k.storedSituation}</div>}
                          {k.sim.reason && <div className="sub">{k.sim.reason}</div>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
