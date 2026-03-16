"""Tests for the Multi-Cloud Resilience Comparator."""

import pytest

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    HealthStatus,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.cloud_comparator import (
    CloudComparisonReport,
    CloudComparator,
    CloudProvider,
    CloudServiceMapping,
    ComparisonResult,
    MigrationRisk,
    ProviderResilienceScore,
    ServiceCategory,
    _COMPONENT_TO_CATEGORY,
    _DEFAULT_MAPPINGS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _comp(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    *,
    replicas: int = 1,
    failover: bool = False,
    autoscaling: bool = False,
    health: HealthStatus = HealthStatus.HEALTHY,
) -> Component:
    return Component(
        id=cid,
        name=cid,
        type=ctype,
        replicas=replicas,
        failover=FailoverConfig(enabled=failover),
        autoscaling=AutoScalingConfig(enabled=autoscaling),
        health=health,
    )


def _graph(*components: Component, deps: list[tuple[str, str]] | None = None) -> InfraGraph:
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in (deps or []):
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


def _basic_graph() -> InfraGraph:
    """A small multi-tier graph for most tests."""
    return _graph(
        _comp("lb", ComponentType.LOAD_BALANCER, replicas=2, failover=True),
        _comp("app", ComponentType.APP_SERVER),
        _comp("db", ComponentType.DATABASE),
        _comp("cache", ComponentType.CACHE),
        deps=[("lb", "app"), ("app", "db"), ("app", "cache")],
    )


def _rich_graph() -> InfraGraph:
    """A larger graph covering many component types."""
    return _graph(
        _comp("lb", ComponentType.LOAD_BALANCER, replicas=2, failover=True),
        _comp("app1", ComponentType.APP_SERVER, replicas=3, autoscaling=True),
        _comp("app2", ComponentType.WEB_SERVER, replicas=2),
        _comp("db", ComponentType.DATABASE, replicas=2, failover=True),
        _comp("cache", ComponentType.CACHE, replicas=2),
        _comp("queue", ComponentType.QUEUE),
        _comp("store", ComponentType.STORAGE),
        _comp("dns", ComponentType.DNS),
        deps=[
            ("lb", "app1"), ("lb", "app2"),
            ("app1", "db"), ("app1", "cache"),
            ("app2", "db"), ("app2", "queue"),
            ("queue", "store"),
        ],
    )


# ===================================================================
# CloudProvider enum
# ===================================================================


class TestCloudProviderEnum:
    def test_values(self):
        assert CloudProvider.AWS.value == "aws"
        assert CloudProvider.GCP.value == "gcp"
        assert CloudProvider.AZURE.value == "azure"
        assert CloudProvider.ON_PREMISE.value == "on_premise"

    def test_member_count(self):
        assert len(CloudProvider) == 4

    def test_str_enum(self):
        assert str(CloudProvider.AWS) == "CloudProvider.AWS" or "aws" in CloudProvider.AWS.value

    def test_from_value(self):
        assert CloudProvider("aws") == CloudProvider.AWS
        assert CloudProvider("gcp") == CloudProvider.GCP


# ===================================================================
# ServiceCategory enum
# ===================================================================


class TestServiceCategoryEnum:
    def test_values(self):
        assert ServiceCategory.COMPUTE.value == "compute"
        assert ServiceCategory.DATABASE.value == "database"
        assert ServiceCategory.CACHE.value == "cache"
        assert ServiceCategory.QUEUE.value == "queue"
        assert ServiceCategory.STORAGE.value == "storage"
        assert ServiceCategory.LOAD_BALANCER.value == "load_balancer"
        assert ServiceCategory.DNS.value == "dns"
        assert ServiceCategory.CDN.value == "cdn"

    def test_member_count(self):
        assert len(ServiceCategory) == 8

    def test_from_value(self):
        assert ServiceCategory("cdn") == ServiceCategory.CDN


# ===================================================================
# CloudServiceMapping model
# ===================================================================


class TestCloudServiceMapping:
    def test_create_basic(self):
        m = CloudServiceMapping(
            category=ServiceCategory.COMPUTE,
            aws_service="EC2",
            gcp_service="CE",
            azure_service="VM",
        )
        assert m.category == ServiceCategory.COMPUTE
        assert m.aws_sla == 99.9  # default

    def test_create_with_sla(self):
        m = CloudServiceMapping(
            category=ServiceCategory.DNS,
            aws_service="Route53",
            gcp_service="Cloud DNS",
            azure_service="Azure DNS",
            aws_sla=100.0,
            gcp_sla=100.0,
            azure_sla=100.0,
        )
        assert m.aws_sla == 100.0

    def test_fields_accessible(self):
        m = _DEFAULT_MAPPINGS[0]
        assert m.category == ServiceCategory.COMPUTE
        assert isinstance(m.aws_service, str)
        assert isinstance(m.gcp_service, str)
        assert isinstance(m.azure_service, str)


# ===================================================================
# ProviderResilienceScore model
# ===================================================================


class TestProviderResilienceScore:
    def test_defaults(self):
        s = ProviderResilienceScore(provider=CloudProvider.AWS)
        assert s.overall_score == 0.0
        assert s.availability_score == 0.0
        assert s.recovery_score == 0.0
        assert s.redundancy_score == 0.0
        assert s.cost_normalized_score == 0.0

    def test_with_values(self):
        s = ProviderResilienceScore(
            provider=CloudProvider.GCP,
            overall_score=85.5,
            availability_score=99.0,
            recovery_score=70.0,
            redundancy_score=80.0,
            cost_normalized_score=60.0,
        )
        assert s.overall_score == 85.5
        assert s.provider == CloudProvider.GCP


# ===================================================================
# ComparisonResult model
# ===================================================================


class TestComparisonResult:
    def test_defaults(self):
        r = ComparisonResult(category=ServiceCategory.COMPUTE)
        assert r.scores_by_provider == {}
        assert r.winner == CloudProvider.AWS
        assert r.margin == 0.0
        assert r.analysis == ""

    def test_with_values(self):
        r = ComparisonResult(
            category=ServiceCategory.DATABASE,
            winner=CloudProvider.AZURE,
            margin=3.5,
            analysis="Azure leads",
        )
        assert r.winner == CloudProvider.AZURE
        assert r.margin == 3.5


# ===================================================================
# MigrationRisk model
# ===================================================================


class TestMigrationRisk:
    def test_defaults(self):
        r = MigrationRisk(
            source_provider=CloudProvider.AWS,
            target_provider=CloudProvider.GCP,
        )
        assert r.risk_score == 0.0
        assert r.data_transfer_risk == 0.0
        assert r.compatibility_issues == []
        assert r.estimated_downtime_hours == 0.0

    def test_with_values(self):
        r = MigrationRisk(
            source_provider=CloudProvider.GCP,
            target_provider=CloudProvider.AZURE,
            risk_score=0.7,
            data_transfer_risk=0.5,
            compatibility_issues=["schema diff"],
            estimated_downtime_hours=4.0,
        )
        assert r.risk_score == 0.7
        assert len(r.compatibility_issues) == 1


# ===================================================================
# CloudComparisonReport model
# ===================================================================


class TestCloudComparisonReport:
    def test_defaults(self):
        r = CloudComparisonReport()
        assert r.components_analyzed == 0
        assert r.provider_rankings == []
        assert r.category_results == []
        assert r.migration_risks == []
        assert r.recommendations == []
        assert r.best_multi_cloud_strategy == ""


# ===================================================================
# Default mappings
# ===================================================================


class TestDefaultMappings:
    def test_count(self):
        assert len(_DEFAULT_MAPPINGS) == 8

    def test_categories_unique(self):
        cats = [m.category for m in _DEFAULT_MAPPINGS]
        assert len(cats) == len(set(cats))

    def test_compute_mapping(self):
        m = next(m for m in _DEFAULT_MAPPINGS if m.category == ServiceCategory.COMPUTE)
        assert m.aws_service == "EC2"
        assert m.gcp_service == "Compute Engine"
        assert m.azure_service == "Virtual Machines"
        assert m.aws_sla == 99.99

    def test_database_mapping(self):
        m = next(m for m in _DEFAULT_MAPPINGS if m.category == ServiceCategory.DATABASE)
        assert m.aws_service == "RDS"
        assert m.azure_sla == 99.99

    def test_cache_mapping(self):
        m = next(m for m in _DEFAULT_MAPPINGS if m.category == ServiceCategory.CACHE)
        assert m.aws_service == "ElastiCache"

    def test_queue_mapping(self):
        m = next(m for m in _DEFAULT_MAPPINGS if m.category == ServiceCategory.QUEUE)
        assert m.gcp_sla == 99.95

    def test_storage_mapping(self):
        m = next(m for m in _DEFAULT_MAPPINGS if m.category == ServiceCategory.STORAGE)
        assert m.aws_sla == 99.99
        assert m.gcp_sla == 99.95
        assert m.azure_sla == 99.9

    def test_lb_mapping(self):
        m = next(m for m in _DEFAULT_MAPPINGS if m.category == ServiceCategory.LOAD_BALANCER)
        assert m.aws_sla == 99.99

    def test_dns_mapping(self):
        m = next(m for m in _DEFAULT_MAPPINGS if m.category == ServiceCategory.DNS)
        assert m.aws_sla == 100.0
        assert m.gcp_sla == 100.0
        assert m.azure_sla == 100.0

    def test_cdn_mapping(self):
        m = next(m for m in _DEFAULT_MAPPINGS if m.category == ServiceCategory.CDN)
        assert m.aws_sla == 99.9


# ===================================================================
# _COMPONENT_TO_CATEGORY mapping
# ===================================================================


class TestComponentToCategoryMapping:
    def test_app_server(self):
        assert _COMPONENT_TO_CATEGORY[ComponentType.APP_SERVER] == ServiceCategory.COMPUTE

    def test_web_server(self):
        assert _COMPONENT_TO_CATEGORY[ComponentType.WEB_SERVER] == ServiceCategory.COMPUTE

    def test_database(self):
        assert _COMPONENT_TO_CATEGORY[ComponentType.DATABASE] == ServiceCategory.DATABASE

    def test_cache(self):
        assert _COMPONENT_TO_CATEGORY[ComponentType.CACHE] == ServiceCategory.CACHE

    def test_queue(self):
        assert _COMPONENT_TO_CATEGORY[ComponentType.QUEUE] == ServiceCategory.QUEUE

    def test_storage(self):
        assert _COMPONENT_TO_CATEGORY[ComponentType.STORAGE] == ServiceCategory.STORAGE

    def test_load_balancer(self):
        assert _COMPONENT_TO_CATEGORY[ComponentType.LOAD_BALANCER] == ServiceCategory.LOAD_BALANCER

    def test_dns(self):
        assert _COMPONENT_TO_CATEGORY[ComponentType.DNS] == ServiceCategory.DNS

    def test_external_api_not_mapped(self):
        assert ComponentType.EXTERNAL_API not in _COMPONENT_TO_CATEGORY

    def test_custom_not_mapped(self):
        assert ComponentType.CUSTOM not in _COMPONENT_TO_CATEGORY


# ===================================================================
# CloudComparator.__init__
# ===================================================================


class TestCloudComparatorInit:
    def test_init_stores_graph(self):
        g = _basic_graph()
        cc = CloudComparator(g)
        assert cc.graph is g

    def test_init_populates_mappings(self):
        cc = CloudComparator(_basic_graph())
        assert len(cc._mappings) == 8

    def test_init_empty_graph(self):
        cc = CloudComparator(InfraGraph())
        assert cc.graph.components == {}


# ===================================================================
# get_service_mapping
# ===================================================================


class TestGetServiceMapping:
    def test_compute(self):
        cc = CloudComparator(_basic_graph())
        m = cc.get_service_mapping(ServiceCategory.COMPUTE)
        assert m.aws_service == "EC2"

    def test_database(self):
        cc = CloudComparator(_basic_graph())
        m = cc.get_service_mapping(ServiceCategory.DATABASE)
        assert m.category == ServiceCategory.DATABASE

    def test_all_categories(self):
        cc = CloudComparator(_basic_graph())
        for cat in ServiceCategory:
            m = cc.get_service_mapping(cat)
            assert m.category == cat

    def test_returns_correct_sla(self):
        cc = CloudComparator(_basic_graph())
        m = cc.get_service_mapping(ServiceCategory.DNS)
        assert m.aws_sla == 100.0


# ===================================================================
# score_provider
# ===================================================================


class TestScoreProvider:
    def test_empty_graph(self):
        cc = CloudComparator(InfraGraph())
        s = cc.score_provider(CloudProvider.AWS)
        assert s.overall_score == 0.0
        assert s.provider == CloudProvider.AWS

    def test_basic_graph_aws(self):
        cc = CloudComparator(_basic_graph())
        s = cc.score_provider(CloudProvider.AWS)
        assert 0 < s.overall_score <= 100
        assert s.provider == CloudProvider.AWS

    def test_basic_graph_gcp(self):
        cc = CloudComparator(_basic_graph())
        s = cc.score_provider(CloudProvider.GCP)
        assert s.overall_score > 0

    def test_basic_graph_azure(self):
        cc = CloudComparator(_basic_graph())
        s = cc.score_provider(CloudProvider.AZURE)
        assert s.overall_score > 0

    def test_on_premise(self):
        cc = CloudComparator(_basic_graph())
        s = cc.score_provider(CloudProvider.ON_PREMISE)
        assert s.overall_score >= 0

    def test_availability_positive(self):
        cc = CloudComparator(_basic_graph())
        s = cc.score_provider(CloudProvider.AWS)
        assert s.availability_score > 0

    def test_recovery_score_no_failover(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER))
        cc = CloudComparator(g)
        s = cc.score_provider(CloudProvider.AWS)
        assert s.recovery_score == 0.0

    def test_recovery_score_with_failover(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, failover=True))
        cc = CloudComparator(g)
        s = cc.score_provider(CloudProvider.AWS)
        assert s.recovery_score > 0

    def test_recovery_score_with_autoscaling(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, autoscaling=True))
        cc = CloudComparator(g)
        s = cc.score_provider(CloudProvider.AWS)
        assert s.recovery_score > 0

    def test_redundancy_score_single_replica(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=1))
        cc = CloudComparator(g)
        s = cc.score_provider(CloudProvider.AWS)
        assert s.redundancy_score == 20.0

    def test_redundancy_score_multi_replica(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2))
        cc = CloudComparator(g)
        s = cc.score_provider(CloudProvider.AWS)
        assert s.redundancy_score == 50.0

    def test_redundancy_score_multi_replica_failover(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=2, failover=True))
        cc = CloudComparator(g)
        s = cc.score_provider(CloudProvider.AWS)
        assert s.redundancy_score == 80.0

    def test_redundancy_score_triple_replica_failover(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER, replicas=3, failover=True))
        cc = CloudComparator(g)
        s = cc.score_provider(CloudProvider.AWS)
        assert s.redundancy_score == 100.0

    def test_overall_score_bounded(self):
        cc = CloudComparator(_rich_graph())
        for p in CloudProvider:
            s = cc.score_provider(p)
            assert 0.0 <= s.overall_score <= 100.0

    def test_cost_normalized_positive(self):
        cc = CloudComparator(_basic_graph())
        s = cc.score_provider(CloudProvider.AWS)
        assert s.cost_normalized_score >= 0.0

    def test_rich_graph_higher_recovery(self):
        cc = CloudComparator(_rich_graph())
        s = cc.score_provider(CloudProvider.AWS)
        # Rich graph has some failover/autoscaling
        assert s.recovery_score > 0


# ===================================================================
# compare_category
# ===================================================================


class TestCompareCategory:
    def test_compute_has_scores(self):
        cc = CloudComparator(_basic_graph())
        r = cc.compare_category(ServiceCategory.COMPUTE)
        assert len(r.scores_by_provider) == 3
        assert "aws" in r.scores_by_provider
        assert "gcp" in r.scores_by_provider
        assert "azure" in r.scores_by_provider

    def test_winner_is_cloud_provider(self):
        cc = CloudComparator(_basic_graph())
        r = cc.compare_category(ServiceCategory.DATABASE)
        assert isinstance(r.winner, CloudProvider)

    def test_margin_non_negative(self):
        cc = CloudComparator(_basic_graph())
        for cat in ServiceCategory:
            r = cc.compare_category(cat)
            assert r.margin >= 0.0

    def test_analysis_not_empty(self):
        cc = CloudComparator(_basic_graph())
        r = cc.compare_category(ServiceCategory.STORAGE)
        assert len(r.analysis) > 0

    def test_analysis_contains_winner(self):
        cc = CloudComparator(_basic_graph())
        r = cc.compare_category(ServiceCategory.STORAGE)
        assert r.winner.value.upper() in r.analysis

    def test_dns_all_equal_availability(self):
        cc = CloudComparator(_basic_graph())
        r = cc.compare_category(ServiceCategory.DNS)
        # All DNS SLAs are 100%, so availability should be equal
        scores = list(r.scores_by_provider.values())
        avails = [s.availability_score for s in scores]
        assert avails[0] == avails[1] == avails[2] == 100.0

    def test_queue_gcp_advantage(self):
        cc = CloudComparator(_basic_graph())
        r = cc.compare_category(ServiceCategory.QUEUE)
        # GCP Pub/Sub has 99.95 vs 99.9 for AWS/Azure
        assert r.winner == CloudProvider.GCP

    def test_storage_aws_advantage(self):
        cc = CloudComparator(_basic_graph())
        r = cc.compare_category(ServiceCategory.STORAGE)
        assert r.winner == CloudProvider.AWS

    def test_category_field_set(self):
        cc = CloudComparator(_basic_graph())
        r = cc.compare_category(ServiceCategory.CDN)
        assert r.category == ServiceCategory.CDN

    def test_empty_graph_compare(self):
        cc = CloudComparator(InfraGraph())
        r = cc.compare_category(ServiceCategory.COMPUTE)
        assert len(r.scores_by_provider) == 3

    def test_database_azure_higher_availability(self):
        cc = CloudComparator(_basic_graph())
        r = cc.compare_category(ServiceCategory.DATABASE)
        # Azure SQL has 99.99 vs 99.95 for AWS/GCP
        azure_score = r.scores_by_provider["azure"]
        aws_score = r.scores_by_provider["aws"]
        assert azure_score.availability_score > aws_score.availability_score


# ===================================================================
# assess_migration_risk
# ===================================================================


class TestAssessMigrationRisk:
    def test_same_provider(self):
        cc = CloudComparator(_basic_graph())
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.AWS)
        assert r.risk_score == 0.0
        assert r.data_transfer_risk == 0.0
        assert r.compatibility_issues == []
        assert r.estimated_downtime_hours == 0.0

    def test_aws_to_gcp(self):
        cc = CloudComparator(_basic_graph())
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.GCP)
        assert r.risk_score > 0
        assert r.source_provider == CloudProvider.AWS
        assert r.target_provider == CloudProvider.GCP

    def test_has_database_issues(self):
        cc = CloudComparator(_basic_graph())
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.GCP)
        db_issues = [i for i in r.compatibility_issues if "database" in i.lower()]
        assert len(db_issues) > 0

    def test_on_premise_source_higher_risk(self):
        cc = CloudComparator(_basic_graph())
        r_cloud = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.GCP)
        r_onprem = cc.assess_migration_risk(CloudProvider.ON_PREMISE, CloudProvider.GCP)
        assert r_onprem.risk_score >= r_cloud.risk_score

    def test_on_premise_target(self):
        cc = CloudComparator(_basic_graph())
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.ON_PREMISE)
        network_issues = [i for i in r.compatibility_issues if "network" in i.lower() or "VPN" in i]
        assert len(network_issues) > 0

    def test_data_transfer_risk_with_db(self):
        cc = CloudComparator(_basic_graph())
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.AZURE)
        assert r.data_transfer_risk > 0

    def test_data_transfer_risk_no_db(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER))
        cc = CloudComparator(g)
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.GCP)
        assert r.data_transfer_risk == 0.1

    def test_estimated_downtime_positive(self):
        cc = CloudComparator(_basic_graph())
        r = cc.assess_migration_risk(CloudProvider.GCP, CloudProvider.AZURE)
        assert r.estimated_downtime_hours > 0

    def test_empty_graph(self):
        cc = CloudComparator(InfraGraph())
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.GCP)
        assert r.risk_score == 0.0
        assert r.estimated_downtime_hours >= 0

    def test_unhealthy_components_increase_risk(self):
        g = _graph(
            _comp("app", ComponentType.APP_SERVER, health=HealthStatus.DOWN),
            _comp("db", ComponentType.DATABASE, health=HealthStatus.DEGRADED),
        )
        cc = CloudComparator(g)
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.GCP)
        unhealthy_issues = [i for i in r.compatibility_issues if "not healthy" in i]
        assert len(unhealthy_issues) > 0

    def test_risk_score_capped_at_1(self):
        comps = [_comp(f"c{i}", ComponentType.APP_SERVER) for i in range(50)]
        g = _graph(*comps)
        cc = CloudComparator(g)
        r = cc.assess_migration_risk(CloudProvider.ON_PREMISE, CloudProvider.AWS)
        assert r.risk_score <= 1.0

    def test_data_transfer_risk_capped(self):
        comps = [_comp(f"db{i}", ComponentType.DATABASE) for i in range(20)]
        g = _graph(*comps)
        cc = CloudComparator(g)
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.GCP)
        assert r.data_transfer_risk <= 1.0

    def test_queue_migration_warning(self):
        g = _graph(
            _comp("q", ComponentType.QUEUE),
            _comp("app", ComponentType.APP_SERVER),
        )
        cc = CloudComparator(g)
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.GCP)
        queue_issues = [i for i in r.compatibility_issues if "queue" in i.lower() or "message" in i.lower()]
        assert len(queue_issues) > 0


# ===================================================================
# recommend_multi_cloud_strategy
# ===================================================================


class TestRecommendMultiCloudStrategy:
    def test_empty_graph(self):
        cc = CloudComparator(InfraGraph())
        s = cc.recommend_multi_cloud_strategy()
        assert "No components" in s

    def test_small_architecture(self):
        g = _graph(_comp("app", ComponentType.APP_SERVER))
        cc = CloudComparator(g)
        s = cc.recommend_multi_cloud_strategy()
        assert "Single-cloud" in s

    def test_three_components(self):
        g = _graph(
            _comp("app", ComponentType.APP_SERVER),
            _comp("db", ComponentType.DATABASE),
            _comp("cache", ComponentType.CACHE),
        )
        cc = CloudComparator(g)
        s = cc.recommend_multi_cloud_strategy()
        assert "Single-cloud" in s

    def test_active_active_strategy(self):
        g = _graph(
            _comp("lb", ComponentType.LOAD_BALANCER),
            _comp("app", ComponentType.APP_SERVER),
            _comp("db1", ComponentType.DATABASE),
            _comp("db2", ComponentType.DATABASE),
            _comp("dns", ComponentType.DNS),
        )
        cc = CloudComparator(g)
        s = cc.recommend_multi_cloud_strategy()
        assert "Active-Active" in s

    def test_primary_dr_strategy(self):
        g = _graph(
            _comp("lb", ComponentType.LOAD_BALANCER),
            _comp("app", ComponentType.APP_SERVER),
            _comp("app2", ComponentType.APP_SERVER),
            _comp("db", ComponentType.DATABASE),
        )
        cc = CloudComparator(g)
        s = cc.recommend_multi_cloud_strategy()
        assert "Primary-DR" in s

    def test_containerised_strategy(self):
        g = _graph(
            _comp("app1", ComponentType.APP_SERVER),
            _comp("app2", ComponentType.APP_SERVER),
            _comp("app3", ComponentType.APP_SERVER),
            _comp("app4", ComponentType.APP_SERVER),
        )
        cc = CloudComparator(g)
        s = cc.recommend_multi_cloud_strategy()
        assert "Kubernetes" in s or "containerised" in s

    def test_returns_string(self):
        cc = CloudComparator(_basic_graph())
        s = cc.recommend_multi_cloud_strategy()
        assert isinstance(s, str)
        assert len(s) > 0

    def test_cdn_id_triggers_active_active(self):
        g = _graph(
            _comp("lb", ComponentType.LOAD_BALANCER),
            _comp("app", ComponentType.APP_SERVER),
            _comp("db1", ComponentType.DATABASE),
            _comp("db2", ComponentType.DATABASE),
            _comp("cdn-main", ComponentType.CUSTOM),
        )
        cc = CloudComparator(g)
        s = cc.recommend_multi_cloud_strategy()
        assert "Active-Active" in s


# ===================================================================
# generate_report
# ===================================================================


class TestGenerateReport:
    def test_report_type(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        assert isinstance(r, CloudComparisonReport)

    def test_components_analyzed(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        assert r.components_analyzed == 4

    def test_provider_rankings_count(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        assert len(r.provider_rankings) == 3

    def test_provider_rankings_sorted(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        scores = [p.overall_score for p in r.provider_rankings]
        assert scores == sorted(scores, reverse=True)

    def test_category_results_present(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        assert len(r.category_results) > 0

    def test_category_results_unique(self):
        cc = CloudComparator(_rich_graph())
        r = cc.generate_report()
        cats = [cr.category for cr in r.category_results]
        assert len(cats) == len(set(cats))

    def test_migration_risks_present(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        # 3 providers -> 3 pairs
        assert len(r.migration_risks) == 3

    def test_recommendations_not_empty(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        assert len(r.recommendations) > 0

    def test_strategy_set(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        assert len(r.best_multi_cloud_strategy) > 0

    def test_empty_graph_report(self):
        cc = CloudComparator(InfraGraph())
        r = cc.generate_report()
        assert r.components_analyzed == 0
        assert len(r.provider_rankings) == 3
        assert r.category_results == []

    def test_rich_graph_covers_many_categories(self):
        cc = CloudComparator(_rich_graph())
        r = cc.generate_report()
        cats = {cr.category for cr in r.category_results}
        assert ServiceCategory.COMPUTE in cats
        assert ServiceCategory.DATABASE in cats

    def test_migration_risks_no_self_pairs(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        for mr in r.migration_risks:
            assert mr.source_provider != mr.target_provider

    def test_report_recommendations_include_ranking(self):
        cc = CloudComparator(_basic_graph())
        r = cc.generate_report()
        # First recommendation should mention the top-ranked provider
        top = r.provider_rankings[0]
        assert top.provider.value.upper() in r.recommendations[0]

    def test_report_with_single_component(self):
        g = _graph(_comp("db", ComponentType.DATABASE))
        cc = CloudComparator(g)
        r = cc.generate_report()
        assert r.components_analyzed == 1
        assert len(r.category_results) == 1
        assert r.category_results[0].category == ServiceCategory.DATABASE


# ===================================================================
# Private helper methods
# ===================================================================


class TestPrivateHelpers:
    def test_sla_for_aws(self):
        cc = CloudComparator(_basic_graph())
        m = cc.get_service_mapping(ServiceCategory.COMPUTE)
        assert cc._sla_for_provider(m, CloudProvider.AWS) == 99.99

    def test_sla_for_gcp(self):
        cc = CloudComparator(_basic_graph())
        m = cc.get_service_mapping(ServiceCategory.STORAGE)
        assert cc._sla_for_provider(m, CloudProvider.GCP) == 99.95

    def test_sla_for_azure(self):
        cc = CloudComparator(_basic_graph())
        m = cc.get_service_mapping(ServiceCategory.DATABASE)
        assert cc._sla_for_provider(m, CloudProvider.AZURE) == 99.99

    def test_sla_for_on_premise(self):
        cc = CloudComparator(_basic_graph())
        m = cc.get_service_mapping(ServiceCategory.COMPUTE)
        assert cc._sla_for_provider(m, CloudProvider.ON_PREMISE) == 99.0

    def test_availability_score_empty(self):
        cc = CloudComparator(InfraGraph())
        assert cc._availability_score(CloudProvider.AWS) == 99.0

    def test_availability_score_with_components(self):
        cc = CloudComparator(_basic_graph())
        score = cc._availability_score(CloudProvider.AWS)
        assert 99.0 <= score <= 100.0

    def test_recovery_score_empty(self):
        cc = CloudComparator(InfraGraph())
        assert cc._recovery_score() == 0.0

    def test_recovery_score_mixed(self):
        g = _graph(
            _comp("a", ComponentType.APP_SERVER, failover=True),
            _comp("b", ComponentType.APP_SERVER),
        )
        cc = CloudComparator(g)
        score = cc._recovery_score()
        assert 0 < score < 100

    def test_redundancy_score_empty(self):
        cc = CloudComparator(InfraGraph())
        assert cc._redundancy_score() == 0.0

    def test_cost_normalized_score(self):
        cc = CloudComparator(_basic_graph())
        score = cc._cost_normalized_score(CloudProvider.AWS)
        assert 0.0 <= score <= 100.0

    def test_build_recommendations_empty(self):
        cc = CloudComparator(InfraGraph())
        recs = cc._build_recommendations([], [])
        assert any("Add components" in r for r in recs)

    def test_build_recommendations_with_margin(self):
        cc = CloudComparator(_basic_graph())
        rankings = [
            ProviderResilienceScore(provider=CloudProvider.AWS, overall_score=90.0),
        ]
        cr = ComparisonResult(
            category=ServiceCategory.STORAGE,
            winner=CloudProvider.AWS,
            margin=5.0,
        )
        recs = cc._build_recommendations(rankings, [cr])
        assert any("AWS" in r for r in recs)

    def test_build_recommendations_no_margin(self):
        cc = CloudComparator(_basic_graph())
        rankings = [
            ProviderResilienceScore(provider=CloudProvider.GCP, overall_score=85.0),
        ]
        cr = ComparisonResult(
            category=ServiceCategory.DNS,
            winner=CloudProvider.GCP,
            margin=0.5,
        )
        recs = cc._build_recommendations(rankings, [cr])
        # margin <= 1.0, no recommendation for that category
        category_recs = [r for r in recs if "dns" in r.lower()]
        assert len(category_recs) == 0


# ===================================================================
# Edge cases and integration
# ===================================================================


class TestEdgeCases:
    def test_custom_component_not_in_category_results(self):
        g = _graph(_comp("custom1", ComponentType.CUSTOM))
        cc = CloudComparator(g)
        r = cc.generate_report()
        assert r.category_results == []

    def test_external_api_not_in_category_results(self):
        g = _graph(_comp("ext", ComponentType.EXTERNAL_API))
        cc = CloudComparator(g)
        r = cc.generate_report()
        assert r.category_results == []

    def test_all_providers_scored(self):
        cc = CloudComparator(_rich_graph())
        for p in [CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE]:
            s = cc.score_provider(p)
            assert s.provider == p

    def test_multiple_same_type_components(self):
        g = _graph(
            _comp("db1", ComponentType.DATABASE, replicas=3, failover=True),
            _comp("db2", ComponentType.DATABASE, replicas=1),
        )
        cc = CloudComparator(g)
        r = cc.generate_report()
        # Should only have one DATABASE category result
        db_results = [cr for cr in r.category_results if cr.category == ServiceCategory.DATABASE]
        assert len(db_results) == 1

    def test_score_provider_with_all_healthy(self):
        g = _graph(
            _comp("a", ComponentType.APP_SERVER, replicas=3, failover=True, autoscaling=True),
        )
        cc = CloudComparator(g)
        s = cc.score_provider(CloudProvider.AWS)
        assert s.recovery_score == 100.0
        assert s.redundancy_score == 100.0

    def test_recovery_with_replicas_only(self):
        g = _graph(
            _comp("a", ComponentType.APP_SERVER, replicas=2),
        )
        cc = CloudComparator(g)
        s = cc.score_provider(CloudProvider.AWS)
        assert s.recovery_score == 20.0

    def test_large_graph_performance(self):
        comps = [
            _comp(f"app{i}", ComponentType.APP_SERVER, replicas=2)
            for i in range(20)
        ]
        g = _graph(*comps)
        cc = CloudComparator(g)
        r = cc.generate_report()
        assert r.components_analyzed == 20

    def test_migration_risk_many_databases(self):
        comps = [_comp(f"db{i}", ComponentType.DATABASE) for i in range(10)]
        g = _graph(*comps)
        cc = CloudComparator(g)
        r = cc.assess_migration_risk(CloudProvider.AWS, CloudProvider.GCP)
        assert r.data_transfer_risk <= 1.0
        assert r.risk_score > 0

    def test_compare_all_categories(self):
        cc = CloudComparator(_rich_graph())
        for cat in ServiceCategory:
            r = cc.compare_category(cat)
            assert isinstance(r, ComparisonResult)
            assert r.category == cat

    def test_report_strategy_for_rich_graph(self):
        cc = CloudComparator(_rich_graph())
        r = cc.generate_report()
        assert len(r.best_multi_cloud_strategy) > 0

    def test_on_premise_source_migration(self):
        g = _graph(
            _comp("app", ComponentType.APP_SERVER),
            _comp("db", ComponentType.DATABASE),
        )
        cc = CloudComparator(g)
        r = cc.assess_migration_risk(CloudProvider.ON_PREMISE, CloudProvider.AWS)
        assert any("network" in i.lower() or "VPN" in i for i in r.compatibility_issues)

    def test_on_premise_both(self):
        cc = CloudComparator(_basic_graph())
        r = cc.assess_migration_risk(CloudProvider.ON_PREMISE, CloudProvider.ON_PREMISE)
        assert r.risk_score == 0.0

    def test_cost_normalized_empty_mappings(self):
        cc = CloudComparator(_basic_graph())
        cc._mappings = {}
        score = cc._cost_normalized_score(CloudProvider.AWS)
        assert score == 50.0
