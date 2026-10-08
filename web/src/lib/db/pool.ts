import { Pool, types } from "pg";

// Datas como texto `AAAA-MM-DD` (sem passar por Date, que desloca pelo fuso) e numeric como texto
// (sem perder precisão). timestamptz fica como Date e é convertido em `iso()` nas consultas.
const parsers = (oid: number, format?: "text" | "binary") => {
  if (oid === types.builtins.DATE) return (v: string) => v;
  return types.getTypeParser(oid, format as "text");
};

declare global {
  var __acoesPool: Pool | undefined;
}

/** Pool único por instância (sobrevive ao hot reload). Usa só a URL do pooler da Vercel. */
export function getPool(): Pool {
  if (!globalThis.__acoesPool) {
    const url = process.env.NEON_DATABASE_URL_POOLED;
    if (!url) throw new Error("NEON_DATABASE_URL_POOLED não definida");
    globalThis.__acoesPool = new Pool({
      connectionString: url,
      max: 3,
      idleTimeoutMillis: 10_000,
      connectionTimeoutMillis: 8_000,
      types: { getTypeParser: parsers as never },
    });
  }
  return globalThis.__acoesPool;
}

/** Pool para testes, com os mesmos conversores de tipo. */
export function createPool(connectionString: string): Pool {
  return new Pool({ connectionString, max: 2, types: { getTypeParser: parsers as never } });
}
