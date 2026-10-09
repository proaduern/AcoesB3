import "server-only";
import { requireUser } from "@/lib/auth/session";
import { type DataFreshness, loadDataFreshness } from "./core";
import { getPool } from "./pool";
import * as company from "./company";
import type { CeilingTab, CompanyHeader, FilterTab, OriginTab, Period, PriceTab } from "@/lib/company";
import type { SimulatorData } from "@/lib/ceiling/view";
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

export async function getCompanyHeader(cvm: number): Promise<CompanyHeader | null> {
  await requireUser();
  return company.loadCompanyHeader(getPool(), cvm);
}

export async function getCeilingTab(cvm: number): Promise<CeilingTab> {
  await requireUser();
  return company.loadCeilingTab(getPool(), cvm);
}

export async function getFilterTab(cvm: number): Promise<FilterTab> {
  await requireUser();
  return company.loadFilterTab(getPool(), cvm);
}

export async function getPriceTab(
  cvm: number,
  tickers: string[],
  wanted: string | null,
  period: Period,
): Promise<PriceTab> {
  await requireUser();
  return company.loadPriceTab(getPool(), cvm, tickers, wanted, period);
}

export async function getOriginTab(cvm: number, tickers: string[]): Promise<OriginTab> {
  await requireUser();
  return company.loadOriginTab(getPool(), cvm, tickers);
}

export async function getSimulatorData(cvm: number): Promise<SimulatorData | null> {
  await requireUser();
  return company.loadSimulatorData(getPool(), cvm);
}
