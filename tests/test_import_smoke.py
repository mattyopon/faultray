# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Import smoke tests — verify all FaultRay modules can be imported."""
import importlib
import pkgutil
import pytest

import faultray


def _iter_modules():
    """Yield all module names under faultray package."""
    prefix = faultray.__name__ + "."
    for importer, modname, ispkg in pkgutil.walk_packages(
        faultray.__path__, prefix=prefix
    ):
        yield modname


# Modules that require optional extras (not installed in default CI).
# These are skipped rather than failed when their dependency is absent.
_OPTIONAL_EXTRA_MODULES = {
    "faultray.mcp_server",  # requires mcp extra: pip install faultray[mcp]
}


@pytest.mark.parametrize("module_name", list(_iter_modules()))
def test_import(module_name):
    """Every module in the faultray package should be importable."""
    try:
        importlib.import_module(module_name)
    except ImportError as exc:
        if module_name in _OPTIONAL_EXTRA_MODULES:
            pytest.skip(f"{module_name} requires optional extra (not installed): {exc}")
        raise
