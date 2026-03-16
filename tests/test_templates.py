"""Tests for Scenario Templates Library."""

from __future__ import annotations

from pathlib import Path

import pytest

from faultray.templates import TEMPLATES, get_template_path, list_templates


# ---------------------------------------------------------------------------
# Template registry tests
# ---------------------------------------------------------------------------


class TestTemplateRegistry:
    def test_templates_dict_not_empty(self):
        assert len(TEMPLATES) >= 5

    def test_all_expected_templates(self):
        expected = {"web-app", "microservices", "data-pipeline", "ecommerce", "fintech"}
        assert expected.issubset(set(TEMPLATES.keys()))

    def test_list_templates_returns_list(self):
        result = list_templates()
        assert isinstance(result, list)
        assert len(result) >= 5

    def test_list_templates_entry_keys(self):
        for entry in list_templates():
            assert "name" in entry
            assert "file" in entry
            assert "path" in entry

    def test_get_template_path_valid(self):
        path = get_template_path("web-app")
        assert isinstance(path, Path)
        assert path.name == "web_app_basic.yaml"

    def test_get_template_path_invalid_raises(self):
        with pytest.raises(KeyError, match="Unknown template"):
            get_template_path("nonexistent-template")


# ---------------------------------------------------------------------------
# Template file existence and loading tests
# ---------------------------------------------------------------------------


class TestTemplateFiles:
    @pytest.mark.parametrize("name", list(TEMPLATES.keys()))
    def test_template_file_exists(self, name: str):
        path = get_template_path(name)
        assert path.exists(), f"Template file missing: {path}"

    @pytest.mark.parametrize("name", list(TEMPLATES.keys()))
    def test_template_loadable(self, name: str):
        """Each template must be loadable by the YAML loader."""
        from faultray.model.loader import load_yaml

        path = get_template_path(name)
        graph = load_yaml(path)
        assert len(graph.components) > 0

    @pytest.mark.parametrize("name", list(TEMPLATES.keys()))
    def test_template_has_dependencies(self, name: str):
        from faultray.model.loader import load_yaml

        path = get_template_path(name)
        graph = load_yaml(path)
        edges = graph.all_dependency_edges()
        assert len(edges) > 0, f"Template '{name}' has no dependencies"

    @pytest.mark.parametrize("name", list(TEMPLATES.keys()))
    def test_template_resilience_score_positive(self, name: str):
        from faultray.model.loader import load_yaml

        path = get_template_path(name)
        graph = load_yaml(path)
        score = graph.resilience_score()
        assert score > 0, f"Template '{name}' has zero resilience score"

    @pytest.mark.parametrize("name", list(TEMPLATES.keys()))
    def test_template_has_security_profiles(self, name: str):
        """Templates should have at least some security settings."""
        from faultray.model.loader import load_yaml

        path = get_template_path(name)
        graph = load_yaml(path)
        has_security = any(
            comp.security.encryption_in_transit or comp.security.encryption_at_rest
            for comp in graph.components.values()
        )
        assert has_security, f"Template '{name}' has no security config"

    @pytest.mark.parametrize("name", list(TEMPLATES.keys()))
    def test_template_has_cost_profiles(self, name: str):
        """Templates should have realistic cost profiles."""
        from faultray.model.loader import load_yaml

        path = get_template_path(name)
        graph = load_yaml(path)
        has_cost = any(
            comp.cost_profile.hourly_infra_cost > 0
            for comp in graph.components.values()
        )
        assert has_cost, f"Template '{name}' has no cost profile"


# ---------------------------------------------------------------------------
# Template-specific content tests
# ---------------------------------------------------------------------------


class TestTemplateContent:
    def test_web_app_has_lb_app_db_cache(self):
        from faultray.model.loader import load_yaml
        from faultray.model.components import ComponentType

        graph = load_yaml(get_template_path("web-app"))
        types = {comp.type for comp in graph.components.values()}
        assert ComponentType.LOAD_BALANCER in types
        assert ComponentType.APP_SERVER in types
        assert ComponentType.DATABASE in types
        assert ComponentType.CACHE in types

    def test_fintech_has_hsm_and_waf(self):
        from faultray.model.loader import load_yaml

        graph = load_yaml(get_template_path("fintech"))
        ids = set(graph.components.keys())
        assert "hsm" in ids, "Fintech template must have HSM component"
        assert "waf" in ids, "Fintech template must have WAF component"
