#!/usr/bin/env bash
# ==============================================================================
# SECURE EXECUTION VM DEPLOYMENT PIPELINE — OMEGA-V5
#
# This script automates the creation of a secure GCP environment for the
# Omega V5 execution engine. It is idempotent and can be run multiple times.
# ==============================================================================
set -euo pipefail

# --- 1. CONFIGURATION & STATE INITIALIZATION ---
echo "====== [1/6] RESOLVING GCP ENVIRONMENT ======"
# Your GitHub username and repository name
VM_NAME="omega-executor-vm-1"
VM_ZONE="us-east1-b"
VM_MACHINE_TYPE="e2-standard-2"
VM_IMAGE_FAMILY="debian-12"
VM_IMAGE_PROJECT="debian-cloud"

REPO_OWNER="your-username"
REPO_NAME="omega-V5-copilot-update-jupyter-notebook-matrix-setup"

# Configuration Check
if [[ "${REPO_OWNER}" == "your-username" ]]; then
    echo "[!] ERROR: Please edit this script and set REPO_OWNER to your GitHub username."
    exit 1
fi

# Target project resolved from active context
export PROJECT_ID=$(gcloud config get-value project 2>/dev/null)

if [ -z "${PROJECT_ID}" ] || [ "${PROJECT_ID}" == "(unset)" ]; then
    echo "[!] ERROR: No active gcloud project set. Run: gcloud config set project <id>"
    exit 1
fi

echo "Target GCP Project ID: ${PROJECT_ID}"
echo "Execution Default Target: Polygon PoS (Chain 137)"
echo "----------------------------------------------------"

# --- 2. IAM & SERVICE ACCOUNT PROVISIONING ---
echo "====== [2/6] PROVISIONING SERVICE ACCOUNT ======"
SA_EMAIL="omega-executor-vm@${PROJECT_ID}.iam.gserviceaccount.com"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud iam service-accounts create omega-executor-vm \
      --display-name="Omega V5 Execution VM Service Account" \
      --project="${PROJECT_ID}"
    echo "[✓] Service account created successfully."
else
    echo "[i] Service account 'omega-executor-vm' already exists. Skipping creation."
fi

echo "Binding IAM Least-Privilege Roles..."
gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${SA_EMAIL}" --role="roles/secretmanager.secretAccessor" --quiet &> /dev/null
gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member="serviceAccount:${SA_EMAIL}" --role="roles/artifactregistry.reader" --quiet &> /dev/null
echo "[✓] IAM roles (secretAccessor, artifactregistry.reader) successfully bound to Service Account."
echo "----------------------------------------------------"

# --- 3. CRYPTOGRAPHIC VAULT PROVISIONING ---
echo "====== [3/6] CONFIGURING SECRET MANAGER VAULT ======"
if ! gcloud secrets describe EXECUTOR_PRIVATE_KEY --project="${PROJECT_ID}" &>/dev/null; then
    gcloud secrets create EXECUTOR_PRIVATE_KEY \
      --replication-policy="automatic" \
      --project="${PROJECT_ID}"
    echo "[✓] Secret 'EXECUTOR_PRIVATE_KEY' container initialized."
else
    echo "[i] Secret container 'EXECUTOR_PRIVATE_KEY' already exists."
fi

echo -n "Enter the 0x execution private key for live trading: "
read -s PRIVATE_KEY_INPUT
echo ""

if [[ ! $PRIVATE_KEY_INPUT =~ ^0x[a-fA-F0-9]{64}$ ]]; then
    echo "[!] WARNING: Entered key format does not exactly match a standard 64-character hex private key string."
fi

printf "%s" "$PRIVATE_KEY_INPUT" | gcloud secrets versions add EXECUTOR_PRIVATE_KEY --data-file=- --project="${PROJECT_ID}"
echo "[✓] Secret version successfully loaded into runtime memory engine storage."
unset PRIVATE_KEY_INPUT
echo "----------------------------------------------------"

# --- 4. HARDENED FIREWALL PROVISIONING ---
echo "====== [4/6] PROVISIONING NETWORK PERIMETER ======"
if ! gcloud compute firewall-rules describe allow-ssh-iap --project="${PROJECT_ID}" &>/dev/null; then
    gcloud compute firewall-rules create allow-ssh-iap \
      --project="${PROJECT_ID}" \
      --network=default \
      --allow=tcp:22 \
      --source-ranges=35.235.240.0/20 \
      --description="Isolate ingress to Google Cloud Identity-Aware Proxy (IAP) tunnels only"
    echo "[✓] Ingress perimeter locked down to IAP range (35.235.240.0/20)."
else
    echo "[i] Firewall rule 'allow-ssh-iap' already established."
fi
echo "----------------------------------------------------"

# --- 5. COMPUTE INSTANCE EMISSION ---
echo "====== [5/6] PROVISIONING COMPUTE ENGINE VM ======"
if ! gcloud compute instances describe "${VM_NAME}" --project="${PROJECT_ID}" --zone="${VM_ZONE}" &>/dev/null; then
    gcloud compute instances create "${VM_NAME}" \
      --project="${PROJECT_ID}" \
      --zone="${VM_ZONE}" \
      --machine-type="${VM_MACHINE_TYPE}" \
      --image-family="${VM_IMAGE_FAMILY}" \
      --image-project="${VM_IMAGE_PROJECT}" \
      --service-account="${SA_EMAIL}" \
      --scopes=https://www.googleapis.com/auth/cloud-platform \
      --metadata=enable-oslogin=TRUE \
      --boot-disk-size=30GB \
      --boot-disk-type=pd-ssd
    echo "[✓] VM Instance '${VM_NAME}' initialized successfully."
else
    echo "[i] Instance '${VM_NAME}' already exists."
fi
echo "----------------------------------------------------"

# --- 6. TARGET MACHINE BOOTSTRAP ---
echo "====== [6/6] BOOTSTRAPPING VM AND FINALIZING SETUP ======"
echo "The secure core infrastructure has been created."
echo "Now automatically SSH-ing into the VM to run final setup..."
echo "----------------------------------------------------"

gcloud compute ssh "${VM_NAME}" --project="${PROJECT_ID}" --zone="${VM_ZONE}" --command="
    set -euo pipefail
    echo '====== Starting Remote Provisioning ======'
    sudo apt-get update && sudo apt-get install -y git
    if [ ! -d '/opt/apex-omega' ]; then
        sudo git clone https://github.com/${REPO_OWNER}/${REPO_NAME}.git /opt/apex-omega
    fi
    cd /opt/apex-omega
    sudo git pull
    sudo bash infra/cloud/prep_instance_2.0.sh
    if [ ! -f '.env' ]; then
        sudo cp .env.example .env
    fi
    if ! grep -q 'GCP_PROJECT_ID' .env; then
        printf '\nGCP_PROJECT_ID=%s\n' '${PROJECT_ID}' | sudo tee -a .env > /dev/null
    fi
    echo '====== Remote Provisioning Complete ======'
    echo 'You are now inside the secure VM. The application is at /opt/apex-omega.'
    echo 'Next steps: 1. cd /opt/apex-omega  2. nano .env (to set RPCs)  3. Run the cloud_run_finalizer.ps1 script.'
"