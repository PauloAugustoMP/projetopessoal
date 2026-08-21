/** Typed calls for the endpoints the dashboard consumes. The wire types come
 * from src/api/types.ts, generated from docs/openapi/openapi.yaml via
 * `npm run generate:api` — regenerate whenever the contract changes. */

import { api } from "./client";
import type { components } from "./types";

export type Position = components["schemas"]["Position"];
export type PortfolioSummary = components["schemas"]["PortfolioSummary"];
export type PortfolioSnapshot = components["schemas"]["PortfolioSnapshot"];
export type GrowthBreakdown = components["schemas"]["GrowthBreakdown"];
export type Asset = components["schemas"]["Asset"];
export type AssetCategory = components["schemas"]["AssetCategory"];

export function login(password: string) {
  return api.post<{ accessToken: string; refreshToken: string }>("/auth/login", {
    password,
  });
}

export function fetchSummary() {
  return api.get<PortfolioSummary>("/portfolio/summary");
}

export function fetchPositions() {
  return api.get<Position[]>("/positions");
}

export function fetchSnapshots(params?: { from?: string; to?: string }) {
  const query = new URLSearchParams();
  if (params?.from) query.set("from", params.from);
  if (params?.to) query.set("to", params.to);
  const suffix = query.size > 0 ? `?${query.toString()}` : "";
  return api.get<PortfolioSnapshot[]>(`/portfolio/snapshots${suffix}`);
}
