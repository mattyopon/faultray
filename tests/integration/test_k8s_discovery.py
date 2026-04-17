"""K8s Discovery integration test (Phase 0 baseline validation, Task 2).

This test spins up a real kind cluster (control-plane + worker), deploys three
Deployments + ClusterIP Services (nginx / redis / app) in the ``faultray-demo``
namespace, and runs ``python -m faultray scan --k8s`` against it. It then
asserts that all three components are discovered.

Runtime requirements (test is *skipped* if any are missing):

* Docker daemon reachable (the current user's primary group must include
  ``docker`` — Docker Desktop WSL integration works).
* ``kind`` >= 0.27 on ``PATH`` (or at ``/home/user/.local/bin/kind``).
* ``kubectl`` >= 1.30 on ``PATH`` (or at ``/home/user/.local/bin/kubectl``).

To run this test explicitly::

    pytest -m integration tests/integration/test_k8s_discovery.py

By default it is skipped because (a) it pulls container images, (b) it takes
roughly 60-90 s to create the cluster and wait for pods Ready, and (c) it
requires the ``integration`` marker to be selected.

Manual verification (the *primary* evidence for Phase 0 Task 2) is recorded in
``docs/phase0-validation-report.md`` under the "K8s Discovery" section.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import pytest

# ---------------------------------------------------------------------------
# Environment detection
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures"
KIND_CONFIG = FIXTURE_DIR / "kind-config.yaml"
CLUSTER_NAME = "faultray-test"
NAMESPACE = "faultray-demo"
KUBE_CONTEXT = f"kind-{CLUSTER_NAME}"

# Tool lookup: honour PATH but fall back to the locations used in the FaultRay
# development VM (see docs/phase0-validation-report.md).
_LOCAL_BIN = Path("/home/user/.local/bin")


def _which(name: str) -> str | None:
    path = shutil.which(name)
    if path:
        return path
    fallback = _LOCAL_BIN / name
    if fallback.exists():
        return str(fallback)
    return None


KIND_BIN = _which("kind")
KUBECTL_BIN = _which("kubectl")


def _docker_reachable() -> bool:
    """Return True iff ``docker info`` exits 0 in the current environment."""
    docker = _which("docker")
    if docker is None:
        return False
    try:
        result = subprocess.run(
            [docker, "info"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


SKIP_REASON = "requires kind+docker+kubectl (integration only)"
RUNTIME_OK = bool(KIND_BIN and KUBECTL_BIN and _docker_reachable())

# Gate the whole module behind the integration marker *and* the env check.
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not RUNTIME_OK, reason=SKIP_REASON),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(cmd: list[str], *, check: bool = True, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    """Run ``cmd`` and return the CompletedProcess, capturing both streams."""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(cmd)}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )
    return result


SAMPLE_MANIFEST = """\
apiVersion: v1
kind: Namespace
metadata:
  name: faultray-demo
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nginx
  namespace: faultray-demo
  labels: {app: nginx}
spec:
  replicas: 2
  selector: {matchLabels: {app: nginx}}
  template:
    metadata: {labels: {app: nginx}}
    spec:
      containers:
        - {name: nginx, image: nginx:alpine, ports: [{containerPort: 80}]}
---
apiVersion: v1
kind: Service
metadata: {name: nginx, namespace: faultray-demo}
spec:
  type: ClusterIP
  selector: {app: nginx}
  ports: [{port: 80, targetPort: 80}]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: redis
  namespace: faultray-demo
  labels: {app: redis}
spec:
  replicas: 1
  selector: {matchLabels: {app: redis}}
  template:
    metadata: {labels: {app: redis}}
    spec:
      containers:
        - {name: redis, image: redis:alpine, ports: [{containerPort: 6379}]}
---
apiVersion: v1
kind: Service
metadata: {name: redis, namespace: faultray-demo}
spec:
  type: ClusterIP
  selector: {app: redis}
  ports: [{port: 6379, targetPort: 6379}]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
  namespace: faultray-demo
  labels: {app: app}
spec:
  replicas: 3
  selector: {matchLabels: {app: app}}
  template:
    metadata: {labels: {app: app}}
    spec:
      containers:
        - {name: app, image: nginx:alpine, ports: [{containerPort: 8080}]}
---
apiVersion: v1
kind: Service
metadata: {name: app, namespace: faultray-demo}
spec:
  type: ClusterIP
  selector: {app: app}
  ports: [{port: 8080, targetPort: 8080}]
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def kind_cluster(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Create a ``faultray-test`` kind cluster for the session and tear it down.

    Yields the kube context name. Honours ``FAULTRAY_REUSE_KIND=1`` to skip
    create/delete (useful when iterating locally).
    """
    assert KIND_BIN is not None
    reuse = os.environ.get("FAULTRAY_REUSE_KIND") == "1"

    if not reuse:
        # Defensively delete any pre-existing cluster with the same name.
        subprocess.run(
            [KIND_BIN, "delete", "cluster", "--name", CLUSTER_NAME],
            capture_output=True,
            text=True,
            timeout=120,
        )
        _run(
            [
                KIND_BIN,
                "create",
                "cluster",
                "--name",
                CLUSTER_NAME,
                "--config",
                str(KIND_CONFIG),
            ],
            timeout=420,
        )

    try:
        yield KUBE_CONTEXT
    finally:
        if not reuse:
            subprocess.run(
                [KIND_BIN, "delete", "cluster", "--name", CLUSTER_NAME],
                capture_output=True,
                text=True,
                timeout=180,
            )


@pytest.fixture(scope="session")
def demo_namespace(kind_cluster: str, tmp_path_factory: pytest.TempPathFactory) -> str:
    """Deploy the 3-component sample workload and wait for all pods Ready."""
    assert KUBECTL_BIN is not None
    manifest = tmp_path_factory.mktemp("k8s") / "sample.yaml"
    manifest.write_text(SAMPLE_MANIFEST)

    _run(
        [KUBECTL_BIN, "--context", kind_cluster, "apply", "-f", str(manifest)],
        timeout=120,
    )
    _run(
        [
            KUBECTL_BIN,
            "--context",
            kind_cluster,
            "-n",
            NAMESPACE,
            "wait",
            "--for=condition=Available",
            "--timeout=180s",
            "deployment/nginx",
            "deployment/redis",
            "deployment/app",
        ],
        timeout=240,
    )
    # A tiny grace period so Service endpoints reconcile before scan.
    time.sleep(2)
    return NAMESPACE


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_faultray_scan_k8s_discovers_three_components(
    kind_cluster: str,
    demo_namespace: str,
    tmp_path: Path,
) -> None:
    """`faultray scan --k8s` must discover nginx, redis, and app as components."""
    output = tmp_path / "k8s-topology.json"
    result = _run(
        [
            sys.executable,
            "-m",
            "faultray",
            "scan",
            "--k8s",
            "--context",
            kind_cluster,
            "--namespace",
            demo_namespace,
            "--output",
            str(output),
        ],
        timeout=120,
    )

    assert output.exists(), (
        f"faultray scan did not write output file. stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    model = json.loads(output.read_text())

    # Parseable + has expected top-level keys.
    assert "components" in model
    assert "dependencies" in model

    # All three workloads must be discovered (names may be namespaced).
    names = {c.get("name", "") for c in model["components"]}
    for expected in ("nginx", "redis", "app"):
        assert any(expected in n for n in names), (
            f"component {expected!r} not found. discovered: {sorted(names)}"
        )

    # Sanity: 3 components total.
    assert len(model["components"]) == 3, (
        f"expected 3 components, got {len(model['components'])}: {sorted(names)}"
    )


def test_faultray_simulate_consumes_k8s_topology(
    kind_cluster: str,
    demo_namespace: str,
    tmp_path: Path,
) -> None:
    """`faultray simulate --model <scan-output>` must run without error."""
    output = tmp_path / "k8s-topology.json"
    _run(
        [
            sys.executable,
            "-m",
            "faultray",
            "scan",
            "--k8s",
            "--context",
            kind_cluster,
            "--namespace",
            demo_namespace,
            "--output",
            str(output),
        ],
        timeout=120,
    )

    sim = _run(
        [
            sys.executable,
            "-m",
            "faultray",
            "simulate",
            "--model",
            str(output),
            "--json",
        ],
        timeout=180,
    )
    # --json summary should parse.
    payload = json.loads(sim.stdout)
    assert "scenarios" in payload or "resilience_score" in payload, (
        f"unexpected simulate --json payload keys: {list(payload)[:10]}"
    )
