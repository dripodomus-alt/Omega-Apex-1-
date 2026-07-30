// ==============================================================================
// ecosystem.config.js — PM2 configuration for the Omega V5 ecosystem.
//
// NOTE: PM2 on Windows has known issues (bash interpreter, daemon permissions).
// Prefer direct Python execution for local development on Windows.
//
// Usage:
//   pm2 start ecosystem.config.js
//   pm2 stop all
//   pm2 delete all
// ==============================================================================

require('dotenv').config();

const isWindows = process.platform === 'win32';
const PYTHON_INTERPRETER = 'python';

module.exports = {
  apps: [
    {
      name: 'anvil-fork',
      script: 'anvil',
      args: `--fork-url ${process.env.FORK_UPSTREAM_RPC_URL || process.env.HTTP_URL} --port 8545 --silent`,
      // 'bash' interpreter is unreliable on Windows. Use native or Docker instead.
      interpreter: isWindows ? 'cmd' : 'bash',
      watch: false,
      autorestart: true,
      restart_delay: 5000,
    },
    {
      name: 'redis',
      script: 'redis-server',
      args: '--port 6379',
      interpreter: isWindows ? 'cmd' : 'bash',
      watch: false,
      autorestart: true,
      restart_delay: 5000,
    },
    {
      name: 'omega-api',
      script: 'uvicorn',
      args: `omega_v5.api:app --host ${process.env.API_HOST || '127.0.0.1'} --port ${process.env.API_PORT || 8080}`,
      interpreter: PYTHON_INTERPRETER,
      watch: false,
      autorestart: true,
      restart_delay: 1000,
      env: {
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8',
      },
    },
    {
      name: 'omega-dashboard',
      script: 'npm',
      args: 'run dev',
      watch: false,
      autorestart: true,
      restart_delay: 2000,
      env: {
        HOST: process.env.DASHBOARD_HOST || '0.0.0.0',
        PORT: process.env.DASHBOARD_PORT || '3000',
        APEX_API_PROXY_TARGET: process.env.APEX_API_PROXY_TARGET || 'http://127.0.0.1:8080',
        REQUIRE_FORK_SIM_BEFORE_SUBMIT: process.env.REQUIRE_FORK_SIM_BEFORE_SUBMIT || 'true',
        REQUIRE_CHAIN_ID_MATCH: process.env.REQUIRE_CHAIN_ID_MATCH || 'true',
      },
    },    {
      name: 'omega-engine',
      script: PYTHON_INTERPRETER,
      args: '-m omega_v5.main',
      watch: false,
      autorestart: true,
      restart_delay: 2000,
      env: {
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8',
      },
    },
    {
      name: 'omega-liquidation-watcher',
      script: PYTHON_INTERPRETER,
      args: '-m omega_v5.liquidation_watcher',
      watch: false,
      autorestart: true,
      restart_delay: 10000,
      env: {
        PYTHONUTF8: '1',
        PYTHONIOENCODING: 'utf-8',
      },
    },
  ],
};

