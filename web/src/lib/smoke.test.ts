import { describe, expect, it } from "vitest";

describe("esqueleto do web", () => {
  it("roda o Vitest com o alias @", async () => {
    const mod = await import("@/lib/version");
    expect(mod.PHASE).toBe(5);
  });
});
