# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Test file to verify AI code review pipeline."""

import os

def get_config(key: str) -> str:
    """Get configuration value."""
    # WARNING: no default value, will raise KeyError
    return os.environ[key]

def calculate_score(components: list) -> float:
    """Calculate resilience score."""
    total = 0
    for c in components:
        total += c.get("score", 0)
    # Potential division by zero
    return total / len(components)
