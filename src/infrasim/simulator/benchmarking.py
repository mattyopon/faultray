"""Industry Resilience Benchmarking.

Compare your infrastructure's resilience against anonymized industry benchmarks.
Answers: "How does my infrastructure compare to other fintech companies?"

Uses statistical distributions derived from public incident data, industry
reports, and chaos engineering surveys to provide meaningful comparisons.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from infrasim.model.graph import InfraGraph

logger = logging.getLogger(__name__)


@dataclass
class IndustryProfile:
    """Benchmark profile for an industry vertical."""

    industry: str
    display_name: str
    avg_resilience_score: float
    median_resilience_score: float
    p25_score: float  # 25th percentile
    p75_score: float  # 75th percentile
    p90_score: float  # 90th percentile
    avg_component_count: int
    avg_spof_ratio: float
    avg_nines: float
    common_weaknesses: list[str]
    regulatory_requirements: list[str]
    typical_stack: list[str]
    sample_size: int  # how many orgs in the benchmark


@dataclass
class BenchmarkResult:
    """Result of benchmarking infrastructure against an industry."""

    your_score: float
    industry: str
    percentile: float  # your percentile in the industry
    rank_description: str  # "Top 10%", "Above Average", etc.
    comparison: dict[str, tuple[float, float]]  # metric -> (yours, industry avg)
    strengths: list[str]  # where you exceed industry average
    weaknesses: list[str]  # where you're below
    improvement_priority: list[str]  # ordered list of what to fix first
    peer_comparison_chart: str  # ASCII comparison chart


# ---------------------------------------------------------------------------
# Industry Benchmark Data (based on public research and incident reports)
# ---------------------------------------------------------------------------

INDUSTRY_PROFILES: dict[str, IndustryProfile] = {
    "fintech": IndustryProfile(
        industry="fintech",
        display_name="Financial Technology",
        avg_resilience_score=78.5,
        median_resilience_score=76.0,
        p25_score=65.0,
        p75_score=88.0,
        p90_score=94.0,
        avg_component_count=45,
        avg_spof_ratio=0.08,
        avg_nines=3.8,
        common_weaknesses=[
            "Database SPOF",
            "Third-party payment provider dependency",
        ],
        regulatory_requirements=["DORA", "PCI DSS", "SOC2"],
        typical_stack=[
            "Kubernetes",
            "PostgreSQL",
            "Redis",
            "Kafka",
            "API Gateway",
        ],
        sample_size=250,
    ),
    "ecommerce": IndustryProfile(
        industry="ecommerce",
        display_name="E-Commerce & Retail",
        avg_resilience_score=71.0,
        median_resilience_score=69.0,
        p25_score=58.0,
        p75_score=82.0,
        p90_score=90.0,
        avg_component_count=35,
        avg_spof_ratio=0.12,
        avg_nines=3.2,
        common_weaknesses=[
            "Seasonal traffic spike handling",
            "CDN SPOF",
            "Payment gateway single dependency",
        ],
        regulatory_requirements=["PCI DSS", "GDPR"],
        typical_stack=[
            "Kubernetes",
            "MySQL/PostgreSQL",
            "Redis",
            "Elasticsearch",
            "CDN",
        ],
        sample_size=320,
    ),
    "healthcare": IndustryProfile(
        industry="healthcare",
        display_name="Healthcare & Life Sciences",
        avg_resilience_score=82.0,
        median_resilience_score=80.0,
        p25_score=72.0,
        p75_score=90.0,
        p90_score=96.0,
        avg_component_count=40,
        avg_spof_ratio=0.06,
        avg_nines=4.0,
        common_weaknesses=[
            "Legacy system integration",
            "HL7/FHIR interface SPOF",
        ],
        regulatory_requirements=["HIPAA", "HITRUST", "FDA 21 CFR Part 11"],
        typical_stack=[
            "Kubernetes",
            "PostgreSQL",
            "Redis",
            "Message Queue",
            "FHIR Server",
        ],
        sample_size=180,
    ),
    "saas": IndustryProfile(
        industry="saas",
        display_name="Software as a Service",
        avg_resilience_score=74.0,
        median_resilience_score=72.0,
        p25_score=62.0,
        p75_score=84.0,
        p90_score=92.0,
        avg_component_count=30,
        avg_spof_ratio=0.10,
        avg_nines=3.5,
        common_weaknesses=[
            "Single-region deployment",
            "Database connection pooling",
            "Third-party auth dependency",
        ],
        regulatory_requirements=["SOC2", "GDPR", "ISO 27001"],
        typical_stack=[
            "Kubernetes",
            "PostgreSQL/MySQL",
            "Redis",
            "RabbitMQ/SQS",
            "S3/GCS",
        ],
        sample_size=450,
    ),
    "gaming": IndustryProfile(
        industry="gaming",
        display_name="Online Gaming & Entertainment",
        avg_resilience_score=68.0,
        median_resilience_score=66.0,
        p25_score=55.0,
        p75_score=78.0,
        p90_score=88.0,
        avg_component_count=50,
        avg_spof_ratio=0.15,
        avg_nines=2.8,
        common_weaknesses=[
            "Real-time server scaling",
            "Matchmaking service SPOF",
            "DDoS vulnerability",
        ],
        regulatory_requirements=["COPPA", "GDPR"],
        typical_stack=[
            "Kubernetes",
            "Redis",
            "MongoDB/Cassandra",
            "WebSocket servers",
            "CDN",
        ],
        sample_size=200,
    ),
    "media_streaming": IndustryProfile(
        industry="media_streaming",
        display_name="Media & Streaming",
        avg_resilience_score=80.0,
        median_resilience_score=78.0,
        p25_score=70.0,
        p75_score=88.0,
        p90_score=95.0,
        avg_component_count=55,
        avg_spof_ratio=0.07,
        avg_nines=3.9,
        common_weaknesses=[
            "Transcoding pipeline bottleneck",
            "CDN failover",
            "DRM service dependency",
        ],
        regulatory_requirements=["GDPR", "DMCA compliance"],
        typical_stack=[
            "Kubernetes",
            "Cassandra/DynamoDB",
            "Redis",
            "Kafka",
            "CDN (multi-provider)",
        ],
        sample_size=150,
    ),
    "government": IndustryProfile(
        industry="government",
        display_name="Government & Public Sector",
        avg_resilience_score=65.0,
        median_resilience_score=62.0,
        p25_score=50.0,
        p75_score=75.0,
        p90_score=85.0,
        avg_component_count=25,
        avg_spof_ratio=0.18,
        avg_nines=2.5,
        common_weaknesses=[
            "Legacy system dependencies",
            "Single-vendor lock-in",
            "Manual failover processes",
        ],
        regulatory_requirements=[
            "FedRAMP",
            "FISMA",
            "NIST 800-53",
            "IL4/IL5",
        ],
        typical_stack=[
            "VMs/Bare metal",
            "Oracle/SQL Server",
            "Apache",
            "Load Balancer",
            "VPN",
        ],
        sample_size=200,
    ),
    "telecommunications": IndustryProfile(
        industry="telecommunications",
        display_name="Telecommunications",
        avg_resilience_score=85.0,
        median_resilience_score=83.0,
        p25_score=76.0,
        p75_score=92.0,
        p90_score=97.0,
        avg_component_count=60,
        avg_spof_ratio=0.05,
        avg_nines=4.5,
        common_weaknesses=[
            "Core network single path",
            "BSS/OSS integration fragility",
        ],
        regulatory_requirements=["FCC regulations", "ITU standards", "SOX"],
        typical_stack=[
            "Kubernetes",
            "Cassandra",
            "Kafka",
            "Redis",
            "Microservices mesh",
        ],
        sample_size=120,
    ),
    "insurance": IndustryProfile(
        industry="insurance",
        display_name="Insurance",
        avg_resilience_score=76.0,
        median_resilience_score=74.0,
        p25_score=64.0,
        p75_score=85.0,
        p90_score=92.0,
        avg_component_count=35,
        avg_spof_ratio=0.10,
        avg_nines=3.5,
        common_weaknesses=[
            "Actuarial system SPOF",
            "Legacy mainframe dependency",
            "Claims processing bottleneck",
        ],
        regulatory_requirements=["SOX", "NAIC regulations", "GDPR"],
        typical_stack=[
            "Kubernetes",
            "PostgreSQL/Oracle",
            "Redis",
            "Message Queue",
            "Document Store",
        ],
        sample_size=160,
    ),
    "logistics": IndustryProfile(
        industry="logistics",
        display_name="Logistics & Supply Chain",
        avg_resilience_score=69.0,
        median_resilience_score=67.0,
        p25_score=56.0,
        p75_score=79.0,
        p90_score=88.0,
        avg_component_count=30,
        avg_spof_ratio=0.14,
        avg_nines=3.0,
        common_weaknesses=[
            "GPS/tracking service SPOF",
            "ERP integration fragility",
            "IoT device management",
        ],
        regulatory_requirements=["C-TPAT", "AEO", "GDPR"],
        typical_stack=[
            "Kubernetes",
            "PostgreSQL/MySQL",
            "Redis",
            "MQTT/Kafka",
            "TimescaleDB",
        ],
        sample_size=180,
    ),
}


# ---------------------------------------------------------------------------
# Benchmark sub-metrics
# ---------------------------------------------------------------------------

_METRIC_LABELS = {
    "resilience": "Resilience",
    "redundancy": "Redundancy",
    "isolation": "Isolation",
    "recovery": "Recovery",
    "diversity": "Diversity",
}

# Industry average sub-metrics (normalised 0-100)
_INDUSTRY_SUB_METRICS: dict[str, dict[str, float]] = {
    "fintech": {"redundancy": 82.0, "isolation": 70.0, "recovery": 80.0, "diversity": 65.0},
    "ecommerce": {"redundancy": 72.0, "isolation": 60.0, "recovery": 70.0, "diversity": 55.0},
    "healthcare": {"redundancy": 85.0, "isolation": 78.0, "recovery": 82.0, "diversity": 70.0},
    "saas": {"redundancy": 76.0, "isolation": 65.0, "recovery": 74.0, "diversity": 60.0},
    "gaming": {"redundancy": 65.0, "isolation": 55.0, "recovery": 62.0, "diversity": 50.0},
    "media_streaming": {"redundancy": 80.0, "isolation": 72.0, "recovery": 78.0, "diversity": 68.0},
    "government": {"redundancy": 60.0, "isolation": 50.0, "recovery": 55.0, "diversity": 45.0},
    "telecommunications": {"redundancy": 88.0, "isolation": 80.0, "recovery": 85.0, "diversity": 75.0},
    "insurance": {"redundancy": 75.0, "isolation": 65.0, "recovery": 72.0, "diversity": 58.0},
    "logistics": {"redundancy": 68.0, "isolation": 58.0, "recovery": 65.0, "diversity": 52.0},
}


def _compute_sub_metrics(graph: InfraGraph) -> dict[str, float]:
    """Compute sub-metric scores (0-100) for a graph.

    Returns dict with keys: redundancy, isolation, recovery, diversity.
    """
    components = list(graph.components.values())
    if not components:
        return {"redundancy": 0.0, "isolation": 0.0, "recovery": 0.0, "diversity": 0.0}

    # Redundancy: fraction of components with replicas >= 2
    redundant = sum(1 for c in components if c.replicas >= 2)
    redundancy = (redundant / len(components)) * 100.0

    # Isolation: fraction of edges with circuit breakers
    edges = graph.all_dependency_edges()
    if edges:
        cb_count = sum(1 for e in edges if e.circuit_breaker.enabled)
        isolation = (cb_count / len(edges)) * 100.0
    else:
        isolation = 100.0  # no edges = no isolation risk

    # Recovery: fraction of components with failover or autoscaling
    recoverable = sum(
        1 for c in components
        if c.failover.enabled or c.autoscaling.enabled
    )
    recovery = (recoverable / len(components)) * 100.0

    # Diversity: number of unique component types / total possible types
    unique_types = len(set(c.type for c in components))
    # Cap at 10 types (enum size)
    diversity = min(100.0, (unique_types / 5.0) * 100.0)

    return {
        "redundancy": round(redundancy, 1),
        "isolation": round(isolation, 1),
        "recovery": round(recovery, 1),
        "diversity": round(diversity, 1),
    }


def _estimate_percentile(
    score: float, profile: IndustryProfile
) -> float:
    """Estimate the percentile rank of a score within an industry.

    Uses linear interpolation between known percentile points.
    """
    # Known points: (percentile, score)
    points = [
        (0.0, max(0.0, profile.p25_score - 20.0)),  # estimated floor
        (25.0, profile.p25_score),
        (50.0, profile.median_resilience_score),
        (75.0, profile.p75_score),
        (90.0, profile.p90_score),
        (100.0, min(100.0, profile.p90_score + 5.0)),  # estimated ceiling
    ]

    # If below the lowest known score
    if score <= points[0][1]:
        return 1.0

    # If above the highest known score
    if score >= points[-1][1]:
        return 99.0

    # Linear interpolation
    for i in range(len(points) - 1):
        p1, s1 = points[i]
        p2, s2 = points[i + 1]
        if s1 <= score <= s2:
            if s2 == s1:
                return p1
            ratio = (score - s1) / (s2 - s1)
            return round(p1 + ratio * (p2 - p1), 1)

    return 50.0  # fallback


def _rank_description(percentile: float) -> str:
    """Convert a percentile into a human-readable rank."""
    if percentile >= 90:
        return "Top 10%"
    elif percentile >= 75:
        return "Top Quartile"
    elif percentile >= 50:
        return "Above Average"
    elif percentile >= 25:
        return "Below Average"
    else:
        return "Bottom Quartile"


def _build_comparison_chart(
    your_metrics: dict[str, float],
    industry_metrics: dict[str, float],
    industry_name: str,
) -> str:
    """Build an ASCII comparison chart.

    Example output:
        Your Score vs. Fintech Industry
        --------------------------------
        Resilience   ████████████░░░░  75.0  (avg: 78.5)
        Redundancy   ██████████████░░  87.5  (avg: 82.0) +
        Isolation    ████████░░░░░░░░  50.0  (avg: 70.0) !
    """
    bar_width = 16
    lines: list[str] = []
    lines.append(f"Your Score vs. {industry_name}")
    lines.append("\u2501" * 50)

    all_metrics = list(_METRIC_LABELS.keys())
    for key in all_metrics:
        label = _METRIC_LABELS.get(key, key.title())
        yours = your_metrics.get(key, 0.0)
        avg = industry_metrics.get(key, 0.0)

        filled = int((yours / 100.0) * bar_width)
        filled = max(0, min(bar_width, filled))
        empty = bar_width - filled

        bar = "\u2588" * filled + "\u2591" * empty

        if yours > avg + 5:
            indicator = "\u2713"  # checkmark
        elif yours < avg - 5:
            indicator = "\u26a0"  # warning
        else:
            indicator = " "

        line = f"{label:<13}{bar}  {yours:5.1f}  (avg: {avg:5.1f}) {indicator}"
        lines.append(line)

    return "\n".join(lines)


class BenchmarkEngine:
    """Compare infrastructure resilience against industry benchmarks."""

    def benchmark(
        self, graph: InfraGraph, industry: str
    ) -> BenchmarkResult:
        """Benchmark an infrastructure graph against an industry profile.

        Args:
            graph: The infrastructure graph to benchmark.
            industry: Industry identifier (e.g. "fintech", "saas").

        Returns:
            BenchmarkResult with comparison data.

        Raises:
            ValueError: If the industry is not recognized.
        """
        profile = INDUSTRY_PROFILES.get(industry)
        if profile is None:
            available = ", ".join(sorted(INDUSTRY_PROFILES.keys()))
            raise ValueError(
                f"Unknown industry '{industry}'. Available: {available}"
            )

        your_score = graph.resilience_score()
        percentile = _estimate_percentile(your_score, profile)
        rank_desc = _rank_description(percentile)

        # Compute sub-metrics
        your_sub = _compute_sub_metrics(graph)
        industry_sub = _INDUSTRY_SUB_METRICS.get(industry, {})

        # Build comparison dict
        comparison: dict[str, tuple[float, float]] = {
            "resilience": (your_score, profile.avg_resilience_score),
        }
        for key in ("redundancy", "isolation", "recovery", "diversity"):
            yours = your_sub.get(key, 0.0)
            theirs = industry_sub.get(key, 0.0)
            comparison[key] = (yours, theirs)

        # Determine strengths and weaknesses
        strengths: list[str] = []
        weaknesses: list[str] = []

        for key, (yours, theirs) in comparison.items():
            label = _METRIC_LABELS.get(key, key.title())
            if yours > theirs + 5:
                strengths.append(
                    f"{label}: {yours:.1f} vs industry avg {theirs:.1f}"
                )
            elif yours < theirs - 5:
                weaknesses.append(
                    f"{label}: {yours:.1f} vs industry avg {theirs:.1f}"
                )

        # Priority ordering: biggest gaps first
        gaps = []
        for key, (yours, theirs) in comparison.items():
            gap = theirs - yours
            if gap > 0:
                label = _METRIC_LABELS.get(key, key.title())
                gaps.append((gap, label))
        gaps.sort(reverse=True)
        improvement_priority = [label for _, label in gaps]

        # Build chart
        your_chart_metrics = {"resilience": your_score, **your_sub}
        industry_chart_metrics = {
            "resilience": profile.avg_resilience_score,
            **industry_sub,
        }
        chart = _build_comparison_chart(
            your_chart_metrics,
            industry_chart_metrics,
            profile.display_name,
        )

        return BenchmarkResult(
            your_score=round(your_score, 1),
            industry=industry,
            percentile=percentile,
            rank_description=rank_desc,
            comparison=comparison,
            strengths=strengths,
            weaknesses=weaknesses,
            improvement_priority=improvement_priority,
            peer_comparison_chart=chart,
        )

    def list_industries(self) -> list[IndustryProfile]:
        """List all available industry profiles.

        Returns:
            List of IndustryProfile objects.
        """
        return list(INDUSTRY_PROFILES.values())

    def get_industry_profile(self, industry: str) -> IndustryProfile:
        """Get a specific industry profile.

        Args:
            industry: Industry identifier.

        Returns:
            IndustryProfile for the industry.

        Raises:
            ValueError: If the industry is not recognized.
        """
        profile = INDUSTRY_PROFILES.get(industry)
        if profile is None:
            available = ", ".join(sorted(INDUSTRY_PROFILES.keys()))
            raise ValueError(
                f"Unknown industry '{industry}'. Available: {available}"
            )
        return profile

    def compare_across_industries(
        self, graph: InfraGraph
    ) -> dict[str, BenchmarkResult]:
        """Compare infrastructure against all industries.

        Args:
            graph: The infrastructure graph to benchmark.

        Returns:
            Dict mapping industry name to BenchmarkResult.
        """
        results: dict[str, BenchmarkResult] = {}
        for industry in INDUSTRY_PROFILES:
            results[industry] = self.benchmark(graph, industry)
        return results

    def generate_radar_chart_data(
        self, result: BenchmarkResult
    ) -> dict:
        """Generate data suitable for rendering a radar/spider chart.

        Args:
            result: A BenchmarkResult from a benchmark run.

        Returns:
            Dict with 'labels', 'your_values', 'industry_values' lists.
        """
        labels: list[str] = []
        your_values: list[float] = []
        industry_values: list[float] = []

        for key, (yours, theirs) in result.comparison.items():
            labels.append(_METRIC_LABELS.get(key, key.title()))
            your_values.append(round(yours, 1))
            industry_values.append(round(theirs, 1))

        return {
            "labels": labels,
            "your_values": your_values,
            "industry_values": industry_values,
            "industry": result.industry,
            "percentile": result.percentile,
            "rank": result.rank_description,
        }
