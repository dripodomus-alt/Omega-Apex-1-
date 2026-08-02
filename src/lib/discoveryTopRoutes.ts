export type DiscoveryBankingTag = "healthy" | "buffered" | "tight";

export interface DiscoveryTopRouteRow {
  id: string;
  routeKey: string;
  score: number;
  bankBalance: number;
  state: "stable" | "warming" | "cooling" | "watch";
  rank: number;
  bankingTag: DiscoveryBankingTag;
}

interface DiscoveryRouteCandidate {
  [key: string]: any;
}

function safeNumber(value: unknown): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function inferState(row: DiscoveryRouteCandidate): DiscoveryTopRouteRow["state"] {
  if (row.c1ExecutionEligible || row.executionReady) return "stable";
  if (safeNumber(row.confidence) >= 90 || safeNumber(row.netProfitUsd ?? row.profit_usd) > 0) {
    return "warming";
  }
  if (safeNumber(row.rawSpreadBps ?? row.spread_bps) > 0) {
    return "cooling";
  }
  return "watch";
}

export function buildDiscoveryTopRoutes(
  incoming: DiscoveryRouteCandidate[],
  limit = 10,
): DiscoveryTopRouteRow[] {
  const normalized = incoming
    .map((row) => {
      const score = safeNumber(row.netProfitUsd ?? row.profit_usd ?? row.rawSpreadBps ?? row.spread_bps ?? row.confidence);
      const bankBalance = safeNumber(row.maxApplicableCapital ?? row.maxApplicableCapitalUsd ?? row.routePoolStateCapUsd ?? row.routePoolStateCap ?? row.rawSpreadDelta);

      return {
        id: String(row.routeId ?? row.id ?? `${row.pair ?? row.path ?? row.route ?? "route"}-${Math.random()}`),
        routeKey: String(row.pair || row.path || row.route || row.venues || "DISCOVERY_ROUTE"),
        score,
        bankBalance,
        state: inferState(row),
      };
    })
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      return b.bankBalance - a.bankBalance;
    })
    .slice(0, limit);

  return normalized.map((row, index) => {
    const bankingTag: DiscoveryBankingTag =
      row.bankBalance > 100000
        ? "healthy"
        : row.bankBalance > 25000
          ? "buffered"
          : "tight";

    return {
      ...row,
      rank: index + 1,
      bankingTag,
    };
  });
}
