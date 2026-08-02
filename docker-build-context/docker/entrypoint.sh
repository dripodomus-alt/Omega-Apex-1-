#!/bin/sh
set -eu

START_FOUNDRY_FORK=${START_FOUNDRY_FORK:-false}
FORK_RPC_URL=${FORK_RPC_URL:-http://127.0.0.1:8545}
FORK_SIM_RPC_URL=${FORK_SIM_RPC_URL:-$FORK_RPC_URL}
CHAIN_ID=${CHAIN_ID:-137}
PORT=${PORT:-8080}

if [ "$START_FOUNDRY_FORK" = "true" ] && [ -n "${FORK_UPSTREAM_RPC_URL:-}" ]; then
  if command -v anvil >/dev/null 2>&1; then
    echo "Starting local Anvil fork for Cloud Run runtime"
    export FORK_RPC_URL
    export FORK_SIM_RPC_URL
    anvil --fork-url "$FORK_UPSTREAM_RPC_URL" --chain-id "$CHAIN_ID" --host 0.0.0.0 --port 8545 >/tmp/anvil.log 2>&1 &

    for _ in $(seq 1 30); do
      if curl -fsS http://127.0.0.1:8545 >/dev/null 2>&1; then
        echo "Anvil fork is ready"
        break
      fi
      sleep 1
    done
  else
    echo "anvil not installed; skipping fork startup"
  fi
else
  echo "Foundry fork startup disabled or upstream RPC missing"
fi

exec uvicorn omega_v5.api:app --host 0.0.0.0 --port "$PORT"
