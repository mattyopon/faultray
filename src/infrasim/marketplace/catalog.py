"""Chaos Scenario Marketplace - Community chaos scenario sharing.

A curated catalog of chaos engineering scenarios that users can:
- Browse by category, provider, severity
- Import into their ChaosProof instance
- Rate and review
- Contribute their own scenarios
- Share with teams

Think of it as 'npm for chaos scenarios' - a package manager for failure simulations.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from infrasim.simulator.scenarios import Scenario

logger = logging.getLogger(__name__)

MARKETPLACE_DIR = Path.home() / ".chaosproof" / "marketplace" / "packages"

VALID_CATEGORIES = frozenset({
    "infrastructure",
    "security",
    "compliance",
    "performance",
    "disaster_recovery",
})

VALID_PROVIDERS = frozenset({
    "aws",
    "azure",
    "gcp",
    "kubernetes",
    "generic",
})

VALID_SEVERITIES = frozenset({
    "critical",
    "high",
    "medium",
    "low",
})

VALID_DIFFICULTIES = frozenset({
    "beginner",
    "intermediate",
    "advanced",
    "expert",
})


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ScenarioReview:
    """A user review of a scenario package."""

    author: str
    rating: int  # 1-5
    comment: str
    date: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "author": self.author,
            "rating": self.rating,
            "comment": self.comment,
            "date": self.date.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioReview:
        date = data.get("date")
        if isinstance(date, str):
            try:
                date = datetime.fromisoformat(date)
            except (ValueError, TypeError):
                date = datetime.now(timezone.utc)
        elif not isinstance(date, datetime):
            date = datetime.now(timezone.utc)
        return cls(
            author=data["author"],
            rating=data["rating"],
            comment=data.get("comment", ""),
            date=date,
        )


@dataclass
class ScenarioPackage:
    """A downloadable/importable chaos scenario package."""

    id: str  # e.g. "aws-az-failover-v2"
    name: str
    version: str
    description: str
    author: str
    category: str  # infrastructure, security, compliance, performance, disaster_recovery
    provider: str  # aws, azure, gcp, kubernetes, generic
    severity: str  # critical, high, medium, low
    tags: list[str]
    scenarios: list[dict]  # scenario definitions
    prerequisites: list[str]  # required component types
    estimated_duration: str  # "5min", "30min", "1hr"
    difficulty: str  # beginner, intermediate, advanced, expert
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    downloads: int = 0
    rating: float = 0.0  # 0-5
    reviews: list[ScenarioReview] = field(default_factory=list)
    featured: bool = False

    @property
    def average_rating(self) -> float:
        if not self.reviews:
            return self.rating
        return sum(r.rating for r in self.reviews) / len(self.reviews)

    @property
    def scenario_count(self) -> int:
        return len(self.scenarios)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "category": self.category,
            "provider": self.provider,
            "severity": self.severity,
            "tags": self.tags,
            "scenarios": self.scenarios,
            "prerequisites": self.prerequisites,
            "estimated_duration": self.estimated_duration,
            "difficulty": self.difficulty,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "downloads": self.downloads,
            "rating": self.rating,
            "reviews": [r.to_dict() for r in self.reviews],
            "featured": self.featured,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioPackage:
        def _parse_dt(val: object) -> datetime:
            if isinstance(val, str):
                try:
                    return datetime.fromisoformat(val)
                except (ValueError, TypeError):
                    pass
            if isinstance(val, datetime):
                return val
            return datetime.now(timezone.utc)

        reviews = [ScenarioReview.from_dict(r) for r in data.get("reviews", [])]
        return cls(
            id=data["id"],
            name=data["name"],
            version=data.get("version", "1.0.0"),
            description=data.get("description", ""),
            author=data.get("author", "unknown"),
            category=data.get("category", "infrastructure"),
            provider=data.get("provider", "generic"),
            severity=data.get("severity", "medium"),
            tags=data.get("tags", []),
            scenarios=data.get("scenarios", []),
            prerequisites=data.get("prerequisites", []),
            estimated_duration=data.get("estimated_duration", "30min"),
            difficulty=data.get("difficulty", "intermediate"),
            created_at=_parse_dt(data.get("created_at")),
            updated_at=_parse_dt(data.get("updated_at")),
            downloads=data.get("downloads", 0),
            rating=data.get("rating", 0.0),
            reviews=reviews,
            featured=data.get("featured", False),
        )


@dataclass
class MarketplaceCategory:
    """Metadata for a marketplace category."""

    name: str
    display_name: str
    description: str
    icon: str  # emoji
    package_count: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "package_count": self.package_count,
        }


# ---------------------------------------------------------------------------
# Category definitions
# ---------------------------------------------------------------------------

CATEGORIES: list[MarketplaceCategory] = [
    MarketplaceCategory(
        name="infrastructure",
        display_name="Infrastructure",
        description="Core infrastructure failure scenarios: compute, network, storage",
        icon="[blue]INFRA[/]",
    ),
    MarketplaceCategory(
        name="security",
        display_name="Security",
        description="Security attack simulations and vulnerability testing",
        icon="[red]SEC[/]",
    ),
    MarketplaceCategory(
        name="compliance",
        display_name="Compliance",
        description="Regulatory compliance validation: DORA, SOC2, PCI-DSS, HIPAA",
        icon="[green]COMP[/]",
    ),
    MarketplaceCategory(
        name="performance",
        display_name="Performance",
        description="Load testing, resource exhaustion, and performance degradation",
        icon="[yellow]PERF[/]",
    ),
    MarketplaceCategory(
        name="disaster_recovery",
        display_name="Disaster Recovery",
        description="Region/AZ failover, data recovery, and business continuity",
        icon="[magenta]DR[/]",
    ),
]


# ---------------------------------------------------------------------------
# Marketplace engine
# ---------------------------------------------------------------------------


class ScenarioMarketplace:
    """Local-first marketplace for chaos engineering scenario packages.

    Packages are stored as JSON files in ``~/.chaosproof/marketplace/packages/``.
    Built-in packages are loaded from :mod:`infrasim.marketplace.builtin_packages`
    and merged with any user-installed packages.
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._store = store_path or MARKETPLACE_DIR
        self._store.mkdir(parents=True, exist_ok=True)
        self._builtin: list[ScenarioPackage] = []
        self._load_builtins()

    # ------------------------------------------------------------------
    # Built-in loading
    # ------------------------------------------------------------------

    def _load_builtins(self) -> None:
        """Load built-in packages from the builtin_packages module."""
        try:
            from infrasim.marketplace.builtin_packages import BUILTIN_PACKAGES

            self._builtin = list(BUILTIN_PACKAGES)
        except Exception:
            logger.warning("Could not load built-in marketplace packages.", exc_info=True)
            self._builtin = []

    def _all_packages(self) -> list[ScenarioPackage]:
        """Return all packages: built-in + user-installed."""
        user_pkgs = self._load_user_packages()
        user_ids = {p.id for p in user_pkgs}
        # Built-ins that are not overridden by user packages
        combined = [p for p in self._builtin if p.id not in user_ids]
        combined.extend(user_pkgs)
        return combined

    def _load_user_packages(self) -> list[ScenarioPackage]:
        """Load user-installed packages from the store directory."""
        packages: list[ScenarioPackage] = []
        for path in sorted(self._store.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                packages.append(ScenarioPackage.from_dict(data))
            except (json.JSONDecodeError, KeyError, TypeError):
                logger.debug("Skipping invalid package file: %s", path)
        return packages

    def _package_path(self, package_id: str) -> Path:
        return self._store / f"{package_id}.json"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_packages(
        self,
        category: str | None = None,
        provider: str | None = None,
    ) -> list[ScenarioPackage]:
        """List all packages, optionally filtered by category and/or provider."""
        packages = self._all_packages()
        if category:
            packages = [p for p in packages if p.category == category]
        if provider:
            packages = [p for p in packages if p.provider == provider]
        return packages

    def search(self, query: str) -> list[ScenarioPackage]:
        """Search packages by free-text query across name, description, tags."""
        q = query.lower()
        results: list[ScenarioPackage] = []
        for pkg in self._all_packages():
            haystack = " ".join([
                pkg.name,
                pkg.description,
                pkg.author,
                pkg.category,
                pkg.provider,
                " ".join(pkg.tags),
            ]).lower()
            if q in haystack:
                results.append(pkg)
        return results

    def get_package(self, package_id: str) -> ScenarioPackage:
        """Get a specific package by its ID."""
        for pkg in self._all_packages():
            if pkg.id == package_id:
                return pkg
        raise KeyError(f"Package not found: {package_id}")

    def install_package(self, package_id: str) -> list[Scenario]:
        """Install a package: convert its scenarios to ChaosProof Scenario objects.

        Also persists the package locally with an incremented download count.
        """
        from infrasim.simulator.scenarios import Fault, FaultType, Scenario

        pkg = self.get_package(package_id)
        pkg.downloads += 1

        # Persist to local store
        path = self._package_path(pkg.id)
        path.write_text(
            json.dumps(pkg.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )

        scenarios: list[Scenario] = []
        for i, s_data in enumerate(pkg.scenarios):
            faults: list[Fault] = []
            for f_data in s_data.get("faults", []):
                try:
                    fault_type = FaultType(f_data.get("fault_type", "component_down"))
                except ValueError:
                    fault_type = FaultType.COMPONENT_DOWN

                faults.append(Fault(
                    target_component_id=f_data.get("target_component_id", f"target-{i}"),
                    fault_type=fault_type,
                    severity=f_data.get("severity", 1.0),
                    duration_seconds=f_data.get("duration_seconds", 300),
                    parameters=f_data.get("parameters", {}),
                ))

            scenarios.append(Scenario(
                id=f"marketplace-{pkg.id}-{i}",
                name=s_data.get("name", f"{pkg.name} #{i + 1}"),
                description=s_data.get("description", pkg.description),
                faults=faults,
                traffic_multiplier=s_data.get("traffic_multiplier", 1.0),
            ))

        return scenarios

    def export_scenarios(
        self,
        scenarios: list,
        package_name: str,
        author: str = "ChaosProof User",
        category: str = "infrastructure",
        provider: str = "generic",
        severity: str = "medium",
        difficulty: str = "intermediate",
    ) -> ScenarioPackage:
        """Create a package from local Scenario objects for sharing."""
        scenario_dicts: list[dict] = []
        for s in scenarios:
            faults_data = []
            for f in s.faults:
                faults_data.append({
                    "target_component_id": f.target_component_id,
                    "fault_type": f.fault_type.value if hasattr(f.fault_type, "value") else str(f.fault_type),
                    "severity": f.severity,
                    "duration_seconds": f.duration_seconds,
                    "parameters": f.parameters,
                })
            scenario_dicts.append({
                "name": s.name,
                "description": s.description,
                "faults": faults_data,
                "traffic_multiplier": getattr(s, "traffic_multiplier", 1.0),
            })

        pkg_id = package_name.lower().replace(" ", "-").replace("_", "-")
        pkg = ScenarioPackage(
            id=pkg_id,
            name=package_name,
            version="1.0.0",
            description=f"Exported scenario package: {package_name}",
            author=author,
            category=category,
            provider=provider,
            severity=severity,
            tags=["exported", "custom"],
            scenarios=scenario_dicts,
            prerequisites=[],
            estimated_duration="30min",
            difficulty=difficulty,
        )

        # Save to store
        path = self._package_path(pkg.id)
        path.write_text(
            json.dumps(pkg.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return pkg

    def get_categories(self) -> list[MarketplaceCategory]:
        """Return all categories with current package counts."""
        packages = self._all_packages()
        counts: dict[str, int] = {}
        for pkg in packages:
            counts[pkg.category] = counts.get(pkg.category, 0) + 1

        result: list[MarketplaceCategory] = []
        for cat in CATEGORIES:
            cat_copy = MarketplaceCategory(
                name=cat.name,
                display_name=cat.display_name,
                description=cat.description,
                icon=cat.icon,
                package_count=counts.get(cat.name, 0),
            )
            result.append(cat_copy)
        return result

    def get_featured(self) -> list[ScenarioPackage]:
        """Return curated featured/top-pick packages."""
        return [p for p in self._all_packages() if p.featured]

    def get_popular(self) -> list[ScenarioPackage]:
        """Return packages sorted by download count descending."""
        packages = self._all_packages()
        packages.sort(key=lambda p: p.downloads, reverse=True)
        return packages[:10]

    def get_new(self) -> list[ScenarioPackage]:
        """Return recently added packages sorted by creation date descending."""
        packages = self._all_packages()
        packages.sort(key=lambda p: p.created_at, reverse=True)
        return packages[:10]

    def add_review(
        self,
        package_id: str,
        author: str,
        rating: int,
        comment: str = "",
    ) -> None:
        """Add or update a review on a package."""
        if rating < 1 or rating > 5:
            raise ValueError("Rating must be between 1 and 5")

        pkg = self.get_package(package_id)

        # Update existing review or append
        existing = [r for r in pkg.reviews if r.author == author]
        if existing:
            existing[0].rating = rating
            existing[0].comment = comment
            existing[0].date = datetime.now(timezone.utc)
        else:
            pkg.reviews.append(ScenarioReview(
                author=author,
                rating=rating,
                comment=comment,
            ))

        # Recalculate rating
        pkg.rating = pkg.average_rating

        # Persist
        path = self._package_path(pkg.id)
        path.write_text(
            json.dumps(pkg.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
