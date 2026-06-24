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


def _post_request_with_content_length(value: str | None):
    """Build a minimal POST Request to /api/topology-diff carrying the given
    Content-Length. The pre-parse guard returns before reading the body, so no
    real multipart payload is needed (and `user` is passed directly, bypassing
    the auth dependency that FastAPI would otherwise inject)."""
    from starlette.requests import Request

    headers = []
    if value is not None:
        headers.append((b"content-length", value.encode()))

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/topology-diff",
        "headers": headers,
        "query_string": b"",
    }
    return Request(scope, receive)


def test_oversize_content_length_rejected_before_form_parsing() -> None:
    # A declared Content-Length past the whole-body cap is rejected up front,
    # before await request.form() spools the payload to temp disk.
    from faultray.api.routes.graph import _MAX_REQUEST_BYTES, topology_diff_api

    req = _post_request_with_content_length(str(_MAX_REQUEST_BYTES + 1))
    resp = asyncio.run(topology_diff_api(req, user={"id": "t"}))
    assert resp.status_code == 413


def test_invalid_content_length_rejected_with_400() -> None:
    from faultray.api.routes.graph import topology_diff_api

    req = _post_request_with_content_length("not-a-number")
    resp = asyncio.run(topology_diff_api(req, user={"id": "t"}))
    assert resp.status_code == 400


def test_oversize_body_without_content_length_rejected_during_parsing() -> None:
    # Chunked / omitted Content-Length: the header pre-check is skipped, so the
    # ASGI receive cap must reject the body DURING parsing, before request.form()
    # spools the whole multipart payload to temp disk.
    from starlette.requests import Request

    from faultray.api.routes.graph import _MAX_REQUEST_BYTES, topology_diff_api

    boundary = b"capTESTboundary"
    head = (
        b"--" + boundary + b"\r\n"
        b'Content-Disposition: form-data; name="after_file"; filename="a.yaml"\r\n'
        b"\r\n"
    )
    one_mb = b"x" * (1024 * 1024)
    # Enough 1 MB file-content chunks to push the cumulative body past the cap
    # (the closing boundary is intentionally never reached).
    n_chunks = _MAX_REQUEST_BYTES // len(one_mb) + 2
    messages = [head] + [one_mb] * n_chunks

    idx = 0

    async def receive():
        nonlocal idx
        if idx < len(messages):
            body = messages[idx]
            idx += 1
            return {"type": "http.request", "body": body, "more_body": True}
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/topology-diff",
        # No content-length header → header pre-check is skipped on purpose.
        "headers": [(b"content-type", b"multipart/form-data; boundary=" + boundary)],
        "query_string": b"",
    }
    req = Request(scope, receive)
    resp = asyncio.run(topology_diff_api(req, user={"id": "t"}))
    assert resp.status_code == 413


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
