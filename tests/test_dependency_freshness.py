"""Tests for dependency freshness tracker."""

from __future__ import annotations

import pytest

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph
from faultray.simulator.dependency_freshness import (
    ComponentFreshness,
    DependencyFreshnessTracker,
    FreshnessLevel,
    FreshnessReport,
    TechCategory,
    TechInfo,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    name: str,
    ctype: ComponentType = ComponentType.DATABASE,
    replicas: int = 1,
    tags: list[str] | None = None,
) -> Component:
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    if tags:
        c.tags = tags
    return c


def _graph_with(*components: Component) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    return g


# ---------------------------------------------------------------------------
# Technology Detection — all supported techs
# ---------------------------------------------------------------------------


class TestTechnologyDetection:
    """Verify that detect_technology identifies every supported technology."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    # -- Databases --

    def test_detect_postgres_from_name(self):
        comp = _comp("pg", "postgres-primary-14")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "PostgreSQL"
        assert version == "14"

    def test_detect_postgres_pg_prefix(self):
        comp = _comp("pg", "pg-replica-15")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "PostgreSQL"
        assert version == "15"

    def test_detect_postgres_psql(self):
        comp = _comp("pg", "psql-analytics")
        tech, _ = self.tracker.detect_technology(comp)
        assert tech == "PostgreSQL"

    def test_detect_mysql(self):
        comp = _comp("db", "mysql-primary-8")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "MySQL"
        assert version == "8"

    def test_detect_mariadb(self):
        comp = _comp("db", "mariadb-cluster-11")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "MariaDB"
        assert version == "11"

    def test_detect_mongodb(self):
        comp = _comp("db", "mongo-shard-7")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "MongoDB"
        assert version == "7"

    def test_detect_dynamodb(self):
        comp = _comp("db", "dynamodb-users")
        tech, _ = self.tracker.detect_technology(comp)
        assert tech == "DynamoDB"

    def test_detect_cassandra(self):
        comp = _comp("db", "cassandra-ring-5")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Cassandra"
        assert version == "5"

    # -- Caches --

    def test_detect_redis(self):
        comp = _comp("cache", "redis-cluster-7")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Redis"
        assert version == "7"

    def test_detect_memcached(self):
        comp = _comp("cache", "memcached-session-1")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Memcached"
        assert version == "1"

    def test_detect_memcache_alias(self):
        comp = _comp("cache", "memcache-pool")
        tech, _ = self.tracker.detect_technology(comp)
        assert tech == "Memcached"

    def test_detect_elasticsearch(self):
        comp = _comp("search", "elastic-logs-8")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Elasticsearch"
        assert version == "8"

    def test_detect_elasticsearch_es_prefix(self):
        comp = _comp("search", "es-analytics")
        tech, _ = self.tracker.detect_technology(comp)
        assert tech == "Elasticsearch"

    # -- Queues --

    def test_detect_rabbitmq(self):
        comp = _comp("q", "rabbit-events-3")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "RabbitMQ"
        assert version == "3"

    def test_detect_rabbitmq_rmq(self):
        comp = _comp("q", "rmq-worker")
        tech, _ = self.tracker.detect_technology(comp)
        assert tech == "RabbitMQ"

    def test_detect_kafka(self):
        comp = _comp("q", "kafka-broker-3")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Kafka"
        assert version == "3"

    def test_detect_sqs(self):
        comp = _comp("q", "sqs-notifications")
        tech, _ = self.tracker.detect_technology(comp)
        assert tech == "SQS"

    # -- Runtimes --

    def test_detect_nodejs(self):
        comp = _comp("app", "nodejs-api-22")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Node.js"
        assert version == "22"

    def test_detect_node_prefix(self):
        comp = _comp("app", "node-backend-18")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Node.js"
        assert version == "18"

    def test_detect_python(self):
        comp = _comp("app", "python-worker-3.11")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Python"
        assert version == "3.11"

    def test_detect_java(self):
        comp = _comp("app", "java-service-21")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Java"
        assert version == "21"

    def test_detect_go(self):
        comp = _comp("app", "golang-gateway-1.22")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Go"
        assert version == "1.22"

    def test_detect_go_prefix(self):
        comp = _comp("app", "go-microservice")
        tech, _ = self.tracker.detect_technology(comp)
        assert tech == "Go"

    # -- Web / Proxy --

    def test_detect_nginx(self):
        comp = _comp("lb", "nginx-proxy-1.27")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Nginx"
        assert version == "1.27"

    def test_detect_apache(self):
        comp = _comp("web", "apache-server-2.4")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Apache"
        assert version == "2.4"

    def test_detect_haproxy(self):
        comp = _comp("lb", "haproxy-frontend-2.9")
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "HAProxy"
        assert version == "2.9"

    # -- Detection from tags --

    def test_detect_tech_from_tags(self):
        comp = _comp("db", "primary-database", tags=["postgres-14", "production"])
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "PostgreSQL"
        assert version == "14"

    def test_detect_version_from_tags_only(self):
        """Name has the tech hint; version is in tags."""
        comp = _comp("db", "redis-cache", tags=["v7.2", "production"])
        tech, version = self.tracker.detect_technology(comp)
        assert tech == "Redis"
        assert version == "7.2"

    def test_detect_unknown_technology(self):
        comp = _comp("svc", "mystery-service")
        tech, version = self.tracker.detect_technology(comp)
        assert tech is None
        assert version is None


# ---------------------------------------------------------------------------
# Version Extraction
# ---------------------------------------------------------------------------


class TestVersionExtraction:
    """Test version number extraction from component names."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    def test_version_with_dash(self):
        comp = _comp("x", "pg-14")
        _, version = self.tracker.detect_technology(comp)
        assert version == "14"

    def test_version_with_dot(self):
        comp = _comp("x", "python-3.11")
        _, version = self.tracker.detect_technology(comp)
        assert version == "3.11"

    def test_version_with_triple_dot(self):
        comp = _comp("x", "redis-7.2.4")
        _, version = self.tracker.detect_technology(comp)
        assert version == "7.2.4"

    def test_version_from_tag_with_v_prefix(self):
        comp = _comp("x", "postgres-db", tags=["v16"])
        _, version = self.tracker.detect_technology(comp)
        assert version == "16"

    def test_no_version_detected(self):
        comp = _comp("x", "redis-cache")
        _, version = self.tracker.detect_technology(comp)
        # "redis-cache" — the regex matches digits after dash; 'c' is not a digit
        # so no version is found
        assert version is None

    def test_version_underscore_separator(self):
        comp = _comp("x", "mongo_5")
        _, version = self.tracker.detect_technology(comp)
        assert version == "5"


# ---------------------------------------------------------------------------
# Freshness Classification
# ---------------------------------------------------------------------------


class TestFreshnessClassification:
    """Test CURRENT / AGING / OUTDATED / EOL classification."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    # CURRENT — latest or N-1

    def test_current_latest(self):
        comp = _comp("pg", "postgres-17")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.freshness == FreshnessLevel.CURRENT

    def test_current_n_minus_1(self):
        comp = _comp("pg", "postgres-16")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.freshness == FreshnessLevel.CURRENT

    # AGING — N-2

    def test_aging(self):
        comp = _comp("pg", "postgres-15")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.freshness == FreshnessLevel.AGING

    # OUTDATED — N-3+

    def test_outdated(self):
        comp = _comp("pg", "postgres-14")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.freshness == FreshnessLevel.OUTDATED

    def test_outdated_very_old(self):
        comp = _comp("pg", "postgres-12")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.freshness == FreshnessLevel.OUTDATED

    # EOL — in eol_versions list

    def test_eol_exact_match(self):
        comp = _comp("pg", "postgres-9")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL
        assert result.eol_date == "EOL"

    def test_eol_minor_version_match(self):
        comp = _comp("db", "mysql-5.7")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_minor_with_patch(self):
        """mysql 5.6.51 should match EOL pattern 5.6."""
        comp = _comp("db", "mysql-5.6.51")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_range_pattern(self):
        """Kafka 2.5 should match EOL range 2.0-2.8."""
        comp = _comp("q", "kafka-2.5")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "q")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_range_boundary_low(self):
        """Kafka 2.0 — lower bound of range."""
        comp = _comp("q", "kafka-2.0")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "q")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_range_boundary_high(self):
        """Kafka 2.8 — upper bound of range."""
        comp = _comp("q", "kafka-2.8")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "q")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_elasticsearch_range(self):
        """Elasticsearch 7.5 falls in EOL range 7.0-7.9."""
        comp = _comp("es", "elastic-search-7.5")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "es")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_risk_factors(self):
        comp = _comp("pg", "postgres-10")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL
        assert any("end-of-life" in rf for rf in result.risk_factors)

    def test_eol_node14(self):
        comp = _comp("app", "node-14")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "app")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_python37(self):
        comp = _comp("app", "python-3.7")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "app")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_java8(self):
        comp = _comp("app", "java-8")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "app")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_redis5(self):
        comp = _comp("cache", "redis-5")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "cache")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_mongodb_4_0(self):
        comp = _comp("db", "mongo-4.0")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_eol_rabbitmq_3_8(self):
        comp = _comp("q", "rabbit-3.8")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "q")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL


# ---------------------------------------------------------------------------
# Full Graph Analysis
# ---------------------------------------------------------------------------


class TestFullGraphAnalysis:
    """Test analyze() on complete graphs."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    def test_analyze_mixed_graph(self):
        graph = _graph_with(
            _comp("pg", "postgres-17"),     # CURRENT
            _comp("cache", "redis-5"),      # EOL
            _comp("app", "node-18"),        # EOL
            _comp("lb", "nginx-proxy-1.27"),  # CURRENT
        )
        report = self.tracker.analyze(graph)

        assert isinstance(report, FreshnessReport)
        assert len(report.components) == 4
        assert report.current_count == 2
        assert report.eol_count == 2
        assert report.aging_count == 0
        assert report.outdated_count == 0
        assert report.unknown_count == 0

    def test_analyze_all_current(self):
        graph = _graph_with(
            _comp("pg", "postgres-17"),
            _comp("cache", "redis-7"),
        )
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 100.0
        assert report.current_count == 2

    def test_analyze_all_eol(self):
        graph = _graph_with(
            _comp("pg", "postgres-9"),
            _comp("cache", "redis-5"),
        )
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 10.0
        assert report.eol_count == 2
        assert len(report.critical_upgrades) == 2

    def test_analyze_scoring(self):
        """Score = average of component freshness points."""
        graph = _graph_with(
            _comp("a", "postgres-17"),   # CURRENT = 100
            _comp("b", "redis-5"),       # EOL = 10
        )
        report = self.tracker.analyze(graph)
        expected_score = (100.0 + 10.0) / 2  # 55.0
        assert report.overall_freshness_score == expected_score

    def test_analyze_scoring_with_aging(self):
        """AGING component contributes 70 points."""
        graph = _graph_with(
            _comp("a", "postgres-15"),  # AGING = 70
        )
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 70.0

    def test_analyze_scoring_with_outdated(self):
        """OUTDATED component contributes 40 points."""
        graph = _graph_with(
            _comp("a", "postgres-14"),  # OUTDATED = 40
        )
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 40.0

    def test_analyze_scoring_with_unknown(self):
        """UNKNOWN component contributes 50 points."""
        graph = _graph_with(
            _comp("a", "mystery-svc"),  # UNKNOWN = 50
        )
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 50.0

    def test_analyze_critical_upgrades_format(self):
        graph = _graph_with(
            _comp("pg", "postgres-9"),
        )
        report = self.tracker.analyze(graph)
        assert len(report.critical_upgrades) == 1
        assert "postgres-9" in report.critical_upgrades[0]
        assert "PostgreSQL" in report.critical_upgrades[0]

    def test_analyze_recommendations_eol(self):
        graph = _graph_with(
            _comp("pg", "postgres-9"),
        )
        report = self.tracker.analyze(graph)
        assert any("CRITICAL" in r for r in report.recommendations)

    def test_analyze_recommendations_outdated(self):
        graph = _graph_with(
            _comp("pg", "postgres-14"),
        )
        report = self.tracker.analyze(graph)
        assert any("HIGH" in r for r in report.recommendations)

    def test_analyze_recommendations_aging(self):
        graph = _graph_with(
            _comp("pg", "postgres-15"),
        )
        report = self.tracker.analyze(graph)
        assert any("MEDIUM" in r for r in report.recommendations)

    def test_analyze_recommendations_unknown(self):
        graph = _graph_with(
            _comp("x", "some-generic-service"),
        )
        report = self.tracker.analyze(graph)
        assert any("INFO" in r for r in report.recommendations)


# ---------------------------------------------------------------------------
# Single Component Analysis
# ---------------------------------------------------------------------------


class TestSingleComponentAnalysis:
    """Test analyze_component()."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    def test_analyze_existing_component(self):
        graph = _graph_with(_comp("pg", "postgres-17"))
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.component_id == "pg"
        assert result.detected_tech == "PostgreSQL"
        assert result.detected_version == "17"
        assert result.freshness == FreshnessLevel.CURRENT

    def test_analyze_nonexistent_component(self):
        graph = _graph_with(_comp("pg", "postgres-17"))
        result = self.tracker.analyze_component(graph, "missing")
        assert result is None

    def test_analyze_component_with_tags(self):
        comp = _comp("db", "primary-database", tags=["postgres-14", "production"])
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.detected_tech == "PostgreSQL"
        assert result.detected_version == "14"

    def test_analyze_component_fields(self):
        graph = _graph_with(_comp("pg", "postgres-10"))
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.component_id == "pg"
        assert result.component_name == "postgres-10"
        assert result.freshness == FreshnessLevel.EOL
        assert result.tech_category == TechCategory.DATABASE
        assert result.upgrade_path is not None
        assert result.eol_date == "EOL"
        assert len(result.risk_factors) > 0

    def test_analyze_component_upgrade_path_for_current(self):
        """CURRENT components should have no upgrade path."""
        graph = _graph_with(_comp("pg", "postgres-17"))
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.upgrade_path is None

    def test_analyze_component_upgrade_path_for_eol(self):
        """EOL components should have an upgrade path."""
        graph = _graph_with(_comp("pg", "postgres-9"))
        result = self.tracker.analyze_component(graph, "pg")
        assert result is not None
        assert result.upgrade_path is not None
        assert "17" in result.upgrade_path


# ---------------------------------------------------------------------------
# Upgrade Suggestions
# ---------------------------------------------------------------------------


class TestUpgradeSuggestions:
    """Test get_upgrade_suggestions()."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    def test_no_suggestions_for_current(self):
        graph = _graph_with(_comp("pg", "postgres-17"))
        report = self.tracker.analyze(graph)
        suggestions = self.tracker.get_upgrade_suggestions(report)
        assert suggestions == []

    def test_suggestion_for_eol(self):
        graph = _graph_with(_comp("pg", "postgres-9"))
        report = self.tracker.analyze(graph)
        suggestions = self.tracker.get_upgrade_suggestions(report)
        assert len(suggestions) == 1
        assert suggestions[0]["priority"] == "critical"
        assert suggestions[0]["freshness"] == "eol"
        assert suggestions[0]["current_tech"] == "PostgreSQL"

    def test_suggestion_for_outdated(self):
        graph = _graph_with(_comp("pg", "postgres-14"))
        report = self.tracker.analyze(graph)
        suggestions = self.tracker.get_upgrade_suggestions(report)
        assert len(suggestions) == 1
        assert suggestions[0]["priority"] == "high"

    def test_suggestion_for_aging(self):
        graph = _graph_with(_comp("pg", "postgres-15"))
        report = self.tracker.analyze(graph)
        suggestions = self.tracker.get_upgrade_suggestions(report)
        assert len(suggestions) == 1
        assert suggestions[0]["priority"] == "medium"

    def test_suggestions_sorted_by_priority(self):
        graph = _graph_with(
            _comp("a", "postgres-15"),   # AGING -> medium
            _comp("b", "redis-5"),       # EOL -> critical
            _comp("c", "mongo-4.0"),     # EOL -> critical
            _comp("d", "node-14"),       # EOL -> critical
        )
        report = self.tracker.analyze(graph)
        suggestions = self.tracker.get_upgrade_suggestions(report)
        priorities = [s["priority"] for s in suggestions]
        assert priorities == sorted(
            priorities,
            key=lambda p: {"critical": 0, "high": 1, "medium": 2, "low": 3}[p],
        )

    def test_suggestion_fields(self):
        graph = _graph_with(_comp("pg", "postgres-9"))
        report = self.tracker.analyze(graph)
        suggestions = self.tracker.get_upgrade_suggestions(report)
        s = suggestions[0]
        assert "component" in s
        assert "current_tech" in s
        assert "current_version" in s
        assert "recommended_version" in s
        assert "freshness" in s
        assert "priority" in s

    def test_no_suggestions_for_unknown(self):
        graph = _graph_with(_comp("x", "mystery-service"))
        report = self.tracker.analyze(graph)
        suggestions = self.tracker.get_upgrade_suggestions(report)
        assert suggestions == []


# ---------------------------------------------------------------------------
# Tech Database
# ---------------------------------------------------------------------------


class TestTechDatabase:
    """Test get_tech_database() and database contents."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    def test_database_has_at_least_20_entries(self):
        db = self.tracker.get_tech_database()
        assert len(db) >= 20

    def test_database_returns_copy(self):
        db1 = self.tracker.get_tech_database()
        db2 = self.tracker.get_tech_database()
        assert db1 is not db2

    def test_database_contains_postgresql(self):
        db = self.tracker.get_tech_database()
        assert "postgresql" in db
        info = db["postgresql"]
        assert info.name == "PostgreSQL"
        assert info.latest_major == 17
        assert "9" in info.eol_versions

    def test_database_contains_redis(self):
        db = self.tracker.get_tech_database()
        assert "redis" in db
        assert db["redis"].category == TechCategory.CACHE

    def test_database_contains_kafka(self):
        db = self.tracker.get_tech_database()
        assert "kafka" in db
        assert db["kafka"].category == TechCategory.QUEUE

    def test_database_contains_nodejs(self):
        db = self.tracker.get_tech_database()
        assert "nodejs" in db
        assert db["nodejs"].category == TechCategory.RUNTIME
        assert db["nodejs"].latest_major == 22

    def test_database_cloud_services_have_no_eol(self):
        db = self.tracker.get_tech_database()
        for key, info in db.items():
            if info.category == TechCategory.CLOUD_SERVICE:
                assert info.eol_versions == [], (
                    f"Cloud service {key} should have no EOL versions"
                )

    def test_all_entries_have_recommended_version(self):
        db = self.tracker.get_tech_database()
        for key, info in db.items():
            assert info.recommended_version, (
                f"Tech {key} missing recommended_version"
            )

    def test_all_entries_have_notes(self):
        db = self.tracker.get_tech_database()
        for key, info in db.items():
            assert info.notes, f"Tech {key} missing notes"


# ---------------------------------------------------------------------------
# Unknown / Undetectable Components
# ---------------------------------------------------------------------------


class TestUnknownComponents:
    """Test behaviour when technology cannot be detected."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    def test_unknown_tech_from_name(self):
        comp = _comp("svc", "custom-payment-gateway")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "svc")
        assert result is not None
        assert result.freshness == FreshnessLevel.UNKNOWN
        assert result.detected_tech is None
        assert result.detected_version is None
        assert result.tech_category is None

    def test_unknown_tech_risk_factors(self):
        comp = _comp("svc", "custom-service")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "svc")
        assert result is not None
        assert len(result.risk_factors) > 0
        assert any("detect" in rf.lower() or "unable" in rf.lower()
                    for rf in result.risk_factors)

    def test_tech_detected_but_no_version(self):
        """Known tech but no version → UNKNOWN freshness."""
        comp = _comp("cache", "redis-cache")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "cache")
        assert result is not None
        assert result.detected_tech == "Redis"
        assert result.detected_version is None
        assert result.freshness == FreshnessLevel.UNKNOWN
        assert result.tech_category == TechCategory.CACHE

    def test_cloud_service_no_version(self):
        """Managed cloud services typically have no version."""
        comp = _comp("q", "sqs-orders")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "q")
        assert result is not None
        assert result.detected_tech == "SQS"
        assert result.freshness == FreshnessLevel.UNKNOWN


# ---------------------------------------------------------------------------
# Scoring Calculation
# ---------------------------------------------------------------------------


class TestScoringCalculation:
    """Test the overall_freshness_score calculation."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    def test_all_current_score(self):
        graph = _graph_with(
            _comp("a", "postgres-17"),
            _comp("b", "redis-7"),
            _comp("c", "nginx-proxy-1.27"),
        )
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 100.0

    def test_all_eol_score(self):
        graph = _graph_with(
            _comp("a", "postgres-9"),
            _comp("b", "redis-5"),
        )
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 10.0

    def test_mixed_score(self):
        """CURRENT(100) + EOL(10) → avg 55.0."""
        graph = _graph_with(
            _comp("a", "postgres-17"),
            _comp("b", "redis-5"),
        )
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 55.0

    def test_single_aging_score(self):
        graph = _graph_with(_comp("a", "postgres-15"))
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 70.0

    def test_single_outdated_score(self):
        graph = _graph_with(_comp("a", "postgres-14"))
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 40.0

    def test_single_unknown_score(self):
        graph = _graph_with(_comp("a", "mystery-svc"))
        report = self.tracker.analyze(graph)
        assert report.overall_freshness_score == 50.0

    def test_complex_mix_score(self):
        """CURRENT(100) + AGING(70) + OUTDATED(40) + EOL(10) → avg 55.0."""
        graph = _graph_with(
            _comp("a", "postgres-17"),    # CURRENT  = 100
            _comp("b", "postgres-15"),    # AGING    = 70
            _comp("c", "postgres-14"),    # OUTDATED = 40
            _comp("d", "postgres-9"),     # EOL      = 10
        )
        report = self.tracker.analyze(graph)
        expected = (100 + 70 + 40 + 10) / 4  # 55.0
        assert report.overall_freshness_score == expected


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    def test_empty_graph(self):
        graph = InfraGraph()
        report = self.tracker.analyze(graph)
        assert isinstance(report, FreshnessReport)
        assert len(report.components) == 0
        assert report.overall_freshness_score == 100.0
        assert report.current_count == 0
        assert report.aging_count == 0
        assert report.outdated_count == 0
        assert report.eol_count == 0
        assert report.unknown_count == 0
        assert report.critical_upgrades == []
        assert report.recommendations == []

    def test_single_component_graph(self):
        graph = _graph_with(_comp("pg", "postgres-17"))
        report = self.tracker.analyze(graph)
        assert len(report.components) == 1

    def test_graph_with_no_detectable_tech(self):
        graph = _graph_with(
            _comp("a", "frontend-app"),
            _comp("b", "backend-api"),
            _comp("c", "worker-process"),
        )
        report = self.tracker.analyze(graph)
        assert report.unknown_count == 3
        assert report.overall_freshness_score == 50.0

    def test_component_with_empty_tags(self):
        comp = _comp("svc", "redis-cache", tags=[])
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "svc")
        assert result is not None

    def test_component_with_many_tags(self):
        comp = _comp(
            "db", "primary-db",
            tags=["production", "tier-1", "postgres-16", "us-east-1"],
        )
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.detected_tech == "PostgreSQL"
        assert result.detected_version == "16"

    def test_version_range_outside_eol(self):
        """Kafka 3.5 is NOT in EOL range 2.0-2.8."""
        comp = _comp("q", "kafka-3.5")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "q")
        assert result is not None
        assert result.freshness != FreshnessLevel.EOL

    def test_mariadb_eol_10_3(self):
        comp = _comp("db", "mariadb-10.3")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_mariadb_current(self):
        comp = _comp("db", "mariadb-11")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.freshness == FreshnessLevel.CURRENT

    def test_cassandra_eol_3(self):
        comp = _comp("db", "cassandra-3")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_freshness_level_enum_values(self):
        assert FreshnessLevel.CURRENT.value == "current"
        assert FreshnessLevel.AGING.value == "aging"
        assert FreshnessLevel.OUTDATED.value == "outdated"
        assert FreshnessLevel.EOL.value == "eol"
        assert FreshnessLevel.UNKNOWN.value == "unknown"

    def test_tech_category_enum_values(self):
        assert TechCategory.DATABASE.value == "database"
        assert TechCategory.CACHE.value == "cache"
        assert TechCategory.QUEUE.value == "queue"
        assert TechCategory.RUNTIME.value == "runtime"
        assert TechCategory.OS.value == "os"
        assert TechCategory.FRAMEWORK.value == "framework"
        assert TechCategory.CLOUD_SERVICE.value == "cloud_service"

    def test_dynamodb_detected_from_dynamo_prefix(self):
        comp = _comp("db", "dynamo-table-users")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.detected_tech == "DynamoDB"

    def test_node_with_space_in_name(self):
        comp = _comp("app", "node server")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "app")
        assert result is not None
        assert result.detected_tech == "Node.js"

    def test_large_graph(self):
        """Analyze a graph with many components."""
        components = []
        for i in range(50):
            components.append(_comp(f"pg-{i}", f"postgres-{17 - (i % 5)}"))
        graph = _graph_with(*components)
        report = self.tracker.analyze(graph)
        assert len(report.components) == 50
        total = (
            report.current_count
            + report.aging_count
            + report.outdated_count
            + report.eol_count
            + report.unknown_count
        )
        assert total == 50

    def test_upgrade_suggestions_empty_for_all_current_and_unknown(self):
        graph = _graph_with(
            _comp("a", "postgres-17"),
            _comp("b", "mystery-svc"),
        )
        report = self.tracker.analyze(graph)
        suggestions = self.tracker.get_upgrade_suggestions(report)
        assert suggestions == []

    def test_elasticsearch_6_eol(self):
        comp = _comp("es", "elastic-6")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "es")
        assert result is not None
        assert result.freshness == FreshnessLevel.EOL

    def test_mongodb_current_version(self):
        comp = _comp("db", "mongo-7")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.freshness == FreshnessLevel.CURRENT

    def test_java_21_current(self):
        comp = _comp("app", "java-21")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "app")
        assert result is not None
        assert result.freshness == FreshnessLevel.CURRENT

    def test_go_current(self):
        comp = _comp("app", "golang-1.22")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "app")
        assert result is not None
        assert result.freshness == FreshnessLevel.CURRENT

    def test_nginx_current(self):
        comp = _comp("lb", "nginx-1.27")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "lb")
        assert result is not None
        assert result.freshness == FreshnessLevel.CURRENT

    def test_apache_current(self):
        comp = _comp("web", "apache-2.4")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "web")
        assert result is not None
        assert result.freshness == FreshnessLevel.CURRENT

    def test_haproxy_current(self):
        comp = _comp("lb", "haproxy-2.9")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "lb")
        assert result is not None
        assert result.freshness == FreshnessLevel.CURRENT


# ---------------------------------------------------------------------------
# Internal Method Edge Cases (for coverage)
# ---------------------------------------------------------------------------


class TestInternalEdgeCases:
    """Cover remaining internal branches for near-100% coverage."""

    def setup_method(self):
        self.tracker = DependencyFreshnessTracker()

    def test_tech_detected_but_not_in_database(self):
        """When detect_technology matches a pattern but the key is missing
        from the tech database, we should get UNKNOWN with detected_tech set."""
        # Temporarily inject a detection pattern for a tech not in the DB
        import faultray.simulator.dependency_freshness as mod
        original_patterns = mod._DETECTION_PATTERNS
        mod._DETECTION_PATTERNS = [("fakedb", "fakedb")] + list(original_patterns)
        try:
            comp = _comp("db", "fakedb-primary-9")
            graph = _graph_with(comp)
            result = self.tracker.analyze_component(graph, "db")
            assert result is not None
            assert result.freshness == FreshnessLevel.UNKNOWN
            assert result.detected_tech == "fakedb"
            assert any("not in freshness database" in rf for rf in result.risk_factors)
        finally:
            mod._DETECTION_PATTERNS = original_patterns

    def test_version_in_range_invalid_format(self):
        """_version_in_range with a range that has no dash returns False."""
        result = self.tracker._version_in_range("2.5", "nope")
        assert result is False

    def test_version_in_range_non_numeric(self):
        """_version_in_range with non-numeric version returns False."""
        result = self.tracker._version_in_range("abc", "1.0-2.0")
        assert result is False

    def test_parse_major_non_numeric(self):
        """_parse_major with a non-numeric string returns None."""
        result = DependencyFreshnessTracker._parse_major("abc")
        assert result is None

    def test_parse_major_empty_string(self):
        """_parse_major with an empty string returns None."""
        result = DependencyFreshnessTracker._parse_major("")
        assert result is None

    def test_resolve_tech_key_fallback(self):
        """_resolve_tech_key falls back to normalized name when not in DB."""
        result = self.tracker._resolve_tech_key("Unknown Tech 2.0")
        assert result == "unknowntech20"

    def test_classify_freshness_unparseable_major(self):
        """A non-EOL version with unparseable major returns UNKNOWN."""
        tech_info = TechInfo(
            name="TestTech",
            category=TechCategory.DATABASE,
            latest_major=10,
            eol_versions=[],
            recommended_version="TestTech 10",
            notes="Test",
        )
        freshness, risk_factors, eol_date = self.tracker._classify_freshness(
            "abc", tech_info
        )
        assert freshness == FreshnessLevel.UNKNOWN
        assert any("Could not parse" in rf for rf in risk_factors)
        assert eol_date is None

    def test_cockroachdb_detection(self):
        """Test CockroachDB detection via 'cockroach' pattern."""
        comp = _comp("db", "cockroach-cluster-24")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.detected_tech == "CockroachDB"
        assert result.detected_version == "24"
        assert result.freshness == FreshnessLevel.CURRENT

    def test_cockroachdb_crdb_prefix(self):
        """Test CockroachDB detection via 'crdb' pattern."""
        comp = _comp("db", "crdb-node-22")
        graph = _graph_with(comp)
        result = self.tracker.analyze_component(graph, "db")
        assert result is not None
        assert result.detected_tech == "CockroachDB"
        assert result.freshness == FreshnessLevel.EOL

    def test_cockroachdb_in_database(self):
        db = self.tracker.get_tech_database()
        assert "cockroachdb" in db
        assert db["cockroachdb"].latest_major == 24
