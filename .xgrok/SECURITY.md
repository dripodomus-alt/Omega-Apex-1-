# Security checklist (Grok-aware)

- [x] No secrets in git (use env vars / Secret Storage).
- [x] Dependencies from trusted registries only.
- [x] Input validation on all external data (`pipeline_validation.py`).
- [x] Least privilege for file/shell tools and IAM roles.
- [x] HTTPS / WSS / `rediss://` for all network clients (encryption in transit).
- [x] Avoid logging PII or raw private keys.
- [x] Review generated code for injection (SQL, XSS, command).
- [x] Automated data validation gates are integrated into the readiness benchmark.
- [x] Data at rest (secrets) is encrypted via GCP Secret Manager.
- [x] Regular compliance and security audits are part of the operational cycle (`audit_omega_v5.ps1`).

Reference `docs/data_governance.md` for full data security and lifecycle policies.

Grok must refuse to hardcode credentials or disable security checks for convenience.
