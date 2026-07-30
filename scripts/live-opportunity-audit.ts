#!/usr/bin/env tsx

import "dotenv/config";
import { spawn } from "node:child_process";

const API_BASE = process.env.APEX_API_BASE || "http://127.0.0.1:3000";
const DEFAULT_TIMEOUT_MS = 300_000;

type Json = Record<string, any>;
type ParsedLine = { tag: string; fields: Record<string, string> };

function intEnv(name: string, fallback: number) {
  const parsed = Number(process.env[name]);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : fallback;
}

async function getJson(path: string): Promise<Json> {
  const response = await fetch(`${API_BASE}${path}`);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${path} HTTP ${response.status}: ${text.slice(0, 240)}`);
  }
  return text ? JSON.parse(text) : {};
}

function parseTaggedLine(line: string): ParsedLine | null {
  const trimmed = line.trim();
  if (!trimmed || !trimmed.includes("|")) return null;
  const [tag, ...parts] = trimmed.split("|");
  const fields: Record<string, string> = {};
  for (const part of parts) {
    const separator = part.indexOf("=");
    if (separator === -1) continue;
    fields[part.slice(0, separator)] = part.slice(separator + 1);
  }
  return { tag, fields };
}

function asNumber(value: string | number | undefined) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function boolEnv(name: string, fallback = false) {
  const raw = process.env[name];
  if (raw === undefined || raw.trim() === "") return fallback;
  return raw === "true" || raw === "1";
}

function printCheck(name: string, passed: boolean, detail: string) {
  console.log(`LIVE_AUDIT_CHECK|name=${name}|passed=${passed}|detail=${detail}`);
}

async function runLiveCycleAudit() {
  const timeoutMs = intEnv("LIVE_AUDIT_CYCLE_TIMEOUT_MS", DEFAULT_TIMEOUT_MS);
  const lines: string[] = [];

  await new Promise<void>((resolve, reject) => {
    const child = spawn(process.execPath, ["node_modules/tsx/dist/cli.mjs", "scripts/live-cycle.ts"], {
      cwd: process.cwd(),
      env: {
        ...process.env,
        LIVE_ROUTE_PRINT_LIMIT: process.env.LIVE_ROUTE_PRINT_LIMIT || "20",
        MAX_DYNAMIC_ROUTES: process.env.LIVE_AUDIT_MAX_DYNAMIC_ROUTES || process.env.MAX_DYNAMIC_ROUTES || "80",
        C1_EXECUTABLE_LIMIT_PER_CYCLE: boolEnv("LIVE_AUDIT_ALLOW_BROADCAST")
          ? process.env.C1_EXECUTABLE_LIMIT_PER_CYCLE || "10"
          : "0",
      },
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let settled = false;
    const finish = (error?: Error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (error) reject(error);
      else resolve();
    };

    const handleChunk = (chunk: Buffer) => {
      const text = chunk.toString();
      process.stdout.write(text);
      lines.push(...text.split(/\r?\n/).filter(Boolean));
    };

    child.stdout.on("data", handleChunk);
    child.stderr.on("data", handleChunk);
    child.on("error", (error) => finish(error));
    child.on("close", (code) => {
      if ((code ?? 1) !== 0) {
        const failure = lines.find((line) => line.startsWith("LIVE_CYCLE_FAILED|"));
        finish(new Error(failure || `LIVE_CYCLE_EXIT_${code ?? 1}`));
        return;
      }
      finish();
    });

    const timer = setTimeout(() => {
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 2_000).unref();
      finish(new Error(`LIVE_AUDIT_TIMEOUT:${timeoutMs}`));
    }, timeoutMs);
  });

  const parsed = lines.map(parseTaggedLine).filter((item): item is ParsedLine => item !== null);
  return {
    parsed,
    discovery: parsed.find((item) => item.tag === "DISCOVERY_SUMMARY")?.fields,
    routeRanks: parsed.filter((item) => item.tag === "ROUTE_RANK").map((item) => item.fields),
    decision: parsed.find((item) => item.tag === "OPPORTUNITY_DECISION")?.fields,
    c1Execution: parsed.find((item) => item.tag === "C1_EXECUTION_RESULT")?.fields,
  };
}

async function main() {
  console.log(`LIVE_AUDIT_START|api=${API_BASE}|timeoutMs=${intEnv("LIVE_AUDIT_CYCLE_TIMEOUT_MS", DEFAULT_TIMEOUT_MS)}`);

  const [health, readiness, controlState, opportunities] = await Promise.all([
    getJson("/api/system/healthz"),
    getJson("/api/system/readiness"),
    getJson("/api/execution/control/state"),
    getJson("/api/execution/opportunities"),
  ]);

  const healthPassed = health.status === "OPERATIONAL" || health.success === true;
  printCheck("api_health", healthPassed, health.status || String(health.success));

  const readinessPassed = readiness.ready === true && readiness.status === "LIVE_READY";
  printCheck("api_readiness", readinessPassed, readiness.status || "UNKNOWN");

  const liveExecutionEnabled = controlState?.mode?.LIVE_EXECUTION === "true";
  const shadowModeDisabled = controlState?.mode?.SHADOW_MODE === "false";
  printCheck(
    "runtime_mode",
    liveExecutionEnabled && shadowModeDisabled,
    `LIVE_EXECUTION=${controlState?.mode?.LIVE_EXECUTION ?? "UNKNOWN"},SHADOW_MODE=${controlState?.mode?.SHADOW_MODE ?? "UNKNOWN"}`,
  );

  const feedAvailable = Array.isArray(opportunities.opportunities);
  const feedCount = feedAvailable ? opportunities.opportunities.length : 0;
  const feedExecutableCount = feedAvailable
    ? opportunities.opportunities.filter((item: any) => item.c1ExecutionEligible || item.executionReady).length
    : 0;
  printCheck(
    "opportunity_feed",
    feedAvailable,
    `visible=${feedCount},executableVisible=${feedExecutableCount},source=${opportunities.source || "UNKNOWN"}`,
  );

  const cycle = await runLiveCycleAudit();
  const discovery = cycle.discovery || {};
  const routeRanks = cycle.routeRanks;
  const executableRanks = routeRanks.filter((item) => item.status === "EXECUTABLE_PROFIT_CANDIDATE" || item.c1ExecutionEligible === "true");
  const requireExecutable = boolEnv("LIVE_AUDIT_REQUIRE_EXECUTABLE");

  const flashloanAssets = asNumber(discovery.flashloanAssets);
  const discoveredPools = asNumber(discovery.discoveredPools);
  const directedEdges = asNumber(discovery.directedEdges);
  const routeCycles = asNumber(discovery.routeCycles);
  const rejectedPreSend = asNumber(discovery.rejectedPreSend);

  printCheck(
    "flashloan_assets",
    flashloanAssets > 0,
    `count=${flashloanAssets}`,
  );
  printCheck(
    "discovery_graph",
    discoveredPools > 0 && directedEdges > 0,
    `pools=${discoveredPools},edges=${directedEdges},rejectedPreSend=${rejectedPreSend}`,
  );
  printCheck(
    "route_enumeration",
    routeCycles > 0 && routeRanks.length > 0,
    `routeCycles=${routeCycles},rankedRoutes=${routeRanks.length}`,
  );

  const executableEvidence = executableRanks.length > 0 || feedExecutableCount > 0;
  printCheck(
    "executable_opportunity_visible",
    executableEvidence || !requireExecutable,
    `cycleExecutable=${executableRanks.length},feedExecutable=${feedExecutableCount},required=${requireExecutable}`,
  );

  const c1Execution = cycle.c1Execution;
  if (c1Execution) {
    printCheck(
      "c1_submission",
      c1Execution.success === "true",
      `success=${c1Execution.success},hash=${c1Execution.hash || "NONE"},forkOk=${c1Execution.forkOk || "UNKNOWN"},error=${c1Execution.error || "NONE"}`,
    );
  }

  let status = executableEvidence ? "PASS" : "PASS_NO_EXECUTABLE";
  let reason = executableEvidence ? "EXECUTABLE_OPPORTUNITY_VISIBLE" : cycle.decision?.reason || "NO_EXECUTABLE_ROUTE_VISIBLE";
  const failClosedNoRouteReason = cycle.decision?.reason === "NO_ATOMIC_USDCE_FLASHLOAN_CAPITAL";
  if (!healthPassed || !readinessPassed || !liveExecutionEnabled || !shadowModeDisabled) {
    status = "BLOCKED";
    reason = "RUNTIME_NOT_LIVE_READY";
  } else if (flashloanAssets === 0 || discoveredPools === 0 || directedEdges === 0 || routeCycles === 0 || routeRanks.length === 0) {
    status = failClosedNoRouteReason ? "PASS_NO_EXECUTABLE" : "BLOCKED";
    reason = cycle.decision?.reason || "DISCOVERY_PIPELINE_NOT_PRODUCING_ROUTES";
  } else if (!executableEvidence && requireExecutable) {
    status = "NO_EXECUTABLE_OPPORTUNITY";
    reason = cycle.decision?.reason || "NO_EXECUTABLE_ROUTE_VISIBLE";
  }

  console.log(
    `LIVE_AUDIT_RESULT|status=${status}|reason=${reason}|feedVisible=${feedCount}|feedExecutable=${feedExecutableCount}|cycleRanked=${routeRanks.length}|cycleExecutable=${executableRanks.length}|decision=${cycle.decision?.decision || "UNKNOWN"}`,
  );

  if (status === "BLOCKED" || status === "NO_EXECUTABLE_OPPORTUNITY") process.exit(1);
}

main().catch((error) => {
  console.error(`LIVE_AUDIT_FAILED|error=${error?.message || error}`);
  process.exit(1);
});
