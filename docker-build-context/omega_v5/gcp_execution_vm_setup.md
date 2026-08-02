# Secure Execution VM Setup on Google Cloud

This guide provides a production-ready, secure method for setting up a Google Cloud VM to run the Omega V5 execution engine. This VM is designed to be a secure, isolated environment for handling your private keys and executing live trades.

**Architectural Principle:** The execution engine runs on a private VM with minimal exposure. The public-facing dashboard and API run separately on Cloud Run. This separation is a critical security boundary.

## 1. Go-Live Operational Plan

The entire GCP infrastructure setup process is automated by the `provision_secure_vm.sh` script. This script is idempotent, meaning it can be run multiple times without causing errors. It will:

1.  Create a dedicated IAM Service Account with least-privilege roles.
2.  Create a secret in Google Secret Manager to hold your private key.
3.  Prompt you to securely enter your `EXECUTOR_PRIVATE_KEY`.
4.  Create a hardened firewall rule to only allow SSH via Google's secure IAP.
5.  Create the `e2-standard-2` Compute Engine VM instance.
6.  Automatically SSH into the new VM and run the final setup commands (clone repo, install dependencies, configure `.env`).

### Step 1.1: Provision the Secure VM

First, open `scripts/cloud/provision_secure_vm.sh` and update the `REPO_OWNER` variable at the top of the file to your GitHub username. The script will fail with an error if you forget this step.

> **Note for Windows Users:** This script must be run in a `bash` shell. If you are on Windows, use a terminal like **Git Bash** (which comes with Git for Windows) or **WSL** (Windows Subsystem for Linux). Do not use PowerShell or Command Prompt for this step.

> **Windows Troubleshooting:** If you see an error like `Failed to attach disk ... to WSL2`, it indicates an issue with your local Windows Subsystem for Linux (WSL) installation.
>
> **Solution 1: Simple Reset**
> Open a Windows PowerShell (as Administrator) and run `wsl --shutdown`. Then, close and reopen your Git Bash terminal and try again.
>
> **Solution 2: Full Repair (if the disk file is missing)**
> If the simple reset doesn't work, or you've confirmed the `.vhdx` file is missing, your WSL installation is corrupted. You must reinstall it. **Warning:** This will delete any data inside your Linux environment.
>
> 1.  Open PowerShell (as Administrator).
> 2.  List your distributions: `wsl --list --verbose`
> 3.  Unregister the broken distribution (replace `Ubuntu` with your distribution's name): `wsl --unregister Ubuntu`
> 4.  Reinstall the distribution: `wsl --install` (or install "Ubuntu" from the Microsoft Store).
> 5.  Once complete, open a new Git Bash terminal and proceed with the deployment.

Then, from your **local machine's terminal** (that has `gcloud` installed and authenticated), run the script:

```bash
bash scripts/cloud/provision_secure_vm.sh
```

Follow the on-screen prompts. You will be asked to enter your private key, which will be sent directly to Google Secret Manager.

After the script completes, you will be in an SSH session inside your new secure VM. The application code is located at `/opt/apex-omega`.

---

### The following steps must be run *inside the VM's SSH session* that was just opened.

---

### Step 1.2: Configure the Engine & Begin Data Collection

The `cloud_run_finalizer.ps1` script is the master entrypoint for booting, verifying, and activating the system for autonomous 24/7 operation.

First, run the finalizer in `dry_run` mode. This will start all services safely and begin collecting data for your AI model.

1.  Navigate to the code directory: `cd /opt/apex-omega`
2.  Edit the `.env` file to add your RPC provider URLs. You can use a simple text editor like `nano`:
    ```bash
    nano .env
    ```
3.  Enable the ML data collector by running this command, which will append the required setting to your `.env` file:
    ```bash
    echo "OMEGA_ML_ALPHA_ENABLED=true" >> .env
    ```
4.  Run the finalizer script. Let this run for at least a few days to collect data.
    ```powershell
    # From the /opt/apex-omega directory inside the VM
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts\ops\cloud_run_finalizer.ps1 -Mode dry_run
    ```

### Step 1.3: Train Your AI Model

After collecting data, you can train your first model.

1.  Stop the running services: `pm2 delete all`
2.  Run the training script:
    ```bash
    python scripts/ml/train_vqc_ranker.py
    ```

### Step 1.4: Go Live

With a trained model, you are ready to arm the system for live trading.

1.  Run the finalizer in `live` mode:
    ```powershell
    powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/cloud_run_finalizer.ps1 -Mode live -LiveAck I_UNDERSTAND_POLYGON_MAINNET_RISK
    ```

The system will start in a safe `canary_mode`, executing only one trade per cycle. Your system is now live and generating profit.

## 2. Monitoring Your Live System

To view the live dashboard running on your private VM, open a **new terminal on your local computer** and run the secure tunnel script:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\cloud\start_dashboard_tunnel.ps1
```

While that script is running, open your web browser and go to **`http://localhost:8080`**. You will see the live dashboard from your secure VM.

Your execution engine is now running securely on Google Cloud. The private key is fetched on-demand from Secret Manager and only ever exists in the memory of the `omega-engine` process.

## 3. Scaling Up Live Trading

Once your system is live and you are comfortable with its performance in `canary_mode`, you can scale up its operations using the API. These commands should be run from your **local machine's PowerShell terminal** while the secure tunnel is active (`.\scripts\cloud\start_dashboard_tunnel.ps1`).

### Step 3.1: Disable Canary Mode

This removes the one-trade-per-cycle safety limit.

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/runtime/settings `
  -ContentType "application/json" `
  -Body '{"canary_mode":false}'
```

### Step 3.2: Increase Trading Volume

You can increase the number of opportunities the engine attempts to execute per cycle. The allowed values are `5`, `10`, and `15`.

```powershell
# Example: Increase the execution batch size to 10
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8080/api/runtime/settings `
  -ContentType "application/json" `
  -Body '{"execute_top":10}'
```

To increase the capital size (`MAX_FLASH_PRINCIPAL_USD`), you must SSH into the VM, edit the `/opt/apex-omega/.env` file, and restart the engine with `pm2 restart omega-engine`.