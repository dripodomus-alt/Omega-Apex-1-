# ==============================================================================
# Dockerfile for OMEGA-FINALLY-RICH Monorepo
#
# This is a multi-stage build optimized for pnpm workspaces.
# It creates a lean production image by separating build dependencies
# from the final runtime environment.
# ==============================================================================

# --- 1. Base Stage ---
# Use a specific Node.js version for reproducibility.
FROM node:20-slim AS base
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable

# --- 2. Dependencies Stage ---
# Install all dependencies, including devDependencies, needed for the build.
FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
COPY pnpm-workspace.yaml ./
COPY apps/api/package.json ./apps/api/
COPY apps/web/package.json ./apps/web/
COPY apps/worker/package.json ./apps/worker/
COPY packages/ui/package.json ./packages/ui/
COPY packages/shared/package.json ./packages/shared/
# Add other packages as needed
RUN --mount=type=cache,id=pnpm,target=/pnpm/store pnpm install --frozen-lockfile

# --- 3. Builder Stage ---
# Build all the applications in the monorepo.
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN pnpm build

# --- 4. Runner Stage ---
# Create the final, lean image for production.
FROM base AS runner
WORKDIR /app

# Copy only the necessary production dependencies
COPY --from=deps /app/node_modules ./node_modules
# Copy the built application code
COPY --from=builder /app/apps/api/dist ./apps/api/dist
COPY --from=builder /app/apps/worker/dist ./apps/worker/dist
COPY --from=builder /app/apps/web/.next ./apps/web/.next
COPY --from=builder /app/apps/web/public ./apps/web/public
COPY --from=builder /app/apps/web/package.json ./apps/web/package.json
# Expose the ports for the services
EXPOSE 3000
EXPOSE 8000