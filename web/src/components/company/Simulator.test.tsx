import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { dataFor } from "../../../tests/helpers/simulatorData";
import { Simulator } from "./Simulator";

const render = (name: string, initial?: Parameters<typeof Simulator>[0]["initial"]) =>
  renderToStaticMarkup(<Simulator data={dataFor(name)} initial={initial} />);

describe("Simulator (renderização inicial)", () => {
  it("abre com os parâmetros do pipeline, idêntico ao gravado e com o aviso de que nada é gravado", () => {
    const html = render("comum_completo");
    expect(html).toContain("nada é gravado e o resultado não é o preço teto oficial");
    expect(html).toContain("05/10/2026");
    expect(html).toContain("Com os valores atuais o resultado é idêntico ao gravado.");
    expect(html).not.toContain('class="tag"'); // nada alterado
    expect(html).toContain('id="sim-bazin_rate"');
    expect(html).toMatch(/id="sim-bazin_rate"[^>]*value="6"/);
    expect(html).toMatch(/id="sim-graham_multiplier"[^>]*value="22,5"/);
    expect(html).toContain("Com 3 métodos aplicáveis");
    expect(html).toContain("Voltar aos valores gravados");
    expect(html).toMatch(/<button[^>]*disabled[^>]*>Voltar aos valores gravados/); // nada a voltar
  });

  it("mostra métodos e papéis com gravado e simulado lado a lado", () => {
    const html = render("comum_completo");
    for (const m of ["Bazin", "Graham", "Gordon", "Múltiplos", "DCF"]) expect(html).toContain(m);
    expect(html).toContain("gravado: R$");
    expect(html).toContain('aria-label="Preço de ALFA3"');
    expect(html).toContain('aria-label="Preço de ALFA11"');
    expect(html).not.toContain("R$ 0,00");
  });

  it("alteração vira marca 'alterado' em texto, no campo e no resultado", () => {
    const html = render("comum_completo", { fields: { bazin_rate: "8" } });
    expect(html).toContain("alterado");
    expect(html).not.toContain("idêntico ao gravado");
    expect(html).toMatch(/<button(?![^>]*disabled)[^>]*>Voltar aos valores gravados/);
  });

  it("campo inválido mostra o erro e não mostra resultado", () => {
    const html = render("comum_completo", { fields: { gordon_k: "doze" } });
    expect(html).toContain('role="alert"');
    expect(html).toContain("Retorno exigido (k): valor inválido.");
    expect(html).not.toContain("Teto consolidado");
    expect(html).toContain('aria-invalid="true"');
  });

  it("preço alterado marca o papel como caro e tira a compra", () => {
    const html = render("comum_completo", { prices: { ALFA3: "9999" } });
    expect(html).toContain("Cara, avaliar venda");
  });

  it("DCF sem crescimento histórico: explica o motivo e aceita o crescimento informado", () => {
    const html = render("dcf_pede_crescimento");
    expect(html).toContain("informe o crescimento da empresa");
    const after = render("dcf_pede_crescimento", { fields: { dcf_growth: "3" } });
    expect(after).not.toContain("informe o crescimento da empresa");
    expect(after).toContain("alterado");
  });

  it("método sem insumos para refazer é marcado como valor gravado", () => {
    const html = render("banco");
    expect(html).toContain("faltam insumos para refazer"); // Graham e DCF excluídos pelo plano de contas
  });

  it("dados insuficientes: o teto aparece e a compra não", () => {
    const html = render("dois_metodos_dados_insuficientes");
    expect(html).toContain("dados insuficientes: nunca é compra");
    expect(html).not.toContain("COMPRA");
  });
});
