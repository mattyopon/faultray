"""Tests for Natural Language to Infrastructure Converter.

Tests cover:
1. Simple English input
2. Complex multi-component input
3. Japanese input
4. Property extraction (CPU, memory, autoscaling)
5. Multi-sentence input
6. Edge cases (empty, no components, ambiguous)
7. YAML generation format
8. InfraGraph generation
9. Read replica handling
10. Relationship inference
"""

from __future__ import annotations

import pytest
import yaml

from faultray.ai.nl_to_infra import (
    NLInfraParser,
    ParsedComponent,
    ParsedInfrastructure,
    ParsedRelationship,
)
from faultray.model.components import ComponentType


@pytest.fixture
def parser() -> NLInfraParser:
    """Create a fresh parser instance for each test."""
    return NLInfraParser()


# ---------------------------------------------------------------------------
# 1. Simple input
# ---------------------------------------------------------------------------


class TestSimpleParsing:
    """Test basic component extraction."""

    def test_simple_web_servers_behind_lb(self, parser: NLInfraParser) -> None:
        """2 web servers behind a load balancer."""
        parsed = parser.parse("2 web servers behind a load balancer")

        # Should find both web server and load balancer
        types = {c.component_type for c in parsed.components}
        assert ComponentType.WEB_SERVER in types
        assert ComponentType.LOAD_BALANCER in types

        # Web server should have 2 replicas
        web_servers = [
            c for c in parsed.components if c.component_type == ComponentType.WEB_SERVER
        ]
        assert len(web_servers) == 1
        assert web_servers[0].replicas == 2

    def test_single_alb(self, parser: NLInfraParser) -> None:
        """ALB alone should be detected."""
        parsed = parser.parse("An ALB for our service")

        assert len(parsed.components) >= 1
        alb = [c for c in parsed.components if c.name == "alb"]
        assert len(alb) == 1
        assert alb[0].component_type == ComponentType.LOAD_BALANCER

    def test_redis_cache(self, parser: NLInfraParser) -> None:
        """Redis should be detected as CACHE."""
        parsed = parser.parse("We need a Redis cache")

        cache_comps = [
            c for c in parsed.components if c.component_type == ComponentType.CACHE
        ]
        assert len(cache_comps) >= 1

    def test_sqs_queue(self, parser: NLInfraParser) -> None:
        """SQS should be detected as QUEUE."""
        parsed = parser.parse("Add an SQS queue for async processing")

        queue_comps = [
            c for c in parsed.components if c.component_type == ComponentType.QUEUE
        ]
        assert len(queue_comps) >= 1


# ---------------------------------------------------------------------------
# 2. Complex multi-component input
# ---------------------------------------------------------------------------


class TestComplexParsing:
    """Test complex multi-component descriptions."""

    def test_full_stack(self, parser: NLInfraParser) -> None:
        """ALB + 3 EC2 + Aurora with 2 read replicas + Redis + SQS + S3."""
        text = (
            "ALB with 3 EC2 instances connected to Aurora primary with 2 read replicas, "
            "Redis cache, SQS queue, and S3 for storage"
        )
        parsed = parser.parse(text)

        types = {c.component_type for c in parsed.components}
        assert ComponentType.LOAD_BALANCER in types  # ALB
        assert ComponentType.APP_SERVER in types  # EC2
        assert ComponentType.DATABASE in types  # Aurora
        assert ComponentType.CACHE in types  # Redis
        assert ComponentType.QUEUE in types  # SQS
        assert ComponentType.STORAGE in types  # S3

        # EC2 should have 3 replicas
        ec2_comps = [
            c for c in parsed.components
            if c.component_type == ComponentType.APP_SERVER
            and "ec2" in c.name
        ]
        assert len(ec2_comps) >= 1
        assert ec2_comps[0].replicas == 3

        # Should have relationships
        assert len(parsed.relationships) > 0

    def test_read_replicas_create_separate_component(
        self, parser: NLInfraParser
    ) -> None:
        """Read replicas should create a separate database component."""
        parsed = parser.parse("Aurora with 2 read replicas")

        db_comps = [
            c for c in parsed.components if c.component_type == ComponentType.DATABASE
        ]
        # Should have primary + replica
        assert len(db_comps) == 2

        primary = [c for c in db_comps if "primary" in c.name]
        replica = [c for c in db_comps if "replica" in c.name]

        assert len(primary) == 1
        assert len(replica) == 1
        assert primary[0].replicas == 1
        assert replica[0].replicas == 2


# ---------------------------------------------------------------------------
# 3. Japanese input
# ---------------------------------------------------------------------------


class TestJapaneseParsing:
    """Test Japanese language input."""

    def test_japanese_basic(self, parser: NLInfraParser) -> None:
        """ALBの後ろにEC2が3台、Auroraに接続."""
        parsed = parser.parse("ALBの後ろにEC2が3台、Auroraに接続")

        types = {c.component_type for c in parsed.components}
        assert ComponentType.LOAD_BALANCER in types  # ALB
        assert ComponentType.APP_SERVER in types  # EC2
        assert ComponentType.DATABASE in types  # Aurora

        # EC2 should have 3 replicas
        ec2_comps = [
            c for c in parsed.components
            if c.component_type == ComponentType.APP_SERVER
        ]
        assert len(ec2_comps) >= 1
        assert ec2_comps[0].replicas == 3

    def test_japanese_cache(self, parser: NLInfraParser) -> None:
        """Redisキャッシュを追加."""
        parsed = parser.parse("Redisキャッシュを追加")

        cache_comps = [
            c for c in parsed.components if c.component_type == ComponentType.CACHE
        ]
        assert len(cache_comps) >= 1

    def test_japanese_lb(self, parser: NLInfraParser) -> None:
        """ロードバランサーの後ろにサーバーが2台."""
        parsed = parser.parse("ロードバランサーの後ろにサーバーが2台")

        types = {c.component_type for c in parsed.components}
        assert ComponentType.LOAD_BALANCER in types
        assert ComponentType.APP_SERVER in types


# ---------------------------------------------------------------------------
# 4. Property extraction
# ---------------------------------------------------------------------------


class TestPropertyExtraction:
    """Test extracting properties like CPU, memory, autoscaling."""

    def test_cpu_and_memory(self, parser: NLInfraParser) -> None:
        """4 web servers with 8 vCPU, 16GB RAM."""
        parsed = parser.parse(
            "4 web servers with 8 vCPU, 16GB RAM, autoscaling enabled, behind ALB with circuit breaker"
        )

        web_servers = [
            c for c in parsed.components if c.component_type == ComponentType.WEB_SERVER
        ]
        assert len(web_servers) >= 1
        ws = web_servers[0]
        assert ws.replicas == 4
        assert ws.properties.get("cpu") == 8
        assert ws.properties.get("memory_gb") == 16
        assert ws.properties.get("autoscaling") is True

    def test_autoscaling_property(self, parser: NLInfraParser) -> None:
        """Autoscaling should be detected."""
        parsed = parser.parse("3 EC2 instances with autoscaling")

        ec2 = [c for c in parsed.components if "ec2" in c.name]
        assert len(ec2) >= 1
        assert ec2[0].properties.get("autoscaling") is True

    def test_failover_property(self, parser: NLInfraParser) -> None:
        """Failover should be detected."""
        parsed = parser.parse("Aurora database with failover enabled")

        db = [c for c in parsed.components if c.component_type == ComponentType.DATABASE]
        assert len(db) >= 1
        assert db[0].properties.get("failover") is True

    def test_circuit_breaker_property(self, parser: NLInfraParser) -> None:
        """Circuit breaker should be detected."""
        parsed = parser.parse("ALB with circuit breaker")

        alb = [c for c in parsed.components if c.name == "alb"]
        assert len(alb) == 1
        assert alb[0].properties.get("circuit_breaker") is True


# ---------------------------------------------------------------------------
# 5. Multi-sentence input
# ---------------------------------------------------------------------------


class TestMultiSentence:
    """Test multi-sentence descriptions."""

    def test_multi_sentence_architecture(self, parser: NLInfraParser) -> None:
        """Multiple sentences describing a full architecture."""
        text = (
            "I have a web app. "
            "The frontend is served by CloudFront CDN. "
            "Behind it is an ALB distributing to 4 app servers. "
            "The app uses PostgreSQL with a read replica and Redis for caching."
        )
        parsed = parser.parse(text)

        types = {c.component_type for c in parsed.components}
        assert ComponentType.LOAD_BALANCER in types  # CloudFront + ALB
        assert ComponentType.APP_SERVER in types  # 4 app servers
        assert ComponentType.DATABASE in types  # PostgreSQL
        assert ComponentType.CACHE in types  # Redis

        # App servers should have 4 replicas
        app_servers = [
            c for c in parsed.components if c.component_type == ComponentType.APP_SERVER
        ]
        assert len(app_servers) >= 1
        assert any(s.replicas == 4 for s in app_servers)

        # PostgreSQL should have primary and replica
        db_comps = [
            c for c in parsed.components if c.component_type == ComponentType.DATABASE
        ]
        assert len(db_comps) >= 2  # primary + replica

    def test_three_tier_architecture(self, parser: NLInfraParser) -> None:
        """Classic 3-tier: LB -> App -> DB."""
        text = (
            "A load balancer distributing to 2 web servers. "
            "The web servers connect to a MySQL database."
        )
        parsed = parser.parse(text)

        types = {c.component_type for c in parsed.components}
        assert ComponentType.LOAD_BALANCER in types
        assert ComponentType.WEB_SERVER in types
        assert ComponentType.DATABASE in types

        # Should have LB -> web server and web server -> DB relationships
        assert len(parsed.relationships) >= 2


# ---------------------------------------------------------------------------
# 6. Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_input(self, parser: NLInfraParser) -> None:
        """Empty input should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            parser.parse("")

    def test_whitespace_only(self, parser: NLInfraParser) -> None:
        """Whitespace-only input should raise ValueError."""
        with pytest.raises(ValueError, match="empty"):
            parser.parse("   \n\t  ")

    def test_no_components_found(self, parser: NLInfraParser) -> None:
        """Input with no recognizable components should raise ValueError."""
        with pytest.raises(ValueError, match="No infrastructure components"):
            parser.parse("The weather is nice today")

    def test_single_component_no_relationships(
        self, parser: NLInfraParser
    ) -> None:
        """Single component should work without relationships."""
        parsed = parser.parse("A Redis cache")
        assert len(parsed.components) >= 1
        # Single component might have no relationships (or auto-inferred ones)

    def test_duplicate_component_types(self, parser: NLInfraParser) -> None:
        """Multiple components of the same type should get unique IDs."""
        parsed = parser.parse("An SQS queue and a Kafka queue")

        queue_comps = [
            c for c in parsed.components if c.component_type == ComponentType.QUEUE
        ]
        assert len(queue_comps) >= 2

        # IDs should be unique
        ids = [c.name for c in parsed.components]
        assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# 7. YAML generation
# ---------------------------------------------------------------------------


class TestYAMLGeneration:
    """Test YAML output format."""

    def test_yaml_has_components_key(self, parser: NLInfraParser) -> None:
        """Generated YAML should have 'components' key."""
        parsed = parser.parse("ALB with 2 EC2 instances")
        yaml_str = parser.to_yaml(parsed)
        data = yaml.safe_load(yaml_str)

        assert "components" in data
        assert isinstance(data["components"], list)
        assert len(data["components"]) >= 2

    def test_yaml_has_dependencies_key(self, parser: NLInfraParser) -> None:
        """Generated YAML should have 'dependencies' key."""
        parsed = parser.parse("ALB with 2 EC2 instances connected to Aurora")
        yaml_str = parser.to_yaml(parsed)
        data = yaml.safe_load(yaml_str)

        assert "dependencies" in data
        assert isinstance(data["dependencies"], list)

    def test_yaml_component_has_required_fields(
        self, parser: NLInfraParser
    ) -> None:
        """Each component should have id, name, type, replicas."""
        parsed = parser.parse("An ALB load balancer")
        yaml_str = parser.to_yaml(parsed)
        data = yaml.safe_load(yaml_str)

        comp = data["components"][0]
        assert "id" in comp
        assert "name" in comp
        assert "type" in comp
        assert "replicas" in comp
        assert "host" in comp
        assert "port" in comp

    def test_yaml_dependency_has_required_fields(
        self, parser: NLInfraParser
    ) -> None:
        """Each dependency should have source, target, type."""
        parsed = parser.parse("ALB connected to 2 EC2 instances")
        yaml_str = parser.to_yaml(parsed)
        data = yaml.safe_load(yaml_str)

        if data["dependencies"]:
            dep = data["dependencies"][0]
            assert "source" in dep
            assert "target" in dep
            assert "type" in dep

    def test_yaml_is_valid_yaml(self, parser: NLInfraParser) -> None:
        """Generated output should be valid YAML."""
        parsed = parser.parse(
            "ALB with 3 EC2 instances, Aurora with 2 read replicas, Redis cache"
        )
        yaml_str = parser.to_yaml(parsed)

        # Should not raise
        data = yaml.safe_load(yaml_str)
        assert isinstance(data, dict)

    def test_yaml_component_types_match_enum(
        self, parser: NLInfraParser
    ) -> None:
        """Component types in YAML should match ComponentType enum values."""
        parsed = parser.parse("ALB, EC2, Aurora, Redis, SQS, S3")
        yaml_str = parser.to_yaml(parsed)
        data = yaml.safe_load(yaml_str)

        valid_types = {t.value for t in ComponentType}
        for comp in data["components"]:
            assert comp["type"] in valid_types, (
                f"Component type '{comp['type']}' not in valid types: {valid_types}"
            )


# ---------------------------------------------------------------------------
# 8. InfraGraph generation
# ---------------------------------------------------------------------------


class TestGraphGeneration:
    """Test InfraGraph generation."""

    def test_to_graph_creates_components(self, parser: NLInfraParser) -> None:
        """to_graph should create Component objects in the graph."""
        parsed = parser.parse("ALB with 2 EC2 instances")
        graph = parser.to_graph(parsed)

        assert len(graph.components) >= 2

    def test_to_graph_creates_dependencies(
        self, parser: NLInfraParser
    ) -> None:
        """to_graph should create Dependency edges."""
        parsed = parser.parse("ALB connected to 2 EC2 instances and Aurora")
        graph = parser.to_graph(parsed)

        edges = graph.all_dependency_edges()
        assert len(edges) > 0

    def test_to_graph_component_types_correct(
        self, parser: NLInfraParser
    ) -> None:
        """Component types should be correct in the graph."""
        parsed = parser.parse("ALB with Redis cache and SQS queue")
        graph = parser.to_graph(parsed)

        types = {c.type for c in graph.components.values()}
        assert ComponentType.LOAD_BALANCER in types
        assert ComponentType.CACHE in types
        assert ComponentType.QUEUE in types

    def test_to_graph_resilience_score(self, parser: NLInfraParser) -> None:
        """Generated graph should have a calculable resilience score."""
        parsed = parser.parse(
            "ALB with 3 EC2 instances connected to Aurora with failover and Redis cache"
        )
        graph = parser.to_graph(parsed)

        score = graph.resilience_score()
        assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# 9. Read replica handling
# ---------------------------------------------------------------------------


class TestReadReplicas:
    """Test database read replica handling."""

    def test_aurora_with_read_replicas(self, parser: NLInfraParser) -> None:
        """Aurora with 2 read replicas creates primary + replica."""
        parsed = parser.parse("Aurora with 2 read replicas")

        db_comps = [
            c for c in parsed.components if c.component_type == ComponentType.DATABASE
        ]
        assert len(db_comps) == 2

        primary_names = [c.name for c in db_comps if "primary" in c.name]
        replica_names = [c.name for c in db_comps if "replica" in c.name]
        assert len(primary_names) == 1
        assert len(replica_names) == 1

    def test_replica_has_async_relationship(
        self, parser: NLInfraParser
    ) -> None:
        """Primary -> Replica should have async relationship."""
        parsed = parser.parse("Aurora with 2 read replicas")

        async_rels = [
            r for r in parsed.relationships if r.relationship_type == "async"
        ]
        # Should have at least one async relationship (primary -> replica)
        assert len(async_rels) >= 1


# ---------------------------------------------------------------------------
# 10. Relationship inference
# ---------------------------------------------------------------------------


class TestRelationshipInference:
    """Test auto-inference of relationships."""

    def test_lb_to_server_auto_inferred(self, parser: NLInfraParser) -> None:
        """LB -> Server should be auto-inferred if both exist."""
        parsed = parser.parse("An ALB and 2 EC2 instances")

        # Should have at least one relationship
        lb_to_server = [
            r for r in parsed.relationships
            if any(
                c.component_type == ComponentType.LOAD_BALANCER
                for c in parsed.components if c.name == r.source
            )
            and any(
                c.component_type == ComponentType.APP_SERVER
                for c in parsed.components if c.name == r.target
            )
        ]
        assert len(lb_to_server) >= 1

    def test_server_to_db_auto_inferred(self, parser: NLInfraParser) -> None:
        """Server -> DB should be auto-inferred if both exist."""
        parsed = parser.parse("2 EC2 instances and an Aurora database")

        server_to_db = [
            r for r in parsed.relationships
            if any(
                c.component_type == ComponentType.APP_SERVER
                for c in parsed.components if c.name == r.source
            )
            and any(
                c.component_type == ComponentType.DATABASE
                for c in parsed.components if c.name == r.target
            )
        ]
        assert len(server_to_db) >= 1

    def test_server_to_cache_auto_inferred(
        self, parser: NLInfraParser
    ) -> None:
        """Server -> Cache should be auto-inferred if both exist."""
        parsed = parser.parse("2 EC2 instances with Redis")

        server_to_cache = [
            r for r in parsed.relationships
            if any(
                c.component_type in (ComponentType.APP_SERVER, ComponentType.WEB_SERVER)
                for c in parsed.components if c.name == r.source
            )
            and any(
                c.component_type == ComponentType.CACHE
                for c in parsed.components if c.name == r.target
            )
        ]
        assert len(server_to_cache) >= 1


# ---------------------------------------------------------------------------
# 11. Smart defaults
# ---------------------------------------------------------------------------


class TestSmartDefaults:
    """Test smart default application."""

    def test_lb_gets_default_replicas(self, parser: NLInfraParser) -> None:
        """LB without explicit count should get default replicas."""
        parsed = parser.parse("An ALB load balancer")

        alb_comps = [
            c for c in parsed.components
            if c.component_type == ComponentType.LOAD_BALANCER
        ]
        assert len(alb_comps) >= 1
        # Default replicas for LB is 2
        assert alb_comps[0].replicas == 2

    def test_db_gets_default_port(self, parser: NLInfraParser) -> None:
        """Database should get default port 5432."""
        parsed = parser.parse("A PostgreSQL database")

        db_comps = [
            c for c in parsed.components
            if c.component_type == ComponentType.DATABASE
        ]
        assert len(db_comps) >= 1
        assert db_comps[0].properties.get("port") == 5432

    def test_cache_gets_default_port(self, parser: NLInfraParser) -> None:
        """Cache should get default port 6379."""
        parsed = parser.parse("A Redis cache")

        cache_comps = [
            c for c in parsed.components if c.component_type == ComponentType.CACHE
        ]
        assert len(cache_comps) >= 1
        assert cache_comps[0].properties.get("port") == 6379

    def test_lb_gets_failover_default(self, parser: NLInfraParser) -> None:
        """Load balancer should get failover enabled by default."""
        parsed = parser.parse("An ALB")

        alb = [c for c in parsed.components if c.name == "alb"]
        assert len(alb) == 1
        assert alb[0].properties.get("failover") is True


# ---------------------------------------------------------------------------
# 12. Qualifier suppression – English qualifier
# ---------------------------------------------------------------------------


class TestQualifierSuppression:
    """Qualifier suppression tests for English qualifiers."""

    def test_english_qualifier_suppressed_ec2_instances(
        self, parser: NLInfraParser
    ) -> None:
        """'instances' should be suppressed as qualifier after 'EC2 instances'."""
        parsed = parser.parse("EC2 instances behind a load balancer")
        app_comps = [
            c for c in parsed.components
            if c.component_type == ComponentType.APP_SERVER
        ]
        assert len(app_comps) == 1
        assert app_comps[0].name == "ec2"


# ---------------------------------------------------------------------------
# 13. Overlap detection in component extraction (lines 555-556, 559)
# ---------------------------------------------------------------------------


class TestComponentOverlapDetection:
    """Lines 555-556, 559: When a new pattern match overlaps with an already-matched
    component position, the new match should be skipped."""

    def test_overlapping_japanese_serverless(self, parser: NLInfraParser) -> None:
        """Japanese 'サーバーレス': 'サーバー' pattern matches first at (0,4),
        then 'サーバーレス' at (0,6) overlaps and is skipped."""
        parsed = parser.parse("サーバーレスの構成")
        comps = parsed.components
        names = [c.name for c in comps]
        assert "server" in names
        assert names.count("serverless-function") == 0 or len(comps) == 1


# ---------------------------------------------------------------------------
# 14. Count pattern skip if replicas already set (line 588)
# ---------------------------------------------------------------------------


class TestCountPatternSkipIfReplicasSet:
    """Line 588: If a component already has replicas != 0, the count detection
    in strategy 1 should skip it."""

    def test_replicas_preset_skips_strategy1(
        self, parser: NLInfraParser
    ) -> None:
        """Directly call _apply_counts with pre-set replicas to hit line 588."""
        comp = ParsedComponent(
            name="ec2",
            component_type=ComponentType.APP_SERVER,
            source_text="EC2",
            position=2,
            replicas=5,  # Already set -> line 588 fires
        )
        parser._apply_counts("3 EC2", [comp])
        # replicas should NOT be overwritten by "3"
        assert comp.replicas == 5


# ---------------------------------------------------------------------------
# 15. Count pattern fallback to _find_closest_component (lines 610, 625-634)
# ---------------------------------------------------------------------------


class TestCountFallbackClosestComponent:
    """Lines 610, 625-634: When no preceding component is found, the count
    pattern falls back to _find_closest_component."""

    def test_count_after_no_preceding_uses_closest(
        self, parser: NLInfraParser
    ) -> None:
        """A count phrase at the start of text with no preceding comp."""
        parsed = parser.parse("3台のEC2")
        ec2_comps = [
            c for c in parsed.components
            if c.component_type == ComponentType.APP_SERVER
        ]
        assert len(ec2_comps) >= 1
        assert ec2_comps[0].replicas == 3

    def test_count_fallback_closest_directly(
        self, parser: NLInfraParser
    ) -> None:
        """Call _apply_counts where count pattern is far before all components,
        so _find_preceding_component returns None -> _find_closest_component used."""
        comp = ParsedComponent(
            name="ec2",
            component_type=ComponentType.APP_SERVER,
            source_text="EC2",
            position=50,
        )
        # "3台" at position 0; comp at 50 > 20 (max_dist for preceding)
        # so _find_preceding_component returns None
        # _find_closest_component(max_dist=60) finds comp at distance 50
        text = "3台" + " " * 47 + "EC2"
        parser._apply_counts(text, [comp])
        assert comp.replicas == 3


# ---------------------------------------------------------------------------
# 16. Property application fallback to closest component (line 684)
# ---------------------------------------------------------------------------


class TestPropertyFallbackClosest:
    """Line 684: When no preceding component is found for a property, it
    falls back to _find_closest_component."""

    def test_property_applied_to_closest_when_no_preceding(
        self, parser: NLInfraParser
    ) -> None:
        """A property at the start of text applied to closest component."""
        parsed = parser.parse("autoscaling enabled, an EC2")
        ec2 = [
            c for c in parsed.components
            if c.component_type == ComponentType.APP_SERVER
        ]
        assert len(ec2) >= 1
        assert ec2[0].properties.get("autoscaling") is True

    def test_property_fallback_directly(
        self, parser: NLInfraParser
    ) -> None:
        """Call _apply_properties where property is at start, component is after.
        _find_preceding_component returns None -> _find_closest_component used."""
        comp = ParsedComponent(
            name="ec2",
            component_type=ComponentType.APP_SERVER,
            source_text="EC2",
            position=30,
        )
        # "failover" at position ~0, comp at 30 -> not preceding
        parser._apply_properties("failover enabled and then EC2", [comp])
        assert comp.properties.get("failover") is True


# ---------------------------------------------------------------------------
# 17. Auto-infer skip same-name components (line 839)
# ---------------------------------------------------------------------------


class TestAutoInferSkipSameName:
    """Line 839: When auto-inferring relationships, skip if source and target
    have the same name (self-reference)."""

    def test_same_name_different_type_skipped(
        self, parser: NLInfraParser
    ) -> None:
        """Directly test _auto_infer_relationships with same-name components."""
        parsed = ParsedInfrastructure(raw_text="test")
        parsed.components = [
            ParsedComponent(
                name="shared",
                component_type=ComponentType.APP_SERVER,
                source_text="shared",
                position=0,
            ),
            ParsedComponent(
                name="shared",
                component_type=ComponentType.DATABASE,
                source_text="shared",
                position=10,
            ),
        ]
        parsed.relationships = []
        parser._auto_infer_relationships(parsed)
        # No relationship should be inferred since source.name == target.name
        for rel in parsed.relationships:
            assert rel.source != rel.target


# ---------------------------------------------------------------------------
# 18. YAML autoscaling output (line 944)
# ---------------------------------------------------------------------------


class TestYAMLAutoscalingOutput:
    """Line 944: When autoscaling is enabled, YAML should include autoscaling."""

    def test_yaml_contains_autoscaling(self, parser: NLInfraParser) -> None:
        """Components with autoscaling should include autoscaling in YAML output."""
        parsed = parser.parse("3 EC2 with autoscaling enabled")
        yaml_str = parser.to_yaml(parsed)
        data = yaml.safe_load(yaml_str)
        ec2_comps = [c for c in data["components"] if c["id"] == "ec2"]
        assert len(ec2_comps) == 1
        assert "autoscaling" in ec2_comps[0]
        assert ec2_comps[0]["autoscaling"]["enabled"] is True


# ---------------------------------------------------------------------------
# 19. Circuit breaker in dependency output (line 996)
# ---------------------------------------------------------------------------


class TestCircuitBreakerInDependency:
    """Line 996: circuit_breaker in the dependency dict when source has it."""

    def test_yaml_dependency_has_circuit_breaker(
        self, parser: NLInfraParser
    ) -> None:
        """Dependencies from components with circuit_breaker should include it."""
        parsed = parser.parse(
            "An ALB with circuit breaker connected to a web server"
        )
        yaml_str = parser.to_yaml(parsed)
        data = yaml.safe_load(yaml_str)
        deps = data.get("dependencies", [])
        cb_deps = [d for d in deps if d.get("circuit_breaker")]
        assert len(cb_deps) >= 1
        assert cb_deps[0]["circuit_breaker"]["enabled"] is True


# ---------------------------------------------------------------------------
# 20. Autoscaling in _parsed_to_component (InfraGraph, line 1026)
# ---------------------------------------------------------------------------


class TestAutoscalingInfraGraph:
    """Line 1026: AutoScalingConfig with enabled=True in _parsed_to_component."""

    def test_graph_component_has_autoscaling(
        self, parser: NLInfraParser
    ) -> None:
        """Components with autoscaling should have AutoScalingConfig in InfraGraph."""
        parsed = parser.parse("3 EC2 with autoscaling enabled")
        graph = parser.to_graph(parsed)
        ec2 = [c for c in graph.components.values() if "ec2" in c.id.lower()]
        assert len(ec2) >= 1
        assert ec2[0].autoscaling.enabled is True
