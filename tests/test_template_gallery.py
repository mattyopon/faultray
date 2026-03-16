"""Tests for the Infrastructure Template Gallery."""

from __future__ import annotations

import pytest
import yaml

from faultray.model.graph import InfraGraph
from faultray.templates.gallery import (
    GALLERY_TEMPLATES,
    InfraTemplate,
    TemplateCategory,
    TemplateGallery,
    _build_graph_from_template,
)


# ---------------------------------------------------------------------------
# Gallery registry tests
# ---------------------------------------------------------------------------


class TestGalleryRegistry:
    """Tests for the template registry."""

    def test_gallery_has_at_least_12_templates(self):
        assert len(GALLERY_TEMPLATES) >= 12

    def test_all_templates_have_unique_ids(self):
        ids = [t.id for t in GALLERY_TEMPLATES]
        assert len(ids) == len(set(ids)), f"Duplicate IDs found: {ids}"

    def test_all_templates_have_required_fields(self):
        for t in GALLERY_TEMPLATES:
            assert t.id, f"Template missing id"
            assert t.name, f"Template {t.id} missing name"
            assert isinstance(t.category, TemplateCategory), f"Template {t.id} bad category"
            assert t.description, f"Template {t.id} missing description"
            assert len(t.components) > 0, f"Template {t.id} has no components"
            assert len(t.edges) > 0, f"Template {t.id} has no edges"
            assert t.resilience_score > 0, f"Template {t.id} has zero resilience score"
            assert t.target_nines > 0, f"Template {t.id} has zero target nines"

    def test_expected_template_ids_exist(self):
        expected_ids = {
            "ha-web-3tier",
            "microservices-k8s",
            "data-pipeline-streaming",
            "serverless-api",
            "ml-training-inference",
            "multi-region-active-active",
            "iot-edge",
            "ecommerce-peak",
            "healthcare-hipaa",
            "fintech-dora",
            "event-driven-saga",
            "minimal-startup",
        }
        actual_ids = {t.id for t in GALLERY_TEMPLATES}
        assert expected_ids.issubset(actual_ids), (
            f"Missing templates: {expected_ids - actual_ids}"
        )

    def test_all_categories_represented(self):
        """At least some categories should be represented."""
        categories = {t.category for t in GALLERY_TEMPLATES}
        # Should have at least web_application, microservices, and a few others
        assert TemplateCategory.WEB_APPLICATION in categories
        assert TemplateCategory.MICROSERVICES in categories
        assert TemplateCategory.DATA_PIPELINE in categories

    def test_difficulty_levels_present(self):
        difficulties = {t.difficulty for t in GALLERY_TEMPLATES}
        assert "starter" in difficulties
        assert "intermediate" in difficulties or "advanced" in difficulties
        assert "expert" in difficulties


# ---------------------------------------------------------------------------
# TemplateGallery class tests
# ---------------------------------------------------------------------------


class TestTemplateGallery:
    """Tests for the TemplateGallery class."""

    def setup_method(self):
        self.gallery = TemplateGallery()

    def test_list_templates_returns_all(self):
        templates = self.gallery.list_templates()
        assert len(templates) >= 12

    def test_list_templates_filter_by_category(self):
        web_templates = self.gallery.list_templates(category="web_application")
        assert len(web_templates) >= 1
        for t in web_templates:
            assert t.category == TemplateCategory.WEB_APPLICATION

    def test_list_templates_filter_by_category_name(self):
        ms_templates = self.gallery.list_templates(category="microservices")
        assert len(ms_templates) >= 1

    def test_list_templates_unknown_category_returns_empty(self):
        result = self.gallery.list_templates(category="nonexistent_category")
        assert result == []

    def test_get_template_valid(self):
        t = self.gallery.get_template("ha-web-3tier")
        assert isinstance(t, InfraTemplate)
        assert t.id == "ha-web-3tier"

    def test_get_template_invalid_raises(self):
        with pytest.raises(KeyError, match="Unknown template"):
            self.gallery.get_template("nonexistent-template")

    def test_search_by_name(self):
        results = self.gallery.search("kubernetes")
        assert len(results) >= 1
        assert any("k8s" in t.id for t in results)

    def test_search_by_tag(self):
        results = self.gallery.search("kafka")
        assert len(results) >= 1

    def test_search_by_description(self):
        results = self.gallery.search("HIPAA")
        assert len(results) >= 1

    def test_search_case_insensitive(self):
        results_upper = self.gallery.search("KAFKA")
        results_lower = self.gallery.search("kafka")
        assert len(results_upper) == len(results_lower)

    def test_search_no_results(self):
        results = self.gallery.search("zzzznonexistent12345")
        assert results == []


# ---------------------------------------------------------------------------
# Template instantiation tests
# ---------------------------------------------------------------------------


class TestTemplateInstantiation:
    """Tests that templates can be instantiated as valid InfraGraphs."""

    def setup_method(self):
        self.gallery = TemplateGallery()

    @pytest.mark.parametrize(
        "template_id",
        [t.id for t in GALLERY_TEMPLATES],
    )
    def test_instantiate_creates_valid_graph(self, template_id: str):
        graph = self.gallery.instantiate(template_id)
        assert isinstance(graph, InfraGraph)
        assert len(graph.components) > 0

    @pytest.mark.parametrize(
        "template_id",
        [t.id for t in GALLERY_TEMPLATES],
    )
    def test_instantiate_has_dependencies(self, template_id: str):
        graph = self.gallery.instantiate(template_id)
        edges = graph.all_dependency_edges()
        assert len(edges) > 0, f"Template '{template_id}' graph has no dependencies"

    @pytest.mark.parametrize(
        "template_id",
        [t.id for t in GALLERY_TEMPLATES],
    )
    def test_instantiate_resilience_score_positive(self, template_id: str):
        graph = self.gallery.instantiate(template_id)
        score = graph.resilience_score()
        assert score > 0, f"Template '{template_id}' has zero resilience score"

    @pytest.mark.parametrize(
        "template_id",
        [t.id for t in GALLERY_TEMPLATES],
    )
    def test_instantiate_has_security_profiles(self, template_id: str):
        graph = self.gallery.instantiate(template_id)
        has_security = any(
            comp.security.encryption_in_transit or comp.security.encryption_at_rest
            for comp in graph.components.values()
        )
        assert has_security, f"Template '{template_id}' has no security config"

    @pytest.mark.parametrize(
        "template_id",
        [t.id for t in GALLERY_TEMPLATES],
    )
    def test_instantiate_has_cost_profiles(self, template_id: str):
        graph = self.gallery.instantiate(template_id)
        has_cost = any(
            comp.cost_profile.hourly_infra_cost > 0
            for comp in graph.components.values()
        )
        assert has_cost, f"Template '{template_id}' has no cost profile"


# ---------------------------------------------------------------------------
# YAML export tests
# ---------------------------------------------------------------------------


class TestTemplateYAMLExport:
    """Tests for YAML export functionality."""

    def setup_method(self):
        self.gallery = TemplateGallery()

    @pytest.mark.parametrize(
        "template_id",
        [t.id for t in GALLERY_TEMPLATES],
    )
    def test_to_yaml_is_valid(self, template_id: str):
        yaml_str = self.gallery.to_yaml(template_id)
        assert isinstance(yaml_str, str)
        assert len(yaml_str) > 0

        # Parse the YAML to verify it's valid
        data = yaml.safe_load(yaml_str)
        assert isinstance(data, dict)
        assert "schema_version" in data
        assert "components" in data
        assert "dependencies" in data
        assert len(data["components"]) > 0
        assert len(data["dependencies"]) > 0

    @pytest.mark.parametrize(
        "template_id",
        [t.id for t in GALLERY_TEMPLATES],
    )
    def test_yaml_loadable_by_loader(self, template_id: str, tmp_path):
        """Exported YAML must be loadable by the standard YAML loader."""
        from faultray.model.loader import load_yaml

        yaml_str = self.gallery.to_yaml(template_id)
        yaml_file = tmp_path / f"{template_id}.yaml"
        yaml_file.write_text(yaml_str, encoding="utf-8")

        graph = load_yaml(yaml_file)
        assert len(graph.components) > 0


# ---------------------------------------------------------------------------
# Template comparison tests
# ---------------------------------------------------------------------------


class TestTemplateComparison:
    """Tests for the compare_with functionality."""

    def setup_method(self):
        self.gallery = TemplateGallery()

    def _make_simple_graph(self) -> InfraGraph:
        """Create a simple test graph."""
        from faultray.model.components import Component, ComponentType, Dependency

        graph = InfraGraph()
        graph.add_component(Component(
            id="app",
            name="App Server",
            type=ComponentType.APP_SERVER,
            replicas=1,
        ))
        graph.add_component(Component(
            id="db",
            name="Database",
            type=ComponentType.DATABASE,
            replicas=1,
        ))
        graph.add_dependency(Dependency(
            source_id="app",
            target_id="db",
            dependency_type="requires",
        ))
        return graph

    def test_compare_with_returns_dict(self):
        user_graph = self._make_simple_graph()
        result = self.gallery.compare_with("minimal-startup", user_graph)
        assert isinstance(result, dict)
        assert "template_id" in result
        assert "user_score" in result
        assert "template_score" in result
        assert "score_gap" in result
        assert "recommendations" in result

    def test_compare_with_recommendations(self):
        user_graph = self._make_simple_graph()
        result = self.gallery.compare_with("ha-web-3tier", user_graph)
        # A simple graph should have many recommendations vs a HA template
        assert len(result["recommendations"]) > 0

    def test_compare_with_includes_feature_comparison(self):
        user_graph = self._make_simple_graph()
        result = self.gallery.compare_with("ha-web-3tier", user_graph)
        assert "feature_comparison" in result
        assert "failover" in result["feature_comparison"]
        assert "circuit_breakers" in result["feature_comparison"]
        assert "autoscaling" in result["feature_comparison"]

    def test_compare_with_component_comparison(self):
        user_graph = self._make_simple_graph()
        result = self.gallery.compare_with("ha-web-3tier", user_graph)
        assert "component_comparison" in result
        assert "user_count" in result["component_comparison"]
        assert "template_count" in result["component_comparison"]

    def test_compare_with_invalid_template_raises(self):
        user_graph = self._make_simple_graph()
        with pytest.raises(KeyError):
            self.gallery.compare_with("nonexistent-template", user_graph)


# ---------------------------------------------------------------------------
# Specific template content tests
# ---------------------------------------------------------------------------


class TestSpecificTemplates:
    """Content validation for specific templates."""

    def setup_method(self):
        self.gallery = TemplateGallery()

    def test_ha_web_3tier_has_cdn_alb_web_db_cache(self):
        graph = self.gallery.instantiate("ha-web-3tier")
        ids = set(graph.components.keys())
        assert "cdn" in ids
        assert "alb" in ids
        assert "web" in ids
        assert "db-primary" in ids
        assert "cache" in ids

    def test_healthcare_hipaa_compliance(self):
        t = self.gallery.get_template("healthcare-hipaa")
        assert "HIPAA" in t.compliance

    def test_fintech_dora_compliance(self):
        t = self.gallery.get_template("fintech-dora")
        assert "DORA" in t.compliance
        assert "PCI_DSS" in t.compliance

    def test_minimal_startup_is_starter_difficulty(self):
        t = self.gallery.get_template("minimal-startup")
        assert t.difficulty == "starter"

    def test_multi_region_has_multiple_regions(self):
        graph = self.gallery.instantiate("multi-region-active-active")
        ids = set(graph.components.keys())
        assert "region1-app" in ids
        assert "region2-app" in ids
        assert "global-lb" in ids

    def test_serverless_has_lambda_and_dynamodb(self):
        graph = self.gallery.instantiate("serverless-api")
        ids = set(graph.components.keys())
        assert "lambda-api" in ids
        assert "dynamodb" in ids

    def test_all_templates_have_mermaid_diagrams(self):
        for t in GALLERY_TEMPLATES:
            assert t.diagram_mermaid, f"Template '{t.id}' missing Mermaid diagram"

    def test_all_templates_have_best_practices(self):
        for t in GALLERY_TEMPLATES:
            assert len(t.best_practices) > 0, (
                f"Template '{t.id}' missing best practices"
            )
