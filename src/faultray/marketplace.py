"""Chaos Experiment Marketplace — community-contributed chaos scenarios.

Scenarios are stored locally in ``~/.faultray/marketplace/`` as JSON files.
No external service is required.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph
    from faultray.simulator.scenarios import Scenario


MARKETPLACE_DIR = Path.home() / ".faultray" / "marketplace"

VALID_CATEGORIES = {"database", "network", "security", "traffic", "compound"}
VALID_DOMAINS = {"ecommerce", "fintech", "saas", "healthcare", "general"}


@dataclass
class ScenarioManifest:
    """A published chaos scenario with metadata, ratings, and tamper-proof seal."""

    id: str
    name: str
    description: str
    category: str  # "database", "network", "security", "traffic", "compound"
    domain: str  # "ecommerce", "fintech", "saas", "healthcare", "general"
    author: str
    version: str
    blast_radius: float  # 0-1, measured
    component_types_required: list[str]  # e.g. ["database", "cache"]
    scenario_data: dict  # serialized Scenario
    ratings: list[dict] = field(default_factory=list)  # [{author, score, comment}]
    downloads: int = 0

    @property
    def average_rating(self) -> float:
        """Return the average rating score, or 0.0 if no ratings exist."""
        if not self.ratings:
            return 0.0
        return sum(r["score"] for r in self.ratings) / len(self.ratings)

    def seal(self, key: str) -> str:
        """Create a tamper-proof SHA-256 hash of the scenario data."""
        payload = json.dumps(self.scenario_data, sort_keys=True).encode() + key.encode()
        return hashlib.sha256(payload).hexdigest()

    def to_dict(self) -> dict:
        """Serialise the manifest to a plain dict."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "domain": self.domain,
            "author": self.author,
            "version": self.version,
            "blast_radius": self.blast_radius,
            "component_types_required": self.component_types_required,
            "scenario_data": self.scenario_data,
            "ratings": self.ratings,
            "downloads": self.downloads,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioManifest:
        """Deserialise a manifest from a plain dict."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            category=data["category"],
            domain=data["domain"],
            author=data["author"],
            version=data["version"],
            blast_radius=data["blast_radius"],
            component_types_required=data["component_types_required"],
            scenario_data=data["scenario_data"],
            ratings=data.get("ratings", []),
            downloads=data.get("downloads", 0),
        )


class FairnessProtocol:
    """Prevent marketplace scenarios from being overly destructive on unknown infra.

    If the target infrastructure has fewer matching component types than the
    scenario expects, the blast radius is reduced proportionally.
    """

    @staticmethod
    def apply(manifest: ScenarioManifest, target_graph: InfraGraph) -> ScenarioManifest:
        """Adjust blast radius based on component type coverage."""
        required = set(manifest.component_types_required)
        if not required:
            return manifest  # No requirements means no restriction
        target_types = {c.type.value for c in target_graph.components.values()}
        coverage = len(target_types & required) / len(required)
        if coverage < 0.5:
            manifest.blast_radius *= 0.6  # Significant reduction for unknown infra
        return manifest


class ScenarioMarketplace:
    """Local marketplace for chaos scenarios, stored as JSON files."""

    def __init__(self, store_path: Path | None = None) -> None:
        self._store = store_path or MARKETPLACE_DIR
        self._store.mkdir(parents=True, exist_ok=True)

    def _manifest_path(self, manifest_id: str) -> Path:
        return self._store / f"{manifest_id}.json"

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def publish(self, manifest: ScenarioManifest) -> str:
        """Persist a manifest and return its ID."""
        if not manifest.id:
            manifest.id = uuid.uuid4().hex[:12]
        path = self._manifest_path(manifest.id)
        path.write_text(json.dumps(manifest.to_dict(), indent=2, default=str), encoding="utf-8")
        return manifest.id

    def download(self, manifest_id: str) -> ScenarioManifest:
        """Load a manifest by ID, incrementing its download counter."""
        path = self._manifest_path(manifest_id)
        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["downloads"] = data.get("downloads", 0) + 1
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        return ScenarioManifest.from_dict(data)

    def get(self, manifest_id: str) -> ScenarioManifest:
        """Load a manifest by ID without changing counters."""
        path = self._manifest_path(manifest_id)
        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_id}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return ScenarioManifest.from_dict(data)

    def search(
        self,
        query: str = "",
        category: str = "",
        domain: str = "",
    ) -> list[ScenarioManifest]:
        """Search manifests by free-text query, category, or domain."""
        results: list[ScenarioManifest] = []
        for p in sorted(self._store.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                m = ScenarioManifest.from_dict(data)
            except (json.JSONDecodeError, KeyError):
                continue

            if category and m.category != category:
                continue
            if domain and m.domain != domain:
                continue
            if query:
                q = query.lower()
                haystack = f"{m.name} {m.description} {m.author}".lower()
                if q not in haystack:
                    continue
            results.append(m)
        return results

    def rate(
        self,
        manifest_id: str,
        author: str,
        score: int,
        comment: str = "",
    ) -> None:
        """Add or update a rating on a manifest."""
        if score < 1 or score > 5:
            raise ValueError("Score must be between 1 and 5")
        path = self._manifest_path(manifest_id)
        if not path.exists():
            raise FileNotFoundError(f"Manifest not found: {manifest_id}")

        data = json.loads(path.read_text(encoding="utf-8"))
        ratings = data.get("ratings", [])
        # Update existing rating by the same author, or add new
        for r in ratings:
            if r["author"] == author:
                r["score"] = score
                r["comment"] = comment
                break
        else:
            ratings.append({"author": author, "score": score, "comment": comment})
        data["ratings"] = ratings
        path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")

    def top_rated(self, n: int = 10) -> list[ScenarioManifest]:
        """Return the top-N manifests sorted by average rating (descending)."""
        all_manifests = self.search()
        rated = [m for m in all_manifests if m.ratings]
        rated.sort(key=lambda m: m.average_rating, reverse=True)
        return rated[:n]

    def import_to_simulation(
        self,
        manifest: ScenarioManifest,
        graph: InfraGraph,
    ) -> Scenario:
        """Convert a marketplace manifest into a runnable Scenario.

        Applies the FairnessProtocol and re-maps target component IDs to the
        closest matching components in the target graph.
        """
        from faultray.simulator.scenarios import Fault, FaultType, Scenario

        manifest = FairnessProtocol.apply(manifest, graph)

        # Re-map fault targets to actual component IDs in the target graph
        graph_ids = list(graph.components.keys())
        graph_types = {c.id: c.type.value for c in graph.components.values()}

        faults: list[Fault] = []
        for f_data in manifest.scenario_data.get("faults", []):
            target = f_data.get("target_component_id", "")
            # Try exact match first, then match by type
            if target not in graph_ids:
                # Find a component whose type matches the required type
                needed_type = f_data.get("_required_type", "")
                matched = [
                    cid
                    for cid, ctype in graph_types.items()
                    if ctype == needed_type and cid not in [ff.target_component_id for ff in faults]
                ]
                target = matched[0] if matched else (graph_ids[0] if graph_ids else target)

            try:
                fault_type = FaultType(f_data.get("fault_type", "component_down"))
            except ValueError:
                fault_type = FaultType.COMPONENT_DOWN

            faults.append(
                Fault(
                    target_component_id=target,
                    fault_type=fault_type,
                    severity=min(f_data.get("severity", 1.0) * manifest.blast_radius, 1.0),
                    duration_seconds=f_data.get("duration_seconds", 300),
                    parameters=f_data.get("parameters", {}),
                )
            )

        return Scenario(
            id=f"marketplace-{manifest.id}",
            name=manifest.name,
            description=manifest.description,
            faults=faults,
            traffic_multiplier=manifest.scenario_data.get("traffic_multiplier", 1.0),
        )
