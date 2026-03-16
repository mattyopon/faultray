"""Dependency Freshness Tracker for FaultRay.

Tracks the "freshness" of infrastructure components — identifying outdated,
end-of-life, or potentially vulnerable technology choices based on version
patterns and component naming.

Usage:
    from faultray.simulator.dependency_freshness import DependencyFreshnessTracker
    tracker = DependencyFreshnessTracker()
    report = tracker.analyze(graph)
    suggestions = tracker.get_upgrade_suggestions(report)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

from faultray.model.graph import InfraGraph


class FreshnessLevel(str, Enum):
    """Freshness classification for a component's technology stack."""

    CURRENT = "current"
    AGING = "aging"
    OUTDATED = "outdated"
    EOL = "eol"
    UNKNOWN = "unknown"


class TechCategory(str, Enum):
    """Technology category for classification."""

    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    RUNTIME = "runtime"
    OS = "os"
    FRAMEWORK = "framework"
    CLOUD_SERVICE = "cloud_service"


@dataclass
class TechInfo:
    """Known technology metadata for freshness assessment."""

    name: str
    category: TechCategory
    latest_major: int
    eol_versions: list[str]
    recommended_version: str
    notes: str


@dataclass
class ComponentFreshness:
    """Freshness assessment for a single component."""

    component_id: str
    component_name: str
    detected_tech: str | None
    detected_version: str | None
    freshness: FreshnessLevel
    tech_category: TechCategory | None
    risk_factors: list[str]
    upgrade_path: str | None
    eol_date: str | None


@dataclass
class FreshnessReport:
    """Full freshness analysis report for an infrastructure graph."""

    components: list[ComponentFreshness]
    overall_freshness_score: float
    current_count: int
    aging_count: int
    outdated_count: int
    eol_count: int
    unknown_count: int
    critical_upgrades: list[str]
    recommendations: list[str]


# Points assigned to each freshness level for scoring
_FRESHNESS_POINTS: dict[FreshnessLevel, float] = {
    FreshnessLevel.CURRENT: 100.0,
    FreshnessLevel.AGING: 70.0,
    FreshnessLevel.OUTDATED: 40.0,
    FreshnessLevel.EOL: 10.0,
    FreshnessLevel.UNKNOWN: 50.0,
}

# Heuristic patterns mapping component name substrings to technology names.
# Each entry is (pattern, tech_key) where pattern is matched case-insensitively
# against the component name and tags.
_DETECTION_PATTERNS: list[tuple[str, str]] = [
    ("postgres", "postgresql"),
    ("pg-", "postgresql"),
    ("psql", "postgresql"),
    ("mariadb", "mariadb"),
    ("mysql", "mysql"),
    ("mongo", "mongodb"),
    ("redis", "redis"),
    ("memcached", "memcached"),
    ("memcache", "memcached"),
    ("elastic", "elasticsearch"),
    ("es-", "elasticsearch"),
    ("rabbit", "rabbitmq"),
    ("rmq", "rabbitmq"),
    ("kafka", "kafka"),
    ("sqs", "sqs"),
    ("dynamodb", "dynamodb"),
    ("dynamo", "dynamodb"),
    ("cassandra", "cassandra"),
    ("cockroach", "cockroachdb"),
    ("crdb", "cockroachdb"),
    ("nodejs", "nodejs"),
    ("node-", "nodejs"),
    ("node ", "nodejs"),
    ("python", "python"),
    ("java", "java"),
    ("golang", "go"),
    ("go-", "go"),
    ("nginx", "nginx"),
    ("apache", "apache"),
    ("haproxy", "haproxy"),
]

# Regex to extract version numbers from strings like "pg-14", "redis-7.2",
# "node-18", "python-3.11", etc.
_VERSION_RE = re.compile(r"[\-_v](\d+(?:\.\d+)*)")


class DependencyFreshnessTracker:
    """Analyse infrastructure components for technology freshness.

    Detects technology choices from component names/tags and classifies them
    as CURRENT, AGING, OUTDATED, EOL or UNKNOWN based on a built-in
    knowledge base of major technology versions.
    """

    def __init__(self) -> None:
        self._tech_db: dict[str, TechInfo] = self._build_tech_database()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze(self, graph: InfraGraph) -> FreshnessReport:
        """Analyse all components in *graph* and return a freshness report."""
        freshness_results: list[ComponentFreshness] = []

        for cid, comp in graph.components.items():
            cf = self._assess_component(cid, comp)
            freshness_results.append(cf)

        # Aggregate counts
        current_count = sum(
            1 for c in freshness_results if c.freshness == FreshnessLevel.CURRENT
        )
        aging_count = sum(
            1 for c in freshness_results if c.freshness == FreshnessLevel.AGING
        )
        outdated_count = sum(
            1 for c in freshness_results if c.freshness == FreshnessLevel.OUTDATED
        )
        eol_count = sum(
            1 for c in freshness_results if c.freshness == FreshnessLevel.EOL
        )
        unknown_count = sum(
            1 for c in freshness_results if c.freshness == FreshnessLevel.UNKNOWN
        )

        # Overall score = average of all component scores
        if freshness_results:
            total_points = sum(
                _FRESHNESS_POINTS[c.freshness] for c in freshness_results
            )
            overall_score = total_points / len(freshness_results)
        else:
            overall_score = 100.0

        # Critical upgrades — components that are EOL
        critical_upgrades = [
            f"{c.component_name} ({c.detected_tech} {c.detected_version})"
            for c in freshness_results
            if c.freshness == FreshnessLevel.EOL
        ]

        # Recommendations
        recommendations = self._generate_recommendations(freshness_results)

        return FreshnessReport(
            components=freshness_results,
            overall_freshness_score=round(overall_score, 1),
            current_count=current_count,
            aging_count=aging_count,
            outdated_count=outdated_count,
            eol_count=eol_count,
            unknown_count=unknown_count,
            critical_upgrades=critical_upgrades,
            recommendations=recommendations,
        )

    def analyze_component(
        self, graph: InfraGraph, component_id: str
    ) -> ComponentFreshness | None:
        """Analyse a single component by *component_id*.

        Returns ``None`` if the component is not found in the graph.
        """
        comp = graph.get_component(component_id)
        if comp is None:
            return None
        return self._assess_component(component_id, comp)

    def detect_technology(self, component) -> tuple[str | None, str | None]:
        """Detect technology name and version from a component.

        Inspects the component's ``name`` and ``tags`` to identify known
        technology patterns and extract version numbers.

        Returns:
            A ``(tech_name, version)`` tuple.  Either or both may be ``None``
            if detection fails.
        """
        # Build a list of strings to search (name + tags)
        search_strings = [component.name.lower()]
        if hasattr(component, "tags") and component.tags:
            search_strings.extend(t.lower() for t in component.tags)

        combined = " ".join(search_strings)

        # Try to match each detection pattern
        tech_key: str | None = None
        matched_pattern: str | None = None
        for pattern, key in _DETECTION_PATTERNS:
            if pattern in combined:
                tech_key = key
                matched_pattern = pattern
                break

        if tech_key is None:
            return None, None

        # Resolve display name from tech database
        tech_info = self._tech_db.get(tech_key)
        tech_name = tech_info.name if tech_info else tech_key

        # Extract version — prefer strings that contain the matched pattern
        # to avoid picking up unrelated numbers from other tags.
        matched_strings = [
            s for s in search_strings if matched_pattern in s
        ]
        version = self._extract_version(matched_strings)
        if version is None:
            # Fall back to all search strings
            version = self._extract_version(search_strings)

        return tech_name, version

    def get_upgrade_suggestions(self, report: FreshnessReport) -> list[dict]:
        """Return actionable upgrade suggestions derived from *report*.

        Each item is a dict with keys:
        ``component``, ``current_tech``, ``current_version``,
        ``recommended_version``, ``freshness``, ``priority``.
        """
        suggestions: list[dict] = []
        for comp in report.components:
            if comp.freshness in (
                FreshnessLevel.EOL,
                FreshnessLevel.OUTDATED,
                FreshnessLevel.AGING,
            ):
                priority = {
                    FreshnessLevel.EOL: "critical",
                    FreshnessLevel.OUTDATED: "high",
                    FreshnessLevel.AGING: "medium",
                }.get(comp.freshness, "low")

                suggestions.append(
                    {
                        "component": comp.component_name,
                        "current_tech": comp.detected_tech,
                        "current_version": comp.detected_version,
                        "recommended_version": comp.upgrade_path,
                        "freshness": comp.freshness.value,
                        "priority": priority,
                    }
                )

        # Sort by priority: critical > high > medium > low
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        suggestions.sort(key=lambda s: priority_order.get(s["priority"], 9))
        return suggestions

    def get_tech_database(self) -> dict[str, TechInfo]:
        """Return the built-in technology database."""
        return dict(self._tech_db)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assess_component(
        self, component_id: str, component
    ) -> ComponentFreshness:
        """Assess a single component and return its freshness."""
        tech_name, version = self.detect_technology(component)

        if tech_name is None:
            return ComponentFreshness(
                component_id=component_id,
                component_name=component.name,
                detected_tech=None,
                detected_version=None,
                freshness=FreshnessLevel.UNKNOWN,
                tech_category=None,
                risk_factors=["Unable to detect technology from component name/tags"],
                upgrade_path=None,
                eol_date=None,
            )

        # Look up in tech database
        tech_key = self._resolve_tech_key(tech_name)
        tech_info = self._tech_db.get(tech_key)

        if tech_info is None:
            return ComponentFreshness(
                component_id=component_id,
                component_name=component.name,
                detected_tech=tech_name,
                detected_version=version,
                freshness=FreshnessLevel.UNKNOWN,
                tech_category=None,
                risk_factors=["Technology not in freshness database"],
                upgrade_path=None,
                eol_date=None,
            )

        if version is None:
            return ComponentFreshness(
                component_id=component_id,
                component_name=component.name,
                detected_tech=tech_name,
                detected_version=None,
                freshness=FreshnessLevel.UNKNOWN,
                tech_category=tech_info.category,
                risk_factors=[
                    "Version not detected; cannot assess freshness"
                ],
                upgrade_path=tech_info.recommended_version,
                eol_date=None,
            )

        # Classify freshness
        freshness, risk_factors, eol_date = self._classify_freshness(
            version, tech_info
        )

        upgrade_path: str | None = None
        if freshness != FreshnessLevel.CURRENT:
            upgrade_path = tech_info.recommended_version

        return ComponentFreshness(
            component_id=component_id,
            component_name=component.name,
            detected_tech=tech_name,
            detected_version=version,
            freshness=freshness,
            tech_category=tech_info.category,
            risk_factors=risk_factors,
            upgrade_path=upgrade_path,
            eol_date=eol_date,
        )

    def _classify_freshness(
        self, version: str, tech_info: TechInfo
    ) -> tuple[FreshnessLevel, list[str], str | None]:
        """Classify *version* against *tech_info*.

        Returns ``(freshness_level, risk_factors, eol_date)``.
        """
        risk_factors: list[str] = []
        eol_date: str | None = None

        # Parse the major version from the detected version string
        major = self._parse_major(version)

        # Check EOL first — version string or major version in EOL list
        if self._is_eol(version, tech_info):
            risk_factors.append(
                f"{tech_info.name} {version} is end-of-life (no security patches)"
            )
            eol_date = "EOL"
            return FreshnessLevel.EOL, risk_factors, eol_date

        if major is None:
            risk_factors.append("Could not parse major version")
            return FreshnessLevel.UNKNOWN, risk_factors, None

        latest = tech_info.latest_major
        diff = latest - major

        if diff <= 1:
            return FreshnessLevel.CURRENT, risk_factors, None
        elif diff == 2:
            risk_factors.append(
                f"{tech_info.name} {version} is 2 major versions behind latest ({latest})"
            )
            return FreshnessLevel.AGING, risk_factors, None
        else:
            risk_factors.append(
                f"{tech_info.name} {version} is {diff} major versions behind latest ({latest})"
            )
            return FreshnessLevel.OUTDATED, risk_factors, None

    def _is_eol(self, version: str, tech_info: TechInfo) -> bool:
        """Check whether *version* matches any EOL version pattern."""
        for eol_v in tech_info.eol_versions:
            if "-" in eol_v:
                # Range pattern, e.g. "2.0-2.8" or "7.0-7.9"
                if self._version_in_range(version, eol_v):
                    return True
            elif version == eol_v or version.startswith(eol_v + "."):
                return True
            # Also check bare major match, e.g. eol "5" matches "5" or "5.x"
            elif eol_v == str(self._parse_major(version)):
                return True
        return False

    def _version_in_range(self, version: str, range_str: str) -> bool:
        """Check if *version* falls within a range like ``"2.0-2.8"``."""
        parts = range_str.split("-")
        if len(parts) != 2:
            return False
        lo, hi = parts
        try:
            lo_tuple = tuple(int(x) for x in lo.split("."))
            hi_tuple = tuple(int(x) for x in hi.split("."))
            ver_tuple = tuple(int(x) for x in version.split("."))
            return lo_tuple <= ver_tuple <= hi_tuple
        except (ValueError, TypeError):
            return False

    @staticmethod
    def _parse_major(version: str) -> int | None:
        """Extract the major version number from a version string."""
        try:
            return int(version.split(".")[0])
        except (ValueError, IndexError):
            return None

    @staticmethod
    def _extract_version(search_strings: list[str]) -> str | None:
        """Extract a version number from a list of name/tag strings."""
        for s in search_strings:
            match = _VERSION_RE.search(s)
            if match:
                return match.group(1)
        return None

    def _resolve_tech_key(self, tech_name: str) -> str:
        """Map a display tech name back to the internal database key."""
        for key, info in self._tech_db.items():
            if info.name == tech_name:
                return key
        return tech_name.lower().replace(" ", "").replace(".", "")

    def _generate_recommendations(
        self, results: list[ComponentFreshness]
    ) -> list[str]:
        """Generate human-readable recommendations from assessment results."""
        recommendations: list[str] = []

        eol_components = [r for r in results if r.freshness == FreshnessLevel.EOL]
        outdated_components = [
            r for r in results if r.freshness == FreshnessLevel.OUTDATED
        ]
        aging_components = [
            r for r in results if r.freshness == FreshnessLevel.AGING
        ]
        unknown_components = [
            r for r in results if r.freshness == FreshnessLevel.UNKNOWN
        ]

        if eol_components:
            names = ", ".join(c.component_name for c in eol_components)
            recommendations.append(
                f"CRITICAL: {len(eol_components)} component(s) are running "
                f"end-of-life software ({names}). Upgrade immediately to "
                f"receive security patches."
            )

        if outdated_components:
            names = ", ".join(c.component_name for c in outdated_components)
            recommendations.append(
                f"HIGH: {len(outdated_components)} component(s) are significantly "
                f"outdated ({names}). Plan upgrades within the next quarter."
            )

        if aging_components:
            names = ", ".join(c.component_name for c in aging_components)
            recommendations.append(
                f"MEDIUM: {len(aging_components)} component(s) are aging "
                f"({names}). Consider upgrading during next maintenance window."
            )

        if unknown_components:
            recommendations.append(
                f"INFO: {len(unknown_components)} component(s) could not be "
                f"assessed. Add version tags to enable freshness tracking."
            )

        # Per-component upgrade suggestions for EOL/OUTDATED
        for comp in eol_components + outdated_components:
            if comp.upgrade_path:
                recommendations.append(
                    f"Upgrade {comp.component_name} "
                    f"({comp.detected_tech} {comp.detected_version}) "
                    f"to {comp.upgrade_path}."
                )

        return recommendations

    # ------------------------------------------------------------------
    # Tech database
    # ------------------------------------------------------------------

    @staticmethod
    def _build_tech_database() -> dict[str, TechInfo]:
        """Return the built-in technology freshness database."""
        return {
            # --- Databases ---
            "postgresql": TechInfo(
                name="PostgreSQL",
                category=TechCategory.DATABASE,
                latest_major=17,
                eol_versions=["9", "10", "11"],
                recommended_version="PostgreSQL 17",
                notes="Major release yearly; each version supported ~5 years.",
            ),
            "mysql": TechInfo(
                name="MySQL",
                category=TechCategory.DATABASE,
                latest_major=8,
                eol_versions=["5.5", "5.6", "5.7"],
                recommended_version="MySQL 8",
                notes="LTS release; 5.x branch fully EOL.",
            ),
            "mongodb": TechInfo(
                name="MongoDB",
                category=TechCategory.DATABASE,
                latest_major=7,
                eol_versions=["3", "4.0", "4.2"],
                recommended_version="MongoDB 7",
                notes="Rapid release model with ~18-month support window.",
            ),
            "mariadb": TechInfo(
                name="MariaDB",
                category=TechCategory.DATABASE,
                latest_major=11,
                eol_versions=["10.3", "10.4", "10.5"],
                recommended_version="MariaDB 11",
                notes="Short-term and long-term support branches.",
            ),
            "dynamodb": TechInfo(
                name="DynamoDB",
                category=TechCategory.CLOUD_SERVICE,
                latest_major=0,
                eol_versions=[],
                recommended_version="DynamoDB (managed)",
                notes="Fully managed; no version lifecycle.",
            ),
            "cassandra": TechInfo(
                name="Cassandra",
                category=TechCategory.DATABASE,
                latest_major=5,
                eol_versions=["3", "3.0", "3.11"],
                recommended_version="Cassandra 5",
                notes="Apache project with yearly releases.",
            ),
            "cockroachdb": TechInfo(
                name="CockroachDB",
                category=TechCategory.DATABASE,
                latest_major=24,
                eol_versions=["21", "22"],
                recommended_version="CockroachDB 24",
                notes="Cloud-native distributed SQL; major releases yearly.",
            ),
            # --- Caches ---
            "redis": TechInfo(
                name="Redis",
                category=TechCategory.CACHE,
                latest_major=7,
                eol_versions=["5", "6"],
                recommended_version="Redis 7",
                notes="Major release ~every 2 years.",
            ),
            "memcached": TechInfo(
                name="Memcached",
                category=TechCategory.CACHE,
                latest_major=1,
                eol_versions=[],
                recommended_version="Memcached 1.6+",
                notes="Stable single-major-version project.",
            ),
            "elasticsearch": TechInfo(
                name="Elasticsearch",
                category=TechCategory.CACHE,
                latest_major=8,
                eol_versions=["6", "7.0-7.9"],
                recommended_version="Elasticsearch 8",
                notes="Elastic Stack major releases ~yearly.",
            ),
            # --- Queues ---
            "rabbitmq": TechInfo(
                name="RabbitMQ",
                category=TechCategory.QUEUE,
                latest_major=3,
                eol_versions=["3.8", "3.9"],
                recommended_version="RabbitMQ 3.13+",
                notes="Minor-version-based EOL within major 3.",
            ),
            "kafka": TechInfo(
                name="Kafka",
                category=TechCategory.QUEUE,
                latest_major=3,
                eol_versions=["2.0-2.8"],
                recommended_version="Kafka 3",
                notes="Apache Kafka with rapid minor releases.",
            ),
            "sqs": TechInfo(
                name="SQS",
                category=TechCategory.CLOUD_SERVICE,
                latest_major=0,
                eol_versions=[],
                recommended_version="SQS (managed)",
                notes="Fully managed; no version lifecycle.",
            ),
            # --- Runtimes ---
            "nodejs": TechInfo(
                name="Node.js",
                category=TechCategory.RUNTIME,
                latest_major=22,
                eol_versions=["14", "16", "18"],
                recommended_version="Node.js 22 LTS",
                notes="Even-numbered releases receive LTS support.",
            ),
            "python": TechInfo(
                name="Python",
                category=TechCategory.RUNTIME,
                latest_major=3,
                eol_versions=["3.7", "3.8"],
                recommended_version="Python 3.13",
                notes="Minor releases are the meaningful version unit.",
            ),
            "java": TechInfo(
                name="Java",
                category=TechCategory.RUNTIME,
                latest_major=21,
                eol_versions=["8", "11", "17"],
                recommended_version="Java 21 LTS",
                notes="LTS releases every 2 years; non-LTS EOL quickly.",
            ),
            "go": TechInfo(
                name="Go",
                category=TechCategory.RUNTIME,
                latest_major=1,
                eol_versions=[],
                recommended_version="Go 1.22",
                notes="Single major version; minor releases every 6 months.",
            ),
            # --- Web / Proxy ---
            "nginx": TechInfo(
                name="Nginx",
                category=TechCategory.FRAMEWORK,
                latest_major=1,
                eol_versions=[],
                recommended_version="Nginx 1.27",
                notes="Stable and mainline branches; single major version.",
            ),
            "apache": TechInfo(
                name="Apache",
                category=TechCategory.FRAMEWORK,
                latest_major=2,
                eol_versions=[],
                recommended_version="Apache 2.4",
                notes="Apache HTTP Server 2.4 is the current stable branch.",
            ),
            "haproxy": TechInfo(
                name="HAProxy",
                category=TechCategory.FRAMEWORK,
                latest_major=2,
                eol_versions=[],
                recommended_version="HAProxy 2.9",
                notes="LTS releases every ~2 years.",
            ),
        }
