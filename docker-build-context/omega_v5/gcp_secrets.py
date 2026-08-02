# ==============================================================================
# gcp_secrets.py -- Securely fetch secrets from Google Cloud Secret Manager.
#
# This module provides a utility to access secrets stored in GCP, which is the
# recommended production practice for handling sensitive data like private keys.
# ==============================================================================

from __future__ import annotations

import os
from functools import lru_cache

from google.cloud import secretmanager


@lru_cache(maxsize=None)
def get_secret(secret_id: str, project_id: str, version: str = "latest") -> str | None:
    """
    Retrieves a secret's payload from Google Cloud Secret Manager.

    It uses LRU cache to avoid repeatedly fetching the same secret.
    """
    if not project_id:
        print("Warning: GCP_PROJECT_ID is not set. Cannot fetch secrets from GCP.")
        return None

    try:
        client = secretmanager.SecretManagerServiceClient()
        name = f"projects/{project_id}/secrets/{secret_id}/versions/{version}"
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8")
        return payload
    except Exception as e:
        print(f"Error fetching secret '{secret_id}' from GCP Secret Manager: {e}")
        return None