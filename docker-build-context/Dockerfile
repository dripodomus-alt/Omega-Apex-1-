# Cloud Run backend image for Apex-Omega V5.
# Runs the FastAPI control/status API; scanner execution remains gated by env flags.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.in ./requirements.in
# Install pip-tools first to leverage Docker cache.
# Then install application dependencies. This layer only rebuilds if requirements.in changes.
RUN python -m pip install --upgrade pip \
    && pip install pip-tools \
    && pip-sync requirements.in

COPY omega_v5 ./omega_v5
COPY README.md ./README.md
COPY docker/entrypoint.sh ./docker/entrypoint.sh

RUN chmod +x /app/docker/entrypoint.sh \
    && mkdir -p /app/out /app/logs

EXPOSE 8080

ENTRYPOINT ["/app/docker/entrypoint.sh"]
