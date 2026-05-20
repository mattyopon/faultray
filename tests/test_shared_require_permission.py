# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.
"""Regression tests for #139 — _require_permission must fail closed.

Before #139, any non-HTTPException from the auth layer (DB outage, role
config error, ImportError, ...) was swallowed and the dependency
returned ``None``. Many handlers ignore the principal and only use the
dependency for side effects, so the swallowed exception became a
silent authorization bypass. These tests pin the new contract:

- HTTPException raised by the auth layer is propagated unchanged
  (preserving the existing 401 / 403 contract).
- Any other exception is converted to a 503 so the request is denied.
- Happy path: when the auth layer returns a value, the dependency
  returns it (no regression on normal behavior).
"""
from __future__ import annotations

from typing import Any

import pytest
from fastapi import HTTPException

from faultray.api.routes import _shared


class _FakeRequest:
    """Minimal stand-in for fastapi.Request — never actually used."""


@pytest.fixture
def patch_require_permission(monkeypatch):
    """Replace faultray.api.auth.require_permission with a controllable double."""

    def _install(behavior):
        async def _checker(_request: Any) -> Any:
            return behavior()

        def _require_permission(_permission: str):
            return _checker

        import sys
        import types

        mod = types.ModuleType("faultray.api.auth")
        mod.require_permission = _require_permission  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "faultray.api.auth", mod)

    return _install


@pytest.mark.asyncio
async def test_happy_path_returns_principal(patch_require_permission) -> None:
    patch_require_permission(lambda: {"user_id": "u1", "permission": "view"})
    dep = _shared._require_permission("view")
    result = await dep(_FakeRequest())
    assert result == {"user_id": "u1", "permission": "view"}


@pytest.mark.asyncio
async def test_http_exception_propagates_unchanged(patch_require_permission) -> None:
    def _raise():
        raise HTTPException(status_code=403, detail="not allowed")

    patch_require_permission(_raise)
    dep = _shared._require_permission("view")
    with pytest.raises(HTTPException) as exc_info:
        await dep(_FakeRequest())
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "not allowed"


@pytest.mark.asyncio
async def test_generic_exception_is_converted_to_503(patch_require_permission) -> None:
    """#139: a DB error must NOT silently allow the request through."""

    def _raise():
        raise RuntimeError("simulated auth-layer/DB failure")

    patch_require_permission(_raise)
    dep = _shared._require_permission("manage_billing")
    with pytest.raises(HTTPException) as exc_info:
        await dep(_FakeRequest())
    assert exc_info.value.status_code == 503
    assert "Authorization service" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_import_failure_is_converted_to_503(monkeypatch) -> None:
    """Even an ImportError on the auth module must fail closed."""
    import sys

    monkeypatch.setitem(
        sys.modules,
        "faultray.api.auth",
        None,  # forces ImportError on `from faultray.api.auth import ...`
    )
    dep = _shared._require_permission("view")
    with pytest.raises(HTTPException) as exc_info:
        await dep(_FakeRequest())
    assert exc_info.value.status_code == 503
