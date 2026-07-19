# syntax=docker/dockerfile:1.7

# This Dockerfile is optimized for Cloud Run deployments.
# It uses a multi-stage build to create a small, secure, and efficient final image.

# ==============================================================================
# Stage 1: Build the Rust Engine
# ==============================================================================
FROM rust:1.82-bookworm AS rust-builder

WORKDIR /build/rust_engine

# Cache Cargo dependencies by fetching them before copying source code
COPY rust_engine/Cargo.toml rust_engine/Cargo.lock ./
RUN cargo fetch

# Copy source code and build the release binary
COPY rust_engine/src ./src
RUN cargo build --release

# ==============================================================================
# Stage 2: Build Node.js Vendor Dependencies
# ==============================================================================
FROM node:20-bookworm AS node-builder

WORKDIR /build/vendor/web3-rpc-provider

# Install pnpm, a performant package manager
RUN npm install -g pnpm@10.34.5

# Cache Node.js dependencies by installing them before copying source code
COPY vendor/web3-rpc-provider/package.json vendor/web3-rpc-provider/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

# Copy source code and build the package
COPY vendor/web3-rpc-provider ./
RUN pnpm build

# The result is the entire /build/vendor/web3-rpc-provider directory,
# containing the built application and its production node_modules.

# ==============================================================================
# Stage 3: Final Runtime Image
# ==============================================================================
# Use the official Node.js image as it provides a recent Debian base (Bookworm)
# and we need Node for the vendor dependency's runtime.
FROM node:20-bookworm AS final

# Set environment variables for a non-interactive, clean runtime
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Puppeteer needs to find the system-installed Chromium
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    # Disable features not applicable to a stateless Cloud Run environment
    OMEGA_DISABLE_EMBEDDED_REDIS=true

# Install system dependencies: Python for the app, Chromium for Puppeteer.
# Unnecessary build tools like `foundry` and services like `redis-server` are excluded.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
      python3 \
      python3-pip \
      python3-venv \
      chromium \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/apex-omega

# Install Python dependencies first to leverage Docker layer caching
COPY requirements.txt ./
# Use --break-system-packages for Debian Bookworm's "externally managed" policy
RUN python3 -m pip install --break-system-packages --no-cache-dir -r requirements.txt

# Copy only the necessary application code and pre-built artifacts from previous stages.
# This avoids including development files, local configs, or large git history.
COPY --from=rust-builder /build/rust_engine/target/release/omega_rust_engine ./rust_engine/target/release/
COPY --from=node-builder /build/vendor/web3-rpc-provider ./vendor/web3-rpc-provider/
COPY omega_v5 ./omega_v5/

# Ensure the Rust binary is executable
RUN chmod +x ./rust_engine/target/release/omega_rust_engine

# Create directories for runtime artifacts. These are ephemeral in Cloud Run.
RUN mkdir -p out cache logs

# Expose the port the app will run on. Cloud Run provides the PORT env var, defaulting to 8080.
EXPOSE 8080

# Add a healthcheck to ensure the API is responsive before Cloud Run sends traffic.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8080/health || exit 1

# Set the command to run the Uvicorn server.
# It's crucial to listen on the port specified by the $PORT environment variable,
# which is standard for Cloud Run. `exec` ensures Uvicorn receives signals correctly.
CMD ["sh", "-c", "exec python3 -m uvicorn omega_v5.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
