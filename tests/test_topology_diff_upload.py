"""Tests for hardened topology-diff upload handling (size cap + temp cleanup)."""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest

from faultray.api.routes.graph import (
    _MAX_UPLOAD_BYTES,
    _UploadTooLarge,
    _save_upload_to_temp,
)


class _FakeUpload:
    """Minimal async-read upload stub yielding fixed-size chunks like Starlette."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    async def read(self, size: int = -1) -> bytes:
        if self._pos >= len(self._data):
            return b""
        n = (len(self._data) - self._pos) if size is None or size < 0 else size
        out = self._data[self._pos : self._pos + n]
        self._pos += len(out)
        return out


def test_helper_streams_small_file_to_yaml_temp() -> None:
    path = asyncio.run(_save_upload_to_temp(_FakeUpload(b"name: test\n"), field="before_file"))
    try:
        assert path.exists()
        assert path.suffix == ".yaml"
        assert path.read_bytes() == b"name: test\n"
    finally:
        path.unlink(missing_ok=True)


def test_helper_rejects_oversize_and_leaves_no_temp_file() -> None:
    tmpdir = Path(tempfile.gettempdir())
    before = set(tmpdir.glob("*.yaml"))

    up = _FakeUpload(b"x" * (_MAX_UPLOAD_BYTES + 1024))
    with pytest.raises(_UploadTooLarge) as excinfo:
        asyncio.run(_save_upload_to_temp(up, field="after_file"))

    assert excinfo.value.field == "after_file"
    # The partial temp file must have been cleaned up (no leak).
    assert set(tmpdir.glob("*.yaml")) == before


def test_endpoint_rejects_oversize_upload_with_413(auth_client) -> None:
    small = b"components: []\n"
    oversize = b"x" * (_MAX_UPLOAD_BYTES + 1)
    resp = auth_client.post(
        "/api/topology-diff",
        files={
            "before_file": ("before.yaml", small, "application/x-yaml"),
            "after_file": ("after.yaml", oversize, "application/x-yaml"),
        },
    )
    assert resp.status_code == 413
    assert "after_file" in resp.json()["error"]


def test_endpoint_missing_files_returns_400(auth_client) -> None:
    resp = auth_client.post("/api/topology-diff", files={})
    assert resp.status_code == 400


def test_endpoint_valid_upload_does_not_leak_temp_files(auth_client) -> None:
    tmpdir = Path(tempfile.gettempdir())
    before = set(tmpdir.glob("*.yaml"))
    doc = b"components:\n  - id: a\n    name: A\n    type: web_server\n"
    resp = auth_client.post(
        "/api/topology-diff",
        files={
            "before_file": ("before.yaml", doc, "application/x-yaml"),
            "after_file": ("after.yaml", doc, "application/x-yaml"),
        },
    )
    # Either a successful diff (200) or a handled parse error (400) — never a leak.
    assert resp.status_code in (200, 400)
    assert set(tmpdir.glob("*.yaml")) == before
