# Release artifact verification

FaultRay release pipeline (see `.github/workflows/release.yml`, #95) ships
three integrity signals for every published version:

1. **CycloneDX SBOM** — software bill of materials for Python wheel / sdist
   and Docker image
2. **SLSA v1 build provenance** — cryptographic attestation of *how* and
   *where* the artifact was built
3. **Sigstore cosign signature** — keyless OIDC signature on the Docker
   image itself

This page shows how downstream consumers can verify all three.

## Prerequisites

```bash
# cosign (sigstore client)
go install github.com/sigstore/cosign/v2/cmd/cosign@latest
# OR via binary releases: https://github.com/sigstore/cosign/releases

# GitHub CLI (for attestation verify)
# https://cli.github.com
```

## 1. Verify SLSA provenance for Python wheel

```bash
gh attestation verify faultray-<VERSION>-py3-none-any.whl \
  --owner mattyopon
```

Expected output includes:

```
✓ Verification succeeded!
...
Build: https://github.com/mattyopon/faultray/.github/workflows/release.yml
```

## 2. Verify Docker image signature (cosign keyless)

```bash
IMAGE=ghcr.io/mattyopon/faultray
TAG=v<VERSION>

cosign verify "${IMAGE}:${TAG}" \
  --certificate-identity-regexp="^https://github.com/mattyopon/faultray" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com"
```

Verifies that the image was signed by a workflow run from the
`mattyopon/faultray` repository using OIDC (no long-lived keys).

## 3. Fetch + validate SBOM

### Python package SBOM

Download `faultray-<VERSION>-python.cdx.json` from the GitHub Release
attachments, or regenerate locally:

```bash
syft packages dir:. -o cyclonedx-json > local-sbom.json
```

Feed into `grype`, `trivy`, or any SCA tool for vulnerability tracking.

### Docker image SBOM

SBOM is attached to the image itself via `cosign attest`:

```bash
cosign verify-attestation "${IMAGE}:${TAG}" \
  --type cyclonedx \
  --certificate-identity-regexp="^https://github.com/mattyopon/faultray" \
  --certificate-oidc-issuer="https://token.actions.githubusercontent.com" \
  | jq -r '.payload' | base64 -d | jq '.predicate'
```

Or, for human consumption, download
`faultray-<VERSION>-docker.cdx.json` from the GitHub Release assets.

## 4. Verify SLSA provenance for Docker image

The provenance is pushed to the registry alongside the image via
`actions/attest-build-provenance@v2 --push-to-registry`.

```bash
gh attestation verify oci://${IMAGE}:${TAG} --owner mattyopon
```

## Supply-chain posture summary

| Signal | Tooling | Scope |
|---|---|---|
| SBOM | anchore/sbom-action (syft) | Python dist/ + Docker image |
| Provenance | actions/attest-build-provenance@v2 | SLSA v1, in-toto |
| Image signature | sigstore cosign keyless (OIDC) | Docker only |
| PyPI publish | Trusted Publisher (OIDC) | no long-lived tokens |

For questions or security reports, see [SECURITY.md](../SECURITY.md).
