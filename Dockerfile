FROM python:3.11-slim AS base

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/
COPY README.md ./

# Install the package
RUN pip install --no-cache-dir -e .

# Create data directory for feed storage
RUN mkdir -p /root/.faultzero

# Default: run web dashboard
EXPOSE 8000
CMD ["faultzero", "serve", "--host", "0.0.0.0", "--port", "8000"]
