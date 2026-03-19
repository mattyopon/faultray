"""ML-Based Dependency Inference Engine.

Infers hidden dependencies between infrastructure components by analyzing
statistical correlations in metrics, traffic patterns, and failure co-occurrence.
Uses ONLY the Python standard library -- no numpy, scipy, or scikit-learn.

Algorithms implemented:
- Pearson correlation with lagged causality detection (Granger-like)
- Dynamic Time Warping (DTW) for traffic pattern similarity
- Jaccard similarity for failure co-occurrence analysis
- Weighted multi-method confidence fusion

Example usage::

    from faultray.discovery.ml_dependency_inference import (
        DependencyInferenceEngine,
        IncidentRecord,
        MetricSnapshot,
        TrafficSnapshot,
    )
    from faultray.model.graph import InfraGraph

    graph = InfraGraph.load(Path("model.json"))

    # Build metric history
    metrics = [
        MetricSnapshot(timestamp=0.0, component_id="web", cpu=80.0,
                       memory=60.0, latency=50.0, rps=1000.0, error_rate=0.01),
        MetricSnapshot(timestamp=1.0, component_id="db", cpu=70.0,
                       memory=55.0, latency=40.0, rps=800.0, error_rate=0.005),
        # ... more snapshots at regular intervals
    ]

    engine = DependencyInferenceEngine()
    inferred = engine.infer_all(graph, metrics, traffic_data=[], incident_history=[])
    added = engine.apply_inferred(graph, inferred, min_confidence=0.7)
    print(f"Added {added} inferred dependencies to graph")
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import combinations

from faultray.model.components import Dependency
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MetricSnapshot:
    """A single point-in-time metric observation for a component."""

    timestamp: float  # epoch seconds or monotonic index
    component_id: str
    cpu: float = 0.0
    memory: float = 0.0
    latency: float = 0.0
    rps: float = 0.0
    error_rate: float = 0.0


@dataclass
class TrafficSnapshot:
    """A single point-in-time traffic observation for a component."""

    timestamp: float
    component_id: str
    request_count: float = 0.0
    response_time_ms: float = 0.0


@dataclass
class IncidentRecord:
    """A recorded incident affecting one or more components."""

    timestamp: float
    affected_component_ids: list[str] = field(default_factory=list)
    severity: str = "medium"  # critical / high / medium / low
    duration_seconds: float = 0.0


@dataclass
class InferredDependency:
    """A dependency relationship inferred by statistical analysis."""

    source_id: str
    target_id: str
    confidence: float  # 0.0 - 1.0
    inference_method: str  # metrics_correlation / traffic_dtw / failure_cooccurrence
    evidence: dict = field(default_factory=dict)
    suggested_type: str = "requires"  # requires / optional / async


# ---------------------------------------------------------------------------
# Helper functions (stdlib only — math + statistics)
# ---------------------------------------------------------------------------


def _normalize(values: list[float]) -> list[float]:
    """Min-max normalize a list of floats to [0, 1].

    Returns zeros if all values are identical (zero range).
    """
    if not values:
        return []
    lo = min(values)
    hi = max(values)
    rng = hi - lo
    if rng == 0.0:
        return [0.0] * len(values)
    return [(v - lo) / rng for v in values]


def _mean(xs: list[float]) -> float:
    """Arithmetic mean."""
    if not xs:
        return 0.0
    return sum(xs) / len(xs)


def _pearson_correlation(x: list[float], y: list[float]) -> float:
    """Compute Pearson product-moment correlation coefficient.

    r = sum((xi - x_bar)(yi - y_bar)) / sqrt(sum((xi - x_bar)^2) * sum((yi - y_bar)^2))

    Returns 0.0 when either series has zero variance.
    """
    n = min(len(x), len(y))
    if n < 2:
        return 0.0

    x = x[:n]
    y = y[:n]
    x_bar = _mean(x)
    y_bar = _mean(y)

    num = 0.0
    den_x = 0.0
    den_y = 0.0
    for xi, yi in zip(x, y):
        dx = xi - x_bar
        dy = yi - y_bar
        num += dx * dy
        den_x += dx * dx
        den_y += dy * dy

    denom = math.sqrt(den_x * den_y)
    if denom == 0.0:
        return 0.0
    return num / denom


def _lagged_correlation(
    x: list[float],
    y: list[float],
    max_lag: int = 5,
) -> tuple[float, int]:
    """Find the lag that maximises abs(pearson_correlation(x, y[lag:])).

    Positive best_lag means x leads y by ``best_lag`` steps (x -> y causation).
    Negative best_lag means y leads x (y -> x causation).

    Returns (best_abs_correlation, best_lag).
    """
    best_corr = 0.0
    best_lag = 0

    for lag in range(-max_lag, max_lag + 1):
        if lag > 0:
            # x leads: correlate x[:-lag] with y[lag:]
            xp = x[: len(x) - lag]
            yp = y[lag:]
        elif lag < 0:
            # y leads: correlate x[-lag:] with y[:lag]  (lag is negative)
            xp = x[-lag:]
            yp = y[: len(y) + lag]
        else:
            xp = x
            yp = y

        if len(xp) < 3 or len(yp) < 3:
            continue

        r = _pearson_correlation(xp, yp)
        if abs(r) > abs(best_corr):
            best_corr = r
            best_lag = lag

    return best_corr, best_lag


def _dtw_distance(s: list[float], t: list[float]) -> float:
    """Compute Dynamic Time Warping distance between two time series.

    Uses a full DP matrix (O(n*m) time and space).  Adequate for the
    component-pair comparisons FaultRay performs (typical n, m < 1000).
    """
    n = len(s)
    m = len(t)
    if n == 0 or m == 0:
        return float("inf")

    # dp[i][j] = min cost to align s[:i+1] with t[:j+1]
    dp: list[list[float]] = [[float("inf")] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost = (s[i - 1] - t[j - 1]) ** 2
            dp[i][j] = cost + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])

    return math.sqrt(dp[n][m])


def _jaccard_similarity(set_a: set, set_b: set) -> float:
    """Jaccard similarity: |A ∩ B| / |A ∪ B|."""
    if not set_a and not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return 0.0
    return intersection / union


# ---------------------------------------------------------------------------
# Inference Engine
# ---------------------------------------------------------------------------


class DependencyInferenceEngine:
    """Infer hidden infrastructure dependencies from observational data.

    Three complementary inference methods are provided:

    1. **Metrics correlation** — Pearson + lagged correlation to detect
       causal metric co-movement between component pairs.
    2. **Traffic DTW** — Dynamic Time Warping on request-count time series
       to detect synchronous traffic patterns.
    3. **Failure co-occurrence** — Jaccard similarity on incident records
       to detect components that fail together.

    All methods use only the Python standard library.
    """

    def __init__(
        self,
        *,
        correlation_threshold: float = 0.7,
        dtw_distance_threshold: float = 0.3,
        jaccard_threshold: float = 0.5,
        max_lag: int = 5,
    ) -> None:
        self.correlation_threshold = correlation_threshold
        self.dtw_distance_threshold = dtw_distance_threshold
        self.jaccard_threshold = jaccard_threshold
        self.max_lag = max_lag

    # ------------------------------------------------------------------
    # Method 1: Metrics Correlation
    # ------------------------------------------------------------------

    def infer_from_metrics(
        self,
        graph: InfraGraph,
        metrics_history: list[MetricSnapshot],
    ) -> list[InferredDependency]:
        """Infer dependencies from metrics time-series correlation.

        For each component pair, computes Pearson correlation across
        multiple metric dimensions (cpu, memory, latency, rps, error_rate).
        Pairs exceeding ``correlation_threshold`` undergo lagged-correlation
        analysis to determine causation direction.
        """
        # Group snapshots by component, sorted by timestamp
        by_comp: dict[str, list[MetricSnapshot]] = {}
        for snap in metrics_history:
            by_comp.setdefault(snap.component_id, []).append(snap)
        for comp_snaps in by_comp.values():
            comp_snaps.sort(key=lambda s: s.timestamp)

        component_ids = sorted(by_comp.keys())
        results: list[InferredDependency] = []

        for a, b in combinations(component_ids, 2):
            snaps_a = by_comp[a]
            snaps_b = by_comp[b]

            # Extract aligned time series for each metric dimension
            metric_names = ["cpu", "memory", "latency", "rps", "error_rate"]
            best_corr = 0.0
            best_metric = ""

            for metric in metric_names:
                series_a = [getattr(s, metric) for s in snaps_a]
                series_b = [getattr(s, metric) for s in snaps_b]

                if len(series_a) < 3 or len(series_b) < 3:
                    continue

                # Instantaneous correlation
                r = abs(_pearson_correlation(series_a, series_b))
                if r > abs(best_corr):
                    best_corr = r
                    best_metric = metric

            if best_corr < self.correlation_threshold:
                continue

            # Lagged correlation to determine causation direction
            series_a = [getattr(s, best_metric) for s in snaps_a]
            series_b = [getattr(s, best_metric) for s in snaps_b]
            lag_corr, lag = _lagged_correlation(series_a, series_b, self.max_lag)

            # Determine direction: positive lag means a leads b
            if lag > 0:
                source, target = a, b
            elif lag < 0:
                source, target = b, a
            else:
                # No lag detected — use alphabetical order as tiebreaker
                source, target = (a, b) if a < b else (b, a)

            lag_confidence = 1.0 - (1.0 / (1.0 + abs(lag)))  # 0 for lag=0, approaches 1
            confidence = best_corr * max(0.3, lag_confidence)  # floor at 0.3 even with zero lag
            confidence = min(1.0, confidence)

            results.append(InferredDependency(
                source_id=source,
                target_id=target,
                confidence=round(confidence, 4),
                inference_method="metrics_correlation",
                evidence={
                    "best_metric": best_metric,
                    "pearson_r": round(best_corr, 4),
                    "lag_correlation": round(abs(lag_corr), 4),
                    "lag_steps": abs(lag),
                    "direction": f"{source} -> {target}",
                },
                suggested_type="requires" if confidence >= 0.8 else "optional",
            ))

        return results

    # ------------------------------------------------------------------
    # Method 2: Traffic DTW
    # ------------------------------------------------------------------

    def infer_from_traffic_correlation(
        self,
        graph: InfraGraph,
        traffic_data: list[TrafficSnapshot],
    ) -> list[InferredDependency]:
        """Infer dependencies from traffic pattern similarity using DTW.

        Components whose request-count time series have a small DTW
        distance (after normalization) are likely to share a dependency
        relationship — one forwards requests to the other.
        """
        by_comp: dict[str, list[TrafficSnapshot]] = {}
        for snap in traffic_data:
            by_comp.setdefault(snap.component_id, []).append(snap)
        for comp_snaps in by_comp.values():
            comp_snaps.sort(key=lambda s: s.timestamp)

        component_ids = sorted(by_comp.keys())
        results: list[InferredDependency] = []

        for a, b in combinations(component_ids, 2):
            series_a = _normalize([s.request_count for s in by_comp[a]])
            series_b = _normalize([s.request_count for s in by_comp[b]])

            if len(series_a) < 2 or len(series_b) < 2:
                continue

            dist = _dtw_distance(series_a, series_b)

            # Normalize distance by series length for comparability
            max_possible = math.sqrt(max(len(series_a), len(series_b)))
            if max_possible == 0:
                continue
            norm_dist = dist / max_possible

            if norm_dist > self.dtw_distance_threshold:
                continue

            confidence = max(0.0, min(1.0, 1.0 - norm_dist))

            # Use response time to guess direction: higher latency is downstream
            avg_rt_a = _mean([s.response_time_ms for s in by_comp[a]])
            avg_rt_b = _mean([s.response_time_ms for s in by_comp[b]])
            if avg_rt_a < avg_rt_b:
                source, target = a, b  # a is upstream (faster), b is downstream
            else:
                source, target = b, a

            results.append(InferredDependency(
                source_id=source,
                target_id=target,
                confidence=round(confidence, 4),
                inference_method="traffic_dtw",
                evidence={
                    "dtw_distance": round(dist, 4),
                    "normalized_distance": round(norm_dist, 4),
                    "series_length_a": len(series_a),
                    "series_length_b": len(series_b),
                    "avg_response_time_a_ms": round(avg_rt_a, 2),
                    "avg_response_time_b_ms": round(avg_rt_b, 2),
                },
                suggested_type="requires" if confidence >= 0.8 else "optional",
            ))

        return results

    # ------------------------------------------------------------------
    # Method 3: Failure Co-occurrence
    # ------------------------------------------------------------------

    def infer_from_failure_correlation(
        self,
        graph: InfraGraph,
        incident_history: list[IncidentRecord],
    ) -> list[InferredDependency]:
        """Infer dependencies from failure co-occurrence patterns.

        Components that appear together in incidents more often than
        expected (high Jaccard similarity) likely share a dependency.
        """
        if not incident_history:
            return []

        # Build per-component incident sets: component_id -> set of incident indices
        comp_incidents: dict[str, set[int]] = {}
        for idx, incident in enumerate(incident_history):
            for cid in incident.affected_component_ids:
                comp_incidents.setdefault(cid, set()).add(idx)

        component_ids = sorted(comp_incidents.keys())
        results: list[InferredDependency] = []

        for a, b in combinations(component_ids, 2):
            jaccard = _jaccard_similarity(comp_incidents[a], comp_incidents[b])

            if jaccard < self.jaccard_threshold:
                continue

            # Heuristic for direction: component appearing in more incidents
            # is likely the dependency (upstream) — its failure causes cascading.
            if len(comp_incidents[a]) >= len(comp_incidents[b]):
                source, target = b, a  # b depends on a (a fails more -> cascade)
            else:
                source, target = a, b

            results.append(InferredDependency(
                source_id=source,
                target_id=target,
                confidence=round(jaccard, 4),
                inference_method="failure_cooccurrence",
                evidence={
                    "jaccard_similarity": round(jaccard, 4),
                    "co_occurrence_count": len(comp_incidents[a] & comp_incidents[b]),
                    "incidents_a": len(comp_incidents[a]),
                    "incidents_b": len(comp_incidents[b]),
                    "total_incidents": len(incident_history),
                },
                suggested_type="requires" if jaccard >= 0.8 else "optional",
            ))

        return results

    # ------------------------------------------------------------------
    # Combined Inference
    # ------------------------------------------------------------------

    def infer_all(
        self,
        graph: InfraGraph,
        metrics_history: list[MetricSnapshot] | None = None,
        traffic_data: list[TrafficSnapshot] | None = None,
        incident_history: list[IncidentRecord] | None = None,
    ) -> list[InferredDependency]:
        """Run all inference methods and fuse results.

        When the same component pair is detected by multiple methods,
        confidences are merged using a weighted maximum:

        - If detected by 1 method: confidence as-is
        - If detected by 2 methods: max(c1, c2) * 1.1  (capped at 1.0)
        - If detected by 3 methods: max(c1, c2, c3) * 1.2 (capped at 1.0)

        Dependencies already present in the graph are excluded.
        Results are sorted by confidence descending.
        """
        all_inferred: list[InferredDependency] = []

        if metrics_history:
            all_inferred.extend(self.infer_from_metrics(graph, metrics_history))
        if traffic_data:
            all_inferred.extend(
                self.infer_from_traffic_correlation(graph, traffic_data)
            )
        if incident_history:
            all_inferred.extend(
                self.infer_from_failure_correlation(graph, incident_history)
            )

        # Merge duplicates (same pair detected by multiple methods)
        # Key by sorted pair to handle direction consistently
        pair_map: dict[tuple[str, str], list[InferredDependency]] = {}
        for dep in all_inferred:
            key = (dep.source_id, dep.target_id)
            # Also check reverse — different methods may infer opposite directions
            rev_key = (dep.target_id, dep.source_id)
            if key in pair_map:
                pair_map[key].append(dep)
            elif rev_key in pair_map:
                pair_map[rev_key].append(dep)
            else:
                pair_map[key] = [dep]

        # Build existing edges set for filtering
        existing_edges: set[tuple[str, str]] = set()
        for edge in graph.all_dependency_edges():
            existing_edges.add((edge.source_id, edge.target_id))

        merged: list[InferredDependency] = []
        for (src, tgt), deps in pair_map.items():
            # Skip if already in graph
            if (src, tgt) in existing_edges or (tgt, src) in existing_edges:
                continue

            n_methods = len(deps)
            max_conf = max(d.confidence for d in deps)

            # Boost for multi-method agreement
            if n_methods >= 3:
                fused_confidence = min(1.0, max_conf * 1.2)
            elif n_methods >= 2:
                fused_confidence = min(1.0, max_conf * 1.1)
            else:
                fused_confidence = max_conf

            # Merge evidence from all methods
            combined_evidence: dict = {}
            methods_used: list[str] = []
            for d in deps:
                methods_used.append(d.inference_method)
                combined_evidence[d.inference_method] = d.evidence

            combined_evidence["methods_count"] = n_methods
            combined_evidence["methods_used"] = methods_used

            # Suggested type from highest-confidence contributor
            best_dep = max(deps, key=lambda d: d.confidence)

            merged.append(InferredDependency(
                source_id=src,
                target_id=tgt,
                confidence=round(fused_confidence, 4),
                inference_method=(
                    "+".join(sorted(set(methods_used)))
                    if n_methods > 1
                    else methods_used[0]
                ),
                evidence=combined_evidence,
                suggested_type=best_dep.suggested_type,
            ))

        # Sort by confidence descending
        merged.sort(key=lambda d: d.confidence, reverse=True)
        return merged

    # ------------------------------------------------------------------
    # Apply to Graph
    # ------------------------------------------------------------------

    def apply_inferred(
        self,
        graph: InfraGraph,
        inferred_deps: list[InferredDependency],
        min_confidence: float = 0.7,
    ) -> int:
        """Add high-confidence inferred dependencies to the graph.

        Only adds dependencies where both source and target components
        exist in the graph, the edge does not already exist, and
        confidence >= min_confidence.

        Returns the number of dependencies added.
        """
        added = 0
        for dep in inferred_deps:
            if dep.confidence < min_confidence:
                continue

            # Verify both components exist
            if graph.get_component(dep.source_id) is None:
                continue
            if graph.get_component(dep.target_id) is None:
                continue

            # Check edge doesn't already exist
            if graph.get_dependency_edge(dep.source_id, dep.target_id) is not None:
                continue

            graph.add_dependency(Dependency(
                source_id=dep.source_id,
                target_id=dep.target_id,
                dependency_type=dep.suggested_type,
                protocol="inferred",
                weight=dep.confidence,
            ))
            added += 1

        return added
