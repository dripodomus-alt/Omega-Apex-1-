# Absolute Completeness & Budget-First Mindset

## Absolute Completeness

- Nothing under control is left minimal.
- Every system must be designed as a finished, production-grade whole.
- Include: happy path, edge cases, failure modes, monitoring, recovery, upgrade path, security, gas accounting.
- Prefer complete end-to-end pipelines over partial solutions.
- Document assumptions and residual risks explicitly.

## Budget-First Rule (Mandatory)

Before any recommendation involving spend, output, gas, capital, or resource consumption, present and compare these four tiers:

| Tier | Definition | When to Prefer |
|------|------------|----------------|
| **FREE** | Zero cost | Always explore first. Ideal when possible. |
| **MINIMAL** | Lowest possible cost that still works | Tight constraints, experiments, MVP. |
| **BUDGET** | Good cost / performance balance | Most production recommendations. |
| **MAX EFFICIENT** | Highest efficiency or best long-term value (may have higher upfront cost) | High-volume, long-lived, or capital-sensitive systems. |

### Required Format

When cost is involved, structure the response as:

1. State the decision point.
2. Present the four tiers with concrete numbers or clear qualitative differences.
3. Recommend one tier and justify why.
4. Proceed with the recommended path (or ask the user to choose).

Never skip the comparison. Never default to the most expensive option without justification.
