# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Cache Invalidation Strategy Analyzer.

Analyzes cache invalidation patterns and their impact on system resilience.
Covers TTL-based, event-driven, write-through, write-behind, and write-around
strategies. Models cache coherence protocols, thundering herd / cache stampede
scenarios, stale-while-revalidate patterns, multi-level cache hierarchies,
cache warming, tag/pattern-based invalidation scoping, cache poisoning risk,
eviction policies (LRU, LFU, ARC, FIFO), hit-rate modeling, and consistency
window analysis across cache layers.
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

from pydantic import BaseModel, Field

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_TTL_SECONDS: int = 300
_DEFAULT_ORIGIN_LATENCY_MS: float = 50.0
_STAMPEDE_CONCURRENCY_THRESHOLD: int = 50
_MAX_SCORE: float = 100.0


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InvalidationStrategy(str, Enum):
    """Cache invalidation strategies."""

    TTL_BASED = "ttl_based"
    EVENT_DRIVEN = "event_driven"
    WRITE_THROUGH = "write_through"
    WRITE_BEHIND = "write_behind"
    WRITE_AROUND = "write_around"


class EvictionPolicy(str, Enum):
    """Cache eviction policies."""

    LRU = "lru"
    LFU = "lfu"
    ARC = "arc"
    FIFO = "fifo"
    RANDOM = "random"
    TTL = "ttl"


class CoherenceState(str, Enum):
    """MESI-like cache coherence states for distributed caches."""

    MODIFIED = "modified"
    EXCLUSIVE = "exclusive"
    SHARED = "shared"
    INVALID = "invalid"


class CacheLevel(str, Enum):
    """Levels in a multi-level cache hierarchy."""

    L1_LOCAL = "l1_local"
    L2_SHARED = "l2_shared"
    CDN = "cdn"
    ORIGIN = "origin"


class InvalidationScope(str, Enum):
    """Scope of a cache invalidation operation."""

    SINGLE_KEY = "single_key"
    TAG_BASED = "tag_based"
    PATTERN_BASED = "pattern_based"
    FULL_FLUSH = "full_flush"


class StampedeRisk(str, Enum):
    """Risk level for thundering herd / cache stampede."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class CacheLayerConfig(BaseModel):
    """Configuration for a single cache layer in the hierarchy."""

    level: CacheLevel
    capacity_mb: float = Field(default=256.0, ge=0.0)
    ttl_seconds: int = Field(default=_DEFAULT_TTL_SECONDS, ge=0)
    eviction_policy: EvictionPolicy = EvictionPolicy.LRU
    hit_rate: float = Field(default=0.9, ge=0.0, le=1.0)
    latency_ms: float = Field(default=1.0, ge=0.0)
    replicas: int = Field(default=1, ge=1)
    stale_while_revalidate: bool = False
    stale_ttl_seconds: int = Field(default=0, ge=0)


class InvalidationConfig(BaseModel):
    """Configuration for the invalidation strategy being analyzed."""

    strategy: InvalidationStrategy = InvalidationStrategy.TTL_BASED
    scope: InvalidationScope = InvalidationScope.SINGLE_KEY
    layers: list[CacheLayerConfig] = Field(default_factory=list)
    event_propagation_delay_ms: float = Field(default=10.0, ge=0.0)
    write_buffer_size: int = Field(default=100, ge=0)
    write_buffer_flush_interval_ms: float = Field(default=1000.0, ge=0.0)
    origin_latency_ms: float = Field(default=_DEFAULT_ORIGIN_LATENCY_MS, ge=0.0)
    concurrent_readers: int = Field(default=100, ge=0)
    tags_per_key: int = Field(default=1, ge=0)
    pattern_regex_cost_ms: float = Field(default=0.5, ge=0.0)


class CoherenceTransition(BaseModel):
    """A single state transition in the coherence protocol."""

    node_id: str
    from_state: CoherenceState
    to_state: CoherenceState
    trigger: str = ""
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


class StampedeAnalysis(BaseModel):
    """Analysis of thundering herd / cache stampede risk."""

    risk_level: StampedeRisk = StampedeRisk.NONE
    estimated_concurrent_misses: int = 0
    origin_load_multiplier: float = Field(default=1.0, ge=0.0)
    estimated_recovery_ms: float = Field(default=0.0, ge=0.0)
    mitigations: list[str] = Field(default_factory=list)


class ConsistencyWindow(BaseModel):
    """Describes the consistency gap between cache layers."""

    layer_pair: tuple[str, str] = ("", "")
    max_staleness_ms: float = Field(default=0.0, ge=0.0)
    expected_staleness_ms: float = Field(default=0.0, ge=0.0)
    stale_reads_percent: float = Field(default=0.0, ge=0.0, le=100.0)


class HitRateModel(BaseModel):
    """Modeled hit rate for a cache configuration."""

    effective_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    cold_start_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    steady_state_hit_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    warm_up_time_seconds: float = Field(default=0.0, ge=0.0)
    eviction_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    recommendations: list[str] = Field(default_factory=list)


class CachePoisoningRisk(BaseModel):
    """Risk assessment for cache poisoning attacks."""

    risk_score: float = Field(default=0.0, ge=0.0, le=_MAX_SCORE)
    vulnerable_layers: list[str] = Field(default_factory=list)
    attack_vectors: list[str] = Field(default_factory=list)
    mitigations: list[str] = Field(default_factory=list)


class EvictionAnalysis(BaseModel):
    """Analysis of eviction policy behaviour under memory pressure."""

    policy: EvictionPolicy
    estimated_eviction_rate: float = Field(default=0.0, ge=0.0)
    hit_rate_under_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    fairness_score: float = Field(default=0.0, ge=0.0, le=_MAX_SCORE)
    recommendations: list[str] = Field(default_factory=list)


class CacheInvalidationReport(BaseModel):
    """Full report from the cache invalidation strategy analysis."""

    strategy: InvalidationStrategy
    overall_score: float = Field(default=0.0, ge=0.0, le=_MAX_SCORE)
    stampede_analysis: StampedeAnalysis = Field(
        default_factory=StampedeAnalysis,
    )
    consistency_windows: list[ConsistencyWindow] = Field(default_factory=list)
    hit_rate_model: HitRateModel = Field(default_factory=HitRateModel)
    poisoning_risk: CachePoisoningRisk = Field(
        default_factory=CachePoisoningRisk,
    )
    eviction_analyses: list[EvictionAnalysis] = Field(default_factory=list)
    coherence_transitions: list[CoherenceTransition] = Field(
        default_factory=list,
    )
    recommendations: list[str] = Field(default_factory=list)
    analyzed_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _clamp(value: float, lo: float = 0.0, hi: float = _MAX_SCORE) -> float:
    """Clamp *value* between *lo* and *hi* inclusive."""
    return max(lo, min(hi, value))


def _effective_multilayer_hit_rate(layers: Sequence[CacheLayerConfig]) -> float:
    """Calculate the effective hit rate across a multi-level cache hierarchy.

    Each successive layer only receives the misses from the previous layer.
    The effective hit rate is:  1 - product(1 - layer_hit_rate for each layer).
    """
    if not layers:
        return 0.0
    miss_rate = 1.0
    for layer in layers:
        miss_rate *= (1.0 - layer.hit_rate)
    return _clamp(1.0 - miss_rate, 0.0, 1.0)


def _compute_warm_up_seconds(layers: Sequence[CacheLayerConfig]) -> float:
    """Estimate warm-up time as the max TTL across layers.

    During cold start, caches need roughly one TTL cycle to reach their
    steady-state hit rate.
    """
    if not layers:
        return 0.0
    return float(max(layer.ttl_seconds for layer in layers))


def _eviction_pressure(layer: CacheLayerConfig, working_set_mb: float) -> float:
    """Estimate eviction pressure as ratio of working set to capacity.

    Returns a value in [0.0, 1.0] where 1.0 means extreme pressure.
    """
    if layer.capacity_mb <= 0:
        return 1.0
    return _clamp(working_set_mb / layer.capacity_mb, 0.0, 1.0)


def _stampede_risk_level(concurrent_misses: int) -> StampedeRisk:
    """Classify thundering herd risk based on concurrent misses."""
    if concurrent_misses <= 0:
        return StampedeRisk.NONE
    if concurrent_misses < 10:
        return StampedeRisk.LOW
    if concurrent_misses < _STAMPEDE_CONCURRENCY_THRESHOLD:
        return StampedeRisk.MEDIUM
    if concurrent_misses < 200:
        return StampedeRisk.HIGH
    return StampedeRisk.CRITICAL


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class CacheInvalidationEngine:
    """Analyzes cache invalidation strategies and their resilience impact.

    This engine evaluates:
    * Thundering herd / cache stampede risk
    * Multi-level cache hierarchy consistency windows
    * Hit-rate modelling (cold-start, steady-state, eviction pressure)
    * Cache coherence protocol transitions
    * Cache poisoning risk assessment
    * Eviction policy behaviour under memory pressure
    * Invalidation scope cost analysis
    """

    # ---- Stampede analysis ------------------------------------------------

    def analyze_stampede(
        self,
        config: InvalidationConfig,
    ) -> StampedeAnalysis:
        """Analyze thundering herd / cache stampede risk.

        When a popular cache key expires, many concurrent readers may hit
        the origin simultaneously.  This method estimates the blast radius
        and suggests mitigations.
        """
        concurrent = config.concurrent_readers
        # With stale-while-revalidate the effective concurrent misses
        # are dramatically reduced.
        has_swr = any(
            layer.stale_while_revalidate for layer in config.layers
        )
        if has_swr:
            effective_misses = max(1, concurrent // 10)
        elif config.strategy == InvalidationStrategy.EVENT_DRIVEN:
            # Event-driven invalidation avoids bulk expiry storms.
            effective_misses = max(1, concurrent // 5)
        else:
            effective_misses = concurrent

        risk = _stampede_risk_level(effective_misses)
        origin_multiplier = effective_misses / max(1, 1)

        recovery_ms = config.origin_latency_ms * math.log2(
            max(2, effective_misses)
        )

        mitigations: list[str] = []
        if risk in (StampedeRisk.HIGH, StampedeRisk.CRITICAL):
            if not has_swr:
                mitigations.append(
                    "Enable stale-while-revalidate to serve stale data "
                    "while refreshing in the background."
                )
            mitigations.append(
                "Implement request coalescing / singleflight to collapse "
                "concurrent origin fetches into a single request."
            )
            mitigations.append(
                "Add jitter to TTL values to prevent synchronized expiry."
            )
        if risk == StampedeRisk.CRITICAL:
            mitigations.append(
                "Consider a probabilistic early expiration (PER) strategy "
                "to spread revalidation over time."
            )

        return StampedeAnalysis(
            risk_level=risk,
            estimated_concurrent_misses=effective_misses,
            origin_load_multiplier=origin_multiplier,
            estimated_recovery_ms=round(recovery_ms, 2),
            mitigations=mitigations,
        )

    # ---- Consistency window analysis --------------------------------------

    def analyze_consistency_windows(
        self,
        config: InvalidationConfig,
    ) -> list[ConsistencyWindow]:
        """Analyze consistency gaps between cache layers.

        For each pair of adjacent cache layers the maximum and expected
        staleness are derived from TTL differences and event propagation
        delay.
        """
        layers = config.layers
        if len(layers) < 2:
            return []

        windows: list[ConsistencyWindow] = []
        for i in range(len(layers) - 1):
            upper = layers[i]
            lower = layers[i + 1]

            if config.strategy == InvalidationStrategy.EVENT_DRIVEN:
                max_staleness = config.event_propagation_delay_ms
                expected_staleness = config.event_propagation_delay_ms / 2.0
            elif config.strategy in (
                InvalidationStrategy.WRITE_THROUGH,
                InvalidationStrategy.WRITE_BEHIND,
            ):
                max_staleness = float(abs(upper.ttl_seconds - lower.ttl_seconds)) * 1000.0
                if config.strategy == InvalidationStrategy.WRITE_BEHIND:
                    max_staleness += config.write_buffer_flush_interval_ms
                expected_staleness = max_staleness / 2.0
            else:
                # TTL-based / write-around
                max_staleness = float(max(upper.ttl_seconds, lower.ttl_seconds)) * 1000.0
                expected_staleness = max_staleness / 2.0

            # Stale reads estimate — higher staleness ⇒ more stale reads.
            total_ttl = float(upper.ttl_seconds + lower.ttl_seconds) or 1.0
            stale_pct = _clamp(
                (max_staleness / (total_ttl * 1000.0)) * 100.0,
                0.0,
                100.0,
            )

            windows.append(
                ConsistencyWindow(
                    layer_pair=(upper.level.value, lower.level.value),
                    max_staleness_ms=round(max_staleness, 2),
                    expected_staleness_ms=round(expected_staleness, 2),
                    stale_reads_percent=round(stale_pct, 2),
                )
            )
        return windows

    # ---- Hit-rate modelling -----------------------------------------------

    def model_hit_rate(
        self,
        config: InvalidationConfig,
        working_set_mb: float = 128.0,
    ) -> HitRateModel:
        """Model effective hit rate considering all cache layers.

        Accounts for cold-start, steady-state, eviction pressure, and the
        chosen invalidation strategy.
        """
        layers = config.layers
        if not layers:
            return HitRateModel(
                recommendations=["Add at least one cache layer to improve performance."],
            )

        steady = _effective_multilayer_hit_rate(layers)
        warm_up = _compute_warm_up_seconds(layers)

        # Cold-start is typically ~10-30% of steady state, improving linearly
        cold = steady * 0.1

        # Strategy adjustment — event-driven gets a small boost because it
        # can pre-populate caches proactively.
        strategy_boost = 0.0
        if config.strategy == InvalidationStrategy.EVENT_DRIVEN:
            strategy_boost = 0.02
        elif config.strategy == InvalidationStrategy.WRITE_THROUGH:
            strategy_boost = 0.01
        steady = _clamp(steady + strategy_boost, 0.0, 1.0)

        # Eviction pressure — average across layers
        pressures = [
            _eviction_pressure(layer, working_set_mb / max(len(layers), 1))
            for layer in layers
        ]
        avg_pressure = sum(pressures) / len(pressures)

        # High eviction pressure degrades the effective hit rate
        effective = steady * (1.0 - avg_pressure * 0.3)
        effective = _clamp(effective, 0.0, 1.0)

        recs: list[str] = []
        if effective < 0.8:
            recs.append(
                "Effective hit rate is below 80%. Consider increasing cache "
                "capacity or tuning TTL values."
            )
        if avg_pressure > 0.7:
            recs.append(
                "High eviction pressure detected. Increase cache capacity or "
                "reduce the working set size."
            )
        if warm_up > 600:
            recs.append(
                "Cache warm-up time exceeds 10 minutes. Consider implementing "
                "a cache warming strategy for faster cold-start recovery."
            )

        return HitRateModel(
            effective_hit_rate=round(effective, 4),
            cold_start_hit_rate=round(cold, 4),
            steady_state_hit_rate=round(steady, 4),
            warm_up_time_seconds=round(warm_up, 2),
            eviction_pressure=round(avg_pressure, 4),
            recommendations=recs,
        )

    # ---- Cache coherence --------------------------------------------------

    def simulate_coherence_transitions(
        self,
        node_ids: Sequence[str],
        operation: str = "write",
    ) -> list[CoherenceTransition]:
        """Simulate MESI-like coherence protocol transitions.

        For a *write* operation the writing node transitions to MODIFIED and
        all other nodes are INVALIDATED.  For a *read* the reading node
        transitions to SHARED (or EXCLUSIVE when alone).
        """
        if not node_ids:
            return []

        now = datetime.now(timezone.utc)
        transitions: list[CoherenceTransition] = []

        if operation == "write":
            writer = node_ids[0]
            transitions.append(
                CoherenceTransition(
                    node_id=writer,
                    from_state=CoherenceState.SHARED,
                    to_state=CoherenceState.MODIFIED,
                    trigger="local_write",
                    timestamp=now,
                )
            )
            for nid in node_ids[1:]:
                transitions.append(
                    CoherenceTransition(
                        node_id=nid,
                        from_state=CoherenceState.SHARED,
                        to_state=CoherenceState.INVALID,
                        trigger="remote_write_invalidation",
                        timestamp=now,
                    )
                )
        elif operation == "read":
            reader = node_ids[0]
            if len(node_ids) == 1:
                transitions.append(
                    CoherenceTransition(
                        node_id=reader,
                        from_state=CoherenceState.INVALID,
                        to_state=CoherenceState.EXCLUSIVE,
                        trigger="local_read_exclusive",
                        timestamp=now,
                    )
                )
            else:
                transitions.append(
                    CoherenceTransition(
                        node_id=reader,
                        from_state=CoherenceState.INVALID,
                        to_state=CoherenceState.SHARED,
                        trigger="local_read_shared",
                        timestamp=now,
                    )
                )
                for nid in node_ids[1:]:
                    transitions.append(
                        CoherenceTransition(
                            node_id=nid,
                            from_state=CoherenceState.EXCLUSIVE,
                            to_state=CoherenceState.SHARED,
                            trigger="remote_read_downgrade",
                            timestamp=now,
                        )
                    )

        return transitions

    # ---- Cache poisoning risk ---------------------------------------------

    def assess_poisoning_risk(
        self,
        config: InvalidationConfig,
        graph: InfraGraph | None = None,
    ) -> CachePoisoningRisk:
        """Assess the risk of cache poisoning.

        Cache poisoning occurs when an attacker injects malicious content
        into a cache layer, causing stale or harmful data to be served.
        Factors: TTL length, validation mechanisms, number of public-facing
        layers, and invalidation strategy strength.
        """
        score = 0.0
        vulnerable: list[str] = []
        vectors: list[str] = []
        mitigations: list[str] = []

        for layer in config.layers:
            # Long TTLs increase poisoning window
            if layer.ttl_seconds > 3600:
                score += 15.0
                vulnerable.append(layer.level.value)
                vectors.append(
                    f"Long TTL ({layer.ttl_seconds}s) on {layer.level.value} "
                    f"increases poisoning window."
                )

            # CDN layers are externally accessible
            if layer.level == CacheLevel.CDN:
                score += 20.0
                if layer.level.value not in vulnerable:
                    vulnerable.append(layer.level.value)
                vectors.append(
                    "CDN layer is publicly accessible and susceptible to "
                    "host-header / request-smuggling poisoning."
                )

            # Single replica has no cross-validation
            if layer.replicas <= 1:
                score += 5.0

        # Strategy-based adjustments
        if config.strategy == InvalidationStrategy.TTL_BASED:
            score += 10.0
            vectors.append(
                "TTL-based invalidation relies solely on time expiry — "
                "poisoned entries persist until TTL expiry."
            )
        elif config.strategy == InvalidationStrategy.EVENT_DRIVEN:
            score -= 10.0
            mitigations.append(
                "Event-driven invalidation can quickly purge poisoned entries."
            )

        # Write-through validation reduces risk
        if config.strategy == InvalidationStrategy.WRITE_THROUGH:
            score -= 5.0
            mitigations.append(
                "Write-through ensures origin validation on every write."
            )

        # Check graph for security posture
        if graph:
            for comp in graph.components.values():
                if comp.type == ComponentType.CACHE:
                    if not comp.security.encryption_in_transit:
                        score += 10.0
                        vectors.append(
                            f"Cache component '{comp.id}' lacks encryption in "
                            f"transit — vulnerable to MITM poisoning."
                        )
                    if not comp.security.auth_required:
                        score += 10.0
                        vectors.append(
                            f"Cache component '{comp.id}' has no authentication "
                            f"— open to unauthorized writes."
                        )

        if not mitigations:
            mitigations.append(
                "Implement cache response validation (e.g. signature/hash) "
                "to detect tampered entries."
            )
            mitigations.append(
                "Use short TTLs for sensitive or user-facing content."
            )

        return CachePoisoningRisk(
            risk_score=_clamp(score),
            vulnerable_layers=vulnerable,
            attack_vectors=vectors,
            mitigations=mitigations,
        )

    # ---- Eviction policy analysis -----------------------------------------

    def analyze_eviction_policy(
        self,
        layer: CacheLayerConfig,
        working_set_mb: float = 128.0,
    ) -> EvictionAnalysis:
        """Analyze eviction policy behaviour under memory pressure.

        Different eviction policies have different trade-offs regarding hit
        rate, fairness, and computational cost.
        """
        pressure = _eviction_pressure(layer, working_set_mb)
        policy = layer.eviction_policy

        # Base hit rate under pressure varies by policy
        policy_effectiveness: dict[EvictionPolicy, float] = {
            EvictionPolicy.LRU: 0.85,
            EvictionPolicy.LFU: 0.90,
            EvictionPolicy.ARC: 0.93,
            EvictionPolicy.FIFO: 0.70,
            EvictionPolicy.RANDOM: 0.60,
            EvictionPolicy.TTL: 0.75,
        }

        base = policy_effectiveness.get(policy, 0.7)
        hit_under_pressure = base * (1.0 - pressure * 0.4)
        hit_under_pressure = _clamp(hit_under_pressure, 0.0, 1.0)

        # Fairness — how evenly the policy treats different access patterns
        fairness_map: dict[EvictionPolicy, float] = {
            EvictionPolicy.LRU: 75.0,
            EvictionPolicy.LFU: 60.0,  # biased toward frequent items
            EvictionPolicy.ARC: 90.0,  # adaptive, balances recency/frequency
            EvictionPolicy.FIFO: 85.0,
            EvictionPolicy.RANDOM: 95.0,  # perfectly fair but suboptimal
            EvictionPolicy.TTL: 70.0,
        }
        fairness = fairness_map.get(policy, 50.0)

        eviction_rate = pressure * layer.hit_rate * 1000.0  # evictions/sec estimate

        recs: list[str] = []
        if pressure > 0.8:
            recs.append(
                f"Memory pressure is {pressure:.0%}. Increase cache capacity "
                f"for {layer.level.value}."
            )
        if policy == EvictionPolicy.FIFO and pressure > 0.5:
            recs.append(
                "FIFO eviction performs poorly under pressure. Consider LRU or ARC."
            )
        if policy == EvictionPolicy.RANDOM:
            recs.append(
                "RANDOM eviction is fair but suboptimal. Consider LRU or ARC "
                "for better hit rates."
            )
        if policy == EvictionPolicy.LFU and pressure > 0.6:
            recs.append(
                "LFU may starve new entries under high pressure. Consider ARC "
                "which balances recency and frequency."
            )

        return EvictionAnalysis(
            policy=policy,
            estimated_eviction_rate=round(eviction_rate, 2),
            hit_rate_under_pressure=round(hit_under_pressure, 4),
            fairness_score=fairness,
            recommendations=recs,
        )

    # ---- Invalidation scope cost ------------------------------------------

    def estimate_invalidation_cost(
        self,
        config: InvalidationConfig,
        num_keys: int = 1000,
    ) -> dict[str, float]:
        """Estimate the cost (latency) of an invalidation operation.

        Returns a dict with per-scope cost in milliseconds and the estimated
        number of keys affected.
        """
        scope = config.scope
        base_per_key_ms = 0.05  # 50 microseconds per key

        if scope == InvalidationScope.SINGLE_KEY:
            affected = 1
            cost = base_per_key_ms
        elif scope == InvalidationScope.TAG_BASED:
            affected = max(1, num_keys // config.tags_per_key) if config.tags_per_key > 0 else num_keys
            cost = affected * base_per_key_ms * 1.2  # tag lookup overhead
        elif scope == InvalidationScope.PATTERN_BASED:
            affected = max(1, num_keys // 5)  # heuristic: 20% match
            cost = affected * base_per_key_ms + config.pattern_regex_cost_ms * math.log2(max(2, num_keys))
        else:
            # FULL_FLUSH
            affected = num_keys
            cost = num_keys * base_per_key_ms

        # Multi-layer propagation
        layer_count = max(len(config.layers), 1)
        total_cost = cost * layer_count + config.event_propagation_delay_ms * (layer_count - 1)

        return {
            "scope": scope.value,
            "affected_keys": float(affected),
            "per_layer_cost_ms": round(cost, 4),
            "total_cost_ms": round(total_cost, 4),
            "layer_count": float(layer_count),
        }

    # ---- Cache warming analysis -------------------------------------------

    def analyze_cache_warming(
        self,
        config: InvalidationConfig,
        cold_start: bool = True,
    ) -> dict[str, object]:
        """Analyze cache warming strategies and cold-start impact.

        Returns warming time estimates, recommended pre-population strategy,
        and cold-start traffic impact.
        """
        layers = config.layers
        if not layers:
            return {
                "warming_needed": False,
                "warming_time_seconds": 0.0,
                "cold_start_impact": "none",
                "recommendations": ["No cache layers configured."],
            }

        max_ttl = max(layer.ttl_seconds for layer in layers)
        total_capacity = sum(layer.capacity_mb for layer in layers)

        # Warming time is proportional to total capacity and origin latency
        items_estimate = (total_capacity * 1024) / 4  # ~4KB average item
        warming_time = (items_estimate * config.origin_latency_ms) / 1000.0

        if cold_start:
            impact = "high" if warming_time > 300 else ("medium" if warming_time > 60 else "low")
        else:
            impact = "none"

        recs: list[str] = []
        if warming_time > 300:
            recs.append(
                "Consider pre-populating caches from a snapshot during "
                "deployment to reduce cold-start impact."
            )
        if any(layer.level == CacheLevel.CDN for layer in layers):
            recs.append(
                "CDN cache warming requires synthetic traffic or origin-push. "
                "Schedule warming before traffic cutover."
            )
        has_swr = any(layer.stale_while_revalidate for layer in layers)
        if not has_swr and cold_start:
            recs.append(
                "Enable stale-while-revalidate during warming to serve stale "
                "data while populating fresh entries."
            )

        return {
            "warming_needed": cold_start,
            "warming_time_seconds": round(warming_time, 2),
            "cold_start_impact": impact,
            "max_ttl_seconds": max_ttl,
            "total_capacity_mb": total_capacity,
            "recommendations": recs,
        }

    # ---- Full analysis ----------------------------------------------------

    def analyze(
        self,
        config: InvalidationConfig,
        graph: InfraGraph | None = None,
        working_set_mb: float = 128.0,
    ) -> CacheInvalidationReport:
        """Run full cache invalidation strategy analysis.

        Combines stampede analysis, consistency window analysis, hit-rate
        modelling, coherence simulation, poisoning risk, and eviction
        analysis into a comprehensive report with an overall score.
        """
        stampede = self.analyze_stampede(config)
        consistency = self.analyze_consistency_windows(config)
        hit_rate = self.model_hit_rate(config, working_set_mb)
        poisoning = self.assess_poisoning_risk(config, graph)

        # Eviction analysis per layer
        evictions: list[EvictionAnalysis] = []
        for layer in config.layers:
            evictions.append(
                self.analyze_eviction_policy(
                    layer,
                    working_set_mb / max(len(config.layers), 1),
                )
            )

        # Coherence transitions for cache-type components in the graph
        coherence: list[CoherenceTransition] = []
        if graph:
            cache_ids = [
                cid
                for cid, comp in graph.components.items()
                if comp.type == ComponentType.CACHE
            ]
            if cache_ids:
                coherence = self.simulate_coherence_transitions(
                    cache_ids, "write"
                )

        # ---- Overall score calculation ------------------------------------
        score = _MAX_SCORE

        # Stampede risk penalty
        stampede_penalties = {
            StampedeRisk.NONE: 0,
            StampedeRisk.LOW: 5,
            StampedeRisk.MEDIUM: 15,
            StampedeRisk.HIGH: 25,
            StampedeRisk.CRITICAL: 40,
        }
        score -= stampede_penalties.get(stampede.risk_level, 0)

        # Hit-rate penalty — lower hit rate ⇒ lower score
        if hit_rate.effective_hit_rate < 1.0:
            score -= (1.0 - hit_rate.effective_hit_rate) * 20.0

        # Poisoning risk penalty
        score -= poisoning.risk_score * 0.2

        # Consistency window penalty — large staleness degrades score
        if consistency:
            max_staleness = max(w.max_staleness_ms for w in consistency)
            if max_staleness > 60_000:  # > 1 min
                score -= 10.0
            elif max_staleness > 10_000:  # > 10 sec
                score -= 5.0

        # Eviction pressure penalty
        if hit_rate.eviction_pressure > 0.7:
            score -= 10.0

        score = _clamp(score)

        # ---- Recommendations aggregation ----------------------------------
        all_recs: list[str] = []
        all_recs.extend(stampede.mitigations)
        all_recs.extend(hit_rate.recommendations)
        all_recs.extend(poisoning.mitigations)
        for ev in evictions:
            all_recs.extend(ev.recommendations)

        # Strategy-specific recommendations
        if config.strategy == InvalidationStrategy.WRITE_BEHIND:
            all_recs.append(
                "Write-behind introduces a risk of data loss if the buffer "
                "is not flushed before a crash. Ensure durable buffering."
            )
        if config.strategy == InvalidationStrategy.WRITE_AROUND:
            all_recs.append(
                "Write-around causes cache misses on recently written data. "
                "Pair with background cache warming for frequently accessed keys."
            )
        if config.scope == InvalidationScope.FULL_FLUSH:
            all_recs.append(
                "Full cache flush is expensive and causes a cold-start storm. "
                "Prefer tag-based or pattern-based invalidation."
            )

        # Deduplicate
        seen: set[str] = set()
        unique_recs: list[str] = []
        for rec in all_recs:
            if rec not in seen:
                seen.add(rec)
                unique_recs.append(rec)

        return CacheInvalidationReport(
            strategy=config.strategy,
            overall_score=round(score, 1),
            stampede_analysis=stampede,
            consistency_windows=consistency,
            hit_rate_model=hit_rate,
            poisoning_risk=poisoning,
            eviction_analyses=evictions,
            coherence_transitions=coherence,
            recommendations=unique_recs,
        )

    # ---- Graph-aware helpers ----------------------------------------------

    def find_cache_components(
        self,
        graph: InfraGraph,
    ) -> list[Component]:
        """Return all cache-type components from the infrastructure graph."""
        return [
            comp
            for comp in graph.components.values()
            if comp.type == ComponentType.CACHE
        ]

    def assess_graph_cache_resilience(
        self,
        graph: InfraGraph,
        config: InvalidationConfig | None = None,
    ) -> dict[str, object]:
        """Assess overall cache resilience for an infrastructure graph.

        Identifies cache components, checks for single-points-of-failure,
        evaluates redundancy, and optionally runs full invalidation analysis.
        """
        caches = self.find_cache_components(graph)
        if not caches:
            return {
                "cache_count": 0,
                "spof_caches": [],
                "redundant_caches": [],
                "overall_risk": "high",
                "recommendations": [
                    "No cache components found in the infrastructure graph."
                ],
            }

        spof: list[str] = []
        redundant: list[str] = []
        for c in caches:
            dependents = graph.get_dependents(c.id)
            if c.replicas <= 1 and len(dependents) > 0:
                spof.append(c.id)
            else:
                redundant.append(c.id)

        risk = "low"
        if len(spof) > len(redundant):
            risk = "high"
        elif spof:
            risk = "medium"

        recs: list[str] = []
        for sid in spof:
            recs.append(
                f"Cache '{sid}' is a single point of failure with dependents. "
                f"Add replicas or a failover cache."
            )

        result: dict[str, object] = {
            "cache_count": len(caches),
            "spof_caches": spof,
            "redundant_caches": redundant,
            "overall_risk": risk,
            "recommendations": recs,
        }

        if config is not None:
            report = self.analyze(config, graph)
            result["invalidation_report"] = report

        return result
