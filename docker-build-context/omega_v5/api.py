#!/usr/bin/env python3
# ==============================================================================
# api.py -- lightweight runtime API for PM2-managed Omega services.
# ==============================================================================

from __future__ import annotations

import asyncio
import json
import os
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field

from . import rpc_layer
from .aave_liquidations import AaveLiquidationScanner
from .apex_live_design import live_design_status
from .config import (
    API_CORS_ORIGINS,
    API_FRONTEND_TOKEN_REQUIRED,
    API_PORT,
    API_TOKEN,
    BROADCAST_RPC_URL,
    CHAIN_ID,
    FORK_SIM_RPC_URL,
    HTTP_URL,
    REDIS_URL,
    WSS_URL,
    ENABLE_INDEXER_STATE_READS,
)
from .execution import execution_guard_status, executor_code_status, executor_owner
from .execution_trace import get_trace, recent_traces
from .mainnet_finalizer import finalizer_report
from .ml_alpha import ml_alpha_status
from .pnl_tracker import LIVE_RESET_CONFIRM, current_snapshot, record_reset
from .redis_cache import status as redis_status
from .runtime_control import get_runtime_state, set_runtime_mode, update_runtime_settings
from .rust_engine import assert_rust_engine_ready
from .runtime_alignment import load_latest_alignment, runtime_alignment_status
from .session_proof import load_latest_proof, run_session_signer_proof
from .sourced_layers import sourced_layer_status
from .transport_lanes import transport_status
from .oracle_layer import PriceUnavailable, TOKEN_USD_PRICE, TOKEN_USD_SOURCE, refresh_token_prices, token_price_usd


ROOT = Path(__file__).resolve().parents[1]
LIVE_POOL_SCAN_REPORT = ROOT / "out" / "live_pool_scan_report.json"
PROTOCOL_UPDATE_WATCH_REPORT = ROOT / "out" / "protocol_update_watch_latest.json"
ROUTE_SURFACE_REPORT = ROOT / "out" / "route_surface_report_latest.json"
BACKGROUND_DISCOVERY_REPORT = ROOT / "out" / "background_discovery_latest.json"
ROUTE_EXECUTION_STAGE_REPORT = ROOT / "out" / "route_execution_stage_latest.json"
ASSET_STATE_RESEARCH_REPORT = ROOT / "out" / "asset_state_research_latest.json"
MISSING_METADATA_APPRENTICES_REPORT = ROOT / "out" / "missing_metadata_apprentices_latest.json"
MISSING_METADATA_BACKGROUND_REPORT = ROOT / "out" / "missing_metadata_background_latest.json"
APPRENTICE_METADATA_PROMOTION_REVIEW_REPORT = ROOT / "out" / "apprentice_metadata_promotion_review_latest.json"
app = FastAPI(title="Omega V5 Runtime API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=API_CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Omega-Api-Token"],
    allow_credentials=False,
)


def require_frontend_write_token(request: Request) -> None:
    """
    Optional guard for remote frontend write actions.

    It is disabled by default so the existing local UI and PM2 workflow are not
    broken. Set API_FRONTEND_TOKEN_REQUIRED=true when exposing the API outside
    localhost, then pass Authorization: Bearer <API_TOKEN> or X-Omega-Api-Token.
    """
    if not API_FRONTEND_TOKEN_REQUIRED:
        return
    if not API_TOKEN:
        raise HTTPException(status_code=503, detail="API write token is required but API_TOKEN is not configured")
    auth_header = request.headers.get("authorization", "")
    bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    token = bearer or request.headers.get("x-omega-api-token", "").strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="invalid or missing Omega API token")


class RuntimeModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(live|dry_run|dry-run|simulation)$")
    actor: str = "ui"


class RuntimeSettingsRequest(BaseModel):
    execute_top: int | None = Field(default=None)
    print_top_routes: int | None = Field(default=None)
    ticks: int | None = Field(default=None)
    principal_usd: str | None = Field(default=None)
    interval_seconds: int | None = Field(default=None)
    no_scan: bool | None = Field(default=None)
    canary_mode: bool | None = Field(default=None)


class ResetRequest(BaseModel):
    actor: str = "ui"
    confirm: str = ""


UI_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Omega V5 Runtime</title>
  <style>
    :root { color-scheme: dark; font-family: Segoe UI, Arial, sans-serif; }
    body { margin: 0; background: #0e1116; color: #e8edf2; }
    main { max-width: 1180px; margin: 0 auto; padding: 24px; }
    header { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 20px; }
    h1 { font-size: 24px; margin: 0; font-weight: 650; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }
    .panel { background: #171c23; border: 1px solid #2a323d; border-radius: 8px; padding: 16px; }
    .wide { grid-column: span 3; }
    .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 7px 0; border-bottom: 1px solid #252d37; }
    .row:last-child { border-bottom: 0; }
    .label { color: #a9b4c0; font-size: 13px; }
    .value { font-weight: 650; overflow-wrap: anywhere; text-align: right; }
    button, select, input { background: #222a34; color: #edf3f8; border: 1px solid #3b4654; border-radius: 6px; padding: 9px 11px; }
    button { cursor: pointer; }
    button.live { background: #532527; border-color: #a34545; }
    button.dry { background: #1d3a31; border-color: #3a8a6a; }
    button.reset { background: #3c2f1f; border-color: #90652b; }
    .status { display: inline-flex; align-items: center; gap: 8px; padding: 7px 10px; border-radius: 999px; border: 1px solid #384454; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: #8a96a3; }
    .armed .dot { background: #ff5858; }
    .drymode .dot { background: #52d69a; }
    .risk-critical { color: #ff7373; }
    .risk-warning { color: #ffd37a; }
    .risk-watch { color: #9cc9ff; }
    pre { background: #0b0e12; border: 1px solid #29313b; border-radius: 8px; padding: 12px; overflow: auto; max-height: 320px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: right; border-bottom: 1px solid #28313b; padding: 8px; }
    th:first-child, td:first-child { text-align: left; }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } .wide { grid-column: span 1; } header { align-items: flex-start; flex-direction: column; } }
  </style>
</head>
<body>
<main>
  <header>
    <h1>Omega V5 Runtime Control</h1>
    <div id="modeBadge" class="status drymode"><span class="dot"></span><span>loading</span></div>
  </header>
  <section class="grid">
    <div class="panel">
      <h2>Mode</h2>
      <div class="row"><span class="label">Runtime</span><span class="value" id="runtimeMode">-</span></div>
      <div class="row"><span class="label">Execution armed</span><span class="value" id="armed">-</span></div>
      <div class="row"><span class="label">Executor</span><span class="value" id="executor">-</span></div>
      <div style="display:flex; gap:8px; margin-top:14px; flex-wrap:wrap;">
        <button class="dry" onclick="setMode('dry_run')">Dry Run</button>
        <button class="live" onclick="setMode('live')">Live Production</button>
      </div>
    </div>
    <div class="panel">
      <h2>Cycle Settings</h2>
      <div class="row"><span class="label">Execute top</span><select id="executeTop"><option>5</option><option>10</option><option>15</option></select></div>
      <div class="row"><span class="label">Canary cap</span><input id="canaryMode" type="checkbox" /></div>
      <div class="row"><span class="label">Print top</span><input id="printTop" type="number" min="1" max="200" /></div>
      <div class="row"><span class="label">Interval seconds</span><input id="interval" type="number" min="5" max="3600" /></div>
      <button onclick="saveSettings()">Apply Settings</button>
    </div>
    <div class="panel">
      <h2>Reset</h2>
      <div class="row"><span class="label">Dry-run PnL</span><button class="reset" onclick="resetDry()">Reset Dry</button></div>
      <div class="row"><span class="label">Live PnL</span><input id="liveConfirm" placeholder="RESET_LIVE_PNL" /></div>
      <button class="reset" onclick="resetLive()">Explicit Live Reset</button>
    </div>
    <div class="panel wide">
      <h2>PnL</h2>
      <table>
        <thead><tr><th>Book</th><th>C1 PnL</th><th>C2 PnL</th><th>Combined</th><th>C1 Events</th><th>C2 Events</th></tr></thead>
        <tbody id="pnlRows"></tbody>
      </table>
    </div>
    <div class="panel wide">
      <h2>Pool Discovery Coverage</h2>
      <table>
        <thead><tr><th>Source</th><th>Rows / Live</th><th>Promoted</th><th>Breakdown</th><th>Status</th></tr></thead>
        <tbody id="discoveryRows"></tbody>
      </table>
    </div>
    <div class="panel wide">
      <h2>Opportunity DNA</h2>
      <div class="row"><span class="label">Stage artifact</span><span class="value" id="stageArtifact">-</span></div>
      <div class="row"><span class="label">Quote edges</span><span class="value" id="stageEdges">-</span></div>
      <div class="row"><span class="label">Staged for executor truth</span><span class="value" id="stageReady">-</span></div>
      <div style="display:flex; gap:8px; margin:12px 0; flex-wrap:wrap;">
        <button onclick="runRouteStage()">Refresh Opportunity DNA</button>
      </div>
      <table>
        <thead><tr><th>Route</th><th>Hops</th><th>Status</th><th>Raw Δ</th><th>Net Gain</th><th>Calldata</th><th>Signature</th></tr></thead>
        <tbody id="opportunityDnaRows"></tbody>
      </table>
      <pre id="opportunityDnaJson">{}</pre>
    </div>
    <div class="panel wide">
      <h2>Asset State Research</h2>
      <div class="row"><span class="label">Research artifact</span><span class="value" id="assetResearchArtifact">-</span></div>
      <div class="row"><span class="label">Ready assets</span><span class="value" id="assetResearchReady">-</span></div>
      <div style="display:flex; gap:8px; margin:12px 0; flex-wrap:wrap;">
        <button onclick="runAssetResearch()">Refresh Asset Research</button>
      </div>
      <table>
        <thead><tr><th>Asset</th><th>Metadata</th><th>Live State</th><th>Price</th><th>Pools</th><th>Edges</th><th>Blockers</th></tr></thead>
        <tbody id="assetResearchRows"></tbody>
      </table>
      <pre id="assetResearchJson">{}</pre>
    </div>
    <div class="panel wide">
      <h2>Metadata Apprentices</h2>
      <div class="row"><span class="label">Apprentice artifact</span><span class="value" id="metadataApprenticeArtifact">-</span></div>
      <div class="row"><span class="label">Background artifact</span><span class="value" id="metadataBackgroundArtifact">-</span></div>
      <div class="row"><span class="label">Promotion review artifact</span><span class="value" id="metadataPromotionArtifact">-</span></div>
      <div class="row"><span class="label">Processed / promotable</span><span class="value" id="metadataApprenticeCounts">-</span></div>
      <div class="row"><span class="label">Approved / rejected / applied</span><span class="value" id="metadataPromotionCounts">-</span></div>
      <table>
        <thead><tr><th>Asset</th><th>Blockers</th><th>OpenAI</th><th>Gemini</th><th>Grok</th><th>Promotable</th></tr></thead>
        <tbody id="metadataApprenticeRows"></tbody>
      </table>
      <pre id="metadataApprenticeJson">{}</pre>
    </div>
    <div class="panel wide">
      <h2>Liquidation Tracker</h2>
      <div class="row"><span class="label">Block</span><span class="value" id="liqBlock">-</span></div>
      <div class="row"><span class="label">Alerts</span><span class="value" id="liqAlertSummary">-</span></div>
      <table>
        <thead><tr><th>Risk</th><th>Borrower</th><th>Health</th><th>Debt</th><th>Collateral</th><th>Debt USD</th><th>Collateral USD</th></tr></thead>
        <tbody id="liquidationRows"></tbody>
      </table>
    </div>
    <div class="panel wide">
      <h2>Runtime Status</h2>
      <pre id="statusJson">{}</pre>
    </div>
    <div class="panel wide">
      <h2>Production Design Import</h2>
      <table>
        <thead><tr><th>Concept</th><th>Runtime Mapping</th><th>Status</th></tr></thead>
        <tbody id="designRows"></tbody>
      </table>
      <pre id="designPolicy">{}</pre>
    </div>
    <div class="panel wide">
      <h2>Execution Traces</h2>
      <table>
        <thead><tr><th>Stage</th><th>Status</th><th>Trace Hash</th><th>C1 Tx</th><th>C2 Tx</th><th>Parent</th></tr></thead>
        <tbody id="traceRows"></tbody>
      </table>
    </div>
  </section>
</main>
<script>
async function getJson(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(await res.text());
  return await res.json();
}
function fmt(v) {
  const n = Number(v || 0);
  return n.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 4});
}
function compactMap(value) {
  if (!value || typeof value !== 'object') return '-';
  return Object.entries(value).map(([k, v]) => `${k}:${v}`).join('  ');
}
async function refresh() {
  const [runtime, status, pnl] = await Promise.all([
    getJson('/api/runtime/mode'),
    getJson('/api/runtime/status'),
    getJson('/api/pnl')
  ]);
  const liquidations = await getJson('/api/liquidations/tracker?alert_health_factor=1.10&limit=25');
  const design = await getJson('/api/runtime/design');
  const traces = await getJson('/api/traces?limit=20');
  const mode = runtime.mode;
  const armed = !!status.execution_armed;
  runtimeMode.textContent = mode;
  document.getElementById('armed').textContent = armed ? 'YES' : 'NO';
  executor.textContent = status.executor.owner || status.executor.detail || '-';
  modeBadge.className = 'status ' + (armed ? 'armed' : 'drymode');
  modeBadge.querySelector('span:last-child').textContent = armed ? 'LIVE ARMED' : 'DRY RUN';
  executeTop.value = runtime.settings.execute_top;
  canaryMode.checked = !!runtime.settings.canary_mode;
  printTop.value = runtime.settings.print_top_routes;
  interval.value = runtime.settings.interval_seconds;
  statusJson.textContent = JSON.stringify(status, null, 2);
  designPolicy.textContent = JSON.stringify({policy: design.integration_policy, purge_status: design.purge_status}, null, 2);
  designRows.innerHTML = design.accepted_concepts.map(row => {
    return `<tr><td>${row.concept}</td><td>${row.runtime_mapping}</td><td>${row.integration}</td></tr>`;
  }).join('');
  pnlRows.innerHTML = ['dry_run', 'live'].map(book => {
    const row = pnl[book];
    return `<tr><td>${book}</td><td>$${fmt(row.C1.display_pnl_usd)}</td><td>$${fmt(row.C2.display_pnl_usd)}</td><td>$${fmt(row.combined.display_pnl_usd)}</td><td>${row.C1.events}</td><td>${row.C2.events}</td></tr>`;
  }).join('');
  const latestPoolScan = status.latest_pool_scan || {};
  const routeStage = status.route_execution_stage || {};
  const routeStageRows = routeStage.routes || [];
  const routeStageSummary = routeStage.stage || {};
  const routeStageEdges = routeStage.quote_edges || {};
  stageArtifact.textContent = routeStage.available ? (routeStage.path || '-') : 'not generated';
  stageEdges.textContent = `${routeStageEdges.directional_quote_edges || 0} directional, ${routeStageEdges.rate_pairs || 0} pairs`;
  stageReady.textContent = `${routeStageSummary.staged_for_executor_truth || 0} / ${routeStageSummary.attempted || 0}`;
  opportunityDnaRows.innerHTML = routeStageRows.slice(0, 25).map(row => {
    const tx = row.calldata_transmission || {};
    const calldata = tx.buildable ? `${tx.selector || ''} ${tx.calldata_bytes || 0} bytes` : `blocked: ${tx.reason || row.stage || 'not ready'}`;
    return `<tr><td>${(row.path || []).join(' → ')}</td><td>${row.hop_count || ''}</td><td>${row.status || ''}</td><td>$${fmt(row.raw_delta_usd)}</td><td>$${fmt(row.net_gain_usd)}</td><td>${calldata}</td><td>${row.route_signature || ''}</td></tr>`;
  }).join('');
  opportunityDnaJson.textContent = JSON.stringify({
    mode: routeStage.mode,
    execution_policy: routeStage.execution_policy,
    stage: routeStage.stage,
    pre_rank: routeStage.pre_rank,
    top_routes: routeStageRows.slice(0, 5).map(row => ({
      path: row.path,
      pool_sequence: row.pool_sequence,
      protocol_seq: row.protocol_seq,
      net_formula: row.net_formula,
      sizing: row.sizing,
      calldata_transmission: row.calldata_transmission,
      quote_detail: row.quote_detail,
    }))
  }, null, 2);
  const assetResearch = status.asset_state_research || {};
  const assetSummary = assetResearch.summary || {};
  const assetRows = assetResearch.assets || [];
  assetResearchArtifact.textContent = assetResearch.available ? (assetResearch.path || '-') : 'not generated';
  assetResearchReady.textContent = `${assetSummary.ready_for_route_search || 0} / ${assetSummary.asset_count || 0}`;
  assetResearchRows.innerHTML = assetRows.slice(0, 40).map(row => {
    const edgeCount = Number(row.directional_edges_out || 0) + Number(row.directional_edges_in || 0);
    return `<tr><td>${row.symbol}</td><td>${row.metadata_status}</td><td>${row.live_state_status}</td><td>$${fmt(row.price_usd)} ${row.price_source || ''}</td><td>${row.pool_count || 0}</td><td>${edgeCount}</td><td>${(row.execution_blockers || []).slice(0, 3).join(', ')}</td></tr>`;
  }).join('');
  assetResearchJson.textContent = JSON.stringify({
    mode: assetResearch.mode,
    summary: assetResearch.summary,
    blocker_counts: assetResearch.blocker_counts,
    source_policy: assetResearch.source_policy,
    top_ready_assets: assetRows.filter(row => row.route_research_status === 'ready_for_route_search').slice(0, 20)
  }, null, 2);
  const apprentice = status.missing_metadata_apprentices || {};
  const apprenticeBackground = status.missing_metadata_background || {};
  const promotionReview = status.apprentice_metadata_promotion_review || {};
  const apprenticeRows = apprentice.results || [];
  metadataApprenticeArtifact.textContent = apprentice.available ? (apprentice.path || '-') : 'not generated';
  metadataBackgroundArtifact.textContent = apprenticeBackground.available ? (apprenticeBackground.path || '-') : 'not generated';
  metadataPromotionArtifact.textContent = promotionReview.available ? (promotionReview.path || '-') : 'not generated';
  metadataApprenticeCounts.textContent = `${apprentice.processed || apprenticeBackground.processed || 0} / ${apprentice.promotable_count || apprenticeBackground.promotable_count || 0}`;
  metadataPromotionCounts.textContent = `${promotionReview.approved_count || 0} / ${promotionReview.rejected_count || 0} / ${promotionReview.applied_count || 0}`;
  metadataApprenticeRows.innerHTML = apprenticeRows.slice(0, 25).map(row => {
    const runners = row.runners || [];
    const state = name => {
      const hit = runners.find(r => r.runner === name);
      return hit ? hit.status : '-';
    };
    const c = row.case || {};
    return `<tr><td>${c.symbol || ''}</td><td>${(c.blockers || []).slice(0, 2).join(', ')}</td><td>${state('openai_metadata_apprentice')}</td><td>${state('gemini_metadata_apprentice')}</td><td>${state('grok_metadata_apprentice')}</td><td>${(row.promotable_candidates || []).length}</td></tr>`;
  }).join('');
  metadataApprenticeJson.textContent = JSON.stringify({
    provider_status: apprentice.provider_status,
    policy: apprentice.policy,
    background_policy: apprenticeBackground.policy,
    promotion_policy: promotionReview.policy,
    results: apprenticeRows.slice(0, 5)
  }, null, 2);
  const statusDiscovery = status.discovery || {};
  const statusDiscoveryHasData = !!(
    (statusDiscovery.factory || {}).promoted ||
    (statusDiscovery.dynamic_pool_registry || {}).promoted ||
    (statusDiscovery.curve_pool_registry || {}).promoted ||
    (statusDiscovery.polygon_token_list || {}).runtime_added
  );
  const discovery = statusDiscoveryHasData ? statusDiscovery : (latestPoolScan.discovery || {});
  const factory = discovery.factory || {};
  const dynamicPools = discovery.dynamic_pool_registry || {};
  const curvePools = discovery.curve_pool_registry || {};
  const tokenList = discovery.polygon_token_list || {};
  const subgraph = discovery.subgraph_pool_intel || {};
  discoveryRows.innerHTML = [
    ['Factory live', factory.live_candidates || 0, factory.promoted || 0, compactMap(factory.promoted_by_protocol), `anchor=${factory.v2_anchor || '-'}`],
    ['Dynamic JSON', dynamicPools.rows || 0, dynamicPools.promoted || 0, compactMap(dynamicPools.by_protocol), compactMap(dynamicPools.skipped)],
    ['Curve official', curvePools.rows || 0, curvePools.promoted || 0, compactMap(curvePools.by_family), compactMap(curvePools.skipped)],
    ['Polygon token-list', tokenList.unique_candidates || 0, tokenList.runtime_added || 0, (tokenList.base_pair_bias || []).join(', '), `cache=${tokenList.cache || '-'}`],
    ['Subgraph intel', subgraph.candidate_count || 0, subgraph.promoted || 0, compactMap(subgraph.errors), subgraph.execution_policy || '-'],
    ['Latest live scan', latestPoolScan.pools_loaded || 0, (latestPoolScan.liquidity || {}).with_positive_total_executable_liquidity || 0, compactMap(latestPoolScan.protocol_counts), `$${fmt((latestPoolScan.liquidity || {}).sum_positive_usd)}`],
  ].map(row => `<tr><td>${row[0]}</td><td>${row[1]}</td><td>${row[2]}</td><td>${row[3]}</td><td>${row[4]}</td></tr>`).join('');
  liqBlock.textContent = liquidations.block_number || '-';
  liqAlertSummary.textContent = `${liquidations.alert_count || 0} alert(s), ${liquidations.liquidatable_count || 0} liquidatable`;
  liquidationRows.innerHTML = (liquidations.rows || []).map(row => {
    const cls = row.risk_level === 'critical' ? 'risk-critical' : row.risk_level === 'warning' ? 'risk-warning' : 'risk-watch';
    return `<tr><td class="${cls}">${row.status}</td><td>${row.borrower}</td><td>${row.health_factor}</td><td>${row.debt_symbols.join(', ')}</td><td>${row.collateral_symbols.join(', ')}</td><td>$${fmt(row.total_debt_usd)}</td><td>$${fmt(row.total_collateral_usd)}</td></tr>`;
  }).join('');
  traceRows.innerHTML = traces.traces.slice().reverse().map(t => {
    const link = `/api/traces/${t.trace_hash}`;
    return `<tr><td>${t.stage}</td><td>${t.status}</td><td><a href="${link}" target="_blank">${t.trace_hash}</a></td><td>${t.c1_tx_hash || ''}</td><td>${t.c2_tx_hash || ''}</td><td>${t.parent_trace_hash || ''}</td></tr>`;
  }).join('');
}
async function setMode(mode) {
  await getJson('/api/runtime/mode', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({mode, actor:'ui'})});
  await refresh();
}
async function saveSettings() {
  await getJson('/api/runtime/settings', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({execute_top:Number(executeTop.value), canary_mode:canaryMode.checked, print_top_routes:Number(printTop.value), interval_seconds:Number(interval.value)})});
  await refresh();
}
async function resetDry() {
  await getJson('/api/pnl/reset/dry-run', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({actor:'ui'})});
  await refresh();
}
async function resetLive() {
  await getJson('/api/pnl/reset/live', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({actor:'ui', confirm:liveConfirm.value})});
  liveConfirm.value = '';
  await refresh();
}
async function runRouteStage() {
  await getJson('/api/routes/stage/run?principal_usd=10000&hops=2,3,4&stage_limit=25&max_pre_ranked=100', {method:'POST'});
  await refresh();
}
async function runAssetResearch() {
  await getJson('/api/assets/research/run?onchain_metadata=false', {method:'POST'});
  await refresh();
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>"""


def _rpc_status(url: str, *, probe: bool = False) -> dict[str, Any]:
    if not url:
        return {"configured": False, "connected": False}
    if not probe:
        return {"configured": True, "connected": None, "probe": False}
    try:
        from web3 import Web3

        w3 = Web3(Web3.HTTPProvider(url, request_kwargs={"timeout": 3}))
        connected = bool(w3.is_connected())
        chain_id = int(w3.eth.chain_id) if connected else None
        block = int(w3.eth.block_number) if connected else None
        return {
            "configured": True,
            "connected": connected,
            "chain_id": chain_id,
            "chain_ok": chain_id == CHAIN_ID,
            "block": block,
        }
    except Exception as exc:
        return {
            "configured": True,
            "connected": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _latest_pool_scan_report() -> dict[str, Any]:
    if not LIVE_POOL_SCAN_REPORT.exists():
        return {"available": False, "path": str(LIVE_POOL_SCAN_REPORT)}
    try:
        payload = json.loads(LIVE_POOL_SCAN_REPORT.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["path"] = str(LIVE_POOL_SCAN_REPORT)
        return payload
    except Exception as exc:
        return {
            "available": False,
            "path": str(LIVE_POOL_SCAN_REPORT),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _latest_protocol_update_watch_report() -> dict[str, Any]:
    if not PROTOCOL_UPDATE_WATCH_REPORT.exists():
        return {"available": False, "path": str(PROTOCOL_UPDATE_WATCH_REPORT)}
    try:
        payload = json.loads(PROTOCOL_UPDATE_WATCH_REPORT.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["path"] = str(PROTOCOL_UPDATE_WATCH_REPORT)
        return payload
    except Exception as exc:
        return {
            "available": False,
            "path": str(PROTOCOL_UPDATE_WATCH_REPORT),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _latest_route_surface_report() -> dict[str, Any]:
    if not ROUTE_SURFACE_REPORT.exists():
        return {"available": False, "path": str(ROUTE_SURFACE_REPORT)}
    try:
        payload = json.loads(ROUTE_SURFACE_REPORT.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["path"] = str(ROUTE_SURFACE_REPORT)
        return payload
    except Exception as exc:
        return {
            "available": False,
            "path": str(ROUTE_SURFACE_REPORT),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _latest_background_discovery_report() -> dict[str, Any]:
    if not BACKGROUND_DISCOVERY_REPORT.exists():
        return {"available": False, "path": str(BACKGROUND_DISCOVERY_REPORT)}
    try:
        payload = json.loads(BACKGROUND_DISCOVERY_REPORT.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["path"] = str(BACKGROUND_DISCOVERY_REPORT)
        return payload
    except Exception as exc:
        return {
            "available": False,
            "path": str(BACKGROUND_DISCOVERY_REPORT),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _latest_route_execution_stage_report() -> dict[str, Any]:
    if not ROUTE_EXECUTION_STAGE_REPORT.exists():
        return {"available": False, "path": str(ROUTE_EXECUTION_STAGE_REPORT)}
    try:
        payload = json.loads(ROUTE_EXECUTION_STAGE_REPORT.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["path"] = str(ROUTE_EXECUTION_STAGE_REPORT)
        return payload
    except Exception as exc:
        return {
            "available": False,
            "path": str(ROUTE_EXECUTION_STAGE_REPORT),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _latest_asset_state_research_report() -> dict[str, Any]:
    if not ASSET_STATE_RESEARCH_REPORT.exists():
        return {"available": False, "path": str(ASSET_STATE_RESEARCH_REPORT)}
    try:
        payload = json.loads(ASSET_STATE_RESEARCH_REPORT.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["path"] = str(ASSET_STATE_RESEARCH_REPORT)
        return payload
    except Exception as exc:
        return {
            "available": False,
            "path": str(ASSET_STATE_RESEARCH_REPORT),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _latest_missing_metadata_apprentices_report() -> dict[str, Any]:
    if not MISSING_METADATA_APPRENTICES_REPORT.exists():
        return {"available": False, "path": str(MISSING_METADATA_APPRENTICES_REPORT)}
    try:
        payload = json.loads(MISSING_METADATA_APPRENTICES_REPORT.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["path"] = str(MISSING_METADATA_APPRENTICES_REPORT)
        return payload
    except Exception as exc:
        return {
            "available": False,
            "path": str(MISSING_METADATA_APPRENTICES_REPORT),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _latest_missing_metadata_background_report() -> dict[str, Any]:
    if not MISSING_METADATA_BACKGROUND_REPORT.exists():
        return {"available": False, "path": str(MISSING_METADATA_BACKGROUND_REPORT)}
    try:
        payload = json.loads(MISSING_METADATA_BACKGROUND_REPORT.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["path"] = str(MISSING_METADATA_BACKGROUND_REPORT)
        return payload
    except Exception as exc:
        return {
            "available": False,
            "path": str(MISSING_METADATA_BACKGROUND_REPORT),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _latest_apprentice_metadata_promotion_review_report() -> dict[str, Any]:
    if not APPRENTICE_METADATA_PROMOTION_REVIEW_REPORT.exists():
        return {"available": False, "path": str(APPRENTICE_METADATA_PROMOTION_REVIEW_REPORT)}
    try:
        payload = json.loads(APPRENTICE_METADATA_PROMOTION_REVIEW_REPORT.read_text(encoding="utf-8"))
        payload["available"] = True
        payload["path"] = str(APPRENTICE_METADATA_PROMOTION_REVIEW_REPORT)
        return payload
    except Exception as exc:
        return {
            "available": False,
            "path": str(APPRENTICE_METADATA_PROMOTION_REVIEW_REPORT),
            "error": f"{type(exc).__name__}: {exc}",
        }


@app.get("/health")
def health() -> dict[str, Any]:
    redis_ok, redis_detail = redis_status()
    return {
        "ok": True,
        "service": "omega-api",
        "chain_id": CHAIN_ID,
        "redis": {"ok": redis_ok, "detail": redis_detail, "url": REDIS_URL},
    }


@app.get("/", response_class=HTMLResponse)
def runtime_ui() -> str:
    return UI_HTML


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/runtime/status")
def runtime_status(probe: bool = Query(default=False)) -> dict[str, Any]:
    rpc_connected = rpc_layer.connect(http_urls=[HTTP_URL], wss_url="", prefer_wss=False) if probe else bool(rpc_layer.w3)
    code_ok, code_detail = executor_code_status() if probe and rpc_connected else (False, "probe_disabled" if not probe else "rpc_unavailable")
    redis_ok, redis_detail = redis_status()
    runtime = get_runtime_state()
    guards = execution_guard_status(probe=probe)
    return {
        "chain_id": CHAIN_ID,
        "execution_mode": runtime["mode"],
        "runtime": runtime,
        "http_rpc": _rpc_status(HTTP_URL, probe=probe),
        "wss_rpc": {"configured": bool(WSS_URL), "url": WSS_URL},
        "broadcast_rpc": _rpc_status(BROADCAST_RPC_URL, probe=probe),
        "fork_sim_rpc": _rpc_status(FORK_SIM_RPC_URL, probe=probe),
        "redis": {"ok": redis_ok, "detail": redis_detail},
        "transport": transport_status(probe_if_stale=probe),
        "sourced_layers": sourced_layer_status(),
        "discovery": {
            "factory": rpc_layer.FACTORY_DISCOVERY_STATS,
            "polygon_token_list": rpc_layer.POLYGON_TOKEN_LIST_DISCOVERY_STATS,
            "dynamic_pool_registry": rpc_layer.DYNAMIC_POOL_REGISTRY_STATS,
            "curve_pool_registry": rpc_layer.CURVE_POOL_REGISTRY_STATS,
            "subgraph_pool_intel": rpc_layer.SUBGRAPH_POOL_INTEL_STATS,
        },
        "latest_pool_scan": _latest_pool_scan_report(),
        "protocol_update_watch": _latest_protocol_update_watch_report(),
        "route_surface": _latest_route_surface_report(),
        "route_execution_stage": _latest_route_execution_stage_report(),
        "asset_state_research": _latest_asset_state_research_report(),
        "missing_metadata_apprentices": _latest_missing_metadata_apprentices_report(),
        "missing_metadata_background": _latest_missing_metadata_background_report(),
        "apprentice_metadata_promotion_review": _latest_apprentice_metadata_promotion_review_report(),
        "background_discovery": _latest_background_discovery_report(),
        "indexer": _indexer_status(),
        "rust_engine": _rust_engine_status(),
        "executor": {
            "code_ok": code_ok,
            "detail": code_detail,
            "owner": executor_owner() if probe and rpc_connected else "",
        },
        "guards": guards,
        "execution_armed": all(guards.values()),
    }


@app.get("/api/protocol/watch/status")
def protocol_watch_status() -> dict[str, Any]:
    return _latest_protocol_update_watch_report()


@app.get("/api/routes/surface/status")
def route_surface_status() -> dict[str, Any]:
    return _latest_route_surface_report()


@app.get("/api/routes/stage/status")
def route_execution_stage_status() -> dict[str, Any]:
    return _latest_route_execution_stage_report()


@app.get("/api/assets/research/status")
def asset_state_research_status() -> dict[str, Any]:
    return _latest_asset_state_research_report()


@app.get("/api/assets/metadata-apprentices/status")
def missing_metadata_apprentices_status() -> dict[str, Any]:
    return _latest_missing_metadata_apprentices_report()


@app.get("/api/assets/metadata-background/status")
def missing_metadata_background_status() -> dict[str, Any]:
    return _latest_missing_metadata_background_report()


@app.get("/api/assets/metadata-promotions/status")
def apprentice_metadata_promotions_status() -> dict[str, Any]:
    return _latest_apprentice_metadata_promotion_review_report()


@app.post("/api/assets/metadata-promotions/review")
def apprentice_metadata_promotions_review(
    _: None = Depends(require_frontend_write_token),
    apply: bool = Query(default=True),
    max_promotions: int = Query(default=50, ge=0, le=5000),
) -> dict[str, Any]:
    try:
        from .apprentice_metadata_registry import review_apprentice_metadata_promotions

        return review_apprentice_metadata_promotions(apply=apply, max_promotions=max_promotions)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/assets/metadata-apprentices/run")
def missing_metadata_apprentices_run(
    _: None = Depends(require_frontend_write_token),
    limit: int = Query(default=25, ge=0, le=250),
    search_limit: int = Query(default=5, ge=1, le=20),
    include_price_missing: bool = Query(default=True),
) -> dict[str, Any]:
    try:
        from .missing_metadata_apprentices import run_missing_metadata_apprentices

        return run_missing_metadata_apprentices(
            limit=limit,
            search_limit=search_limit,
            include_price_missing=include_price_missing,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/assets/research/run")
def asset_state_research_run(
    _: None = Depends(require_frontend_write_token),
    onchain_metadata: bool = Query(default=False),
    onchain_limit: int = Query(default=0, ge=0, le=5000),
) -> dict[str, Any]:
    try:
        from .asset_state_research import run_once

        return run_once(onchain_metadata=onchain_metadata, onchain_limit=onchain_limit)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


@app.post("/api/routes/stage/run")
def route_execution_stage_run(
    _: None = Depends(require_frontend_write_token),
    principal_usd: str = Query(default="10000"),
    hops: str = Query(default="2,3,4"),
    stage_limit: int = Query(default=25, ge=0, le=250),
    max_quote_options_per_pair: int = Query(default=0, ge=0, le=100),
    max_token_paths: int = Query(default=0, ge=0, le=200000),
    max_pre_ranked: int = Query(default=100, ge=0, le=10000),
    slippage_bps: str = Query(default="0"),
) -> dict[str, Any]:
    try:
        from .route_execution_stager import _parse_hops, run_once

        return run_once(
            principal_usd=Decimal(str(principal_usd)),
            hops=_parse_hops(hops),
            stage_limit=stage_limit,
            max_quote_options_per_pair=max_quote_options_per_pair,
            max_token_paths=max_token_paths,
            max_pre_ranked=max_pre_ranked,
            slippage_bps=Decimal(str(slippage_bps)),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")


@app.get("/api/discovery/background/status")
def background_discovery_status() -> dict[str, Any]:
    return _latest_background_discovery_report()


def _indexer_status() -> dict[str, Any]:
    if not ENABLE_INDEXER_STATE_READS:
        return {"enabled": False}
    try:
        from .indexer_state import indexer_status

        return indexer_status()
    except Exception as exc:
        return {"enabled": True, "healthy": False, "error": f"{type(exc).__name__}: {exc}"}


def _rust_engine_status() -> dict[str, Any]:
    try:
        binary = assert_rust_engine_ready()
        return {"required": True, "ready": True, "binary": str(binary)}
    except Exception as exc:
        return {"required": True, "ready": False, "error": f"{type(exc).__name__}: {exc}"}


def _usd_value(symbol: str, amount: Decimal) -> Decimal:
    try:
        return amount * token_price_usd(symbol)
    except (PriceUnavailable, ArithmeticError):
        return Decimal("0")


def _risk_level(health_factor: Decimal) -> str:
    if health_factor < Decimal("1"):
        return "critical"
    if health_factor <= Decimal("1.05"):
        return "warning"
    return "watch"


def _health_status(health_factor: Decimal) -> str:
    if health_factor < Decimal("1"):
        return "LIQUIDATABLE"
    if health_factor <= Decimal("1.05"):
        return "NEAR_THRESHOLD"
    return "WATCH"


@app.get("/api/liquidations/tracker")
def liquidation_tracker(
    alert_health_factor: str = Query(default="1.10", description="Alert when Aave health factor is at or below this value"),
    limit: int = Query(default=50, ge=1, le=250),
) -> dict[str, Any]:
    try:
        alert_hf = max(Decimal("1"), Decimal(str(alert_health_factor)))
    except Exception:
        raise HTTPException(status_code=400, detail="alert_health_factor must be a decimal >= 1")

    if rpc_layer.w3 is None or not rpc_layer.RPC_LIVE:
        if not rpc_layer.connect(http_urls=[HTTP_URL], wss_url="", prefer_wss=False):
            return {
                "ok": False,
                "healthy": False,
                "error": "live RPC unavailable",
                "alert_health_factor": str(alert_hf),
                "rows": [],
            }

    try:
        scanner = AaveLiquidationScanner()
        block_number = int(scanner.w3.eth.block_number)
        risks = scanner.reserve_risks(block_number)
        borrowers = scanner.discover_recent_borrowers(block_number)
        rows: list[dict[str, Any]] = []
        scan_errors: list[str] = []

        for borrower in borrowers:
            try:
                health = scanner.account_health(borrower, block_number)
                if health > alert_hf:
                    continue
                positions = scanner.borrower_positions(borrower, risks, block_number)
                debt_symbols = sorted({p.symbol for p in positions if p.raw_debt > 0})
                collateral_symbols = sorted({
                    p.symbol for p in positions
                    if p.raw_collateral > 0 and p.usage_as_collateral
                })
                total_debt_usd = sum((_usd_value(p.symbol, p.normalized_debt()) for p in positions), Decimal("0"))
                total_collateral_usd = sum(
                    (_usd_value(p.symbol, p.normalized_collateral()) for p in positions if p.usage_as_collateral),
                    Decimal("0"),
                )
                rows.append({
                    "borrower": borrower,
                    "block_number": block_number,
                    "health_factor": str(health),
                    "status": _health_status(health),
                    "risk_level": _risk_level(health),
                    "debt_symbols": debt_symbols,
                    "collateral_symbols": collateral_symbols,
                    "total_debt_usd": str(total_debt_usd),
                    "total_collateral_usd": str(total_collateral_usd),
                    "position_count": len(positions),
                })
            except Exception as exc:
                scan_errors.append(f"{borrower}: {type(exc).__name__}: {exc}")

        rows.sort(key=lambda row: Decimal(str(row["health_factor"])))
        rows = rows[:limit]
        return {
            "ok": True,
            "healthy": True,
            "authority": "SCANNER_ONLY",
            "chain_id": CHAIN_ID,
            "aave_pool": scanner.aave_pool_address,
            "block_number": block_number,
            "alert_health_factor": str(alert_hf),
            "borrowers_scanned": len(borrowers),
            "alert_count": len(rows),
            "liquidatable_count": sum(1 for row in rows if row["status"] == "LIQUIDATABLE"),
            "near_threshold_count": sum(1 for row in rows if row["status"] == "NEAR_THRESHOLD"),
            "rows": rows,
            "errors": scan_errors[:20],
        }
    except Exception as exc:
        return {
            "ok": False,
            "healthy": False,
            "error": f"{type(exc).__name__}: {exc}",
            "alert_health_factor": str(alert_hf),
            "rows": [],
        }


@app.get("/api/transport/status")
def transport_status_view(probe: bool = Query(default=False)) -> dict[str, Any]:
    return transport_status(probe_if_stale=probe)


@app.get("/api/oracles/prices")
def oracle_prices(force: bool = Query(default=False)) -> dict[str, Any]:
    try:
        refresh_token_prices(force=force)
        rows = [
            {
                "symbol": symbol,
                "price_usd": str(price),
                "source": TOKEN_USD_SOURCE.get(symbol, "unknown"),
            }
            for symbol, price in sorted(TOKEN_USD_PRICE.items())
        ]
        return {
            "ok": True,
            "healthy": bool(rows),
            "chain_id": CHAIN_ID,
            "count": len(rows),
            "prices": rows,
        }
    except Exception as exc:
        return {
            "ok": False,
            "healthy": False,
            "chain_id": CHAIN_ID,
            "error": f"{type(exc).__name__}: {exc}",
            "prices": [],
        }


@app.get("/api/sourced-layers/status")
def sourced_layers_status_view() -> dict[str, Any]:
    return sourced_layer_status()


@app.get("/api/frontend/manifest")
def frontend_manifest() -> dict[str, Any]:
    return {
        "service": "omega-api",
        "chain_id": CHAIN_ID,
        "write_auth_required": API_FRONTEND_TOKEN_REQUIRED,
        "cors_origins": API_CORS_ORIGINS,
        "read_endpoints": [
            "/health",
            "/api/runtime/status",
            "/api/runtime/mode",
            "/api/runtime/design",
            "/api/transport/status",
            "/api/sourced-layers/status",
            "/api/oracles/prices",
            "/api/pnl",
            "/api/liquidations/tracker",
            "/api/traces",
            "/api/proofs/session-signer",
            "/api/proofs/runtime-alignment",
            "/api/finalizer/report",
            "/api/ml/status",
            "/api/pm2/manifest",
            "/api/assets/metadata-background/status",
            "/api/assets/metadata-promotions/status",
        ],
        "write_endpoints": [
            "/api/runtime/mode",
            "/api/runtime/settings",
            "/api/proofs/session-signer/run",
            "/api/proofs/runtime-alignment/run",
            "/api/pipeline/validate",
            "/api/pnl/reset/dry-run",
            "/api/pnl/reset/live",
            "/api/assets/metadata-promotions/review",
        ],
        "integration_policy": {
            "frontend_executes_transactions": False,
            "frontend_reads_private_keys": False,
            "backend_preserves_execution_gates": True,
            "live_requires_backend_exact_call_and_broadcast_guards": True,
        },
    }

@app.get("/api/runtime/design")
def runtime_design_view() -> dict[str, Any]:
    return live_design_status()


@app.get("/api/finalizer/report")
def finalizer_report_view(probe: bool = Query(default=False)) -> dict[str, Any]:
    return finalizer_report(probe=probe)


@app.get("/api/ml/status")
def ml_status_view() -> dict[str, Any]:
    return ml_alpha_status()


@app.get("/api/proofs/session-signer")
def session_signer_proof_view() -> dict[str, Any]:
    return load_latest_proof()


@app.post("/api/proofs/session-signer/run", dependencies=[Depends(require_frontend_write_token)])
def session_signer_proof_run(samples: int = Query(default=5, ge=1, le=25)) -> dict[str, Any]:
    return run_session_signer_proof(samples=samples)


@app.get("/api/proofs/runtime-alignment")
def runtime_alignment_view() -> dict[str, Any]:
    return load_latest_alignment()


@app.post("/api/proofs/runtime-alignment/run", dependencies=[Depends(require_frontend_write_token)])
def runtime_alignment_run(probe: bool = Query(default=False)) -> dict[str, Any]:
    return runtime_alignment_status(probe=probe)


@app.get("/api/runtime/mode")
def runtime_mode_view() -> dict[str, Any]:
    return get_runtime_state()


@app.post("/api/runtime/mode", dependencies=[Depends(require_frontend_write_token)])
def runtime_mode_update(req: RuntimeModeRequest) -> dict[str, Any]:
    return set_runtime_mode(req.mode, actor=req.actor)


@app.post("/api/runtime/settings", dependencies=[Depends(require_frontend_write_token)])
def runtime_settings_update(req: RuntimeSettingsRequest) -> dict[str, Any]:
    raw = req.model_dump() if hasattr(req, "model_dump") else req.dict()
    payload = {k: v for k, v in raw.items() if v is not None}
    return update_runtime_settings(payload, actor="ui")


@app.get("/api/pnl")
def pnl_view() -> dict[str, Any]:
    return current_snapshot()


@app.get("/api/traces")
def trace_list(
    limit: int = Query(default=50, ge=1, le=500),
    stage: str = Query(default="", pattern="^(|C1|C2|LIQUIDATION)$"),
) -> dict[str, Any]:
    traces = recent_traces(limit=limit, stage=stage)
    return {"count": len(traces), "traces": traces}


@app.get("/api/traces/{trace_hash}")
def trace_detail(trace_hash: str) -> dict[str, Any]:
    trace = get_trace(trace_hash)
    if trace is None:
        raise HTTPException(status_code=404, detail="trace not found")
    return trace


@app.get("/api/traces/by-tx/{tx_hash}")
def trace_by_tx(tx_hash: str) -> dict[str, Any]:
    normalized = tx_hash.strip().lower()
    matches = [
        trace for trace in recent_traces(limit=500)
        if str(trace.get("c1_tx_hash", "")).lower() == normalized
        or str(trace.get("c2_tx_hash", "")).lower() == normalized
    ]
    return {"count": len(matches), "traces": matches}


@app.post("/api/pnl/reset/dry-run", dependencies=[Depends(require_frontend_write_token)])
def pnl_reset_dry_run(req: ResetRequest) -> dict[str, Any]:
    event = record_reset("dry_run", actor=req.actor)
    return {"ok": True, "event": event, "pnl": current_snapshot()}


@app.post("/api/pnl/reset/live", dependencies=[Depends(require_frontend_write_token)])
def pnl_reset_live(req: ResetRequest) -> dict[str, Any]:
    try:
        event = record_reset("live", actor=req.actor, confirm=req.confirm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "required_confirm": LIVE_RESET_CONFIRM, "event": event, "pnl": current_snapshot()}


@app.post("/api/pipeline/validate", dependencies=[Depends(require_frontend_write_token)])
async def validate_pipeline(
    rpc_url: str = Query(default="", description="Override RPC URL; defaults to configured HTTP_URL"),
    exact_rpc_url: str = Query(default="", description="Override exact-call RPC URL for executor truth checks"),
    no_eth_call: bool = Query(default=True),
    max_opps: int = Query(default=50, ge=1, le=200),
    max_size_rungs: int = Query(default=7, ge=1, le=25),
    max_exact_calls: int = Query(default=80, ge=1, le=500),
    timeout_seconds: int = Query(default=300, ge=30, le=1200),
) -> dict[str, Any]:
    args = [
        sys.executable,
        "-m",
        "omega_v5.pipeline_validation",
        "--rpc-url",
        rpc_url or HTTP_URL,
        "--max-opps",
        str(max_opps),
    ]
    if no_eth_call:
        args.append("--no-eth-call")

    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
            env={
                **os.environ.copy(),
                **(
                    {
                        "EXACT_CALL_RPC_URL": exact_rpc_url,
                        "FORK_SIM_RPC_URL": exact_rpc_url,
                    }
                    if exact_rpc_url
                    else {}
                ),
                "OMEGA_TRUTH_MAX_SIZE_RUNGS": str(max_size_rungs),
                "OMEGA_TRUTH_MAX_EXACT_CALLS": str(max_exact_calls),
            },
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"ok": False, "exit_code": None, "timed_out": True, "output": "", "stdout": ""}

    output = stdout.decode("utf-8", errors="replace")
    tail = output[-20000:]
    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "timed_out": False,
        "output": tail,
        "stdout": tail,
    }


@app.get("/api/pm2/manifest")
def pm2_manifest() -> dict[str, Any]:
    return {
        "apps": [
            "omega-redis",
            "omega-anvil-fork",
            "omega-dodo-rpc-provider",
            "omega-api",
            "omega-engine",
        ],
        "ports": {
            "redis": 6379,
            "anvil": 8545,
            "dodo_rpc_provider": 3000,
            "api": API_PORT,
        },
        "boot_script": "scripts/pm2/boot_all.ps1",
        "stop_script": "scripts/pm2/stop_all.ps1",
    }
