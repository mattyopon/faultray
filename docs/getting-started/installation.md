# Installation

FaultRay can be installed via pip, Docker, or from source.

## pip

```bash
pip install faultray
```

## With cloud scanning support

Install optional dependencies for cloud provider integration:

```bash
pip install "faultray[aws]"          # AWS support
pip install "faultray[gcp]"          # GCP support
pip install "faultray[k8s]"          # Kubernetes support
pip install "faultray[azure]"        # Azure support
pip install "faultray[all-clouds]"   # Everything
```

## Docker

Run FaultRay using the official Docker image:

```bash
docker compose up web
```

Or pull the image directly:

```bash
docker pull ghcr.io/mattyopon/faultray:latest
docker run -p 8000:8000 ghcr.io/mattyopon/faultray:latest
```

## From source

```bash
git clone https://github.com/mattyopon/faultray.git
cd faultray
pip install -e ".[dev]"
```

## Requirements

- Python 3.11 or later
- pip 21.0 or later

## Verify installation

```bash
faultray --version
faultray --help
```

You should see the FaultRay version number and a list of available commands.
