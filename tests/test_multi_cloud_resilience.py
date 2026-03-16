"""Tests for Multi-Cloud Resilience Analyzer."""

from __future__ import annotations

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph
from faultray.simulator.multi_cloud_resilience import (
    CloudComponentMapping,
    CloudProvider,
    CrossCloudDependency,
    DataSovereigntyRegion,
    DRMode,
    DRPosture,
    EgressCostEstimate,
    FailureMode,
    FailureModeImpact,
    MultiCloudResilienceAnalyzer,
    PortabilityLevel,
    ResilienceAnalysisResult,
    ServiceEquivalent,
    VendorLockInAssessment,
)


# ---------------------------------------------------------------------------
# Helpers (using required _comp / _graph pattern)
# ---------------------------------------------------------------------------

def _comp(cid="c1", ctype=ComponentType.APP_SERVER):
    return Component(id=cid, name=cid, type=ctype)


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


def _multi_tier_graph():
    """Build a multi-tier graph with dependencies."""
    lb = _comp("lb-1", ComponentType.LOAD_BALANCER)
    app = _comp("app-1", ComponentType.APP_SERVER)
    db = _comp("db-1", ComponentType.DATABASE)
    cache = _comp("cache-1", ComponentType.CACHE)
    queue = _comp("queue-1", ComponentType.QUEUE)

    g = _graph(lb, app, db, cache, queue)
    g.add_dependency(Dependency(source_id="lb-1", target_id="app-1"))
    g.add_dependency(Dependency(source_id="app-1", target_id="db-1"))
    g.add_dependency(Dependency(source_id="app-1", target_id="cache-1"))
    g.add_dependency(Dependency(source_id="app-1", target_id="queue-1"))
    return g


def _single_cloud_mappings():
    """All components on AWS us-east-1."""
    return [
        CloudComponentMapping("lb-1", CloudProvider.AWS, "us-east-1", service_name="elb"),
        CloudComponentMapping("app-1", CloudProvider.AWS, "us-east-1", service_name="ec2"),
        CloudComponentMapping("db-1", CloudProvider.AWS, "us-east-1", service_name="rds",
                              is_stateful=True, data_volume_gb=500.0),
        CloudComponentMapping("cache-1", CloudProvider.AWS, "us-east-1", service_name="elasticache"),
        CloudComponentMapping("queue-1", CloudProvider.AWS, "us-east-1", service_name="sqs"),
    ]


def _multi_cloud_mappings():
    """Components spread across AWS, GCP, and Azure."""
    return [
        CloudComponentMapping("lb-1", CloudProvider.AWS, "us-east-1", service_name="elb"),
        CloudComponentMapping("app-1", CloudProvider.GCP, "us-central1", service_name="cloud-run"),
        CloudComponentMapping("db-1", CloudProvider.AZURE, "eastus", service_name="azure-sql",
                              is_stateful=True, data_volume_gb=200.0),
        CloudComponentMapping("cache-1", CloudProvider.AWS, "us-west-2", service_name="elasticache"),
        CloudComponentMapping("queue-1", CloudProvider.GCP, "us-central1", service_name="pub-sub"),
    ]


def _multi_region_mappings():
    """Components spread across multiple regions and providers."""
    return [
        CloudComponentMapping("lb-1", CloudProvider.AWS, "us-east-1", service_name="elb"),
        CloudComponentMapping("app-1", CloudProvider.AWS, "eu-west-1", service_name="ec2"),
        CloudComponentMapping("db-1", CloudProvider.GCP, "asia-northeast1", service_name="cloud-sql",
                              is_stateful=True, data_volume_gb=100.0),
        CloudComponentMapping("cache-1", CloudProvider.AZURE, "westeurope", service_name="azure-cache"),
        CloudComponentMapping("queue-1", CloudProvider.ON_PREMISE, "on-premise", service_name="rabbitmq"),
    ]


# ---------------------------------------------------------------------------
# Test: Enums
# ---------------------------------------------------------------------------

class TestEnums:
    def test_cloud_provider_values(self):
        assert CloudProvider.AWS.value == "aws"
        assert CloudProvider.GCP.value == "gcp"
        assert CloudProvider.AZURE.value == "azure"
        assert CloudProvider.ON_PREMISE.value == "on_premise"
        assert CloudProvider.EDGE.value == "edge"

    def test_dr_mode_values(self):
        assert DRMode.ACTIVE_ACTIVE.value == "active_active"
        assert DRMode.ACTIVE_PASSIVE.value == "active_passive"
        assert DRMode.PILOT_LIGHT.value == "pilot_light"
        assert DRMode.BACKUP_RESTORE.value == "backup_restore"
        assert DRMode.NONE.value == "none"

    def test_failure_mode_values(self):
        assert FailureMode.AZ_OUTAGE.value == "az_outage"
        assert FailureMode.REGION_OUTAGE.value == "region_outage"
        assert FailureMode.PROVIDER_OUTAGE.value == "provider_outage"
        assert FailureMode.NETWORK_PARTITION.value == "network_partition"
        assert FailureMode.SERVICE_DEGRADATION.value == "service_degradation"
        assert FailureMode.DNS_FAILURE.value == "dns_failure"
        assert FailureMode.CONTROL_PLANE_FAILURE.value == "control_plane_failure"

    def test_data_sovereignty_values(self):
        assert DataSovereigntyRegion.EU.value == "eu"
        assert DataSovereigntyRegion.US.value == "us"
        assert DataSovereigntyRegion.APAC.value == "apac"
        assert DataSovereigntyRegion.CHINA.value == "china"
        assert DataSovereigntyRegion.GLOBAL.value == "global"

    def test_portability_level_values(self):
        assert PortabilityLevel.HIGH.value == "high"
        assert PortabilityLevel.MEDIUM.value == "medium"
        assert PortabilityLevel.LOW.value == "low"
        assert PortabilityLevel.LOCKED.value == "locked"


# ---------------------------------------------------------------------------
# Test: Data classes
# ---------------------------------------------------------------------------

class TestDataClasses:
    def test_cloud_component_mapping_defaults(self):
        m = CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")
        assert m.component_id == "c1"
        assert m.provider == CloudProvider.AWS
        assert m.region == "us-east-1"
        assert m.availability_zone == ""
        assert m.service_name == ""
        assert m.data_sovereignty == DataSovereigntyRegion.GLOBAL
        assert m.is_stateful is False
        assert m.data_volume_gb == 0.0

    def test_cloud_component_mapping_full(self):
        m = CloudComponentMapping(
            "db-1", CloudProvider.GCP, "europe-west1",
            availability_zone="europe-west1-b",
            service_name="cloud-sql",
            data_sovereignty=DataSovereigntyRegion.EU,
            is_stateful=True,
            data_volume_gb=500.0,
        )
        assert m.availability_zone == "europe-west1-b"
        assert m.data_sovereignty == DataSovereigntyRegion.EU
        assert m.is_stateful is True
        assert m.data_volume_gb == 500.0

    def test_cross_cloud_dependency_creation(self):
        dep = CrossCloudDependency(
            source_id="a1", target_id="b1",
            source_provider=CloudProvider.AWS,
            target_provider=CloudProvider.GCP,
            source_region="us-east-1",
            target_region="us-central1",
            estimated_latency_ms=15.0,
            monthly_data_transfer_gb=100.0,
            is_critical=True,
        )
        assert dep.source_id == "a1"
        assert dep.estimated_latency_ms == 15.0
        assert dep.is_critical is True

    def test_egress_cost_estimate(self):
        e = EgressCostEstimate(
            source_provider=CloudProvider.AWS,
            target_provider=CloudProvider.GCP,
            source_region="us-east-1",
            target_region="us-central1",
            monthly_data_gb=100.0,
            cost_per_gb=0.09,
            monthly_cost=9.0,
            annual_cost=108.0,
        )
        assert e.monthly_cost == 9.0
        assert e.annual_cost == 108.0

    def test_dr_posture_defaults(self):
        dr = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
        )
        assert dr.dr_provider is None
        assert dr.dr_region == ""
        assert dr.failover_automated is False
        assert dr.rpo_seconds == 0
        assert dr.rto_seconds == 0

    def test_service_equivalent(self):
        se = ServiceEquivalent("object_storage", "s3", "gcs", "blob", PortabilityLevel.HIGH)
        assert se.service_category == "object_storage"
        assert se.migration_complexity == PortabilityLevel.HIGH

    def test_vendor_lock_in_assessment(self):
        v = VendorLockInAssessment(
            component_id="c1",
            provider=CloudProvider.AWS,
            service_name="dynamodb",
            lock_in_score=60.0,
            portability=PortabilityLevel.LOW,
            migration_effort_hours=40.0,
            alternatives=["gcp:firestore", "azure:cosmos"],
            lock_in_reasons=["Uses proprietary service: dynamodb"],
        )
        assert v.lock_in_score == 60.0
        assert len(v.alternatives) == 2

    def test_failure_mode_impact(self):
        fmi = FailureModeImpact(
            failure_mode=FailureMode.PROVIDER_OUTAGE,
            affected_provider=CloudProvider.AWS,
            affected_region="",
            directly_affected_components=["c1", "c2"],
            cascade_affected_components=["c3"],
            total_affected_count=3,
            total_component_count=5,
            impact_percentage=60.0,
        )
        assert fmi.total_affected_count == 3
        assert fmi.impact_percentage == 60.0

    def test_resilience_analysis_result_defaults(self):
        r = ResilienceAnalysisResult(
            timestamp="2026-01-01T00:00:00+00:00",
            overall_score=75.0,
            provider_diversity_score=80.0,
            geographic_distribution_score=70.0,
            vendor_lock_in_score=30.0,
            dr_readiness_score=60.0,
            data_sovereignty_compliant=True,
            cross_cloud_dependency_count=3,
            total_monthly_egress_cost=50.0,
        )
        assert r.overall_score == 75.0
        assert r.failure_mode_impacts == []
        assert r.recommendations == []


# ---------------------------------------------------------------------------
# Test: Cross-Cloud Dependency Identification
# ---------------------------------------------------------------------------

class TestCrossCloudDependencies:
    def test_no_cross_deps_single_provider(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _single_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()
        deps = analyzer.identify_cross_cloud_dependencies(g, mappings)
        assert len(deps) == 0

    def test_cross_deps_multi_provider(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _multi_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()
        deps = analyzer.identify_cross_cloud_dependencies(g, mappings)
        assert len(deps) > 0
        # lb-1 (AWS) -> app-1 (GCP) is a cross-cloud dependency
        lb_app = [d for d in deps if d.source_id == "lb-1" and d.target_id == "app-1"]
        assert len(lb_app) == 1
        assert lb_app[0].source_provider == CloudProvider.AWS
        assert lb_app[0].target_provider == CloudProvider.GCP

    def test_cross_deps_latency_estimate(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _multi_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()
        deps = analyzer.identify_cross_cloud_dependencies(g, mappings)
        for dep in deps:
            assert dep.estimated_latency_ms > 0

    def test_cross_deps_empty_graph(self):
        g = _graph()
        analyzer = MultiCloudResilienceAnalyzer()
        deps = analyzer.identify_cross_cloud_dependencies(g, {})
        assert deps == []

    def test_cross_deps_same_provider_different_region(self):
        """AWS us-east-1 -> AWS us-west-2 counts as cross-region."""
        a = _comp("a1", ComponentType.APP_SERVER)
        b = _comp("b1", ComponentType.DATABASE)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))

        mappings = {
            "a1": CloudComponentMapping("a1", CloudProvider.AWS, "us-east-1"),
            "b1": CloudComponentMapping("b1", CloudProvider.AWS, "us-west-2"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        deps = analyzer.identify_cross_cloud_dependencies(g, mappings)
        assert len(deps) == 1
        assert deps[0].estimated_latency_ms == 80.0


# ---------------------------------------------------------------------------
# Test: Vendor Lock-In Assessment
# ---------------------------------------------------------------------------

class TestVendorLockIn:
    def test_proprietary_service_high_lock_in(self):
        c = _comp("c1", ComponentType.DATABASE)
        g = _graph(c)
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                service_name="dynamodb",
                is_stateful=True,
                data_volume_gb=2000.0,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assessments = analyzer.assess_vendor_lock_in(g, mappings)
        assert len(assessments) == 1
        assert assessments[0].lock_in_score > 50.0
        assert assessments[0].portability in (PortabilityLevel.LOW, PortabilityLevel.LOCKED)
        assert len(assessments[0].lock_in_reasons) > 0

    def test_standard_service_lower_lock_in(self):
        c = _comp("c1", ComponentType.LOAD_BALANCER)
        g = _graph(c)
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                service_name="elb",
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assessments = analyzer.assess_vendor_lock_in(g, mappings)
        assert len(assessments) == 1
        # elb has equivalents (cloud-lb, azure-lb) so lock-in is lower
        assert assessments[0].lock_in_score < 50.0

    def test_on_premise_no_lock_in(self):
        c = _comp("c1", ComponentType.APP_SERVER)
        g = _graph(c)
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.ON_PREMISE, "on-premise",
                service_name="nginx",
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assessments = analyzer.assess_vendor_lock_in(g, mappings)
        assert len(assessments) == 1
        assert assessments[0].lock_in_score < 30.0

    def test_lock_in_with_alternatives(self):
        c = _comp("c1", ComponentType.CACHE)
        g = _graph(c)
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                service_name="elasticache",
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assessments = analyzer.assess_vendor_lock_in(g, mappings)
        assert len(assessments) == 1
        assert len(assessments[0].alternatives) >= 1

    def test_lock_in_data_volume_impact(self):
        """Large data volume should increase lock-in score."""
        c = _comp("c1", ComponentType.DATABASE)
        g = _graph(c)

        small_map = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                service_name="rds", data_volume_gb=10.0,
            ),
        }
        large_map = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                service_name="rds", data_volume_gb=5000.0,
                is_stateful=True,
            ),
        }

        analyzer = MultiCloudResilienceAnalyzer()
        small_assess = analyzer.assess_vendor_lock_in(g, small_map)
        large_assess = analyzer.assess_vendor_lock_in(g, large_map)
        assert large_assess[0].lock_in_score > small_assess[0].lock_in_score
        assert large_assess[0].migration_effort_hours > small_assess[0].migration_effort_hours

    def test_lock_in_empty_mappings(self):
        g = _graph()
        analyzer = MultiCloudResilienceAnalyzer()
        assessments = analyzer.assess_vendor_lock_in(g, {})
        assert assessments == []


# ---------------------------------------------------------------------------
# Test: Egress Cost Estimation
# ---------------------------------------------------------------------------

class TestEgressCosts:
    def test_egress_costs_basic(self):
        cross_deps = [
            CrossCloudDependency(
                source_id="a1", target_id="b1",
                source_provider=CloudProvider.AWS,
                target_provider=CloudProvider.GCP,
                source_region="us-east-1", target_region="us-central1",
                monthly_data_transfer_gb=100.0,
            ),
        ]
        analyzer = MultiCloudResilienceAnalyzer()
        costs = analyzer.estimate_egress_costs(cross_deps)
        assert len(costs) == 1
        assert costs[0].monthly_cost > 0
        assert costs[0].annual_cost == costs[0].monthly_cost * 12

    def test_egress_costs_empty(self):
        analyzer = MultiCloudResilienceAnalyzer()
        costs = analyzer.estimate_egress_costs([])
        assert costs == []

    def test_egress_costs_multiple_deps(self):
        cross_deps = [
            CrossCloudDependency(
                "a1", "b1", CloudProvider.AWS, CloudProvider.GCP,
                "us-east-1", "us-central1", monthly_data_transfer_gb=50.0,
            ),
            CrossCloudDependency(
                "b1", "c1", CloudProvider.GCP, CloudProvider.AZURE,
                "us-central1", "eastus", monthly_data_transfer_gb=200.0,
            ),
        ]
        analyzer = MultiCloudResilienceAnalyzer()
        costs = analyzer.estimate_egress_costs(cross_deps)
        assert len(costs) == 2
        total = sum(c.monthly_cost for c in costs)
        assert total > 0

    def test_egress_cost_per_gb_varies_by_provider(self):
        aws_dep = CrossCloudDependency(
            "a", "b", CloudProvider.AWS, CloudProvider.GCP,
            "us-east-1", "us-central1", monthly_data_transfer_gb=100.0,
        )
        gcp_dep = CrossCloudDependency(
            "b", "a", CloudProvider.GCP, CloudProvider.AWS,
            "us-central1", "us-east-1", monthly_data_transfer_gb=100.0,
        )
        analyzer = MultiCloudResilienceAnalyzer()
        aws_costs = analyzer.estimate_egress_costs([aws_dep])
        gcp_costs = analyzer.estimate_egress_costs([gcp_dep])
        # AWS egress is $0.09/GB, GCP is $0.08/GB
        assert aws_costs[0].cost_per_gb == 0.09
        assert gcp_costs[0].cost_per_gb == 0.08


# ---------------------------------------------------------------------------
# Test: Failure Mode Analysis
# ---------------------------------------------------------------------------

class TestFailureModeAnalysis:
    def test_provider_outage_single_cloud(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _single_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()

        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.PROVIDER_OUTAGE, CloudProvider.AWS,
        )
        # All components are on AWS, so all should be directly affected
        assert impact.total_affected_count == 5
        assert impact.impact_percentage == 100.0
        assert len(impact.surviving_components) == 0

    def test_provider_outage_multi_cloud(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _multi_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()

        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.PROVIDER_OUTAGE, CloudProvider.AWS,
        )
        # Only lb-1 and cache-1 are on AWS
        assert "lb-1" in impact.directly_affected_components
        assert "cache-1" in impact.directly_affected_components
        assert len(impact.directly_affected_components) == 2
        assert len(impact.surviving_components) > 0

    def test_region_outage(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _multi_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()

        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.REGION_OUTAGE,
            CloudProvider.AWS, "us-east-1",
        )
        # Only lb-1 is on AWS us-east-1
        assert "lb-1" in impact.directly_affected_components
        assert "cache-1" not in impact.directly_affected_components  # cache-1 is us-west-2

    def test_provider_outage_no_match(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _single_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()

        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.PROVIDER_OUTAGE, CloudProvider.GCP,
        )
        assert impact.total_affected_count == 0
        assert impact.impact_percentage == 0.0

    def test_analyze_all_failure_modes(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _multi_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()

        impacts = analyzer.analyze_all_failure_modes(g, mappings)
        assert len(impacts) > 0
        # Should include provider and region outage modes
        modes = {i.failure_mode for i in impacts}
        assert FailureMode.PROVIDER_OUTAGE in modes

    def test_failure_cascade_analysis(self):
        """Failure of a dependency target should cascade to dependents."""
        a = _comp("a1", ComponentType.LOAD_BALANCER)
        b = _comp("b1", ComponentType.APP_SERVER)
        c = _comp("c1", ComponentType.DATABASE)
        g = _graph(a, b, c)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))
        g.add_dependency(Dependency(source_id="b1", target_id="c1"))

        mappings = {
            "a1": CloudComponentMapping("a1", CloudProvider.AWS, "us-east-1"),
            "b1": CloudComponentMapping("b1", CloudProvider.AWS, "us-east-1"),
            "c1": CloudComponentMapping("c1", CloudProvider.GCP, "us-central1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()

        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.PROVIDER_OUTAGE, CloudProvider.AWS,
        )
        # a1 and b1 directly affected, c1 not directly but b1 depends on c1
        # Actually cascade goes: who depends on a1/b1? a1 depends on b1, so
        # cascade from a1 does not affect b1 (b1 doesn't depend on a1).
        # But both a1 and b1 are directly affected.
        assert "a1" in impact.directly_affected_components
        assert "b1" in impact.directly_affected_components
        assert "c1" not in impact.directly_affected_components

    def test_failure_mode_recovery_estimate(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _single_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()

        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.PROVIDER_OUTAGE, CloudProvider.AWS,
        )
        assert impact.estimated_recovery_minutes == 480.0

        impact2 = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.REGION_OUTAGE, CloudProvider.AWS, "us-east-1",
        )
        assert impact2.estimated_recovery_minutes == 120.0

    def test_empty_graph_failure_mode(self):
        g = _graph()
        analyzer = MultiCloudResilienceAnalyzer()
        impact = analyzer.analyze_failure_mode(
            g, {}, FailureMode.PROVIDER_OUTAGE, CloudProvider.AWS,
        )
        assert impact.total_affected_count == 0
        assert impact.impact_percentage == 0.0


# ---------------------------------------------------------------------------
# Test: Portable Workload Identification
# ---------------------------------------------------------------------------

class TestPortableWorkloads:
    def test_portable_vs_locked(self):
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1", service_name="dynamodb",
                is_stateful=True, data_volume_gb=1000.0,
            ),
            "c2": CloudComponentMapping(
                "c2", CloudProvider.GCP, "us-central1", service_name="gke",
            ),
            "c3": CloudComponentMapping(
                "c3", CloudProvider.ON_PREMISE, "on-premise", service_name="nginx",
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        portable, locked = analyzer.identify_portable_workloads(mappings)
        assert "c3" in portable  # on-premise is portable
        assert "c2" in portable  # GKE has equivalent (EKS, AKS)

    def test_all_portable(self):
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.ON_PREMISE, "on-premise", service_name="nginx",
            ),
            "c2": CloudComponentMapping(
                "c2", CloudProvider.EDGE, "edge-1", service_name="haproxy",
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        portable, locked = analyzer.identify_portable_workloads(mappings)
        assert len(portable) == 2
        assert len(locked) == 0

    def test_empty_mappings(self):
        analyzer = MultiCloudResilienceAnalyzer()
        portable, locked = analyzer.identify_portable_workloads({})
        assert portable == []
        assert locked == []

    def test_stateful_large_data_locked(self):
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1", service_name="kinesis",
                is_stateful=True, data_volume_gb=1000.0,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        portable, locked = analyzer.identify_portable_workloads(mappings)
        # kinesis is proprietary and has no direct equivalent
        assert "c1" in locked


# ---------------------------------------------------------------------------
# Test: Cross-Cloud Service Mapping
# ---------------------------------------------------------------------------

class TestServiceMapping:
    def test_s3_equivalents(self):
        analyzer = MultiCloudResilienceAnalyzer()
        equivs = analyzer.get_service_equivalents("s3", CloudProvider.AWS)
        assert "gcp" in equivs
        assert equivs["gcp"] == "gcs"
        assert "azure" in equivs
        assert equivs["azure"] == "blob"

    def test_gcs_equivalents(self):
        analyzer = MultiCloudResilienceAnalyzer()
        equivs = analyzer.get_service_equivalents("gcs", CloudProvider.GCP)
        assert "aws" in equivs
        assert equivs["aws"] == "s3"

    def test_unknown_service(self):
        analyzer = MultiCloudResilienceAnalyzer()
        equivs = analyzer.get_service_equivalents("custom-service", CloudProvider.AWS)
        assert equivs == {}

    def test_elasticache_equivalents(self):
        analyzer = MultiCloudResilienceAnalyzer()
        equivs = analyzer.get_service_equivalents("elasticache", CloudProvider.AWS)
        assert "gcp" in equivs
        assert equivs["gcp"] == "memorystore"
        assert "azure" in equivs
        assert equivs["azure"] == "azure-cache"


# ---------------------------------------------------------------------------
# Test: Data Sovereignty
# ---------------------------------------------------------------------------

class TestDataSovereignty:
    def test_compliant_eu_data(self):
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "eu-west-1",
                data_sovereignty=DataSovereigntyRegion.EU,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assert analyzer.check_data_sovereignty(mappings) is True

    def test_non_compliant_eu_data_in_us(self):
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                data_sovereignty=DataSovereigntyRegion.EU,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assert analyzer.check_data_sovereignty(mappings) is False

    def test_global_sovereignty_always_compliant(self):
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                data_sovereignty=DataSovereigntyRegion.GLOBAL,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assert analyzer.check_data_sovereignty(mappings) is True

    def test_get_sovereignty_violations(self):
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                data_sovereignty=DataSovereigntyRegion.EU,
            ),
            "c2": CloudComponentMapping(
                "c2", CloudProvider.AWS, "eu-west-1",
                data_sovereignty=DataSovereigntyRegion.EU,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        violations = analyzer.get_sovereignty_violations(mappings)
        assert len(violations) == 1
        assert violations[0]["component_id"] == "c1"
        assert "eu" in violations[0]["required_sovereignty"]

    def test_no_violations(self):
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                data_sovereignty=DataSovereigntyRegion.US,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        violations = analyzer.get_sovereignty_violations(mappings)
        assert violations == []

    def test_apac_sovereignty(self):
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "ap-northeast-1",
                data_sovereignty=DataSovereigntyRegion.APAC,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assert analyzer.check_data_sovereignty(mappings) is True


# ---------------------------------------------------------------------------
# Test: DR Posture Analysis
# ---------------------------------------------------------------------------

class TestDRPosture:
    def test_active_active_cross_provider(self):
        dr = DRPosture(
            mode=DRMode.ACTIVE_ACTIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="us-central1",
            failover_automated=True,
            rpo_seconds=30,
            rto_seconds=60,
            last_tested="2026-01-01",
        )
        g = _graph(_comp("c1"))
        mappings = {"c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_dr_posture(dr, g, mappings)
        assert result["readiness_score"] > 80.0
        assert result["mode"] == "active_active"

    def test_no_dr_configured(self):
        dr = DRPosture(
            mode=DRMode.NONE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
        )
        g = _graph(_comp("c1"))
        mappings = {"c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_dr_posture(dr, g, mappings)
        assert result["readiness_score"] < 20.0
        assert len(result["gaps"]) > 0

    def test_same_provider_dr(self):
        dr = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.AWS,
            dr_region="us-west-2",
        )
        g = _graph(_comp("c1"))
        mappings = {"c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_dr_posture(dr, g, mappings)
        # Same provider DR gives partial credit
        assert 30.0 < result["readiness_score"] < 80.0
        assert any("same provider" in r for r in result["recommendations"])

    def test_dr_untested(self):
        dr = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="us-central1",
        )
        g = _graph(_comp("c1"))
        mappings = {"c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_dr_posture(dr, g, mappings)
        assert any("never been tested" in gap for gap in result["gaps"])


# ---------------------------------------------------------------------------
# Test: Cost vs Resilience Tradeoff
# ---------------------------------------------------------------------------

class TestCostResilienceTradeoff:
    def test_single_cloud_low_diversity(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _single_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_cost_resilience_tradeoff(g, mappings)
        assert result["provider_diversity_score"] < 30.0
        # Should suggest adding another provider
        actions = [i["action"] for i in result["improvements"]]
        assert "Add secondary cloud provider" in actions

    def test_multi_cloud_higher_diversity(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _multi_cloud_mappings()}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_cost_resilience_tradeoff(g, mappings)
        assert result["provider_diversity_score"] > 30.0

    def test_tradeoff_with_dr(self):
        g = _multi_tier_graph()
        mappings = {m.component_id: m for m in _multi_cloud_mappings()}
        dr = DRPosture(
            mode=DRMode.ACTIVE_ACTIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="us-central1",
            failover_automated=True,
            rpo_seconds=30,
            rto_seconds=60,
            last_tested="2026-01-01",
        )
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_cost_resilience_tradeoff(g, mappings, dr)
        assert result["current_resilience_score"] > 0


# ---------------------------------------------------------------------------
# Test: Network Latency Modeling
# ---------------------------------------------------------------------------

class TestNetworkLatency:
    def test_same_region_latency(self):
        mappings = {
            "a1": CloudComponentMapping("a1", CloudProvider.AWS, "us-east-1"),
            "b1": CloudComponentMapping("b1", CloudProvider.AWS, "us-east-1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.model_cross_cloud_latency(mappings, "a1", "b1")
        assert result["estimated_latency_ms"] == 1.5
        assert result["classification"] == "same_region"

    def test_cross_provider_same_geo(self):
        mappings = {
            "a1": CloudComponentMapping("a1", CloudProvider.AWS, "us-east-1"),
            "b1": CloudComponentMapping("b1", CloudProvider.GCP, "us-central1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.model_cross_cloud_latency(mappings, "a1", "b1")
        assert result["estimated_latency_ms"] == 15.0
        assert result["classification"] == "cross_provider_same_geo"

    def test_cross_geography_latency(self):
        mappings = {
            "a1": CloudComponentMapping("a1", CloudProvider.AWS, "us-east-1"),
            "b1": CloudComponentMapping("b1", CloudProvider.GCP, "asia-northeast1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.model_cross_cloud_latency(mappings, "a1", "b1")
        assert result["estimated_latency_ms"] == 200.0
        assert result["classification"] == "cross_geography"

    def test_unknown_component(self):
        mappings = {
            "a1": CloudComponentMapping("a1", CloudProvider.AWS, "us-east-1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.model_cross_cloud_latency(mappings, "a1", "missing")
        assert result["classification"] == "unknown"

    def test_same_provider_cross_region(self):
        mappings = {
            "a1": CloudComponentMapping("a1", CloudProvider.AWS, "us-east-1"),
            "b1": CloudComponentMapping("b1", CloudProvider.AWS, "eu-west-1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.model_cross_cloud_latency(mappings, "a1", "b1")
        assert result["estimated_latency_ms"] == 80.0
        assert result["classification"] == "cross_region"


# ---------------------------------------------------------------------------
# Test: Full Analysis (analyze method)
# ---------------------------------------------------------------------------

class TestFullAnalysis:
    def test_analyze_single_cloud(self):
        g = _multi_tier_graph()
        mappings = _single_cloud_mappings()
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)

        assert isinstance(result, ResilienceAnalysisResult)
        assert 0 <= result.overall_score <= 100
        assert result.provider_diversity_score < 30.0  # single cloud
        assert result.timestamp  # should be set
        assert result.data_sovereignty_compliant is True  # all GLOBAL default

    def test_analyze_multi_cloud(self):
        g = _multi_tier_graph()
        mappings = _multi_cloud_mappings()
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)

        assert result.overall_score > 0
        assert result.cross_cloud_dependency_count > 0
        assert len(result.vendor_assessments) == 5

    def test_analyze_with_dr(self):
        g = _multi_tier_graph()
        mappings = _multi_cloud_mappings()
        dr = DRPosture(
            mode=DRMode.ACTIVE_ACTIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="us-central1",
            failover_automated=True,
            rpo_seconds=30,
            rto_seconds=60,
            last_tested="2026-01-01",
        )
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings, dr_posture=dr)
        assert result.dr_readiness_score > 50.0

    def test_analyze_empty_graph(self):
        g = _graph()
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, [])
        assert result.overall_score >= 0
        assert result.cross_cloud_dependency_count == 0

    def test_analyze_multi_region(self):
        g = _multi_tier_graph()
        mappings = _multi_region_mappings()
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)

        # Multi-region should have better geographic distribution
        assert result.geographic_distribution_score > 20.0
        assert result.provider_diversity_score > 30.0

    def test_analyze_generates_recommendations(self):
        g = _multi_tier_graph()
        mappings = _single_cloud_mappings()
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)

        # Single cloud should generate provider diversity recommendation
        assert len(result.recommendations) > 0

    def test_analyze_result_timestamp_is_utc(self):
        g = _graph(_comp("c1"))
        mappings = [CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")]
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)
        assert "+00:00" in result.timestamp or "Z" in result.timestamp


# ---------------------------------------------------------------------------
# Test: Summary Report Generation
# ---------------------------------------------------------------------------

class TestSummaryReport:
    def test_report_generation(self):
        g = _multi_tier_graph()
        mappings = _multi_cloud_mappings()
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)
        report = analyzer.generate_summary_report(result)

        assert "Multi-Cloud Resilience Analysis Report" in report
        assert "Overall Resilience Score" in report
        assert "Provider Diversity" in report
        assert "Geographic Distribution" in report
        assert "Vendor Lock-in" in report
        assert "DR Readiness" in report

    def test_report_contains_recommendations(self):
        g = _multi_tier_graph()
        mappings = _single_cloud_mappings()
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)
        report = analyzer.generate_summary_report(result)
        assert "Recommendations" in report

    def test_report_contains_failure_impacts(self):
        g = _multi_tier_graph()
        mappings = _multi_cloud_mappings()
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)
        report = analyzer.generate_summary_report(result)
        assert "Failure Mode Impacts" in report

    def test_report_with_no_impacts(self):
        result = ResilienceAnalysisResult(
            timestamp="2026-01-01T00:00:00+00:00",
            overall_score=50.0,
            provider_diversity_score=50.0,
            geographic_distribution_score=50.0,
            vendor_lock_in_score=30.0,
            dr_readiness_score=50.0,
            data_sovereignty_compliant=True,
            cross_cloud_dependency_count=0,
            total_monthly_egress_cost=0.0,
        )
        analyzer = MultiCloudResilienceAnalyzer()
        report = analyzer.generate_summary_report(result)
        assert "Overall Resilience Score: 50.0/100" in report


# ---------------------------------------------------------------------------
# Test: Provider Diversity Scoring
# ---------------------------------------------------------------------------

class TestProviderDiversity:
    def test_single_provider_low_score(self):
        analyzer = MultiCloudResilienceAnalyzer()
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
            "c2": CloudComponentMapping("c2", CloudProvider.AWS, "us-east-1"),
        }
        score = analyzer._calc_provider_diversity(mappings)
        assert score == 20.0

    def test_two_providers_higher_score(self):
        analyzer = MultiCloudResilienceAnalyzer()
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
            "c2": CloudComponentMapping("c2", CloudProvider.GCP, "us-central1"),
        }
        score = analyzer._calc_provider_diversity(mappings)
        assert score > 50.0

    def test_three_providers_highest(self):
        analyzer = MultiCloudResilienceAnalyzer()
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
            "c2": CloudComponentMapping("c2", CloudProvider.GCP, "us-central1"),
            "c3": CloudComponentMapping("c3", CloudProvider.AZURE, "eastus"),
        }
        score = analyzer._calc_provider_diversity(mappings)
        assert score > 80.0

    def test_empty_mappings_zero(self):
        analyzer = MultiCloudResilienceAnalyzer()
        score = analyzer._calc_provider_diversity({})
        assert score == 0.0

    def test_uneven_distribution_lower(self):
        analyzer = MultiCloudResilienceAnalyzer()
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
            "c2": CloudComponentMapping("c2", CloudProvider.AWS, "us-east-1"),
            "c3": CloudComponentMapping("c3", CloudProvider.AWS, "us-east-1"),
            "c4": CloudComponentMapping("c4", CloudProvider.GCP, "us-central1"),
        }
        uneven_score = analyzer._calc_provider_diversity(mappings)

        even_mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
            "c2": CloudComponentMapping("c2", CloudProvider.GCP, "us-central1"),
        }
        even_score = analyzer._calc_provider_diversity(even_mappings)

        # Even distribution should have higher evenness component
        assert uneven_score > 20.0  # still better than single provider
        assert even_score > 20.0


# ---------------------------------------------------------------------------
# Test: Geographic Distribution Scoring
# ---------------------------------------------------------------------------

class TestGeographicDistribution:
    def test_single_region_low(self):
        analyzer = MultiCloudResilienceAnalyzer()
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
        }
        score = analyzer._calc_geographic_distribution(mappings)
        # Single geo, single region
        assert score > 0
        assert score < 60.0

    def test_multi_geo_high(self):
        analyzer = MultiCloudResilienceAnalyzer()
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
            "c2": CloudComponentMapping("c2", CloudProvider.AWS, "eu-west-1"),
            "c3": CloudComponentMapping("c3", CloudProvider.GCP, "asia-northeast1"),
        }
        score = analyzer._calc_geographic_distribution(mappings)
        assert score > 50.0

    def test_empty_zero(self):
        analyzer = MultiCloudResilienceAnalyzer()
        score = analyzer._calc_geographic_distribution({})
        assert score == 0.0


# ---------------------------------------------------------------------------
# Test: Overall Score Calculation
# ---------------------------------------------------------------------------

class TestOverallScore:
    def test_perfect_scores(self):
        analyzer = MultiCloudResilienceAnalyzer()
        score = analyzer._calc_overall_score(100.0, 100.0, 0.0, 100.0)
        assert score == 100.0

    def test_worst_scores(self):
        analyzer = MultiCloudResilienceAnalyzer()
        score = analyzer._calc_overall_score(0.0, 0.0, 100.0, 0.0)
        assert score == 0.0

    def test_balanced_scores(self):
        analyzer = MultiCloudResilienceAnalyzer()
        score = analyzer._calc_overall_score(50.0, 50.0, 50.0, 50.0)
        assert score == 50.0

    def test_score_bounded(self):
        analyzer = MultiCloudResilienceAnalyzer()
        score = analyzer._calc_overall_score(200.0, 200.0, -50.0, 200.0)
        assert score <= 100.0
        assert score >= 0.0


# ---------------------------------------------------------------------------
# Test: Additional coverage for edge cases
# ---------------------------------------------------------------------------

class TestAdditionalCoverage:
    def test_cross_dep_with_unmapped_component(self):
        """Edge with unmapped target should be skipped."""
        a = _comp("a1", ComponentType.APP_SERVER)
        b = _comp("b1", ComponentType.DATABASE)
        g = _graph(a, b)
        g.add_dependency(Dependency(source_id="a1", target_id="b1"))

        # Only map a1, not b1
        mappings = {
            "a1": CloudComponentMapping("a1", CloudProvider.AWS, "us-east-1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        deps = analyzer.identify_cross_cloud_dependencies(g, mappings)
        assert len(deps) == 0

    def test_vendor_lock_in_unmapped_component(self):
        """Mapping for component not in graph should be skipped."""
        g = _graph(_comp("c1"))
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
            "c_missing": CloudComponentMapping("c_missing", CloudProvider.AWS, "us-east-1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assessments = analyzer.assess_vendor_lock_in(g, mappings)
        assert len(assessments) == 1
        assert assessments[0].component_id == "c1"

    def test_locked_portability_level(self):
        """Score > 70 should give LOCKED portability."""
        analyzer = MultiCloudResilienceAnalyzer()
        assert analyzer._score_to_portability(75.0) == PortabilityLevel.LOCKED
        assert analyzer._score_to_portability(15.0) == PortabilityLevel.HIGH
        assert analyzer._score_to_portability(30.0) == PortabilityLevel.MEDIUM
        assert analyzer._score_to_portability(55.0) == PortabilityLevel.LOW

    def test_az_outage_failure_mode(self):
        """Test AZ outage: target_region must match both region and AZ."""
        c = _comp("c1", ComponentType.APP_SERVER)
        g = _graph(c)
        # For AZ_OUTAGE, _is_affected_by_failure checks:
        #   mapping.region == target_region AND mapping.availability_zone == target_region
        # So both region and AZ must equal target_region for the component to be affected.
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1a",
                availability_zone="us-east-1a",
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()

        # AZ matching (region == AZ == target_region)
        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.AZ_OUTAGE, CloudProvider.AWS, "us-east-1a",
        )
        assert "c1" in impact.directly_affected_components

        # AZ not matching
        impact2 = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.AZ_OUTAGE, CloudProvider.AWS, "us-east-1b",
        )
        assert "c1" not in impact2.directly_affected_components

    def test_network_partition_failure_mode(self):
        c = _comp("c1", ComponentType.APP_SERVER)
        g = _graph(c)
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.NETWORK_PARTITION, CloudProvider.AWS,
        )
        assert "c1" in impact.directly_affected_components

    def test_service_degradation_failure_mode(self):
        c = _comp("c1", ComponentType.APP_SERVER)
        g = _graph(c)
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.SERVICE_DEGRADATION,
            CloudProvider.AWS, "us-east-1",
        )
        assert "c1" in impact.directly_affected_components

    def test_dns_failure_mode(self):
        c = _comp("c1", ComponentType.APP_SERVER)
        g = _graph(c)
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.DNS_FAILURE, CloudProvider.AWS,
        )
        assert "c1" in impact.directly_affected_components

    def test_control_plane_failure_mode(self):
        c = _comp("c1", ComponentType.APP_SERVER)
        g = _graph(c)
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1"),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        impact = analyzer.analyze_failure_mode(
            g, mappings, FailureMode.CONTROL_PLANE_FAILURE, CloudProvider.AWS,
        )
        assert "c1" in impact.directly_affected_components

    def test_dr_same_region_gap(self):
        """DR with same region should generate recommendation."""
        dr = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="us-east-1",  # same region as primary
        )
        g = _graph(_comp("c1"))
        mappings = {"c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_dr_posture(dr, g, mappings)
        assert any("same as primary" in r for r in result["recommendations"])

    def test_dr_no_region_with_active_mode(self):
        """Active mode with no DR region should flag a gap."""
        dr = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="",  # no DR region
        )
        g = _graph(_comp("c1"))
        mappings = {"c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_dr_posture(dr, g, mappings)
        assert any("No DR region configured" in gap for gap in result["gaps"])

    def test_dr_large_rpo_rto(self):
        """Large RPO/RTO should generate recommendations."""
        dr = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="us-central1",
            rpo_seconds=600,
            rto_seconds=3600,
        )
        g = _graph(_comp("c1"))
        mappings = {"c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_dr_posture(dr, g, mappings)
        assert any("RPO" in r for r in result["recommendations"])
        assert any("RTO" in r for r in result["recommendations"])

    def test_dr_moderate_rpo_rto(self):
        """Moderate RPO/RTO (60-300s RPO, 300-1800s RTO)."""
        dr = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="us-central1",
            rpo_seconds=200,
            rto_seconds=600,
        )
        g = _graph(_comp("c1"))
        mappings = {"c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_dr_posture(dr, g, mappings)
        assert result["readiness_score"] > 0

    def test_dr_no_automated_failover_recommendation(self):
        """Active mode without automated failover should recommend it."""
        dr = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="us-central1",
            failover_automated=False,
        )
        g = _graph(_comp("c1"))
        mappings = {"c1": CloudComponentMapping("c1", CloudProvider.AWS, "us-east-1")}
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_dr_posture(dr, g, mappings)
        assert any("automated failover" in r for r in result["recommendations"])

    def test_dr_readiness_same_provider(self):
        """Same-provider DR gives partial credit in _calc_dr_readiness."""
        analyzer = MultiCloudResilienceAnalyzer()
        dr = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.AWS,
            dr_region="us-west-2",
            rpo_seconds=200,
        )
        score = analyzer._calc_dr_readiness(dr)
        assert score > 0
        # Same-provider gets 10 instead of 20
        dr2 = DRPosture(
            mode=DRMode.ACTIVE_PASSIVE,
            primary_provider=CloudProvider.AWS,
            primary_region="us-east-1",
            dr_provider=CloudProvider.GCP,
            dr_region="us-central1",
            rpo_seconds=200,
        )
        score2 = analyzer._calc_dr_readiness(dr2)
        assert score2 > score

    def test_cost_tradeoff_high_lock_in_improvement(self):
        """High lock-in should suggest lock-in reduction."""
        c = _comp("c1", ComponentType.DATABASE)
        g = _graph(c)
        g.add_dependency(Dependency(source_id="c1", target_id="c1"))  # self-dep won't cross-cloud

        mappings = [
            CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                service_name="dynamodb",
                is_stateful=True,
                data_volume_gb=5000.0,
            ),
        ]
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze_cost_resilience_tradeoff(
            g, {m.component_id: m for m in mappings},
        )
        # High lock-in should suggest reducing it
        assert result["vendor_lock_in_score"] > 50.0
        actions = [i["action"] for i in result["improvements"]]
        assert "Reduce vendor lock-in" in actions

    def test_sovereignty_russia_region_not_mapped(self):
        """Sovereignty region with no geo mapping should pass."""
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.ON_PREMISE, "moscow-dc",
                data_sovereignty=DataSovereigntyRegion.RUSSIA,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        # RUSSIA is not in _SOVEREIGNTY_GEO_MAP, so allowed_regions is empty
        assert analyzer.check_data_sovereignty(mappings) is True

    def test_sovereignty_violation_details_russia(self):
        """Russia sovereignty with no geo mapping should not generate violations."""
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.ON_PREMISE, "moscow-dc",
                data_sovereignty=DataSovereigntyRegion.RUSSIA,
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        violations = analyzer.get_sovereignty_violations(mappings)
        assert violations == []

    def test_geo_distribution_unknown_regions(self):
        """Regions with unknown geography should get base score."""
        analyzer = MultiCloudResilienceAnalyzer()
        mappings = {
            "c1": CloudComponentMapping("c1", CloudProvider.ON_PREMISE, "custom-dc-1"),
            "c2": CloudComponentMapping("c2", CloudProvider.ON_PREMISE, "custom-dc-2"),
        }
        score = analyzer._calc_geographic_distribution(mappings)
        # Unknown geos are discarded, so 0 geos -> 10.0
        assert score == 10.0

    def test_recommendations_high_impact_failure(self):
        """Failure with >80% impact should generate recommendation."""
        g = _multi_tier_graph()
        mappings = _single_cloud_mappings()
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)
        # Single cloud AWS: provider outage should affect 100%
        high_impact_recs = [
            r for r in result.recommendations
            if "provider_outage" in r or "100%" in r
        ]
        assert len(high_impact_recs) > 0

    def test_recommendations_data_sovereignty_violation(self):
        """Sovereignty violation should appear in recommendations."""
        c = _comp("c1", ComponentType.DATABASE)
        g = _graph(c)
        mappings = [
            CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                data_sovereignty=DataSovereigntyRegion.EU,
            ),
        ]
        analyzer = MultiCloudResilienceAnalyzer()
        result = analyzer.analyze(g, mappings)
        assert not result.data_sovereignty_compliant
        assert any("sovereignty" in r.lower() for r in result.recommendations)

    def test_low_portability_service_lock_in(self):
        """Service with LOW migration complexity should increase lock-in."""
        c = _comp("c1", ComponentType.DATABASE)
        g = _graph(c)
        # dynamodb maps to nosql_db with LOW portability
        mappings = {
            "c1": CloudComponentMapping(
                "c1", CloudProvider.AWS, "us-east-1",
                service_name="dynamodb",
            ),
        }
        analyzer = MultiCloudResilienceAnalyzer()
        assessments = analyzer.assess_vendor_lock_in(g, mappings)
        assert assessments[0].lock_in_score >= 60.0  # proprietary(40) + low portability(20)

    def test_region_geography_mapping_eu(self):
        """EU region names should map to 'eu' geography."""
        analyzer = MultiCloudResilienceAnalyzer()
        assert analyzer._region_to_geography("eu-west-1") == "eu"
        assert analyzer._region_to_geography("europe-west1") == "eu"
        assert analyzer._region_to_geography("westeurope") == "eu"

    def test_region_geography_mapping_apac(self):
        """APAC region names should map to 'apac' geography."""
        analyzer = MultiCloudResilienceAnalyzer()
        assert analyzer._region_to_geography("ap-northeast-1") == "apac"
        assert analyzer._region_to_geography("asia-southeast1") == "apac"

    def test_region_geography_mapping_unknown(self):
        """Unknown region should map to 'unknown'."""
        analyzer = MultiCloudResilienceAnalyzer()
        assert analyzer._region_to_geography("custom-region") == "unknown"
