"""Persistent store for feed-generated scenarios.

Saves analyzed incidents and generated scenarios to disk so they persist
across simulation runs.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from faultray.simulator.scenarios import Fault, FaultType, Scenario

logger = logging.getLogger(__name__)

DEFAULT_STORE_DIR = Path.home() / ".faultray"
DEFAULT_STORE_FILE = DEFAULT_STORE_DIR / "feed-scenarios.json"


def _ensure_store_dir() -> None:
    DEFAULT_STORE_DIR.mkdir(parents=True, exist_ok=True)


def _scenario_to_dict(s: Scenario) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "traffic_multiplier": s.traffic_multiplier,
        "faults": [
            {
                "target_component_id": f.target_component_id,
                "fault_type": f.fault_type.value,
                "severity": f.severity,
                "duration_seconds": f.duration_seconds,
                "parameters": f.parameters,
            }
            for f in s.faults
        ],
    }


def _dict_to_scenario(d: dict) -> Scenario:
    return Scenario(
        id=d["id"],
        name=d["name"],
        description=d["description"],
        traffic_multiplier=d.get("traffic_multiplier", 1.0),
        faults=[
            Fault(
                target_component_id=f["target_component_id"],
                fault_type=FaultType(f["fault_type"]),
                severity=f.get("severity", 1.0),
                duration_seconds=f.get("duration_seconds", 300),
                parameters=f.get("parameters", {}),
            )
            for f in d["faults"]
        ],
    )


def save_feed_scenarios(
    scenarios: list[Scenario],
    articles_meta: list[dict] | None = None,
    store_path: Path = DEFAULT_STORE_FILE,
) -> Path:
    """Save feed-generated scenarios to the store.

    Merges with existing scenarios (deduplicates by ID).
    Returns the path to the store file.
    """
    _ensure_store_dir()

    # Load existing
    existing = load_store_raw(store_path)
    existing_by_id = {s["id"]: s for s in existing.get("scenarios", [])}

    # Merge new scenarios
    for s in scenarios:
        existing_by_id[s.id] = _scenario_to_dict(s)

    # Merge article metadata
    existing_articles = {a["link"]: a for a in existing.get("articles", [])}
    for meta in (articles_meta or []):
        existing_articles[meta.get("link", "")] = meta

    store_data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "scenario_count": len(existing_by_id),
        "article_count": len(existing_articles),
        "scenarios": list(existing_by_id.values()),
        "articles": list(existing_articles.values()),
    }

    store_path.write_text(json.dumps(store_data, indent=2, ensure_ascii=False))
    return store_path


def load_feed_scenarios(store_path: Path = DEFAULT_STORE_FILE) -> list[Scenario]:
    """Load feed-generated scenarios from the store."""
    raw = load_store_raw(store_path)
    scenarios = []
    for d in raw.get("scenarios", []):
        try:
            scenarios.append(_dict_to_scenario(d))
        except (KeyError, ValueError) as exc:
            logger.warning("Skipping malformed feed scenario (id=%s): %s", d.get("id", "?"), exc)
            continue
    return scenarios


def load_store_raw(store_path: Path = DEFAULT_STORE_FILE) -> dict:
    """Load raw store data."""
    if not store_path.exists():
        return {"scenarios": [], "articles": [], "last_updated": None}
    try:
        return json.loads(store_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Could not read feed store at %s: %s", store_path, exc)
        return {"scenarios": [], "articles": [], "last_updated": None}


def clear_store(store_path: Path = DEFAULT_STORE_FILE) -> None:
    """Clear the feed scenario store."""
    if store_path.exists():
        store_path.unlink()


def get_store_stats(store_path: Path = DEFAULT_STORE_FILE) -> dict:
    """Get store statistics."""
    raw = load_store_raw(store_path)
    return {
        "last_updated": raw.get("last_updated"),
        "scenario_count": len(raw.get("scenarios", [])),
        "article_count": len(raw.get("articles", [])),
        "store_path": str(store_path),
    }
