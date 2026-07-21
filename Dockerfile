# ==============================================================================
# Dockerfile for Omega V5
#
# This builds a production-ready image with all necessary dependencies:
# - Python 3.10
# - Rust toolchain
# - Foundry (for Anvil)
# - Node.js & pnpm (for the DODO RPC provider)
# ==============================================================================

# ==============================================================================
# Builder Stage: Installs all tools and builds all artifacts.
# ==============================================================================
FROM python:3.10-slim AS builder

# Set environment variables for non-interactive installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies: curl, git, build-essentials for Rust/Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Rust
ENV RUSTUP_HOME=/usr/local/rustup \
    CARGO_HOME=/usr/local/cargo \
    PATH=/usr/local/cargo/bin:$PATH
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Install Foundry (for Anvil)
RUN curl -L https://foundry.paradigm.xyz | bash && \
    /root/.foundry/bin/foundryup
ENV PATH="/root/.foundry/bin:${PATH}"

# Install Node.js (LTS) and pnpm
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - && \
    apt-get install -y nodejs && \
    npm install -g pnpm && \
    npm install -g pm2

# Set up the application directory
WORKDIR /app

# Copy dependency manifests
COPY requirements.txt ./
COPY rust_engine/Cargo.toml ./rust_engine/Cargo.toml
COPY rust_engine/Cargo.lock ./rust_engine/Cargo.lock
COPY vendor/web3-rpc-provider/package.json ./vendor/web3-rpc-provider/
COPY vendor/web3-rpc-provider/pnpm-lock.yaml ./vendor/web3-rpc-provider/

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt
RUN cd vendor/web3-rpc-provider && pnpm install --frozen-lockfile

# Copy the rest of the application source code
COPY . .

# Build the Rust engine
RUN cd rust_engine && cargo build --release

# ==============================================================================
# Final Stage: Creates a lean production image.
# ==============================================================================
FROM python:3.10-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Foundry (for Anvil)
RUN curl -L https://foundry.paradigm.xyz | bash && \
    /root/.foundry/bin/foundryup
ENV PATH="/root/.foundry/bin:${PATH}"

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /app .

# The ecosystem.config.cjs file defines all the services to be run by pm2.
# pm2-runtime is the correct command for running pm2 in a container,
# as it handles signals properly for graceful shutdown.
CMD ["pm2-runtime", "start", "ecosystem.config.cjs"]