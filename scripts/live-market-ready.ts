#!/usr/bin/env tsx

import "dotenv/config";
import { spawn } from "node:child_process";
import { existsSync, rmSync } from "node:fs";
import { join } from "node:path";

function numberEnv(name: string, fallback: number) {
  const parsed = Number(process.env[name]);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function boolEnv(name: string, fallback: boolean) {
  const raw = process.env[name];
  if (raw === undefined) return fallback;
  return raw.toLowerCase() === "true";
}

function withDefault(name: string, value: string) {
  const current = process.env[name];
  if (current === undefined || current.trim() === "") {
    process.env[name] = value;
  }
}

function cachePath() {
  return process.env.DISCOVERY_CACHE_PATH || join(process.cwd(), ".apex-discovery-cache.json");
}

function enforceFlashloanProviderGuard() {
  const balancerSupported = process.env.C1_BALANCER_FLASHLOAN_SUPPORTED === "true";
  if (!balancerSupported) return;
  if (process.env.LIVE_MARKET_ALLOW_BALANCER_C1 === "true") return;
  throw new Error(
    "BALANCER_C1_GUARD: C1_BALANCER_FLASHLOAN_SUPPORTED=true requires LIVE_MARKET_ALLOW_BALANCER_C1=true (set only after callback upgrade).",
  );
}

function applyImmediateDiscoveryProfile() {
  withDefault("DISCOVERY_CACHE_MAX_AGE_BLOCKS", "0");
  withDefault("LIVE_DISCOVERY_LOOKBACK_BLOCKS", "120000");
  withDefault("SIM_MAX_FLASH_TVL_FRACTION", "0.05");
  withDefault("MIN_NET_PROFIT_USD", "1");
  withDefault("RISK_BUFFER_USD", "0");
  withDefault("LIVE_ROUTE_PRINT_LIMIT", "50");
  withDefault("TOP_ROUTE_DISPLAY_LIMIT", "20");
  withDefault("MAX_DYNAMIC_ROUTES", "1000");
  withDefault("LIVE_AUDIT_CYCLE_TIMEOUT_MS", "300000");
}

function maybeColdRescan() {
  if (!boolEnv("LIVE_MARKET_COLD_RESCAN_ONCE", true)) {
    console.log("LIVE_MARKET_READY|coldRescan=false|reason=LIVE_MARKET_COLD_RESCAN_ONCE_DISABLED");
    return;
  }
  const path = cachePath();
  if (!existsSync(path)) {
    console.log(`LIVE_MARKET_READY|coldRescan=true|cacheRemoved=false|cachePath=${path}|reason=CACHE_MISSING`);
    return;
  }
  rmSync(path, { force: true });
  console.log(`LIVE_MARKET_READY|coldRescan=true|cacheRemoved=true|cachePath=${path}`);
}

async function runAudit() {
  const timeoutMs = Math.max(120_000, Math.floor(numberEnv("LIVE_AUDIT_CYCLE_TIMEOUT_MS", 300_000)));
  return await new Promise<void>((resolve, reject) => {
    const child = spawn(process.execPath, ["node_modules/tsx/dist/cli.mjs", "scripts/live-opportunity-audit.ts"], {
      cwd: process.cwd(),
      env: {
        ...process.env,
      },
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 2_000).unref();
      reject(new Error(`LIVE_MARKET_AUDIT_TIMEOUT:${timeoutMs}`));
    }, timeoutMs);

    child.stdout.on("data", (chunk: Buffer) => process.stdout.write(chunk));
    child.stderr.on("data", (chunk: Buffer) => process.stderr.write(chunk));
    child.on("error", (error) => {
      clearTimeout(timer);
      reject(error);
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if ((code ?? 1) !== 0) {
        reject(new Error(`LIVE_MARKET_AUDIT_EXIT_${code ?? 1}`));
        return;
      }
      resolve();
    });
  });
}

async function main() {
  enforceFlashloanProviderGuard();
  applyImmediateDiscoveryProfile();
  maybeColdRescan();
  console.log(
    `LIVE_MARKET_READY_PROFILE|lookback=${process.env.LIVE_DISCOVERY_LOOKBACK_BLOCKS}|flashTvlFraction=${process.env.SIM_MAX_FLASH_TVL_FRACTION}|minNetProfitUsd=${process.env.MIN_NET_PROFIT_USD}|riskBufferUsd=${process.env.RISK_BUFFER_USD}|routePrintLimit=${process.env.LIVE_ROUTE_PRINT_LIMIT}|topRouteDisplayLimit=${process.env.TOP_ROUTE_DISPLAY_LIMIT}|balancerC1=${process.env.C1_BALANCER_FLASHLOAN_SUPPORTED || "false"}`,
  );
  await runAudit();
}

main().catch((error) => {
  console.error(`LIVE_MARKET_READY_FAILED|error=${error?.message || error}`);
  process.exit(1);
});
