# Installation

FaultZero can be installed via pip, Docker, or from source.

## pip

```bash
pip install faultzero
```

## With cloud scanning support

Install optional dependencies for cloud provider integration:

```bash
pip install "faultzero[aws]"          # AWS support
pip install "faultzero[gcp]"          # GCP support
pip install "faultzero[k8s]"          # Kubernetes support
pip install "faultzero[azure]"        # Azure support
pip install "faultzero[all-clouds]"   # Everything
```

## Docker

Run FaultZero using the official Docker image:

```bash
docker compose up web
```

Or pull the image directly:

```bash
docker pull ghcr.io/mattyopon/faultzero:latest
docker run -p 8000:8000 ghcr.io/mattyopon/faultzero:latest
```

## From source

```bash
git clone https://github.com/mattyopon/infrasim.git
cd infrasim
pip install -e ".[dev]"
```

## Requirements

- Python 3.11 or later
- pip 21.0 or later

## Verify installation

```bash
faultzero --version
faultzero --help
```

You should see the FaultZero version number and a list of available commands.
