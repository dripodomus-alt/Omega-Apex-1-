# Apex-Omega Docker / Cloud / Mobile Deployment

This deployment runs the complete Apex-Omega runtime as a containerized cloud stack:

- `omega-api` FastAPI dashboard/API on port `8080`
- `omega-engine` autonomous arbitrage loop through executor-truth gates
- `omega-liquidation-watcher` Aave liquidation watcher and atomic liquidation exact-call lane
- `omega-anvil-fork` local Foundry/Anvil Polygon fork on port `8545`
- `omega-dodo-rpc-provider` endpoint metadata provider on port `3000`
- Redis transport/cache as a dedicated Compose service
- Rust Bellman-Ford engine compiled into the image

## Local Docker Boot

```bash
docker compose build
docker compose up -d redis omega
docker compose logs -f omega
```

Open:

```text
http://127.0.0.1:8080/
http://127.0.0.1:8080/api/runtime/status
http://127.0.0.1:8080/api/pnl
http://127.0.0.1:8080/api/liquidations/tracker
```

## Blank Ubuntu Cloud Boot

From your local machine, if the repo is already available through Git:

```bash
ssh -t user@<server-ip> "curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/infra/cloud/prep_instance_2.0.sh | sudo APEX_REPO_URL=https://github.com/<owner>/<repo>.git APEX_REPO_BRANCH=<branch> bash"
```

If you uploaded the repo to `/opt/apex-omega` manually:

```bash
ssh user@<server-ip>
cd /opt/apex-omega
sudo bash infra/cloud/prep_instance_2.0.sh
```

After boot:

```bash
cd /opt/apex-omega
docker compose ps
docker compose logs -f omega
```

## Mobile Viewing

Direct VM access:

```text
http://<server-ip>:8080/
```

The root dashboard is served by `omega_v5.api` and includes runtime mode, PnL, transport, traces, and liquidation tracker surfaces.

For safer mobile access without exposing the VM directly, use the included Cloudflare Tunnel profile:

```bash
cd /opt/apex-omega
printf '\nCLOUDFLARED_TOKEN=<your-token>\n' | sudo tee -a .env
docker compose --profile mobile-tunnel up -d cloudflared
docker compose logs -f cloudflared
```

## Live Safety Model

The Docker stack can run with `EXECUTION_MODE=live`, but transactions still fail closed unless these gates are true:

- runtime mode is `live`
- Polygon read RPC is healthy
- exact-call RPC is healthy
- writable broadcast RPC is healthy
- executor private key is valid
- executor/liquidation target addresses are configured
- payload construction succeeds
- executor exact-call passes at latest block

No route or liquidation should be broadcast from this stack unless its exact-call proof passes first.

## AI Studio Frontend Integration

Use the cloud dashboard/API URL as the backend origin in the AI Studio app:

```text
https://<your-domain-or-tunnel>/api/frontend/manifest
https://<your-domain-or-tunnel>/api/runtime/status
https://<your-domain-or-tunnel>/api/pnl
https://<your-domain-or-tunnel>/api/traces
https://<your-domain-or-tunnel>/api/liquidations/tracker
```

Keep execution logic in the backend. The frontend should only call runtime/control APIs and display traces, PnL, and liquidation watcher state.
