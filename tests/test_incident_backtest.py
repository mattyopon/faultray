"""Tests for incident YAML files used in backtest expansion.

Validates that all incident YAML files in tests/incidents/ parse correctly
and conform to the expected schema for FaultRay backtest simulations.
"""

from __future__ import annotations

import glob
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore[import-untyped]

INCIDENTS_DIR = Path(__file__).parent / "incidents"

REQUIRED_INCIDENT_FIELDS = {
    "id",
    "provider",
    "date",
    "postmortem_url",
    "root_cause",
    "affected_services",
    "severity",
    "duration_hours",
}
REQUIRED_TOPOLOGY_COMPONENT_FIELDS = {"id", "type", "replicas"}
REQUIRED_DEPENDENCY_FIELDS = {"source", "target", "type"}
REQUIRED_EXPECTED_FIELDS = {"cascade_path", "blast_radius", "severity_level"}
VALID_COMPONENT_TYPES = {"app_server", "database", "load_balancer", "cache"}
VALID_SEVERITY_LEVELS = {"critical", "high", "medium", "low"}
VALID_DEPENDENCY_TYPES = {"requires", "optional"}


def _load_all_incident_files() -> list[tuple[str, dict[str, Any]]]:
    """Load all YAML incident files and return (filename, data) pairs."""
    pattern = str(INCIDENTS_DIR / "*.yaml")
    files = sorted(glob.glob(pattern))
    results: list[tuple[str, dict[str, Any]]] = []
    for filepath in files:
        with open(filepath) as f:
            data = yaml.safe_load(f)
        results.append((Path(filepath).name, data))
    return results


ALL_INCIDENTS = _load_all_incident_files()


@pytest.fixture(params=ALL_INCIDENTS, ids=[name for name, _ in ALL_INCIDENTS])
def incident_file(request: pytest.FixtureRequest) -> tuple[str, dict[str, Any]]:
    """Parametrized fixture yielding (filename, parsed_data) for each incident."""
    result: tuple[str, dict[str, Any]] = request.param
    return result


class TestIncidentYAMLSchema:
    """Validate that each incident YAML file has the correct structure."""

    def test_yaml_parses_successfully(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        assert data is not None, f"{filename}: YAML parsed to None"
        assert isinstance(data, dict), f"{filename}: top-level is not a dict"

    def test_has_incident_section(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        assert "incident" in data, f"{filename}: missing 'incident' section"

    def test_incident_has_required_fields(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        incident = data["incident"]
        missing = REQUIRED_INCIDENT_FIELDS - set(incident.keys())
        assert not missing, f"{filename}: incident missing fields: {missing}"

    def test_incident_id_is_string(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        incident_id = data["incident"]["id"]
        assert isinstance(incident_id, str), f"{filename}: incident.id is not a string"
        assert len(incident_id) > 0, f"{filename}: incident.id is empty"

    def test_severity_is_valid(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        severity = data["incident"]["severity"]
        assert severity in VALID_SEVERITY_LEVELS, f"{filename}: invalid severity '{severity}'"

    def test_affected_services_is_list(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        services = data["incident"]["affected_services"]
        assert isinstance(services, list), f"{filename}: affected_services is not a list"
        assert len(services) > 0, f"{filename}: affected_services is empty"

    def test_postmortem_url_is_http(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        url = data["incident"]["postmortem_url"]
        assert isinstance(url, str), f"{filename}: postmortem_url is not a string"
        assert url.startswith("http"), f"{filename}: postmortem_url does not start with http"

    def test_has_topology_section(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        assert "topology" in data, f"{filename}: missing 'topology' section"

    def test_topology_has_components(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        topology = data["topology"]
        assert "components" in topology, f"{filename}: topology missing 'components'"
        assert isinstance(topology["components"], list), f"{filename}: components is not a list"
        assert len(topology["components"]) > 0, f"{filename}: components is empty"

    def test_topology_components_have_required_fields(
        self, incident_file: tuple[str, dict[str, Any]]
    ) -> None:
        filename, data = incident_file
        for i, comp in enumerate(data["topology"]["components"]):
            missing = REQUIRED_TOPOLOGY_COMPONENT_FIELDS - set(comp.keys())
            assert not missing, f"{filename}: component[{i}] missing fields: {missing}"

    def test_component_types_are_valid(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        for comp in data["topology"]["components"]:
            assert (
                comp["type"] in VALID_COMPONENT_TYPES
            ), f"{filename}: component '{comp['id']}' has invalid type '{comp['type']}'"

    def test_topology_has_dependencies(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        topology = data["topology"]
        assert "dependencies" in topology, f"{filename}: topology missing 'dependencies'"
        assert isinstance(topology["dependencies"], list), f"{filename}: dependencies is not a list"
        assert len(topology["dependencies"]) > 0, f"{filename}: dependencies is empty"

    def test_dependency_fields_are_valid(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        component_ids = {c["id"] for c in data["topology"]["components"]}
        for i, dep in enumerate(data["topology"]["dependencies"]):
            missing = REQUIRED_DEPENDENCY_FIELDS - set(dep.keys())
            assert not missing, f"{filename}: dependency[{i}] missing fields: {missing}"
            assert (
                dep["source"] in component_ids
            ), f"{filename}: dependency[{i}] source '{dep['source']}' not in components"
            assert (
                dep["target"] in component_ids
            ), f"{filename}: dependency[{i}] target '{dep['target']}' not in components"
            assert (
                dep["type"] in VALID_DEPENDENCY_TYPES
            ), f"{filename}: dependency[{i}] has invalid type '{dep['type']}'"

    def test_has_expected_section(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        assert "expected" in data, f"{filename}: missing 'expected' section"

    def test_expected_has_required_fields(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        expected = data["expected"]
        missing = REQUIRED_EXPECTED_FIELDS - set(expected.keys())
        assert not missing, f"{filename}: expected missing fields: {missing}"

    def test_cascade_path_is_nonempty_list(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        cascade = data["expected"]["cascade_path"]
        assert isinstance(cascade, list), f"{filename}: cascade_path is not a list"
        assert len(cascade) > 0, f"{filename}: cascade_path is empty"

    def test_cascade_path_references_valid_components(
        self, incident_file: tuple[str, dict[str, Any]]
    ) -> None:
        filename, data = incident_file
        component_ids = {c["id"] for c in data["topology"]["components"]}
        for item in data["expected"]["cascade_path"]:
            assert (
                item in component_ids
            ), f"{filename}: cascade_path item '{item}' not in components"

    def test_blast_radius_is_positive_int(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        blast = data["expected"]["blast_radius"]
        assert isinstance(blast, int), f"{filename}: blast_radius is not an int"
        assert blast > 0, f"{filename}: blast_radius must be positive"

    def test_severity_level_is_valid(self, incident_file: tuple[str, dict[str, Any]]) -> None:
        filename, data = incident_file
        level = data["expected"]["severity_level"]
        assert level in VALID_SEVERITY_LEVELS, f"{filename}: invalid severity_level '{level}'"


class TestIncidentCollection:
    """Validate properties across the full collection of incident files."""

    def test_minimum_incident_count(self) -> None:
        assert (
            len(ALL_INCIDENTS) >= 35
        ), f"Expected >= 35 incident files, found {len(ALL_INCIDENTS)}"

    def test_unique_incident_ids(self) -> None:
        ids = [data["incident"]["id"] for _, data in ALL_INCIDENTS]
        duplicates = [x for x in ids if ids.count(x) > 1]
        assert len(duplicates) == 0, f"Duplicate incident IDs: {set(duplicates)}"

    def test_multiple_providers_represented(self) -> None:
        providers = {data["incident"]["provider"] for _, data in ALL_INCIDENTS}
        assert len(providers) >= 5, f"Expected >= 5 providers, found {len(providers)}: {providers}"
