#!/bin/bash
#
# This script securely fetches a secret from Google Cloud Secret Manager
# and injects it as an environment variable before executing a command.
# It is intended to be used as an interpreter in a PM2 ecosystem file.

set -e

# The name of the secret in GCP Secret Manager.
SECRET_ID="EXECUTOR_PRIVATE_KEY"

# The GCP Project ID must be passed via the environment.
if [ -z "$GCP_PROJECT_ID" ]; then
  echo "Error: GCP_PROJECT_ID environment variable is not set." >&2
  exit 1
fi

echo "Fetching secret '$SECRET_ID' from project '$GCP_PROJECT_ID'..."

export EXECUTOR_PRIVATE_KEY=$(gcloud secrets versions access latest --secret="$SECRET_ID" --project="$GCP_PROJECT_ID" | tr -d '\n')

echo "Secret fetched successfully. Executing command: $@"
exec "$@"