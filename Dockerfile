# Omega-Apex-1 – Production multi-stage Dockerfile
# Deterministic Cloud Build + Cloud Run (port 3000)
FROM node:22-bookworm-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates \
 && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --ignore-scripts; else npm install --ignore-scripts; fi
COPY . .
ENV NODE_ENV=production
RUN npm run build

FROM node:22-bookworm-slim AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
ENV OMEGA_RUNTIME_MODE=dry-run
ENV EXECUTION_MODE=dry-run
ENV LIVE_TRADING=0
ENV EXECUTION_SINGLETON=0
RUN groupadd --system --gid 1001 omega \
 && useradd --system --uid 1001 --gid omega omega
COPY package.json package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --omit=dev --ignore-scripts; else npm install --omit=dev --ignore-scripts; fi \
 && npm cache clean --force
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/index.html ./index.html
USER omega
EXPOSE 3000
CMD ["node", "dist/server.cjs"]
