#!/usr/bin/env bash
set -Eeuo pipefail

# Safely update Cloud Run service apex-omega
PROJECT="apex-scanner-live1"
SERVICE="flashloan-execution-monitor"
REGION="us-east1"

echo "=== PHASE 1: ENVIRONMENT VALIDATION ==="
if ! command -v gcloud &> /dev/null; then
    echo "gcloud could not be found. Please install Google Cloud SDK."
    exit 1
fi

echo "gcloud version:"
gcloud version

if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q "@"; then
    echo "No authenticated active gcloud account found."
    exit 1
fi

ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)")
echo "Active account: $ACTIVE_ACCOUNT"

gcloud config set project $PROJECT

if ! gcloud run services describe $SERVICE --region=$REGION --format="value(status.url)" >/dev/null 2>&1; then
    echo "Service $SERVICE not found in region $REGION."
    exit 1
fi

echo "Saving current service configuration before mutation..."
gcloud run services describe $SERVICE \
  --project=$PROJECT \
  --region=$REGION \
  --format=export > cloudrun-before.yaml

echo "Saving current IAM policy..."
gcloud run services get-iam-policy $SERVICE \
  --project=$PROJECT \
  --region=$REGION \
  --format=export > cloudrun-iam-before.yaml

CURRENT_URL=$(gcloud run services describe $SERVICE --region=$REGION --format="value(status.url)")
CURRENT_REVISION=$(gcloud run services describe $SERVICE --region=$REGION --format="value(status.latestReadyRevisionName)")
CURRENT_INGRESS=$(gcloud run services describe $SERVICE --region=$REGION --format="value(metadata.annotations['run.googleapis.com/ingress'])")
CURRENT_MIN_INSTANCES=$(gcloud run services describe $SERVICE --region=$REGION --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/minScale'])")
CURRENT_MAX_INSTANCES=$(gcloud run services describe $SERVICE --region=$REGION --format="value(spec.template.metadata.annotations['autoscaling.knative.dev/maxScale'])")

echo "Current URL: $CURRENT_URL"
echo "Current Revision: $CURRENT_REVISION"
echo "Current Ingress: $CURRENT_INGRESS"
echo "Current Min Instances: $CURRENT_MIN_INSTANCES"
echo "Current Max Instances: $CURRENT_MAX_INSTANCES"

echo ""
echo "=== PHASE 2: APPLY MINIMAL CLOUD RUN UPDATE ==="

echo "Updating Cloud Run service ingress and scaling..."
gcloud run services update $SERVICE \
  --project=$PROJECT \
  --region=$REGION \
  --ingress=all \
  --min-instances=1 \
  --max-instances=3 \
  --quiet

echo "Granting public invocation (roles/run.invoker to allUsers)..."
if ! gcloud run services add-iam-policy-binding $SERVICE \
  --project=$PROJECT \
  --region=$REGION \
  --member=allUsers \
  --role=roles/run.invoker \
  --quiet; then
    echo "Warning: Organization policy may block allUsers. Ensure you configure Cloud Load Balancing with IAP or allow authenticated access."
fi

echo ""
echo "=== PHASE 3: POST-DEPLOY VERIFICATION ==="

gcloud run services describe $SERVICE \
  --project=$PROJECT \
  --region=$REGION \
  --format=export > cloudrun-after.yaml

gcloud run services get-iam-policy $SERVICE \
  --project=$PROJECT \
  --region=$REGION \
  --format=export > cloudrun-iam-after.yaml

NEW_URL=$(gcloud run services describe $SERVICE --region=$REGION --format="value(status.url)")
echo "New URL: $NEW_URL"

echo "Testing /health endpoint..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 $NEW_URL/health || echo "Failed")
HEALTH_RESPONSE=$(curl -s --max-time 30 $NEW_URL/health || echo "{}")

echo "HTTP Status: $HTTP_STATUS"
echo "Health Response: $HEALTH_RESPONSE"

echo "Update complete. Please review cloudrun-after.yaml to verify preserved environment variables and secrets."
