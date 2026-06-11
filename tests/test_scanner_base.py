"""Tests for the shared cloud scanner base (discovery/base.py)."""

from __future__ import annotations

import pytest

from faultray.discovery.base import CloudScannerBase
from faultray.model.graph import InfraGraph


class _BoomError(RuntimeError):
    pass


def test_step_failures_become_warnings():
    scanner = CloudScannerBase()
    graph = InfraGraph()
    calls: list[str] = []

    def ok(g):
        calls.append("ok")

    def boom(g):
        raise ValueError("kaput")

    scanner._run_scanners(
        graph,
        [("Good", ok), ("Bad", boom), ("AlsoGood", ok)],
        post_processors=[("post-process", boom)],
    )
    # The failing step is recorded but does not stop later steps
    assert calls == ["ok", "ok"]
    assert scanner._warnings == [
        "Failed to scan Bad: kaput",
        "Failed to post-process: kaput",
    ]


def test_reraise_exceptions_propagate():
    scanner = CloudScannerBase()
    scanner.reraise_exceptions = (_BoomError,)

    def missing_sdk(g):
        raise _BoomError("sdk not installed")

    with pytest.raises(_BoomError):
        scanner._run_scanners(InfraGraph(), [("SDK", missing_sdk)])
    assert scanner._warnings == []


def test_custom_error_format():
    scanner = CloudScannerBase()

    def boom(g):
        raise ValueError("x")

    scanner._run_scanners(
        InfraGraph(),
        [("ECS", boom)],
        scan_error_fmt="Failed to scan Alibaba {name}: {exc}",
    )
    assert scanner._warnings == ["Failed to scan Alibaba ECS: x"]


def test_all_provider_scanners_share_base():
    from faultray.discovery.alibaba_scanner import AlibabaScanner
    from faultray.discovery.aws_scanner import AWSScanner
    from faultray.discovery.azure_scanner import AzureScanner
    from faultray.discovery.gcp_scanner import GCPScanner
    from faultray.discovery.k8s_scanner import K8sScanner
    from faultray.discovery.oci_scanner import OCIScanner
    from faultray.discovery.sakura_scanner import SakuraScanner

    for cls in (
        AWSScanner, GCPScanner, AzureScanner, OCIScanner,
        K8sScanner, AlibabaScanner, SakuraScanner,
    ):
        assert issubclass(cls, CloudScannerBase)
