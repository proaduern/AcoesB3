import { describe, expect, it } from "vitest";
import { isAllowedEmail, parseAllowedEmails } from "./allowed";

describe("parseAllowedEmails", () => {
  it("separa por vírgula, ponto e vírgula e espaço, em minúsculas", () => {
    expect(parseAllowedEmails(" A@x.com, b@Y.com;c@z.com  d@w.com ")).toEqual([
      "a@x.com",
      "b@y.com",
      "c@z.com",
      "d@w.com",
    ]);
  });

  it("vazio, ausente ou só separadores = lista vazia", () => {
    expect(parseAllowedEmails(undefined)).toEqual([]);
    expect(parseAllowedEmails(null)).toEqual([]);
    expect(parseAllowedEmails("")).toEqual([]);
    expect(parseAllowedEmails(" , ; ")).toEqual([]);
  });
});

describe("isAllowedEmail", () => {
  const list = ["eu@exemplo.com"];

  it("aceita e-mail da lista ignorando caixa e espaços", () => {
    expect(isAllowedEmail("Eu@Exemplo.com ", list)).toBe(true);
  });

  it("recusa e-mail fora da lista, vazio ou ausente", () => {
    expect(isAllowedEmail("outro@exemplo.com", list)).toBe(false);
    expect(isAllowedEmail("", list)).toBe(false);
    expect(isAllowedEmail(undefined, list)).toBe(false);
    expect(isAllowedEmail(null, list)).toBe(false);
  });

  it("não casa por trecho (sufixo ou prefixo)", () => {
    expect(isAllowedEmail("eu@exemplo.com.br", list)).toBe(false);
    expect(isAllowedEmail("meu@exemplo.com", list)).toBe(false);
  });

  it("lista vazia recusa todos (falha fechada)", () => {
    expect(isAllowedEmail("eu@exemplo.com", [])).toBe(false);
  });
});
