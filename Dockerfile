# Build stage
FROM python:3.12-slim AS builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md LICENSE ./
COPY src/ ./src/

RUN pip install --no-cache-dir --prefix=/install .

# Runtime stage
FROM python:3.12-slim AS runtime

LABEL org.opencontainers.image.title="FaultRay" \
      org.opencontainers.image.description="Zero-risk infrastructure chaos engineering" \
      org.opencontainers.image.url="https://faultray.com" \
      org.opencontainers.image.source="https://github.com/mattyopon/faultray" \
      org.opencontainers.image.version="10.3.0" \
      org.opencontainers.image.licenses="MIT"

# Create non-root user
RUN groupadd -r faultray && useradd -r -g faultray -d /home/faultray -s /sbin/nologin faultray

COPY --from=builder /install /usr/local

# Create data directory
RUN mkdir -p /home/faultray/.faultray && chown -R faultray:faultray /home/faultray

USER faultray
WORKDIR /home/faultray

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["faultray", "serve", "--host", "0.0.0.0", "--port", "8000"]
