import type { Pool, PoolClient } from "pg";

/**
 * Roda `fn` numa transação **somente leitura**. "A tela só lê" fica garantido pelo banco também:
 * qualquer INSERT/UPDATE/DDL falha com "read-only transaction". Funciona atrás do pooler (pgbouncer em
 * modo transação), que não aceita opções de sessão na conexão.
 */
export async function readOnly<T>(pool: Pick<Pool, "connect">, fn: (c: PoolClient) => Promise<T>) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN READ ONLY");
    const out = await fn(client);
    await client.query("COMMIT");
    return out;
  } catch (e) {
    await client.query("ROLLBACK").catch(() => undefined);
    throw e;
  } finally {
    client.release();
  }
}
