# Firebase Firestore Security Specification

## 1. Data Invariants
- `routes`: Staged routes must have valid ID, path, netProfitUSD, stage, and valid owner `userId` matching `request.auth.uid`.
- `auditLogs`: Audit logs must have valid ID, routeId, status, and owner `userId` matching `request.auth.uid`.

## 2. Dirty Dozen Test Payloads
1. Anonymous write attempt without auth -> REJECTED
2. Route write with missing required field `pathString` -> REJECTED
3. Route write with spoofed `userId` not matching `request.auth.uid` -> REJECTED
4. Route update modifying immutable `id` or `userId` -> REJECTED
5. Route write exceeding max string length -> REJECTED
6. Audit log write with invalid status type -> REJECTED
7. Audit log write with shadow fields -> REJECTED
8. Blanket read request without user owner query -> REJECTED
9. Spoofed email without `email_verified == true` -> REJECTED
10. Route deletion by non-owner -> REJECTED
11. PII injection attack -> REJECTED
12. Malicious document ID injection (>128 chars or special chars) -> REJECTED
