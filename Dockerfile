# ─────────────────────────────────────────────────────────────────────────────
#  OMEGA V5 — Industry-grade multi-stage Dockerfile
#  Target: Polygon PoS MEV / arbitrage engine (Node 22 LTS, Alpine 3.21)
#
#  Stages
#  ------
#  deps      – install only production node_modules (layer-cached)
#  builder   – full dev-deps + vite build + esbuild bundle
#  runner    – minimal runtime image (~120 MB), non-root, read-only capable
# ─────────────────────────────────────────────────────────────────────────────

# ── 1. Dependency layer (production deps only, cache-friendly) ────────────────
FROM node:22-alpine3.21 AS deps

WORKDIR /app

# Install system build deps needed by native addons (pg, ioredis)
RUN apk add --no-cache python3 make g++ \
    && corepack enable

COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts \
    && npm cache clean --force

# ── 2. Builder ────────────────────────────────────────────────────────────────
FROM node:22-alpine3.21 AS builder

WORKDIR /app

RUN apk add --no-cache python3 make g++

COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts && npm cache clean --force

COPY . .

# Type-check, then build frontend (Vite) + server bundle (esbuild)
RUN npm run lint \
    && npm run build

# ── 3. Minimal production runner ──────────────────────────────────────────────
FROM node:22-alpine3.21 AS runner

LABEL org.opencontainers.image.title="OMEGA V5 Polygon MEV Engine" \
      org.opencontainers.image.description="High-frequency Polygon PoS arbitrage & liquidation engine" \
      org.opencontainers.image.source="https://github.com/dripodomus-alt/Omega-Apex-1-" \
      org.opencontainers.image.licenses="UNLICENSED"

WORKDIR /app

# Security: non-root user
RUN addgroup -S omega && adduser -S omega -G omega

# Runtime OS deps (TLS certs for HTTPS RPC calls, timezone data)
RUN apk add --no-cache ca-certificates tzdata curl

# Copy only what we need at runtime
COPY --from=deps    /app/node_modules ./node_modules
COPY --from=builder /app/dist         ./dist
COPY --from=builder /app/package.json ./package.json

# Health-check via the /api/health endpoint
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -sf http://localhost:3000/api/health | grep -q '"status":"ok"' || exit 1

# Run as non-root
USER omega

ENV NODE_ENV=production \
    PORT=3000

EXPOSE 3000

# Use exec form for proper signal handling (SIGTERM → graceful shutdown)
CMD ["node", "dist/server.cjs"]
