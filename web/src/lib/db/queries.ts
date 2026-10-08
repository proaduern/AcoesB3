import "server-only";
import { requireUser } from "@/lib/auth/session";
import { type DataFreshness, loadDataFreshness } from "./core";
import { getPool } from "./pool";

// Toda consulta da tela passa por aqui: confere o usuário e a lista de e-mails antes de tocar o banco,
// e roda em transação somente leitura. Nada de `getPool()` fora deste arquivo.

export async function getDataFreshness(): Promise<DataFreshness> {
  await requireUser();
  return loadDataFreshness(getPool());
}
