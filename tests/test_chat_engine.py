"""Tests for the Conversational Infrastructure Chat Engine."""

from __future__ import annotations

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    CircuitBreakerConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
)
from infrasim.model.graph import InfraGraph
from infrasim.api.chat_engine import (
    ChatEngine,
    ChatIntent,
    ChatResponse,
    INTENT_PATTERNS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    replicas: int = 1,
    autoscaling: AutoScalingConfig | None = None,
    failover: FailoverConfig | None = None,
    region: RegionConfig | None = None,
) -> Component:
    return Component(
        id=cid,
        name=cid.replace("_", " ").title(),
        type=ctype,
        port=8080,
        replicas=replicas,
        autoscaling=autoscaling or AutoScalingConfig(),
        failover=failover or FailoverConfig(),
        region=region or RegionConfig(),
    )


def _simple_graph(
    components: list[Component],
    deps: list[tuple[str, str]] | None = None,
    circuit_breakers: list[tuple[str, str]] | None = None,
) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    cb_set = set(circuit_breakers or [])
    for src, tgt in deps or []:
        cb = CircuitBreakerConfig(enabled=True) if (src, tgt) in cb_set else CircuitBreakerConfig()
        g.add_dependency(Dependency(source_id=src, target_id=tgt, circuit_breaker=cb))
    return g


def _web_app_graph() -> InfraGraph:
    """Build a typical web application graph."""
    lb = _make_component("lb", ComponentType.LOAD_BALANCER, replicas=2)
    web = _make_component("web", ComponentType.WEB_SERVER, replicas=2)
    api = _make_component("api", ComponentType.APP_SERVER, replicas=1)
    db = _make_component("postgres", ComponentType.DATABASE, replicas=1)
    cache = _make_component("redis", ComponentType.CACHE, replicas=1)

    return _simple_graph(
        [lb, web, api, db, cache],
        [
            ("lb", "web"),
            ("web", "api"),
            ("api", "postgres"),
            ("api", "redis"),
        ],
    )


# ---------------------------------------------------------------------------
# Intent detection
# ---------------------------------------------------------------------------

class TestIntentDetection:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_detect_spof_english(self):
        assert self.engine.detect_intent("What are my single points of failure?") == ChatIntent.LIST_SPOF

    def test_detect_spof_abbreviation(self):
        assert self.engine.detect_intent("Show me SPOFs") == ChatIntent.LIST_SPOF

    def test_detect_spof_japanese(self):
        assert self.engine.detect_intent("単一障害点はどこ？") == ChatIntent.LIST_SPOF

    def test_detect_cascade(self):
        assert self.engine.detect_intent("What happens if postgres goes down?") == ChatIntent.CASCADE_ANALYSIS

    def test_detect_cascade_fail(self):
        assert self.engine.detect_intent("Which components are affected if redis fails?") == ChatIntent.CASCADE_ANALYSIS

    def test_detect_cascade_japanese(self):
        assert self.engine.detect_intent("DBが落ちたらどうなる？") == ChatIntent.CASCADE_ANALYSIS

    def test_detect_availability(self):
        assert self.engine.detect_intent("How many nines can I achieve?") == ChatIntent.AVAILABILITY_QUERY

    def test_detect_availability_sla(self):
        assert self.engine.detect_intent("What's my SLA?") == ChatIntent.AVAILABILITY_QUERY

    def test_detect_risk(self):
        assert self.engine.detect_intent("What's the most critical component?") == ChatIntent.RISK_ASSESSMENT

    def test_detect_risk_japanese(self):
        assert self.engine.detect_intent("リスクが一番高いのは？") == ChatIntent.RISK_ASSESSMENT

    def test_detect_config_check(self):
        assert self.engine.detect_intent("Which components don't have circuit breakers?") == ChatIntent.CONFIGURATION_CHECK

    def test_detect_config_missing(self):
        assert self.engine.detect_intent("Show me components without autoscaling") == ChatIntent.CONFIGURATION_CHECK

    def test_detect_recommendation(self):
        assert self.engine.detect_intent("How can I improve my infrastructure?") == ChatIntent.RECOMMENDATION

    def test_detect_recommendation_japanese(self):
        assert self.engine.detect_intent("改善するにはどうすれば？") == ChatIntent.RECOMMENDATION

    def test_detect_status(self):
        assert self.engine.detect_intent("Show me the status overview") == ChatIntent.GENERAL_STATUS

    def test_detect_status_greeting(self):
        assert self.engine.detect_intent("hello") == ChatIntent.GENERAL_STATUS

    def test_detect_help(self):
        assert self.engine.detect_intent("help") == ChatIntent.HELP

    def test_detect_help_japanese(self):
        assert self.engine.detect_intent("何ができる？") == ChatIntent.HELP

    def test_detect_unknown(self):
        assert self.engine.detect_intent("blargh flargh") == ChatIntent.UNKNOWN

    def test_detect_component_info(self):
        assert self.engine.detect_intent("Tell me about the database") == ChatIntent.COMPONENT_INFO

    def test_detect_comparison(self):
        assert self.engine.detect_intent("Compare web and api server") == ChatIntent.COMPARISON

    def test_detect_incident(self):
        assert self.engine.detect_intent("What if us-east-1 has an outage?") == ChatIntent.INCIDENT_IMPACT


# ---------------------------------------------------------------------------
# Component reference extraction
# ---------------------------------------------------------------------------

class TestComponentExtraction:
    def setup_method(self):
        self.engine = ChatEngine()
        self.graph = _web_app_graph()

    def test_extract_by_id(self):
        ref = self.engine.extract_component_reference("Tell me about postgres", self.graph)
        assert ref == "postgres"

    def test_extract_by_name(self):
        ref = self.engine.extract_component_reference("What about Redis?", self.graph)
        assert ref == "redis"

    def test_extract_longest_match(self):
        # "web" is a substring of "web" component
        ref = self.engine.extract_component_reference("What about the web server?", self.graph)
        assert ref == "web"

    def test_extract_none(self):
        ref = self.engine.extract_component_reference("Tell me about foobar", self.graph)
        assert ref is None


# ---------------------------------------------------------------------------
# SPOF handler
# ---------------------------------------------------------------------------

class TestSPOFHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_finds_spofs(self):
        graph = _web_app_graph()
        response = self.engine.ask("What are my SPOFs?", graph)
        assert response.intent == ChatIntent.LIST_SPOF
        assert "single point" in response.text.lower() or "SPOF" in response.text.upper() or "failure" in response.text.lower() or "point" in response.text.lower()
        # api, postgres, redis have replicas=1 and dependents
        assert response.data is not None
        spofs = response.data.get("spofs", [])
        spof_ids = [s["id"] for s in spofs]
        assert "api" in spof_ids
        assert "postgres" in spof_ids

    def test_no_spofs_when_all_redundant(self):
        # All components with dependents have replicas > 1
        lb = _make_component("lb", ComponentType.LOAD_BALANCER, replicas=2)
        web = _make_component("web", ComponentType.WEB_SERVER, replicas=2)
        db = _make_component("db", ComponentType.DATABASE, replicas=3)
        graph = _simple_graph([lb, web, db], [("lb", "web"), ("web", "db")])
        response = self.engine.ask("Any SPOFs?", graph)
        assert response.data["spofs"] == []

    def test_spof_suggestions(self):
        graph = _web_app_graph()
        response = self.engine.ask("What are my SPOFs?", graph)
        assert len(response.suggestions) > 0


# ---------------------------------------------------------------------------
# Cascade handler
# ---------------------------------------------------------------------------

class TestCascadeHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_cascade_with_component(self):
        graph = _web_app_graph()
        response = self.engine.ask("What happens if postgres goes down?", graph)
        assert response.intent == ChatIntent.CASCADE_ANALYSIS
        assert "postgres" in response.text.lower() or "Postgres" in response.text

    def test_cascade_no_component(self):
        graph = _web_app_graph()
        response = self.engine.ask("What happens if something goes down?", graph)
        assert response.intent == ChatIntent.CASCADE_ANALYSIS
        assert "component" in response.text.lower() or "Available" in response.text

    def test_cascade_leaf_node(self):
        # postgres is a leaf - no upstream dependents in a reverse sense
        # Actually, api depends on postgres, so postgres has dependents
        graph = _web_app_graph()
        response = self.engine.ask("What happens if lb fails?", graph)
        assert response.intent == ChatIntent.CASCADE_ANALYSIS


# ---------------------------------------------------------------------------
# Availability handler
# ---------------------------------------------------------------------------

class TestAvailabilityHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_availability_query(self):
        graph = _web_app_graph()
        response = self.engine.ask("How many nines can I achieve?", graph)
        assert response.intent == ChatIntent.AVAILABILITY_QUERY
        assert "availability" in response.text.lower() or "nines" in response.text.lower()
        assert response.data is not None
        assert "system_availability" in response.data
        assert 0 < response.data["system_availability"] <= 1.0

    def test_availability_shows_bottleneck(self):
        graph = _web_app_graph()
        response = self.engine.ask("What's my availability?", graph)
        assert "bottleneck" in response.text.lower()


# ---------------------------------------------------------------------------
# Risk handler
# ---------------------------------------------------------------------------

class TestRiskHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_risk_assessment(self):
        graph = _web_app_graph()
        response = self.engine.ask("What's the most critical component?", graph)
        assert response.intent == ChatIntent.RISK_ASSESSMENT
        assert response.data is not None
        assert "score" in response.data

    def test_risk_shows_breakdown(self):
        graph = _web_app_graph()
        response = self.engine.ask("Show me a risk assessment", graph)
        assert "resilience score" in response.text.lower()


# ---------------------------------------------------------------------------
# Configuration check handler
# ---------------------------------------------------------------------------

class TestConfigCheckHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_config_check_circuit_breakers(self):
        graph = _web_app_graph()
        response = self.engine.ask("Which components don't have circuit breakers?", graph)
        assert response.intent == ChatIntent.CONFIGURATION_CHECK
        assert response.data is not None

    def test_config_check_autoscaling(self):
        graph = _web_app_graph()
        response = self.engine.ask("Show me components without autoscaling", graph)
        assert response.intent == ChatIntent.CONFIGURATION_CHECK

    def test_no_issues_when_configured(self):
        # Single component, no dependents, no edges
        comp = _make_component("solo", ComponentType.CUSTOM, replicas=2,
                               autoscaling=AutoScalingConfig(enabled=True))
        graph = _simple_graph([comp])
        response = self.engine.ask("Show me missing configurations", graph)
        assert response.intent == ChatIntent.CONFIGURATION_CHECK


# ---------------------------------------------------------------------------
# Recommendation handler
# ---------------------------------------------------------------------------

class TestRecommendationHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_recommendations(self):
        graph = _web_app_graph()
        response = self.engine.ask("What do you recommend?", graph)
        assert response.intent == ChatIntent.RECOMMENDATION


# ---------------------------------------------------------------------------
# Status handler
# ---------------------------------------------------------------------------

class TestStatusHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_status_overview(self):
        graph = _web_app_graph()
        response = self.engine.ask("Show me the status", graph)
        assert response.intent == ChatIntent.GENERAL_STATUS
        assert "total components" in response.text.lower()
        assert response.data is not None

    def test_status_greeting(self):
        graph = _web_app_graph()
        response = self.engine.ask("hello", graph)
        assert response.intent == ChatIntent.GENERAL_STATUS


# ---------------------------------------------------------------------------
# Help handler
# ---------------------------------------------------------------------------

class TestHelpHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_help(self):
        graph = _web_app_graph()
        response = self.engine.ask("help", graph)
        assert response.intent == ChatIntent.HELP
        assert "single point" in response.text.lower()
        assert len(response.suggestions) > 0


# ---------------------------------------------------------------------------
# Unknown handler
# ---------------------------------------------------------------------------

class TestUnknownHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_unknown_question(self):
        graph = _web_app_graph()
        response = self.engine.ask("xyzzy plugh", graph)
        assert response.intent == ChatIntent.UNKNOWN
        assert len(response.suggestions) > 0


# ---------------------------------------------------------------------------
# Empty graph
# ---------------------------------------------------------------------------

class TestEmptyGraph:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_empty_graph_response(self):
        graph = InfraGraph()
        response = self.engine.ask("What are my SPOFs?", graph)
        assert "no infrastructure" in response.text.lower()
        assert response.intent == ChatIntent.UNKNOWN


# ---------------------------------------------------------------------------
# Component info handler
# ---------------------------------------------------------------------------

class TestComponentInfoHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_component_info_specific(self):
        graph = _web_app_graph()
        response = self.engine.ask("Tell me about postgres", graph)
        assert response.intent == ChatIntent.COMPONENT_INFO
        assert "postgres" in response.text.lower()
        assert response.data is not None
        assert response.data.get("component_id") == "postgres"

    def test_component_info_general(self):
        graph = _web_app_graph()
        response = self.engine.ask("Describe my components", graph)
        assert response.intent == ChatIntent.COMPONENT_INFO
        assert response.visualization == "table"


# ---------------------------------------------------------------------------
# Comparison handler
# ---------------------------------------------------------------------------

class TestComparisonHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_compare_two_components(self):
        graph = _web_app_graph()
        response = self.engine.ask("Compare web and api", graph)
        assert response.intent == ChatIntent.COMPARISON
        assert "web" in response.text.lower()

    def test_compare_needs_two(self):
        graph = _web_app_graph()
        response = self.engine.ask("Compare nothing vs nothing", graph)
        assert response.intent == ChatIntent.COMPARISON
        assert "two components" in response.text.lower() or "mention" in response.text.lower()


# ---------------------------------------------------------------------------
# Incident impact handler
# ---------------------------------------------------------------------------

class TestIncidentHandler:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_incident_general(self):
        graph = _web_app_graph()
        response = self.engine.ask("What would happen in a major outage?", graph)
        assert response.intent == ChatIntent.INCIDENT_IMPACT

    def test_incident_region_specific(self):
        comp = _make_component("web", ComponentType.WEB_SERVER,
                               region=RegionConfig(region="us-east-1"))
        graph = _simple_graph([comp])
        response = self.engine.ask("What if us-east-1 has an outage?", graph)
        assert response.intent == ChatIntent.INCIDENT_IMPACT
        assert "us-east-1" in response.text


# ---------------------------------------------------------------------------
# Suggestions
# ---------------------------------------------------------------------------

class TestSuggestions:
    def setup_method(self):
        self.engine = ChatEngine()

    def test_get_suggestions(self):
        graph = _web_app_graph()
        suggestions = self.engine.get_suggestions(graph)
        assert len(suggestions) >= 3
        assert any("single point" in s.lower() for s in suggestions)

    def test_get_suggestions_empty_graph(self):
        graph = InfraGraph()
        suggestions = self.engine.get_suggestions(graph)
        assert len(suggestions) >= 2


# ---------------------------------------------------------------------------
# ChatResponse dataclass
# ---------------------------------------------------------------------------

class TestChatResponse:
    def test_dataclass_defaults(self):
        r = ChatResponse(text="hello", intent=ChatIntent.HELP)
        assert r.text == "hello"
        assert r.intent == ChatIntent.HELP
        assert r.data is None
        assert r.suggestions == []
        assert r.visualization is None

    def test_dataclass_with_data(self):
        r = ChatResponse(
            text="result",
            intent=ChatIntent.LIST_SPOF,
            data={"spofs": []},
            suggestions=["Do this"],
            visualization="table",
        )
        assert r.data == {"spofs": []}
        assert r.visualization == "table"
