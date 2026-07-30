# ==============================================================================
# Dockerfile for the OMEGA-FINALLY-RICH Python/Rust Hybrid Application
#
# This is a multi-stage build that:
# 1. Compiles the Rust extension (`scanner_core`) in a builder stage.
# 2. Creates a lean final image with the Python application and the compiled
#    Rust wheel, ready for deployment to Google Cloud Run.
# ==============================================================================

# --- 1. Builder Stage ---
# This stage installs the Rust toolchain and builds the Rust extension wheel.
FROM python:3.11-slim as builder

# Install Rust toolchain
RUN apt-get update && apt-get install -y curl build-essential && \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# Install Python build dependencies
RUN pip install maturin

# Copy the entire project context
WORKDIR /app
COPY . .

# Build the Rust extension as a wheel file.
# This compiles the code in release mode for maximum performance.
RUN maturin build --release -o dist --find-interpreter

# --- 2. Final Stage ---
# This stage creates the lean production image.
FROM python:3.11-slim as final

WORKDIR /app

# Copy requirements file first to leverage Docker layer caching.
COPY ./requirements.txt .

# Install Python application dependencies from the single source of truth.
RUN pip install --no-cache-dir -r requirements.txt
# Copy the compiled Rust wheel from the builder stage
COPY --from=builder /app/dist/*.whl .

# Install the Rust wheel
RUN pip install *.whl

# Copy the Python application code
COPY ./omega_v5 ./omega_v5

# Expose the port the application will run on (as defined in cloudbuild.yaml)
EXPOSE 8080

# Define the command to run the application.
# This assumes you have a web server (like FastAPI/Uvicorn) in your main module.
# Replace `omega_v5.main:app` with your actual application entrypoint.
CMD ["uvicorn", "omega_v5.main:app", "--host", "0.0.0.0", "--port", "8080"]