import "server-only";
import { requireUser } from "@/lib/auth/session";
import { type DataFreshness, loadDataFreshness } from "./core";
import { getPool } from "./pool";
import { loadPending, loadScreen, type Pending, type ScreenPage } from "./screen";
import { loadWatchlist } from "./watchlist";
import type { ScreenFilters } from "@/lib/screen";
import type { WatchlistData } from "@/lib/watchlist";

// Toda consulta da tela passa por aqui: confere o usuário e a lista de e-mails antes de tocar o banco,
// e roda em transação somente leitura. Nada de `getPool()` fora deste arquivo.

export async function getDataFreshness(): Promise<DataFreshness> {
  await requireUser();
  return loadDataFreshness(getPool());
}

export async function getWatchlist(): Promise<WatchlistData> {
  await requireUser();
  return loadWatchlist(getPool());
}

export async function getScreen(filters: ScreenFilters): Promise<ScreenPage> {
  await requireUser();
  return loadScreen(getPool(), filters);
}

export async function getPending(): Promise<Pending> {
  await requireUser();
  return loadPending(getPool());
}
