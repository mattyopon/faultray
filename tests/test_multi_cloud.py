"""Tests for Multi-Cloud Topology Mapper."""

from infrasim.model.components import (
    Component,
    ComponentType,
    Dependency,
)
from infrasim.model.graph import InfraGraph
from infrasim.simulator.multi_cloud import (
    CloudMapping,
    CloudProvider,
    CloudRegion,
    CrossCloudLink,
    MultiCloudMapper,
    MultiCloudRisk,
    MultiCloudTopology,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_graph() -> InfraGraph:
    """Build a basic multi-tier graph for testing."""
    g = InfraGraph()
    g.add_component(Component(
        id="lb-1", name="Load Balancer", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    g.add_component(Component(
        id="app-1", name="App Server", type=ComponentType.APP_SERVER,
        replicas=3,
    ))
    g.add_component(Component(
        id="db-1", name="Database", type=ComponentType.DATABASE,
        replicas=2,
    ))
    g.add_component(Component(
        id="cache-1", name="Cache", type=ComponentType.CACHE,
        replicas=2,
    ))
    g.add_dependency(Dependency(source_id="lb-1", target_id="app-1"))
    g.add_dependency(Dependency(source_id="app-1", target_id="db-1"))
    g.add_dependency(Dependency(source_id="app-1", target_id="cache-1"))
    return g


def _make_aws_mappings() -> list[CloudMapping]:
    """All components on AWS us-east-1."""
    return [
        CloudMapping("lb-1", CloudProvider.AWS, "us-east-1", "us-east-1a", "elb"),
        CloudMapping("app-1", CloudProvider.AWS, "us-east-1", "us-east-1b", "ec2"),
        CloudMapping("db-1", CloudProvider.AWS, "us-east-1", "us-east-1a", "rds"),
        CloudMapping("cache-1", CloudProvider.AWS, "us-east-1", "us-east-1a", "elasticache"),
    ]


def _make_multi_provider_mappings() -> list[CloudMapping]:
    """Components spread across AWS, GCP, and Azure."""
    return [
        CloudMapping("lb-1", CloudProvider.AWS, "us-east-1", service_name="elb"),
        CloudMapping("app-1", CloudProvider.GCP, "us-central1", service_name="cloud-run"),
        CloudMapping("db-1", CloudProvider.AZURE, "eastus", service_name="cosmos"),
        CloudMapping("cache-1", CloudProvider.AWS, "us-west-2", service_name="elasticache"),
    ]


def _make_auto_detect_graph() -> InfraGraph:
    """Graph with component names hinting at cloud providers."""
    g = InfraGraph()
    g.add_component(Component(
        id="rds-primary", name="RDS Primary", type=ComponentType.DATABASE,
        replicas=2,
    ))
    g.add_component(Component(
        id="cloud-sql-replica", name="Cloud SQL Replica", type=ComponentType.DATABASE,
        replicas=1,
    ))
    g.add_component(Component(
        id="cosmos-db-main", name="Cosmos DB Main", type=ComponentType.DATABASE,
        replicas=2,
    ))
    g.add_component(Component(
        id="nginx-lb", name="Nginx LB", type=ComponentType.LOAD_BALANCER,
        replicas=2,
    ))
    return g


# ---------------------------------------------------------------------------
# Test: CloudProvider enum
# ---------------------------------------------------------------------------

class TestCloudProvider:
    def test_enum_values(self):
        assert CloudProvider.AWS.value == "aws"
        assert CloudProvider.GCP.value == "gcp"
        assert CloudProvider.AZURE.value == "azure"
        assert CloudProvider.ON_PREMISE.value == "on_premise"
        assert CloudProvider.HYBRID.value == "hybrid"

    def test_enum_str(self):
        assert str(CloudProvider.AWS) == "CloudProvider.AWS"


# ---------------------------------------------------------------------------
# Test: Data classes
# ---------------------------------------------------------------------------

class TestDataClasses:
    def test_cloud_region_creation(self):
        r = CloudRegion(
            provider=CloudProvider.AWS,
            region_name="us-east-1",
            display_name="US East (N. Virginia)",
            latitude=39.0438,
            longitude=-77.4874,
        )
        assert r.provider == CloudProvider.AWS
        assert r.region_name == "us-east-1"
        assert r.latitude == 39.0438

    def test_cloud_mapping_defaults(self):
        m = CloudMapping(
            component_id="x", provider=CloudProvider.GCP, region="us-central1",
        )
        assert m.availability_zone is None
        assert m.service_name is None

    def test_cloud_mapping_full(self):
        m = CloudMapping(
            component_id="x",
            provider=CloudProvider.AWS,
            region="us-east-1",
            availability_zone="us-east-1a",
            service_name="rds",
        )
        assert m.availability_zone == "us-east-1a"
        assert m.service_name == "rds"

    def test_cross_cloud_link_creation(self):
        link = CrossCloudLink(
            source_provider=CloudProvider.AWS,
            target_provider=CloudProvider.GCP,
            estimated_latency_ms=12.5,
            bandwidth_gbps=5.0,
            is_private_link=True,
        )
        assert link.estimated_latency_ms == 12.5
        assert link.is_private_link is True

    def test_cross_cloud_link_defaults(self):
        link = CrossCloudLink(
            source_provider=CloudProvider.AWS,
            target_provider=CloudProvider.AZURE,
            estimated_latency_ms=100.0,
            bandwidth_gbps=10.0,
        )
        assert link.is_private_link is False

    def test_multi_cloud_risk_creation(self):
        risk = MultiCloudRisk(
            provider_concentration_risk="High",
            region_concentration_risk="Medium",
            cross_cloud_latency_risk="Low",
            vendor_lock_in_score=75.0,
            geographic_distribution_score=40.0,
            recommendations=["diversify providers"],
        )
        assert risk.provider_concentration_risk == "High"
        assert len(risk.recommendations) == 1

    def test_multi_cloud_risk_default_recommendations(self):
        risk = MultiCloudRisk(
            provider_concentration_risk="Low",
            region_concentration_risk="Low",
            cross_cloud_latency_risk="Low",
            vendor_lock_in_score=0.0,
            geographic_distribution_score=100.0,
        )
        assert risk.recommendations == []

    def test_multi_cloud_topology_defaults(self):
        t = MultiCloudTopology()
        assert t.mappings == {}
        assert t.links == []
        assert t.regions_used == []
        assert t.provider_distribution == {}
        assert t.risk_assessment.provider_concentration_risk == "Low"


# ---------------------------------------------------------------------------
# Test: map_topology with explicit mappings
# ---------------------------------------------------------------------------

class TestMapTopology:
    def test_single_provider_mapping(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = _make_aws_mappings()

        topo = mapper.map_topology(g, mappings)

        assert len(topo.mappings) == 4
        assert "lb-1" in topo.mappings
        assert topo.mappings["lb-1"].provider == CloudProvider.AWS
        assert topo.provider_distribution["aws"] == 4

    def test_multi_provider_mapping(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = _make_multi_provider_mappings()

        topo = mapper.map_topology(g, mappings)

        assert topo.provider_distribution["aws"] == 2
        assert topo.provider_distribution["gcp"] == 1
        assert topo.provider_distribution["azure"] == 1

    def test_regions_resolved(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = _make_multi_provider_mappings()

        topo = mapper.map_topology(g, mappings)

        region_names = {r.region_name for r in topo.regions_used}
        assert "us-east-1" in region_names
        assert "us-central1" in region_names
        assert "eastus" in region_names
        assert "us-west-2" in region_names

    def test_cross_cloud_links_generated(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = _make_multi_provider_mappings()

        topo = mapper.map_topology(g, mappings)

        # There should be cross-cloud links for cross-provider deps
        assert len(topo.links) > 0

    def test_no_links_for_same_provider_same_region(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = _make_aws_mappings()  # all same provider, same region

        topo = mapper.map_topology(g, mappings)

        assert len(topo.links) == 0

    def test_ignores_unmapped_components(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        # Only map 2 of 4 components
        mappings = [
            CloudMapping("lb-1", CloudProvider.AWS, "us-east-1"),
            CloudMapping("app-1", CloudProvider.AWS, "us-east-1"),
        ]
        topo = mapper.map_topology(g, mappings)
        assert len(topo.mappings) == 2

    def test_ignores_mapping_for_nonexistent_component(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("nonexistent", CloudProvider.AWS, "us-east-1"),
        ]
        topo = mapper.map_topology(g, mappings)
        assert len(topo.mappings) == 0

    def test_risk_assessment_populated(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = _make_aws_mappings()

        topo = mapper.map_topology(g, mappings)

        assert topo.risk_assessment.provider_concentration_risk == "High"
        assert topo.risk_assessment.region_concentration_risk == "High"


# ---------------------------------------------------------------------------
# Test: auto_detect_providers
# ---------------------------------------------------------------------------

class TestAutoDetectProviders:
    def test_aws_detection(self):
        g = InfraGraph()
        g.add_component(Component(
            id="rds-primary", name="RDS Primary DB",
            type=ComponentType.DATABASE, replicas=1,
        ))
        mapper = MultiCloudMapper()
        mappings = mapper.auto_detect_providers(g)

        assert len(mappings) == 1
        assert mappings[0].provider == CloudProvider.AWS
        assert mappings[0].region == "us-east-1"

    def test_gcp_detection(self):
        g = InfraGraph()
        g.add_component(Component(
            id="cloud-sql-main", name="Cloud SQL Main",
            type=ComponentType.DATABASE, replicas=1,
        ))
        mapper = MultiCloudMapper()
        mappings = mapper.auto_detect_providers(g)

        assert len(mappings) == 1
        assert mappings[0].provider == CloudProvider.GCP
        assert mappings[0].region == "us-central1"

    def test_azure_detection(self):
        g = InfraGraph()
        g.add_component(Component(
            id="cosmos-main", name="Cosmos DB",
            type=ComponentType.DATABASE, replicas=1,
        ))
        mapper = MultiCloudMapper()
        mappings = mapper.auto_detect_providers(g)

        assert len(mappings) == 1
        assert mappings[0].provider == CloudProvider.AZURE
        assert mappings[0].region == "eastus"

    def test_on_premise_fallback(self):
        g = InfraGraph()
        g.add_component(Component(
            id="nginx-lb", name="Nginx Load Balancer",
            type=ComponentType.LOAD_BALANCER, replicas=1,
        ))
        mapper = MultiCloudMapper()
        mappings = mapper.auto_detect_providers(g)

        assert len(mappings) == 1
        assert mappings[0].provider == CloudProvider.ON_PREMISE
        assert mappings[0].region == "on-premise"

    def test_mixed_providers_detection(self):
        g = _make_auto_detect_graph()
        mapper = MultiCloudMapper()
        mappings = mapper.auto_detect_providers(g)

        provider_map = {m.component_id: m.provider for m in mappings}
        assert provider_map["rds-primary"] == CloudProvider.AWS
        assert provider_map["cloud-sql-replica"] == CloudProvider.GCP
        assert provider_map["cosmos-db-main"] == CloudProvider.AZURE
        assert provider_map["nginx-lb"] == CloudProvider.ON_PREMISE

    def test_aws_patterns_comprehensive(self):
        """Test all AWS detection patterns."""
        mapper = MultiCloudMapper()
        patterns = [
            "rds", "dynamodb", "s3", "lambda", "ec2",
            "elb", "cloudfront", "sqs", "sns", "elasticache",
        ]
        for pattern in patterns:
            g = InfraGraph()
            g.add_component(Component(
                id=f"{pattern}-test", name=f"{pattern} test",
                type=ComponentType.APP_SERVER, replicas=1,
            ))
            mappings = mapper.auto_detect_providers(g)
            assert mappings[0].provider == CloudProvider.AWS, \
                f"Pattern '{pattern}' should detect as AWS"

    def test_gcp_patterns_comprehensive(self):
        """Test all GCP detection patterns."""
        mapper = MultiCloudMapper()
        patterns = [
            "cloud-sql", "bigquery", "gcs", "cloud-run",
            "gke", "cloud-cdn", "pub-sub", "memorystore",
        ]
        for pattern in patterns:
            g = InfraGraph()
            g.add_component(Component(
                id=f"{pattern}-test", name=f"{pattern} test",
                type=ComponentType.APP_SERVER, replicas=1,
            ))
            mappings = mapper.auto_detect_providers(g)
            assert mappings[0].provider == CloudProvider.GCP, \
                f"Pattern '{pattern}' should detect as GCP"

    def test_azure_patterns_comprehensive(self):
        """Test all Azure detection patterns."""
        mapper = MultiCloudMapper()
        patterns = [
            "cosmos", "blob", "aks", "app-service",
            "azure-cdn", "service-bus", "azure-cache",
        ]
        for pattern in patterns:
            g = InfraGraph()
            g.add_component(Component(
                id=f"{pattern}-test", name=f"{pattern} test",
                type=ComponentType.APP_SERVER, replicas=1,
            ))
            mappings = mapper.auto_detect_providers(g)
            assert mappings[0].provider == CloudProvider.AZURE, \
                f"Pattern '{pattern}' should detect as Azure"

    def test_service_name_detection(self):
        g = InfraGraph()
        g.add_component(Component(
            id="my-rds-instance", name="RDS Instance",
            type=ComponentType.DATABASE, replicas=1,
        ))
        mapper = MultiCloudMapper()
        mappings = mapper.auto_detect_providers(g)

        assert mappings[0].service_name == "rds"

    def test_no_service_name_for_on_premise(self):
        g = InfraGraph()
        g.add_component(Component(
            id="custom-app", name="Custom App",
            type=ComponentType.APP_SERVER, replicas=1,
        ))
        mapper = MultiCloudMapper()
        mappings = mapper.auto_detect_providers(g)

        assert mappings[0].service_name is None

    def test_empty_graph(self):
        g = InfraGraph()
        mapper = MultiCloudMapper()
        mappings = mapper.auto_detect_providers(g)
        assert mappings == []


# ---------------------------------------------------------------------------
# Test: analyze_cross_cloud_risks
# ---------------------------------------------------------------------------

class TestAnalyzeCrossCloudRisks:
    def test_high_provider_concentration(self):
        """All components on one provider should give High risk."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        risk = topo.risk_assessment
        assert risk.provider_concentration_risk == "High"

    def test_low_provider_concentration(self):
        """Components evenly spread should give Low risk."""
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="c", name="C", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="d", name="D", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="e", name="E", type=ComponentType.APP_SERVER, replicas=1))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("a", CloudProvider.AWS, "us-east-1"),
            CloudMapping("b", CloudProvider.GCP, "us-central1"),
            CloudMapping("c", CloudProvider.AZURE, "eastus"),
            CloudMapping("d", CloudProvider.AWS, "us-west-2"),
            CloudMapping("e", CloudProvider.GCP, "europe-west1"),
        ]
        topo = mapper.map_topology(g, mappings)

        assert topo.risk_assessment.provider_concentration_risk == "Low"

    def test_medium_provider_concentration(self):
        """~70% in one provider should give Medium risk."""
        g = InfraGraph()
        for i in range(10):
            g.add_component(Component(
                id=f"c{i}", name=f"C{i}",
                type=ComponentType.APP_SERVER, replicas=1,
            ))

        mapper = MultiCloudMapper()
        mappings = []
        for i in range(7):
            mappings.append(CloudMapping(f"c{i}", CloudProvider.AWS, "us-east-1"))
        for i in range(7, 10):
            mappings.append(CloudMapping(f"c{i}", CloudProvider.GCP, "us-central1"))

        topo = mapper.map_topology(g, mappings)
        assert topo.risk_assessment.provider_concentration_risk == "Medium"

    def test_high_region_concentration(self):
        """All components in one region should give High region risk."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        assert topo.risk_assessment.region_concentration_risk == "High"

    def test_low_region_concentration(self):
        """Components spread across many regions."""
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="c", name="C", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="d", name="D", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="e", name="E", type=ComponentType.APP_SERVER, replicas=1))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("a", CloudProvider.AWS, "us-east-1"),
            CloudMapping("b", CloudProvider.AWS, "us-west-2"),
            CloudMapping("c", CloudProvider.AWS, "eu-west-1"),
            CloudMapping("d", CloudProvider.AWS, "ap-northeast-1"),
            CloudMapping("e", CloudProvider.AWS, "ap-southeast-1"),
        ]
        topo = mapper.map_topology(g, mappings)

        assert topo.risk_assessment.region_concentration_risk == "Low"

    def test_vendor_lock_in_high(self):
        """All components using provider-specific services."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        # All 4 components have AWS-specific services
        assert topo.risk_assessment.vendor_lock_in_score == 100.0

    def test_vendor_lock_in_zero(self):
        """No provider-specific services used."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("lb-1", CloudProvider.AWS, "us-east-1"),
            CloudMapping("app-1", CloudProvider.AWS, "us-east-1"),
            CloudMapping("db-1", CloudProvider.AWS, "us-east-1"),
            CloudMapping("cache-1", CloudProvider.AWS, "us-east-1"),
        ]
        topo = mapper.map_topology(g, mappings)

        assert topo.risk_assessment.vendor_lock_in_score == 0.0

    def test_geographic_distribution_multi_region(self):
        """Multiple regions should give reasonable geo score."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_multi_provider_mappings())

        assert topo.risk_assessment.geographic_distribution_score > 0

    def test_geographic_distribution_single_region(self):
        """Single region should give low geo score."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        assert topo.risk_assessment.geographic_distribution_score == 20.0

    def test_empty_topology_risk(self):
        """Empty topology should return safe defaults."""
        mapper = MultiCloudMapper()
        topo = MultiCloudTopology()

        risk = mapper.analyze_cross_cloud_risks(topo)
        assert risk.provider_concentration_risk == "Low"
        assert risk.vendor_lock_in_score == 0.0
        assert risk.geographic_distribution_score == 0.0
        assert len(risk.recommendations) > 0

    def test_cross_cloud_latency_risk_high(self):
        """Cross-geography links should have high latency risk."""
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("a", CloudProvider.AWS, "us-east-1"),
            CloudMapping("b", CloudProvider.GCP, "asia-northeast1"),
        ]
        topo = mapper.map_topology(g, mappings)

        assert topo.risk_assessment.cross_cloud_latency_risk == "High"

    def test_cross_cloud_latency_risk_low(self):
        """No cross-cloud links should give low latency risk."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        assert topo.risk_assessment.cross_cloud_latency_risk == "Low"

    def test_recommendations_generated_for_high_risks(self):
        """High risk should generate recommendations."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        assert len(topo.risk_assessment.recommendations) > 0

    def test_medium_region_concentration(self):
        """50% in one region should give Medium region risk."""
        g = InfraGraph()
        for i in range(10):
            g.add_component(Component(
                id=f"c{i}", name=f"C{i}",
                type=ComponentType.APP_SERVER, replicas=1,
            ))

        mapper = MultiCloudMapper()
        mappings = []
        for i in range(5):
            mappings.append(CloudMapping(f"c{i}", CloudProvider.AWS, "us-east-1"))
        for i in range(5, 8):
            mappings.append(CloudMapping(f"c{i}", CloudProvider.AWS, "us-west-2"))
        for i in range(8, 10):
            mappings.append(CloudMapping(f"c{i}", CloudProvider.AWS, "eu-west-1"))

        topo = mapper.map_topology(g, mappings)
        assert topo.risk_assessment.region_concentration_risk == "Medium"

    def test_medium_latency_risk(self):
        """Cross-provider same geography should give Medium latency risk."""
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        mapper = MultiCloudMapper()
        # Same geography (both US East), cross-provider
        # Actually us-east-1 (AWS) and us-central1 (GCP) are ~1500 km apart,
        # which is within the 2000 km same-geography threshold => 12.5ms
        # We need to go cross-geography for Medium, so let's use
        # same-provider cross-region which gives 100ms
        mappings = [
            CloudMapping("a", CloudProvider.AWS, "us-east-1"),
            CloudMapping("b", CloudProvider.AWS, "ap-northeast-1"),
        ]
        topo = mapper.map_topology(g, mappings)

        assert topo.risk_assessment.cross_cloud_latency_risk == "Medium"


# ---------------------------------------------------------------------------
# Test: provider blast radius
# ---------------------------------------------------------------------------

class TestProviderBlastRadius:
    def test_full_provider_outage(self):
        """All components on AWS: 100% affected."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        result = mapper.calculate_provider_blast_radius(g, topo, CloudProvider.AWS)

        assert result["provider"] == "aws"
        assert result["directly_affected_count"] == 4
        assert result["total_affected_percentage"] == 100.0
        assert result["surviving_count"] == 0

    def test_partial_provider_outage(self):
        """Mixed providers: only some affected."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_multi_provider_mappings())

        result = mapper.calculate_provider_blast_radius(g, topo, CloudProvider.GCP)

        assert "app-1" in result["directly_affected"]
        assert result["directly_affected_count"] == 1
        assert result["total_affected_percentage"] < 100.0

    def test_no_components_affected(self):
        """Provider not used: zero affected."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        result = mapper.calculate_provider_blast_radius(g, topo, CloudProvider.GCP)

        assert result["directly_affected_count"] == 0
        assert result["total_affected_count"] == 0
        assert result["surviving_count"] == 4

    def test_cascade_detection(self):
        """Taking down a dependency should cascade to dependents."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        # Put db on GCP, everything else on AWS
        mappings = [
            CloudMapping("lb-1", CloudProvider.AWS, "us-east-1"),
            CloudMapping("app-1", CloudProvider.AWS, "us-east-1"),
            CloudMapping("db-1", CloudProvider.GCP, "us-central1"),
            CloudMapping("cache-1", CloudProvider.AWS, "us-east-1"),
        ]
        topo = mapper.map_topology(g, mappings)

        result = mapper.calculate_provider_blast_radius(g, topo, CloudProvider.GCP)

        # db-1 goes down directly, app-1 depends on db-1, lb-1 depends on app-1
        assert "db-1" in result["directly_affected"]
        # app-1 and lb-1 should be in cascade
        assert result["cascade_affected_count"] >= 1

    def test_empty_graph_blast_radius(self):
        """Empty graph should return zeros."""
        g = InfraGraph()
        mapper = MultiCloudMapper()
        topo = MultiCloudTopology()

        result = mapper.calculate_provider_blast_radius(g, topo, CloudProvider.AWS)

        assert result["directly_affected_count"] == 0
        assert result["total_affected_count"] == 0
        assert result["total_affected_percentage"] == 0.0

    def test_surviving_components(self):
        """Verify surviving components list."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_multi_provider_mappings())

        result = mapper.calculate_provider_blast_radius(g, topo, CloudProvider.AZURE)

        # db-1 is on Azure, it goes down; cascade may affect app-1 and lb-1
        assert "db-1" in result["directly_affected"]
        # cache-1 should survive (it's on AWS and doesn't depend on db)
        assert "cache-1" in result["surviving_components"]


# ---------------------------------------------------------------------------
# Test: region blast radius
# ---------------------------------------------------------------------------

class TestRegionBlastRadius:
    def test_full_region_outage(self):
        """All components in same region: 100% affected."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        result = mapper.calculate_region_blast_radius(g, topo, "us-east-1")

        assert result["region"] == "us-east-1"
        assert result["directly_affected_count"] == 4
        assert result["total_affected_percentage"] == 100.0

    def test_partial_region_outage(self):
        """Components in different regions: partial outage."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_multi_provider_mappings())

        result = mapper.calculate_region_blast_radius(g, topo, "us-east-1")

        # Only lb-1 is in us-east-1
        assert "lb-1" in result["directly_affected"]
        assert result["directly_affected_count"] == 1

    def test_no_region_affected(self):
        """Unused region: zero affected."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        result = mapper.calculate_region_blast_radius(g, topo, "eu-west-1")

        assert result["directly_affected_count"] == 0
        assert result["surviving_count"] == 4

    def test_cascade_on_region_outage(self):
        """Region outage cascading through dependencies."""
        g = InfraGraph()
        g.add_component(Component(id="web", name="Web", type=ComponentType.WEB_SERVER, replicas=1))
        g.add_component(Component(id="api", name="API", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="db", name="DB", type=ComponentType.DATABASE, replicas=1))
        g.add_dependency(Dependency(source_id="web", target_id="api"))
        g.add_dependency(Dependency(source_id="api", target_id="db"))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("web", CloudProvider.AWS, "us-east-1"),
            CloudMapping("api", CloudProvider.AWS, "us-east-1"),
            CloudMapping("db", CloudProvider.AWS, "us-west-2"),
        ]
        topo = mapper.map_topology(g, mappings)

        result = mapper.calculate_region_blast_radius(g, topo, "us-west-2")

        assert "db" in result["directly_affected"]
        # api depends on db, web depends on api
        assert "api" in result["cascade_affected"]
        assert "web" in result["cascade_affected"]

    def test_empty_graph_region_blast(self):
        """Empty graph returns zeros."""
        g = InfraGraph()
        mapper = MultiCloudMapper()
        topo = MultiCloudTopology()

        result = mapper.calculate_region_blast_radius(g, topo, "us-east-1")

        assert result["directly_affected_count"] == 0
        assert result["total_affected_count"] == 0


# ---------------------------------------------------------------------------
# Test: suggest_multi_cloud_strategy
# ---------------------------------------------------------------------------

class TestSuggestMultiCloudStrategy:
    def test_single_provider_suggestion(self):
        """Single provider should suggest distributing."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        suggestions = mapper.suggest_multi_cloud_strategy(g, topo)

        assert any("at least 2 cloud providers" in s for s in suggestions)

    def test_single_region_suggestion(self):
        """Single region should suggest multi-region."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        suggestions = mapper.suggest_multi_cloud_strategy(g, topo)

        assert any("single region" in s for s in suggestions)

    def test_multi_provider_no_distribute_suggestion(self):
        """Multi-provider should not suggest distributing."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_multi_provider_mappings())

        suggestions = mapper.suggest_multi_cloud_strategy(g, topo)

        assert not any("at least 2 cloud providers" in s for s in suggestions)

    def test_high_latency_suggestion(self):
        """High latency links should generate suggestions."""
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("a", CloudProvider.AWS, "us-east-1"),
            CloudMapping("b", CloudProvider.GCP, "asia-northeast1"),
        ]
        topo = mapper.map_topology(g, mappings)

        suggestions = mapper.suggest_multi_cloud_strategy(g, topo)

        assert any("latency" in s.lower() for s in suggestions)

    def test_high_vendor_lock_in_suggestion(self):
        """High vendor lock-in should suggest alternatives."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        suggestions = mapper.suggest_multi_cloud_strategy(g, topo)

        assert any("lock-in" in s.lower() or "lock" in s.lower() for s in suggestions)

    def test_empty_topology_suggestion(self):
        """Empty topology should suggest mapping components."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = MultiCloudTopology()

        suggestions = mapper.suggest_multi_cloud_strategy(g, topo)

        assert any("no components are mapped" in s.lower() for s in suggestions)

    def test_database_without_replica_suggestion(self):
        """Single-replica DB without cross-region replica should get suggestion."""
        g = InfraGraph()
        g.add_component(Component(
            id="db", name="Database", type=ComponentType.DATABASE, replicas=1,
        ))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("db", CloudProvider.AWS, "us-east-1", service_name="rds"),
        ]
        topo = mapper.map_topology(g, mappings)

        suggestions = mapper.suggest_multi_cloud_strategy(g, topo)

        assert any("cross-region replica" in s.lower() for s in suggestions)

    def test_suggestions_deduplicated(self):
        """Suggestions should not have duplicates."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        suggestions = mapper.suggest_multi_cloud_strategy(g, topo)

        assert len(suggestions) == len(set(suggestions))


# ---------------------------------------------------------------------------
# Test: generate_topology_summary
# ---------------------------------------------------------------------------

class TestGenerateTopologySummary:
    def test_summary_contains_provider_distribution(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        summary = mapper.generate_topology_summary(topo)

        assert "aws: 4" in summary
        assert "100.0%" in summary

    def test_summary_contains_regions(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_multi_provider_mappings())

        summary = mapper.generate_topology_summary(topo)

        assert "us-east-1" in summary
        assert "us-central1" in summary

    def test_summary_contains_risk_assessment(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        summary = mapper.generate_topology_summary(topo)

        assert "Risk Assessment:" in summary
        assert "Provider concentration:" in summary
        assert "Vendor lock-in score:" in summary

    def test_summary_contains_cross_cloud_links(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_multi_provider_mappings())

        summary = mapper.generate_topology_summary(topo)

        assert "Cross-cloud links:" in summary

    def test_summary_contains_recommendations(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        summary = mapper.generate_topology_summary(topo)

        assert "Recommendations:" in summary

    def test_summary_header(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        summary = mapper.generate_topology_summary(topo)

        assert summary.startswith("=== Multi-Cloud Topology Summary ===")

    def test_summary_total_components(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        summary = mapper.generate_topology_summary(topo)

        assert "Total mapped components: 4" in summary

    def test_summary_no_links_section_when_none(self):
        """When no cross-cloud links, that section is absent."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        summary = mapper.generate_topology_summary(topo)

        assert "Cross-cloud links:" not in summary

    def test_summary_private_link_tag(self):
        """Private links should show [private] tag."""
        topo = MultiCloudTopology(
            mappings={"a": CloudMapping("a", CloudProvider.AWS, "us-east-1")},
            links=[CrossCloudLink(
                source_provider=CloudProvider.AWS,
                target_provider=CloudProvider.GCP,
                estimated_latency_ms=10.0,
                bandwidth_gbps=10.0,
                is_private_link=True,
            )],
            regions_used=[CloudRegion(
                CloudProvider.AWS, "us-east-1", "US East", 39.0, -77.0,
            )],
            provider_distribution={"aws": 1},
            risk_assessment=MultiCloudRisk(
                provider_concentration_risk="Low",
                region_concentration_risk="Low",
                cross_cloud_latency_risk="Low",
                vendor_lock_in_score=0.0,
                geographic_distribution_score=0.0,
            ),
        )
        mapper = MultiCloudMapper()
        summary = mapper.generate_topology_summary(topo)

        assert "[private]" in summary


# ---------------------------------------------------------------------------
# Test: cross-cloud latency estimation
# ---------------------------------------------------------------------------

class TestLatencyEstimation:
    def test_same_provider_same_region(self):
        """Same provider + same region should be ~1.5ms."""
        mapper = MultiCloudMapper()
        src = CloudMapping("a", CloudProvider.AWS, "us-east-1")
        tgt = CloudMapping("b", CloudProvider.AWS, "us-east-1")

        latency = mapper._estimate_latency(src, tgt)
        assert latency == 1.5

    def test_same_provider_cross_region(self):
        """Same provider + cross region should be ~100ms."""
        mapper = MultiCloudMapper()
        src = CloudMapping("a", CloudProvider.AWS, "us-east-1")
        tgt = CloudMapping("b", CloudProvider.AWS, "ap-northeast-1")

        latency = mapper._estimate_latency(src, tgt)
        assert latency == 100.0

    def test_cross_provider_same_geography(self):
        """Cross provider + nearby regions should be ~12.5ms."""
        mapper = MultiCloudMapper()
        src = CloudMapping("a", CloudProvider.AWS, "us-east-1")
        tgt = CloudMapping("b", CloudProvider.GCP, "us-east1")

        latency = mapper._estimate_latency(src, tgt)
        assert latency == 12.5

    def test_cross_provider_cross_geography(self):
        """Cross provider + distant regions should be ~200ms."""
        mapper = MultiCloudMapper()
        src = CloudMapping("a", CloudProvider.AWS, "us-east-1")
        tgt = CloudMapping("b", CloudProvider.GCP, "asia-northeast1")

        latency = mapper._estimate_latency(src, tgt)
        assert latency == 200.0

    def test_unknown_region_fallback(self):
        """Unknown regions should fallback to 200ms."""
        mapper = MultiCloudMapper()
        src = CloudMapping("a", CloudProvider.AWS, "unknown-region-1")
        tgt = CloudMapping("b", CloudProvider.GCP, "unknown-region-2")

        latency = mapper._estimate_latency(src, tgt)
        assert latency == 200.0

    def test_bandwidth_same_provider_same_region(self):
        mapper = MultiCloudMapper()
        src = CloudMapping("a", CloudProvider.AWS, "us-east-1")
        tgt = CloudMapping("b", CloudProvider.AWS, "us-east-1")

        bw = mapper._estimate_bandwidth(src, tgt)
        assert bw == 25.0

    def test_bandwidth_same_provider_cross_region(self):
        mapper = MultiCloudMapper()
        src = CloudMapping("a", CloudProvider.AWS, "us-east-1")
        tgt = CloudMapping("b", CloudProvider.AWS, "eu-west-1")

        bw = mapper._estimate_bandwidth(src, tgt)
        assert bw == 10.0

    def test_bandwidth_cross_provider(self):
        mapper = MultiCloudMapper()
        src = CloudMapping("a", CloudProvider.AWS, "us-east-1")
        tgt = CloudMapping("b", CloudProvider.GCP, "us-central1")

        bw = mapper._estimate_bandwidth(src, tgt)
        assert bw == 5.0


# ---------------------------------------------------------------------------
# Test: edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_graph(self):
        """Empty graph should be handled gracefully."""
        g = InfraGraph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, [])

        assert len(topo.mappings) == 0
        assert topo.risk_assessment.vendor_lock_in_score == 0.0

    def test_single_component(self):
        """Single component topology."""
        g = InfraGraph()
        g.add_component(Component(
            id="solo", name="Solo", type=ComponentType.APP_SERVER, replicas=1,
        ))

        mapper = MultiCloudMapper()
        mappings = [CloudMapping("solo", CloudProvider.AWS, "us-east-1")]
        topo = mapper.map_topology(g, mappings)

        assert topo.provider_distribution == {"aws": 1}
        assert topo.risk_assessment.provider_concentration_risk == "High"

    def test_all_on_premise(self):
        """All components on-premise."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("lb-1", CloudProvider.ON_PREMISE, "dc-1"),
            CloudMapping("app-1", CloudProvider.ON_PREMISE, "dc-1"),
            CloudMapping("db-1", CloudProvider.ON_PREMISE, "dc-1"),
            CloudMapping("cache-1", CloudProvider.ON_PREMISE, "dc-1"),
        ]
        topo = mapper.map_topology(g, mappings)

        assert topo.provider_distribution["on_premise"] == 4
        assert topo.risk_assessment.provider_concentration_risk == "High"
        assert topo.risk_assessment.vendor_lock_in_score == 0.0

    def test_hybrid_topology(self):
        """Mix of cloud and on-premise components."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("lb-1", CloudProvider.AWS, "us-east-1", service_name="elb"),
            CloudMapping("app-1", CloudProvider.AWS, "us-east-1", service_name="ec2"),
            CloudMapping("db-1", CloudProvider.ON_PREMISE, "dc-1"),
            CloudMapping("cache-1", CloudProvider.ON_PREMISE, "dc-1"),
        ]
        topo = mapper.map_topology(g, mappings)

        assert topo.provider_distribution["aws"] == 2
        assert topo.provider_distribution["on_premise"] == 2

    def test_unknown_region_placeholder(self):
        """Unknown region should create a placeholder."""
        g = InfraGraph()
        g.add_component(Component(
            id="x", name="X", type=ComponentType.APP_SERVER, replicas=1,
        ))

        mapper = MultiCloudMapper()
        mappings = [CloudMapping("x", CloudProvider.AWS, "custom-region-99")]
        topo = mapper.map_topology(g, mappings)

        assert len(topo.regions_used) == 1
        assert topo.regions_used[0].region_name == "custom-region-99"
        assert topo.regions_used[0].latitude == 0.0

    def test_haversine_same_point(self):
        """Haversine distance of same point should be 0."""
        d = MultiCloudMapper._haversine_distance(35.0, 139.0, 35.0, 139.0)
        assert d == 0.0

    def test_haversine_known_distance(self):
        """Rough check: Tokyo to New York is about 10,800 km."""
        d = MultiCloudMapper._haversine_distance(
            35.6762, 139.6503, 40.7128, -74.0060,
        )
        assert 10000 < d < 11500

    def test_mapper_init(self):
        """Mapper initializes with known regions."""
        mapper = MultiCloudMapper()
        assert len(mapper._known_regions) >= 15  # 5 per provider * 3 providers

    def test_default_region_for_each_provider(self):
        mapper = MultiCloudMapper()
        assert mapper._default_region_for_provider(CloudProvider.AWS) == "us-east-1"
        assert mapper._default_region_for_provider(CloudProvider.GCP) == "us-central1"
        assert mapper._default_region_for_provider(CloudProvider.AZURE) == "eastus"
        assert mapper._default_region_for_provider(CloudProvider.ON_PREMISE) == "on-premise"
        assert mapper._default_region_for_provider(CloudProvider.HYBRID) == "hybrid"


# ---------------------------------------------------------------------------
# Test: mixed provider topologies (integration-style)
# ---------------------------------------------------------------------------

class TestMixedProviderTopologies:
    def test_three_provider_topology(self):
        """Full workflow: 3 providers, risk analysis, blast radius."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_multi_provider_mappings())

        # Check distribution
        assert len(topo.provider_distribution) == 3

        # Check risks
        risk = topo.risk_assessment
        assert risk.provider_concentration_risk == "Low"

        # Check blast radius for each provider
        for provider in [CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE]:
            result = mapper.calculate_provider_blast_radius(g, topo, provider)
            assert result["total_affected_percentage"] < 100.0

    def test_auto_detect_then_map(self):
        """Auto-detect providers then map and analyze."""
        g = _make_auto_detect_graph()
        mapper = MultiCloudMapper()

        # Auto-detect
        detected = mapper.auto_detect_providers(g)
        assert len(detected) == 4

        # Map topology
        topo = mapper.map_topology(g, detected)

        # Should have at least 3 providers (AWS, GCP, Azure, ON_PREMISE)
        assert len(topo.provider_distribution) >= 3

        # Generate summary
        summary = mapper.generate_topology_summary(topo)
        assert "Multi-Cloud Topology Summary" in summary

    def test_full_analysis_pipeline(self):
        """Complete analysis pipeline: map -> risks -> blast radius -> strategy -> summary."""
        g = _make_graph()
        mapper = MultiCloudMapper()

        # Map
        topo = mapper.map_topology(g, _make_multi_provider_mappings())

        # Risks
        risk = mapper.analyze_cross_cloud_risks(topo)
        assert risk.vendor_lock_in_score >= 0

        # Blast radius
        for provider in CloudProvider:
            if provider in (CloudProvider.ON_PREMISE, CloudProvider.HYBRID):
                continue
            result = mapper.calculate_provider_blast_radius(g, topo, provider)
            assert "directly_affected" in result

        # Region blast radius
        for m in topo.mappings.values():
            result = mapper.calculate_region_blast_radius(g, topo, m.region)
            assert "directly_affected" in result

        # Strategy
        suggestions = mapper.suggest_multi_cloud_strategy(g, topo)
        assert isinstance(suggestions, list)

        # Summary
        summary = mapper.generate_topology_summary(topo)
        assert isinstance(summary, str)
        assert len(summary) > 100

    def test_complex_dependency_chain_blast_radius(self):
        """Test blast radius with deep dependency chain across providers."""
        g = InfraGraph()
        g.add_component(Component(id="frontend", name="Frontend", type=ComponentType.WEB_SERVER, replicas=2))
        g.add_component(Component(id="gateway", name="API Gateway", type=ComponentType.APP_SERVER, replicas=2))
        g.add_component(Component(id="auth", name="Auth Service", type=ComponentType.APP_SERVER, replicas=2))
        g.add_component(Component(id="user-db", name="User DB", type=ComponentType.DATABASE, replicas=1))
        g.add_component(Component(id="cache", name="Redis Cache", type=ComponentType.CACHE, replicas=2))
        g.add_component(Component(id="queue", name="Message Queue", type=ComponentType.QUEUE, replicas=2))

        g.add_dependency(Dependency(source_id="frontend", target_id="gateway"))
        g.add_dependency(Dependency(source_id="gateway", target_id="auth"))
        g.add_dependency(Dependency(source_id="auth", target_id="user-db"))
        g.add_dependency(Dependency(source_id="gateway", target_id="cache"))
        g.add_dependency(Dependency(source_id="gateway", target_id="queue"))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("frontend", CloudProvider.AWS, "us-east-1"),
            CloudMapping("gateway", CloudProvider.AWS, "us-east-1"),
            CloudMapping("auth", CloudProvider.GCP, "us-central1"),
            CloudMapping("user-db", CloudProvider.GCP, "us-central1"),
            CloudMapping("cache", CloudProvider.AWS, "us-east-1"),
            CloudMapping("queue", CloudProvider.AZURE, "eastus"),
        ]
        topo = mapper.map_topology(g, mappings)

        # GCP outage: auth + user-db go down
        result = mapper.calculate_provider_blast_radius(g, topo, CloudProvider.GCP)
        assert "auth" in result["directly_affected"]
        assert "user-db" in result["directly_affected"]
        # gateway depends on auth, frontend depends on gateway
        assert result["cascade_affected_count"] >= 1

    def test_cross_cloud_links_deduplication(self):
        """Cross-cloud links between same provider pair should be deduplicated."""
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="c", name="C", type=ComponentType.APP_SERVER, replicas=1))
        g.add_dependency(Dependency(source_id="a", target_id="b"))
        g.add_dependency(Dependency(source_id="c", target_id="b"))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("a", CloudProvider.AWS, "us-east-1"),
            CloudMapping("b", CloudProvider.GCP, "us-central1"),
            CloudMapping("c", CloudProvider.AWS, "us-east-1"),
        ]
        topo = mapper.map_topology(g, mappings)

        # Both a->b and c->b cross the same provider pair and regions
        # so there should be only 1 unique link
        assert len(topo.links) == 1


# ---------------------------------------------------------------------------
# Test: risk recommendations
# ---------------------------------------------------------------------------

class TestRiskRecommendations:
    def test_high_provider_concentration_recommendation(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        recs = topo.risk_assessment.recommendations
        assert any(">80%" in r for r in recs)

    def test_medium_provider_concentration_recommendation(self):
        g = InfraGraph()
        for i in range(10):
            g.add_component(Component(
                id=f"c{i}", name=f"C{i}",
                type=ComponentType.APP_SERVER, replicas=1,
            ))

        mapper = MultiCloudMapper()
        mappings = [CloudMapping(f"c{i}", CloudProvider.AWS, "us-east-1") for i in range(7)]
        mappings += [CloudMapping(f"c{i}", CloudProvider.GCP, "us-central1") for i in range(7, 10)]

        topo = mapper.map_topology(g, mappings)
        recs = topo.risk_assessment.recommendations
        assert any("moderate" in r.lower() for r in recs)

    def test_high_region_concentration_recommendation(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        recs = topo.risk_assessment.recommendations
        assert any(">60%" in r for r in recs)

    def test_high_lock_in_recommendation(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        recs = topo.risk_assessment.recommendations
        assert any("lock-in" in r.lower() for r in recs)

    def test_moderate_lock_in_recommendation(self):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("a", CloudProvider.AWS, "us-east-1", service_name="rds"),
            CloudMapping("b", CloudProvider.AWS, "us-east-1"),
        ]
        topo = mapper.map_topology(g, mappings)

        recs = topo.risk_assessment.recommendations
        assert any("lock-in" in r.lower() for r in recs)

    def test_low_geographic_distribution_recommendation(self):
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())

        recs = topo.risk_assessment.recommendations
        assert any("geographic" in r.lower() for r in recs)

    def test_no_medium_latency_recommendation_when_low(self):
        """When latency risk is Low, no latency recommendations."""
        g = _make_graph()
        mapper = MultiCloudMapper()
        topo = mapper.map_topology(g, _make_aws_mappings())  # same region, no links

        recs = topo.risk_assessment.recommendations
        assert not any("latency is moderate" in r.lower() for r in recs)

    def test_high_latency_recommendation(self):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("a", CloudProvider.AWS, "us-east-1"),
            CloudMapping("b", CloudProvider.GCP, "asia-northeast1"),
        ]
        topo = mapper.map_topology(g, mappings)

        recs = topo.risk_assessment.recommendations
        assert any("latency" in r.lower() and "high" in r.lower() for r in recs)

    def test_medium_latency_recommendation(self):
        g = InfraGraph()
        g.add_component(Component(id="a", name="A", type=ComponentType.APP_SERVER, replicas=1))
        g.add_component(Component(id="b", name="B", type=ComponentType.APP_SERVER, replicas=1))
        g.add_dependency(Dependency(source_id="a", target_id="b"))

        mapper = MultiCloudMapper()
        mappings = [
            CloudMapping("a", CloudProvider.AWS, "us-east-1"),
            CloudMapping("b", CloudProvider.AWS, "ap-northeast-1"),
        ]
        topo = mapper.map_topology(g, mappings)

        recs = topo.risk_assessment.recommendations
        assert any("latency is moderate" in r.lower() for r in recs)
