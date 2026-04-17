# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Code-level component models for runtime risk simulation.

Extends FaultRay's infrastructure graph with code-level nodes,
enabling PR diff analysis, runtime cost prediction, and
AI hallucination risk scoring.
"""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class CodeLanguage(str, Enum):
    """Supported programming languages for static analysis."""

    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    UNKNOWN = "unknown"


class ComplexityClass(str, Enum):
    """Big-O complexity classification."""

    O_1 = "O(1)"
    O_LOG_N = "O(log n)"
    O_N = "O(n)"
    O_N_LOG_N = "O(n log n)"
    O_N2 = "O(n²)"
    O_N3 = "O(n³)"
    O_2N = "O(2ⁿ)"
    UNKNOWN = "unknown"


class AuthorType(str, Enum):
    """Who wrote the code — critical for hallucination risk scoring."""

    HUMAN = "human"
    AI_CLAUDE = "ai_claude"
    AI_GPT = "ai_gpt"
    AI_COPILOT = "ai_copilot"
    AI_CODEX = "ai_codex"
    AI_CURSOR = "ai_cursor"
    AI_UNKNOWN = "ai_unknown"
    MIXED = "mixed"  # Human + AI co-authored


class RuntimeCostProfile(BaseModel):
    """Estimated runtime resource cost for a code component.

    **DISCLAIMER**: These are heuristic predictions based on static analysis,
    NOT actual measurements. Values are rough order-of-magnitude estimates
    useful for relative comparison (is change A riskier than change B?),
    not absolute performance numbers. For accurate profiling, use runtime
    tools (py-spy, perf, Datadog Profiler, etc.).
    """

    # CPU cost model
    complexity: ComplexityClass = ComplexityClass.UNKNOWN
    estimated_cpu_ms_per_call: float = 0.0  # Average CPU time per invocation
    estimated_peak_cpu_ms: float = 0.0  # Worst-case CPU time

    # Memory cost model
    estimated_memory_mb_per_call: float = 0.0  # Memory allocated per invocation
    estimated_peak_memory_mb: float = 0.0  # Worst-case memory
    allocations_per_call: int = 0  # Number of heap allocations

    # I/O cost model
    estimated_io_calls_per_invocation: int = 0  # DB queries, API calls, file reads
    estimated_io_latency_ms: float = 0.0  # Average I/O wait time
    network_calls_per_invocation: int = 0  # External HTTP calls

    # Concurrency characteristics
    is_blocking: bool = False  # Does it block the event loop?
    holds_lock: bool = False  # Does it acquire locks?
    lock_duration_ms: float = 0.0  # Estimated lock hold time


class HallucinationRiskProfile(BaseModel):
    """AI hallucination risk assessment for a code component.

    Quantifies the probability that AI-generated code contains
    errors that are syntactically valid but semantically wrong.
    """

    # Author attribution
    author_type: AuthorType = AuthorType.HUMAN
    ai_confidence: float = 1.0  # How confident the AI was (if available)

    # Hallucination indicators
    base_hallucination_risk: float = 0.0  # 0.0 for human, 0.02-0.15 for AI
    uses_nonexistent_api: float = 0.0  # P(calls API that doesn't exist)
    wrong_argument_order: float = 0.0  # P(argument types/order are wrong)
    incorrect_error_handling: float = 0.0  # P(error paths are wrong)
    stale_dependency: float = 0.0  # P(depends on deprecated/removed code)

    # Verification status
    has_tests: bool = False  # Is this code covered by tests?
    tests_pass: bool = False  # Do the tests actually pass?
    human_reviewed: bool = False  # Has a human reviewed this?
    type_checked: bool = False  # Did it pass type checking?

    @property
    def composite_risk(self) -> float:
        """Calculate composite hallucination risk score (0.0 - 1.0).

        Factors:
        - Base risk from author type
        - Specific hallucination indicators
        - Verification discounts (tests, review, types reduce risk)
        """
        # Start with base risk
        risk = self.base_hallucination_risk

        # Add specific indicators (weighted)
        risk += self.uses_nonexistent_api * 0.4
        risk += self.wrong_argument_order * 0.2
        risk += self.incorrect_error_handling * 0.25
        risk += self.stale_dependency * 0.15

        # Verification discounts
        if self.has_tests and self.tests_pass:
            risk *= 0.3  # 70% reduction if tested
        if self.human_reviewed:
            risk *= 0.5  # 50% reduction if reviewed
        if self.type_checked:
            risk *= 0.7  # 30% reduction if type-checked

        return min(risk, 1.0)


class DiffImpact(BaseModel):
    """Impact analysis of a code diff (PR/commit).

    Captures what changed and the estimated runtime impact.
    """

    file_path: str = ""
    language: CodeLanguage = CodeLanguage.UNKNOWN
    lines_added: int = 0
    lines_removed: int = 0
    functions_added: list[str] = Field(default_factory=list)
    functions_modified: list[str] = Field(default_factory=list)
    functions_removed: list[str] = Field(default_factory=list)

    # Complexity change
    complexity_before: ComplexityClass = ComplexityClass.UNKNOWN
    complexity_after: ComplexityClass = ComplexityClass.UNKNOWN

    # Cost change
    cost_before: RuntimeCostProfile = Field(default_factory=RuntimeCostProfile)
    cost_after: RuntimeCostProfile = Field(default_factory=RuntimeCostProfile)

    # AI attribution
    hallucination_risk: HallucinationRiskProfile = Field(
        default_factory=HallucinationRiskProfile
    )

    @property
    def cpu_delta_ms(self) -> float:
        """Estimated CPU cost change per call."""
        return self.cost_after.estimated_cpu_ms_per_call - self.cost_before.estimated_cpu_ms_per_call

    @property
    def memory_delta_mb(self) -> float:
        """Estimated memory change per call."""
        return self.cost_after.estimated_memory_mb_per_call - self.cost_before.estimated_memory_mb_per_call

    @property
    def io_delta(self) -> int:
        """Change in I/O calls per invocation."""
        return (
            self.cost_after.estimated_io_calls_per_invocation
            - self.cost_before.estimated_io_calls_per_invocation
        )

    @property
    def is_regression(self) -> bool:
        """Does this diff increase runtime cost?"""
        return self.cpu_delta_ms > 0 or self.memory_delta_mb > 0 or self.io_delta > 0


class CodeComponent(BaseModel):
    """A code-level component in the FaultRay graph.

    Represents a module, service, or function that can be
    connected to infrastructure components via dependencies.
    """

    id: str
    name: str
    file_path: str = ""
    language: CodeLanguage = CodeLanguage.UNKNOWN
    entry_point: str = ""  # e.g., "main", "handler", "api.routes"

    # Runtime characteristics
    runtime_cost: RuntimeCostProfile = Field(default_factory=RuntimeCostProfile)
    calls_per_minute: float = 0.0  # Expected invocation frequency

    # AI risk
    hallucination_risk: HallucinationRiskProfile = Field(
        default_factory=HallucinationRiskProfile
    )

    # Infrastructure mapping
    infra_component_id: str = ""  # Which infra component runs this code
    depends_on_components: list[str] = Field(default_factory=list)  # Other code components

    @property
    def estimated_cpu_load_percent(self) -> float:
        """Estimated CPU contribution from this code (0-100).

        Based on calls_per_minute * cpu_ms_per_call.
        """
        if self.calls_per_minute <= 0:
            return 0.0
        total_cpu_ms_per_minute = self.calls_per_minute * self.runtime_cost.estimated_cpu_ms_per_call
        # 60,000 ms in a minute, percentage of single core
        return min((total_cpu_ms_per_minute / 60_000) * 100, 100.0)

    @property
    def estimated_memory_load_mb(self) -> float:
        """Estimated memory contribution from concurrent invocations."""
        if self.calls_per_minute <= 0:
            return 0.0
        # Assume average concurrency = calls_per_minute * avg_duration_seconds / 60
        avg_duration_s = self.runtime_cost.estimated_cpu_ms_per_call / 1000
        avg_concurrency = self.calls_per_minute * avg_duration_s / 60
        return avg_concurrency * self.runtime_cost.estimated_memory_mb_per_call

    @property
    def risk_score(self) -> float:
        """Composite risk score (0.0 - 1.0) combining runtime cost and AI risk.

        High runtime cost + high hallucination risk = highest danger.
        """
        # Normalize CPU load (0-1)
        cpu_risk = min(self.estimated_cpu_load_percent / 100, 1.0)

        # Hallucination risk
        ai_risk = self.hallucination_risk.composite_risk

        # Combined: weighted sum (AI risk is weighted higher because
        # a hallucinated hot path is more dangerous than a slow but correct one)
        return min(cpu_risk * 0.3 + ai_risk * 0.7, 1.0)
