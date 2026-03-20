# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""Resilience Contracts - Define resilience requirements as code.

Public API:
    ContractEngine    - validate / generate / save / diff contracts
    ResilienceContract - a set of contract rules
    ContractRule      - a single rule (min_score, max_spof, etc.)
    ContractViolation - a single violation detected during validation
    ContractValidationResult - overall validation outcome
"""

from faultray.contracts.engine import (  # noqa: F401
    ContractEngine,
    ContractRule,
    ContractValidationResult,
    ContractViolation,
    ResilienceContract,
)

__all__ = [
    "ContractEngine",
    "ContractRule",
    "ContractValidationResult",
    "ContractViolation",
    "ResilienceContract",
]
