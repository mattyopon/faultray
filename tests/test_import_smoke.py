# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

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


@pytest.mark.parametrize("module_name", list(_iter_modules()))
def test_import(module_name):
    """Every module in the faultray package should be importable."""
    importlib.import_module(module_name)
