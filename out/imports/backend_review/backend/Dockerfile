# Backend Dockerfile
FROM python:3.11-slim

WORKDIR /app/backend

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY . .

# Expose port
EXPOSE 8001

# Run FastAPI server
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
