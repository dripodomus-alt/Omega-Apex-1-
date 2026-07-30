#!/usr/bin/env tsx

import "dotenv/config";
import { spawn } from "node:child_process";
import { ethers } from "ethers";
import ApexOmegaBootstrap, {
  formatCycleResults,
  CycleResults,
  ExecutionCycle,
} from "../server/engine/SystemBootstrap.js";

const CHAIN_ID = 137n;
const DEFAULT_CYCLE_COUNT = 5;
const DEFAULT_CYCLE_TIMEOUT_MS = 180_000;
const API_BASE = process.env.APEX_API_BASE || "http://127.0.0.1:3000";
const RPC_URL =
  process.env.POLYGON_RPC_URL ||
  process.env.POLYGON_RPC ||
  process.env.RPC_URL ||
  "https://polygon-rpc.com";

function intEnv(name: string, fallback: number) {
  const parsed = Number(process.env[name]);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback;
}

// Validate RPC connectivity and chain ID
async function getJson(path: string) {
  const response = await fetch(`${API_BASE}${path}`);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${path} HTTP ${response.status}: ${text.slice(0, 240)}`);
  }
  return text ? JSON.parse(text) : {};
}

async function validateChain() {
  const provider = new ethers.JsonRpcProvider(RPC_URL, Number(CHAIN_ID), {
    staticNetwork: true,
  });
  const [network, blockNumber, feeData] = await Promise.all([
    provider.getNetwork(),
    provider.getBlockNumber(),
    provider.getFeeData(),
  ]);
  if (network.chainId !== CHAIN_ID) {
    throw new Error(`CHAIN_ID_MISMATCH:${network.chainId}`);
  }
  const gasPrice = feeData.gasPrice || 0n;
  console.log(
    `LIVE_5_PRECHECK|chainId=${network.chainId}|block=${blockNumber}|gasGwei=${ethers.formatUnits(gasPrice, "gwei")}|api=${API_BASE}`
  );
}

function runCycle(cycleNumber: number): Promise<number> {
  return new Promise((resolve) => {
    const started = Date.now();
    const timeoutMs = intEnv("LIVE_5_CYCLE_TIMEOUT_MS", DEFAULT_CYCLE_TIMEOUT_MS);
    let settled = false;
    const finish = (code: number, status: string) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      const durationMs = Date.now() - started;
      console.log(
        `LIVE_5_CYCLE_END|cycle=${cycleNumber}|exitCode=${code}|status=${status}|durationMs=${durationMs}`
      );
      resolve(code);
    };
    const child = spawn(process.execPath, ["node_modules/tsx/dist/cli.mjs", "scripts/live-cycle.ts"], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        LIVE_ROUTE_PRINT_LIMIT:
          process.env.LIVE_ROUTE_PRINT_LIMIT || process.env.LIVE_5_ROUTE_PRINT_LIMIT || "20",
      },
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });
    const timer = setTimeout(() => {
      console.error(`LIVE_5_CYCLE_TIMEOUT|cycle=${cycleNumber}|timeoutMs=${timeoutMs}`);
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 2_000).unref();
      finish(124, "TIMEOUT");
    }, timeoutMs);

    console.log(`LIVE_5_CYCLE_BEGIN|cycle=${cycleNumber}`);

    child.stdout.on("data", (chunk: Buffer) => {
      process.stdout.write(chunk);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      process.stderr.write(chunk);
    });
    child.on("close", (code) => {
      finish(code ?? 1, code === 0 ? "COMPLETE" : "FAILED");
    });
    child.on("error", (error) => {
      console.error(`LIVE_5_CYCLE_FAILED|cycle=${cycleNumber}|error=${error.message}`);
      finish(1, "FAILED");
    });
  });
}

async function main() {
  const cycleCount = intEnv("LIVE_5_CYCLE_COUNT", DEFAULT_CYCLE_COUNT);
  console.log(
    `LIVE_5_START|cycles=${cycleCount}|engine=scripts/live-cycle.ts|mockDataAllowed=false|broadcastPolicy=ONLY_AFTER_PROFIT_AND_FORK_PASS`
  );

  await validateChain();
  const [health, readiness, opportunities] = await Promise.all([
    getJson("/api/system/healthz").catch((error) => ({ error: error.message })),
    getJson("/api/system/readiness").catch((error) => ({ error: error.message })),
    getJson("/api/execution/opportunities").catch((error) => ({ error: error.message })),
  ]);
  console.log(
    `LIVE_5_API_PRECHECK|health=${health.status || health.success || health.error}|readiness=${readiness.status || readiness.ready || readiness.error}|opportunities=${opportunities.opportunities?.length ?? "UNKNOWN"}|source=${opportunities.source || "UNKNOWN"}`
  );

  let failures = 0;
  for (let index = 1; index <= cycleCount; index += 1) {
    const exitCode = await runCycle(index);
    if (exitCode !== 0) failures += 1;
  }

  console.log(
    `LIVE_5_END|cycles=${cycleCount}|failures=${failures}|status=${failures === 0 ? "COMPLETE" : "FAILED"}|pnlUpdated=false_unless_verified_hash_reported_by_cycle`
  );
  if (failures > 0) process.exit(1);
}

main().catch((error) => {
  console.error(`LIVE_5_FAILED|error=${error?.message || error}|pnlUpdated=false`);
  process.exit(1);
});
