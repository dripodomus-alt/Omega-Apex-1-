/**
 * bootAudit.ts
 *
 * Pre-flight deployment checklist executed once at server boot.
 * Validates environment variables, protocol addresses, and optional
 * service connectivity (Redis, Cloud SQL). Prints a structured
 * PASS / WARN / FAIL report to stdout and throws if any critical
 * check fails, preventing a bad deploy from silently serving traffic.
 */

// ─── ANSI colour helpers (work in any POSIX terminal / Cloud Run logs) ────────
const C = {
  reset: '\x1b[0m',
  bold:  '\x1b[1m',
  green: '\x1b[32m',
  red:   '\x1b[31m',
  yellow:'\x1b[33m',
  cyan:  '\x1b[36m',
};

type CheckLevel = 'CRITICAL' | 'WARN' | 'INFO';

interface CheckResult {
  label:   string;
  status:  'PASS' | 'FAIL' | 'WARN' | 'SKIP';
  message: string;
  level:   CheckLevel;
}

const results: CheckResult[] = [];

function check(
  label: string,
  pass: boolean,
  passMsg: string,
  failMsg: string,
  level: CheckLevel = 'CRITICAL',
): CheckResult {
  const r: CheckResult = {
    label,
    status:  pass ? 'PASS' : (level === 'WARN' ? 'WARN' : 'FAIL'),
    message: pass ? passMsg : failMsg,
    level,
  };
  results.push(r);
  return r;
}

function warn(label: string, cond: boolean, msg: string): CheckResult {
  return check(label, cond, msg, msg, 'WARN');
}

// ─── Individual checks ────────────────────────────────────────────────────────

function checkCriticalEnvVars(): void {
  const required = [
    'GEMINI_API_KEY',
    'OMEGA_RUNTIME_MODE',
    'EXECUTION_MODE',
  ] as const;

  for (const key of required) {
    check(
      `ENV:${key}`,
      !!process.env[key],
      'present',
      'MISSING — server will not function correctly',
    );
  }
}

function checkWalletEnvVars(): void {
  const walletKeys = [
    'BOT_ADDRESS',
    'BOT_PROFIT_RECEIVER',
    'EXECUTOR_WALLET',
  ];
  for (const key of walletKeys) {
    const val = process.env[key] ?? '';
    const isEthAddr = /^0x[0-9a-fA-F]{40}$/.test(val);
    check(
      `WALLET:${key}`,
      isEthAddr,
      val,
      `invalid or missing — got "${val}"`,
      'CRITICAL',
    );
  }
}

function checkContractAddresses(): void {
  const contracts: Record<string, string | undefined> = {
    EXECUTOR_CONTRACT_ADDR:     process.env.EXECUTOR_CONTRACT_ADDR,
    LIQUIDATION_EXECUTOR_ADDRESS: process.env.LIQUIDATION_EXECUTOR_ADDRESS,
    C1_ARB_EXECUTOR_ADDRESS:    process.env.C1_ARB_EXECUTOR_ADDRESS,
  };
  for (const [key, val] of Object.entries(contracts)) {
    const isEthAddr = /^0x[0-9a-fA-F]{40}$/.test(val ?? '');
    check(
      `CONTRACT:${key}`,
      isEthAddr,
      val ?? '',
      `invalid or missing — got "${val}"`,
      'CRITICAL',
    );
  }
}

function checkRpcUrls(): void {
  const rpcKeys = [
    'POLYGON_RPC_URL',
    'POLYGON_WSS_URL',
  ];
  for (const key of rpcKeys) {
    const val = process.env[key] ?? '';
    const valid = val.startsWith('https://') || val.startsWith('wss://');
    check(
      `RPC:${key}`,
      valid,
      val,
      `missing or malformed URL — got "${val}"`,
      'WARN',
    );
  }
}

function checkRedisConfig(): void {
  const url = process.env.REDIS_URL ?? '';
  const configured = url.startsWith('redis://') || url.startsWith('rediss://');
  warn(
    'REDIS_URL',
    configured,
    configured
      ? `configured — ${url.replace(/:\/\/[^@]*@/, '://***@')}`
      : 'not configured — Redis endpoints will return 503',
  );
}

function checkCloudSqlConfig(): void {
  const keys = ['CLOUD_SQL_HOST', 'CLOUD_SQL_DATABASE', 'CLOUD_SQL_USER', 'CLOUD_SQL_PASSWORD'];
  const allPresent = keys.every((k) => !!process.env[k]);
  warn(
    'CLOUD_SQL_CONFIG',
    allPresent,
    allPresent
      ? `configured — ${process.env.CLOUD_SQL_DATABASE}@${process.env.CLOUD_SQL_HOST}`
      : `not fully configured (missing: ${keys.filter((k) => !process.env[k]).join(', ')}) — SQL endpoints will return 503`,
  );
}

function checkLiveTradingGuard(): void {
  const liveMode    = process.env.EXECUTION_MODE === 'live' || process.env.LIVE_TRADING === '1';
  const hasConsent  = process.env.CONFIRM_MAINNET_EXECUTION === 'I_UNDERSTAND_POLYGON_MAINNET_RISK';
  if (liveMode) {
    check(
      'LIVE_TRADING_CONSENT',
      hasConsent,
      'CONFIRM_MAINNET_EXECUTION gate satisfied',
      'LIVE_TRADING is enabled but CONFIRM_MAINNET_EXECUTION consent string is missing — refusing to start',
      'CRITICAL',
    );
  } else {
    results.push({ label: 'LIVE_TRADING_CONSENT', status: 'SKIP', message: 'simulation mode', level: 'INFO' });
  }
}

function checkPolygonscanApiKey(): void {
  const key = process.env.POLYGONSCAN_API_KEY ?? '';
  warn('POLYGONSCAN_API_KEY', key.length > 0, key.length > 0 ? 'present' : 'missing — on-chain verification calls will fail');
}

// ─── Report renderer ──────────────────────────────────────────────────────────

function renderReport(): void {
  const line = '─'.repeat(72);
  const pad  = (s: string, n: number) => s.padEnd(n);

  console.log(`\n${C.bold}${C.cyan}╔══ OMEGA V5 BOOT AUDIT ══════════════════════════════════════════════╗${C.reset}`);
  console.log(`${C.bold}${C.cyan}║  Deployment pre-flight checklist @ ${new Date().toISOString()}  ║${C.reset}`);
  console.log(`${C.cyan}${line}${C.reset}\n`);

  for (const r of results) {
    let icon: string;
    let colour: string;
    switch (r.status) {
      case 'PASS': icon = '✔'; colour = C.green;  break;
      case 'WARN': icon = '⚠'; colour = C.yellow; break;
      case 'FAIL': icon = '✘'; colour = C.red;    break;
      default:     icon = '–'; colour = C.reset;  break;
    }
    console.log(
      `  ${colour}${icon}${C.reset}  ${C.bold}${pad(r.label, 32)}${C.reset}` +
      `${colour}${r.status}${C.reset}  ${r.message}`,
    );
  }

  const failures = results.filter((r) => r.status === 'FAIL');
  const warns    = results.filter((r) => r.status === 'WARN');
  const passes   = results.filter((r) => r.status === 'PASS');

  console.log(`\n${C.cyan}${line}${C.reset}`);
  console.log(
    `  ${C.bold}Summary:${C.reset}  ` +
    `${C.green}${passes.length} PASS${C.reset}  ` +
    `${C.yellow}${warns.length} WARN${C.reset}  ` +
    `${C.red}${failures.length} FAIL${C.reset}`,
  );
  console.log(`${C.bold}${C.cyan}╚══════════════════════════════════════════════════════════════════════╝${C.reset}\n`);
}

// ─── Public entry point ───────────────────────────────────────────────────────

export function runBootAudit(): void {
  checkCriticalEnvVars();
  checkWalletEnvVars();
  checkContractAddresses();
  checkRpcUrls();
  checkRedisConfig();
  checkCloudSqlConfig();
  checkLiveTradingGuard();
  checkPolygonscanApiKey();

  renderReport();

  const criticalFailures = results.filter((r) => r.status === 'FAIL' && r.level === 'CRITICAL');
  if (criticalFailures.length > 0) {
    throw new Error(
      `[BOOT AUDIT] ${criticalFailures.length} critical check(s) failed — ` +
      criticalFailures.map((r) => r.label).join(', ') +
      '. Fix the above issues and restart.',
    );
  }
}
