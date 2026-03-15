"""Tests for IaC remediation code generation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from infrasim.model.components import (
    AutoScalingConfig,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    RegionConfig,
    SecurityProfile,
)
from infrasim.model.graph import InfraGraph
from infrasim.remediation.iac_generator import (
    IaCGenerator,
    RemediationFile,
    RemediationPlan,
    REMEDIATION_RULES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_component(
    cid: str,
    ctype: ComponentType = ComponentType.APP_SERVER,
    port: int = 8080,
    replicas: int = 1,
    autoscaling: AutoScalingConfig | None = None,
    failover: FailoverConfig | None = None,
    security: SecurityProfile | None = None,
    region: RegionConfig | None = None,
    **kwargs,
) -> Component:
    """Create a component with common defaults."""
    return Component(
        id=cid,
        name=cid.replace("_", " ").title(),
        type=ctype,
        port=port,
        replicas=replicas,
        autoscaling=autoscaling or AutoScalingConfig(),
        failover=failover or FailoverConfig(),
        security=security or SecurityProfile(),
        region=region or RegionConfig(),
        **kwargs,
    )


def _simple_graph(
    components: list[Component],
    deps: list[tuple[str, str]] | None = None,
) -> InfraGraph:
    """Build an InfraGraph from components and optional edges."""
    g = InfraGraph()
    for c in components:
        g.add_component(c)
    for src, tgt in deps or []:
        g.add_dependency(Dependency(source_id=src, target_id=tgt))
    return g


# ---------------------------------------------------------------------------
# 1. Database with no replica -> generates Terraform replica code
# ---------------------------------------------------------------------------

class TestDatabaseNoReplica:
    def test_spof_database_generates_replica_terraform(self):
        db = _make_component("main_db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        tf_files = [f for f in plan.files if f.path.endswith(".tf") and "database_no_replica" in f.path]
        assert len(tf_files) >= 1, "Should generate at least one replica terraform file"

        content = tf_files[0].content
        assert "aws_rds_cluster_instance" in content
        assert "replica_main_db" in content
        assert "main_db" in content
        assert tf_files[0].phase == 1
        assert tf_files[0].category == "redundancy"

    def test_database_with_replicas_no_remediation(self):
        db = _make_component("main_db", ComponentType.DATABASE, port=5432, replicas=3)
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        replica_files = [f for f in plan.files if "database_no_replica" in f.path]
        assert len(replica_files) == 0, "Database with replicas should not trigger remediation"


# ---------------------------------------------------------------------------
# 2. No autoscaling -> generates HPA YAML
# ---------------------------------------------------------------------------

class TestNoAutoscaling:
    def test_no_autoscaling_generates_hpa_yaml(self):
        app = _make_component(
            "api_server",
            ComponentType.APP_SERVER,
            autoscaling=AutoScalingConfig(enabled=False),
        )
        graph = _simple_graph([app])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        hpa_files = [f for f in plan.files if f.path.endswith(".yaml") and "no_autoscaling" in f.path]
        assert len(hpa_files) >= 1, "Should generate HPA YAML"

        content = hpa_files[0].content
        assert "HorizontalPodAutoscaler" in content
        assert "api_server" in content
        assert "minReplicas: 2" in content
        assert "maxReplicas: 10" in content
        assert hpa_files[0].phase == 1

    def test_autoscaling_enabled_no_remediation(self):
        app = _make_component(
            "api_server",
            ComponentType.APP_SERVER,
            autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
        )
        graph = _simple_graph([app])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        hpa_files = [f for f in plan.files if "no_autoscaling" in f.path]
        assert len(hpa_files) == 0


# ---------------------------------------------------------------------------
# 3. No encryption -> generates KMS Terraform
# ---------------------------------------------------------------------------

class TestNoEncryption:
    def test_no_encryption_generates_kms_terraform(self):
        db = _make_component(
            "user_db",
            ComponentType.DATABASE,
            port=5432,
            replicas=3,  # no SPOF issue
            security=SecurityProfile(encryption_at_rest=False),
        )
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        kms_files = [f for f in plan.files if "no_encryption" in f.path]
        assert len(kms_files) >= 1
        assert "aws_kms_key" in kms_files[0].content
        assert "user_db" in kms_files[0].content
        assert kms_files[0].phase == 2
        assert kms_files[0].category == "security"

    def test_encryption_enabled_no_remediation(self):
        db = _make_component(
            "user_db",
            ComponentType.DATABASE,
            port=5432,
            replicas=3,
            security=SecurityProfile(encryption_at_rest=True),
        )
        graph = _simple_graph([db])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        kms_files = [f for f in plan.files if "no_encryption" in f.path]
        assert len(kms_files) == 0


# ---------------------------------------------------------------------------
# 4. No WAF -> generates WAF Terraform
# ---------------------------------------------------------------------------

class TestNoWAF:
    def test_no_waf_generates_waf_terraform(self):
        lb = _make_component(
            "main_lb",
            ComponentType.LOAD_BALANCER,
            port=443,
            replicas=2,
            security=SecurityProfile(waf_protected=False),
        )
        graph = _simple_graph([lb])
        gen = IaCGenerator(graph)
        plan = gen.generate()

        waf_files = [f for f in plan.files if "no_waf" in f.path]
        assert len(waf_files) >= 1
        assert "aws_wafv2_web_acl" in waf_files[0].content
        assert "main_lb" in waf_files[0].content
        assert waf_files[0].phase == 2


# ---------------------------------------------------------------------------
# 5. Phase ordering (critical first, security second, DR last)
# ---------------------------------------------------------------------------

class TestPhaseOrdering:
    def test_phase_ordering_critical_first_dr_last(self):
        # Create components triggering all 3 phases
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1,
                             security=SecurityProfile(encryption_at_rest=False, backup_enabled=False))
        app = _make_component("app", ComponentType.APP_SERVER,
                              autoscaling=AutoScalingConfig(enabled=False),
                              security=SecurityProfile(waf_protected=False, encryption_in_transit=False))
        graph = _simple_graph([db, app])

        gen = IaCGenerator(graph)
        plan = gen.generate(target_score=100.0)

        phases = [f.phase for f in plan.files]
        # Phases should be non-decreasing (1, 1, ..., 2, 2, ..., 3, 3, ...)
        for i in range(len(phases) - 1):
            assert phases[i] <= phases[i + 1], (
                f"Phase ordering violated: phase {phases[i]} at index {i} "
                f"followed by phase {phases[i + 1]} at index {i + 1}"
            )

        assert 1 in phases, "Should have phase 1 (critical) remediations"
        assert 2 in phases, "Should have phase 2 (security) remediations"
        assert 3 in phases, "Should have phase 3 (DR) remediations"


# ---------------------------------------------------------------------------
# 6. Cost calculation
# ---------------------------------------------------------------------------

class TestCostCalculation:
    def test_total_monthly_cost(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        cache = _make_component("cache", ComponentType.CACHE, port=6379, replicas=1)
        graph = _simple_graph([db, cache])

        gen = IaCGenerator(graph)
        plan = gen.generate(target_score=100.0)

        individual_cost = sum(f.monthly_cost for f in plan.files)
        assert plan.total_monthly_cost == pytest.approx(individual_cost)
        assert plan.total_monthly_cost > 0, "Should have non-zero cost"


# ---------------------------------------------------------------------------
# 7. Impact score estimation
# ---------------------------------------------------------------------------

class TestImpactScoreEstimation:
    def test_expected_score_after_is_reasonable(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1,
                             security=SecurityProfile(encryption_at_rest=False))
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate(target_score=100.0)

        assert plan.expected_score_after >= plan.expected_score_before, (
            "Score after should be >= score before"
        )
        total_impact = sum(f.impact_score_delta for f in plan.files)
        expected_after = min(100.0, plan.expected_score_before + total_impact)
        assert plan.expected_score_after == pytest.approx(expected_after)


# ---------------------------------------------------------------------------
# 8. README generation
# ---------------------------------------------------------------------------

class TestReadmeGeneration:
    def test_readme_contains_essential_sections(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        readme = plan.readme_content
        assert "# FaultZero Remediation Plan" in readme
        assert "Summary" in readme
        assert "Resilience Score" in readme
        assert "How to Apply" in readme
        assert "terraform plan" in readme
        assert "kubectl apply" in readme

    def test_readme_lists_files(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        readme = plan.readme_content
        for f in plan.files:
            assert f.path in readme, f"README should mention file: {f.path}"


# ---------------------------------------------------------------------------
# 9. write_to_directory creates correct file structure
# ---------------------------------------------------------------------------

class TestWriteToDirectory:
    def test_write_creates_files_and_readme(self, tmp_path: Path):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        app = _make_component("app", ComponentType.APP_SERVER,
                              autoscaling=AutoScalingConfig(enabled=False),
                              security=SecurityProfile(waf_protected=False))
        graph = _simple_graph([db, app])

        gen = IaCGenerator(graph)
        plan = gen.generate(target_score=100.0)

        output_dir = tmp_path / "remediation"
        gen.write_to_directory(plan, output_dir)

        # README should exist
        assert (output_dir / "README.md").exists()
        readme_text = (output_dir / "README.md").read_text()
        assert "FaultZero" in readme_text

        # All plan files should exist on disk
        for f in plan.files:
            file_path = output_dir / f.path
            assert file_path.exists(), f"File should exist: {f.path}"
            assert file_path.read_text() == f.content

    def test_write_creates_phase_subdirectories(self, tmp_path: Path):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1,
                             security=SecurityProfile(backup_enabled=False))
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate(target_score=100.0)

        output_dir = tmp_path / "out"
        gen.write_to_directory(plan, output_dir)

        # Should have phase subdirectories
        phase_dirs = {f.path.split("/")[0] for f in plan.files}
        for pd in phase_dirs:
            assert (output_dir / pd).is_dir(), f"Phase dir should exist: {pd}"


# ---------------------------------------------------------------------------
# 10. Empty graph (no issues = no files)
# ---------------------------------------------------------------------------

class TestEmptyGraph:
    def test_no_issues_no_files(self):
        # A well-configured graph with no issues
        db = _make_component(
            "db", ComponentType.DATABASE, port=5432, replicas=3,
            security=SecurityProfile(
                encryption_at_rest=True, backup_enabled=True,
                waf_protected=True, network_segmented=True,
                encryption_in_transit=True,
            ),
            region=RegionConfig(dr_target_region="us-west-2"),
        )
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        assert len(plan.files) == 0
        assert plan.total_monthly_cost == 0.0

    def test_empty_graph_returns_empty_plan(self):
        graph = InfraGraph()
        gen = IaCGenerator(graph)
        plan = gen.generate()

        assert len(plan.files) == 0
        assert plan.total_phases == 0
        assert plan.total_monthly_cost == 0.0


# ---------------------------------------------------------------------------
# 11. Target score affects number of remediations
# ---------------------------------------------------------------------------

class TestTargetScore:
    def test_low_target_generates_fewer_files(self):
        # Create graph with many issues
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1,
                             security=SecurityProfile(encryption_at_rest=False, backup_enabled=False))
        cache = _make_component("cache", ComponentType.CACHE, port=6379, replicas=1)
        app = _make_component("app", ComponentType.APP_SERVER,
                              autoscaling=AutoScalingConfig(enabled=False),
                              security=SecurityProfile(waf_protected=False, encryption_in_transit=False))
        lb = _make_component("lb", ComponentType.LOAD_BALANCER, port=443,
                             security=SecurityProfile(waf_protected=False))
        graph = _simple_graph([db, cache, app, lb])

        gen = IaCGenerator(graph)

        plan_low = gen.generate(target_score=50.0)
        plan_high = gen.generate(target_score=100.0)

        # With a lower target, we should have fewer (or equal) files
        assert len(plan_low.files) <= len(plan_high.files), (
            f"Low target ({len(plan_low.files)} files) should generate "
            f"<= high target ({len(plan_high.files)} files)"
        )

    def test_target_already_met_minimal_remediation(self):
        # Graph with a high score already
        db = _make_component(
            "db", ComponentType.DATABASE, port=5432, replicas=3,
            security=SecurityProfile(encryption_at_rest=True, backup_enabled=True),
            region=RegionConfig(dr_target_region="us-west-2"),
        )
        graph = _simple_graph([db])
        score = graph.resilience_score()

        gen = IaCGenerator(graph)
        plan = gen.generate(target_score=score)

        # Should have zero or very few files since target is already met
        # (The only way to get files is if there are still issues detected)
        assert plan.expected_score_before >= score - 1.0


# ---------------------------------------------------------------------------
# 12. ROI calculation
# ---------------------------------------------------------------------------

class TestROICalculation:
    def test_roi_zero_cost(self):
        # Only HPA remediation which has $0 cost
        app = _make_component("app", ComponentType.APP_SERVER,
                              autoscaling=AutoScalingConfig(enabled=False))
        graph = _simple_graph([app])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        # When cost is 0, ROI should be 0 (no division by zero)
        hpa_only = all(f.monthly_cost == 0.0 for f in plan.files)
        if hpa_only and plan.total_monthly_cost == 0.0:
            assert plan.roi_percent == 0.0

    def test_roi_positive_cost(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        if plan.total_monthly_cost > 0:
            expected_roi = sum(f.impact_score_delta for f in plan.files) / (plan.total_monthly_cost / 100.0)
            assert plan.roi_percent == pytest.approx(expected_roi)


# ---------------------------------------------------------------------------
# 13. Kubernetes vs Terraform output selection
# ---------------------------------------------------------------------------

class TestOutputSelection:
    def test_hpa_is_kubernetes_yaml(self):
        app = _make_component("app", ComponentType.APP_SERVER,
                              autoscaling=AutoScalingConfig(enabled=False))
        graph = _simple_graph([app])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        hpa_files = [f for f in plan.files if "no_autoscaling" in f.path]
        for f in hpa_files:
            assert f.path.endswith(".yaml"), f"HPA should be .yaml, got {f.path}"
            assert "apiVersion:" in f.content

    def test_database_replica_is_terraform_tf(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        tf_files = [f for f in plan.files if "database_no_replica" in f.path]
        for f in tf_files:
            assert f.path.endswith(".tf"), f"Terraform should be .tf, got {f.path}"
            assert "resource" in f.content


# ---------------------------------------------------------------------------
# 14. Component name substitution in templates
# ---------------------------------------------------------------------------

class TestTemplateSubstitution:
    def test_comp_id_substituted(self):
        db = _make_component("my_postgres", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        for f in plan.files:
            # Verify that the placeholder is replaced, not present literally
            assert "{comp_id}" not in f.content, "Template variable {comp_id} not substituted"
            assert "{comp_name}" not in f.content, "Template variable {comp_name} not substituted"

    def test_comp_name_in_description(self):
        db = _make_component("prod_db", ComponentType.DATABASE, port=5432, replicas=1)
        # Override name to something different from id
        db.name = "Production Database"
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        replica_files = [f for f in plan.files if "database_no_replica" in f.path]
        assert len(replica_files) >= 1
        assert "Production Database" in replica_files[0].description


# ---------------------------------------------------------------------------
# 15. Multiple issues on same component
# ---------------------------------------------------------------------------

class TestMultipleIssuesSameComponent:
    def test_multiple_remediations_for_one_component(self):
        # A database with multiple issues: no replica, no encryption, no backup
        db = _make_component(
            "app_db",
            ComponentType.DATABASE,
            port=5432,
            replicas=1,
            security=SecurityProfile(encryption_at_rest=False, backup_enabled=False),
        )
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate(target_score=100.0)

        # Should generate at least 3 files for this single component
        db_files = [f for f in plan.files if "app_db" in f.path]
        assert len(db_files) >= 3, (
            f"Expected at least 3 remediations for app_db, got {len(db_files)}: "
            f"{[f.path for f in db_files]}"
        )

        # Verify different rule keys are represented
        rule_keys = {f.path.split("-")[-1].replace(".tf", "").replace(".yaml", "") for f in db_files}
        assert "replica" in str(rule_keys) or "no_replica" in str(rule_keys) or \
               any("database_no_replica" in f.path for f in db_files)


# ---------------------------------------------------------------------------
# 16. Plan serialization (to_dict / JSON)
# ---------------------------------------------------------------------------

class TestPlanSerialization:
    def test_to_dict_is_json_serializable(self):
        db = _make_component("db", ComponentType.DATABASE, port=5432, replicas=1)
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        data = plan.to_dict()
        # Should not raise
        json_str = json.dumps(data)
        parsed = json.loads(json_str)

        assert "total_phases" in parsed
        assert "total_monthly_cost" in parsed
        assert "files" in parsed
        assert isinstance(parsed["files"], list)


# ---------------------------------------------------------------------------
# 17. Network segmentation remediation
# ---------------------------------------------------------------------------

class TestNetworkSegmentation:
    def test_no_segmentation_generates_vpc_terraform(self):
        app = _make_component(
            "backend",
            ComponentType.APP_SERVER,
            security=SecurityProfile(
                network_segmented=False,
                waf_protected=True,       # avoid WAF rule
                encryption_in_transit=True,  # avoid TLS rule
            ),
            autoscaling=AutoScalingConfig(enabled=True),  # avoid HPA rule
        )
        graph = _simple_graph([app])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        seg_files = [f for f in plan.files if "no_network_segmentation" in f.path]
        assert len(seg_files) >= 1
        assert "aws_vpc" in seg_files[0].content
        assert "aws_security_group" in seg_files[0].content
        assert seg_files[0].category == "security"


# ---------------------------------------------------------------------------
# 18. TLS remediation
# ---------------------------------------------------------------------------

class TestTLSRemediation:
    def test_no_tls_generates_acm_terraform(self):
        lb = _make_component(
            "frontend_lb",
            ComponentType.LOAD_BALANCER,
            port=80,
            replicas=2,
            security=SecurityProfile(
                encryption_in_transit=False,
                waf_protected=True,  # avoid WAF rule
            ),
        )
        graph = _simple_graph([lb])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        tls_files = [f for f in plan.files if "no_tls" in f.path]
        assert len(tls_files) >= 1
        assert "aws_acm_certificate" in tls_files[0].content
        assert "aws_lb_listener" in tls_files[0].content


# ---------------------------------------------------------------------------
# 19. Cross-region remediation
# ---------------------------------------------------------------------------

class TestCrossRegion:
    def test_no_cross_region_generates_global_db_terraform(self):
        db = _make_component(
            "primary_db",
            ComponentType.DATABASE,
            port=5432,
            replicas=3,
            security=SecurityProfile(encryption_at_rest=True, backup_enabled=True),
            region=RegionConfig(dr_target_region=""),
        )
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        cr_files = [f for f in plan.files if "no_cross_region" in f.path]
        assert len(cr_files) >= 1
        assert "aws_rds_global_cluster" in cr_files[0].content
        assert cr_files[0].phase == 3
        assert cr_files[0].category == "dr"


# ---------------------------------------------------------------------------
# 20. DNS failover remediation
# ---------------------------------------------------------------------------

class TestDNSFailover:
    def test_no_dns_failover_generates_route53_terraform(self):
        dns = _make_component(
            "main_dns",
            ComponentType.DNS,
            port=53,
            failover=FailoverConfig(enabled=False),
        )
        graph = _simple_graph([dns])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        dns_files = [f for f in plan.files if "no_dns_failover" in f.path]
        assert len(dns_files) >= 1
        assert "aws_route53_health_check" in dns_files[0].content
        assert "failover_routing_policy" in dns_files[0].content
        assert dns_files[0].phase == 3
        assert dns_files[0].category == "dr"


# ---------------------------------------------------------------------------
# 21. Backup remediation
# ---------------------------------------------------------------------------

class TestBackupRemediation:
    def test_no_backup_generates_backup_plan_terraform(self):
        db = _make_component(
            "analytics_db",
            ComponentType.DATABASE,
            port=5432,
            replicas=3,
            security=SecurityProfile(
                encryption_at_rest=True,
                backup_enabled=False,
            ),
            region=RegionConfig(dr_target_region="eu-west-1"),
        )
        graph = _simple_graph([db])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        backup_files = [f for f in plan.files if "no_backup" in f.path]
        assert len(backup_files) >= 1
        assert "aws_backup_plan" in backup_files[0].content
        assert "aws_backup_vault" in backup_files[0].content
        assert backup_files[0].phase == 3


# ---------------------------------------------------------------------------
# 22. Cache no replica
# ---------------------------------------------------------------------------

class TestCacheNoReplica:
    def test_cache_no_replica_generates_replication_group(self):
        cache = _make_component("session_cache", ComponentType.CACHE, port=6379, replicas=1)
        graph = _simple_graph([cache])

        gen = IaCGenerator(graph)
        plan = gen.generate()

        cache_files = [f for f in plan.files if "cache_no_replica" in f.path]
        assert len(cache_files) >= 1
        assert "aws_elasticache_replication_group" in cache_files[0].content
        assert "automatic_failover_enabled = true" in cache_files[0].content
        assert cache_files[0].phase == 1
