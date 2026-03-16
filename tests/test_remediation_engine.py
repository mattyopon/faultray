"""Comprehensive tests for faultray.simulator.remediation_engine.

Covers all classes, methods, branches, and edge cases for ≥99% code coverage.
"""

from __future__ import annotations

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
    SecurityProfile,
)
from faultray.model.graph import InfraGraph
from faultray.simulator.remediation_engine import (
    ExecutionStatus,
    RemediationAction,
    RemediationEngine,
    RemediationPlan,
    RemediationPriority,
    RemediationReport,
    RemediationStep,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _comp(
    cid,
    name,
    ctype=ComponentType.APP_SERVER,
    replicas=1,
    cpu=0.0,
    memory=0.0,
    disk=0.0,
    health=HealthStatus.HEALTHY,
    failover=False,
    autoscaling=False,
    max_connections=0,
    network_connections=0,
    backup=False,
    encryption=False,
):
    c = Component(id=cid, name=name, type=ctype, replicas=replicas)
    c.metrics = ResourceMetrics(
        cpu_percent=cpu,
        memory_percent=memory,
        disk_percent=disk,
        network_connections=network_connections,
    )
    c.capacity = Capacity(max_connections=max_connections)
    c.health = health
    if failover:
        c.failover = FailoverConfig(enabled=True)
    if autoscaling:
        c.autoscaling = AutoScalingConfig(enabled=True)
    c.security = SecurityProfile(
        backup_enabled=backup, encryption_at_rest=encryption
    )
    return c


def _graph(*comps):
    g = InfraGraph()
    for c in comps:
        g.add_component(c)
    return g


# ===========================================================================
# 1. Empty / Healthy graph -> no plans
# ===========================================================================

class TestEmptyAndHealthyGraph:

    def test_empty_graph_no_plans(self):
        g = InfraGraph()
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        assert report.total_issues_found == 0
        assert report.plans == []
        assert report.auto_remediable_count == 0
        assert report.manual_required_count == 0
        assert report.estimated_total_duration_minutes == 0

    def test_healthy_graph_no_plans(self):
        c = _comp("a1", "AppServer", cpu=10.0, memory=20.0, disk=10.0)
        c.failover = FailoverConfig(enabled=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        assert report.total_issues_found == 0

    def test_risk_summary_no_plans(self):
        summary = RemediationEngine._build_risk_summary([])
        assert "healthy" in summary.lower()


# ===========================================================================
# 2. Component DOWN -> restart/replace plan (IMMEDIATE)
# ===========================================================================

class TestComponentDown:

    def test_down_component_generates_restart_plan(self):
        c = _comp("d1", "DownServer", health=HealthStatus.DOWN, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        down_plans = [
            p for p in report.plans if "DOWN" in p.issue_description
        ]
        assert len(down_plans) == 1
        plan = down_plans[0]
        assert plan.priority == RemediationPriority.IMMEDIATE
        assert plan.plan_id.startswith("REM-")
        assert len(plan.steps) == 2
        assert plan.steps[0].action == RemediationAction.RESTART_COMPONENT
        assert plan.steps[1].action == RemediationAction.DRAIN_AND_REPLACE
        assert not plan.requires_approval

    def test_down_plan_step_details(self):
        c = _comp("d2", "MyDB", health=HealthStatus.DOWN, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        plan = [p for p in report.plans if "DOWN" in p.issue_description][0]
        s1 = plan.steps[0]
        assert s1.step_number == 1
        assert s1.component_id == "d2"
        assert s1.component_name == "MyDB"
        assert s1.risk_level == "medium"
        assert "grace_period_seconds" in s1.parameters
        s2 = plan.steps[1]
        assert s2.risk_level == "high"
        assert "drain_timeout_seconds" in s2.parameters


# ===========================================================================
# 3. Component OVERLOADED -> scale up plan
# ===========================================================================

class TestComponentOverloaded:

    def test_overloaded_generates_scale_up(self):
        c = _comp("o1", "OverloadSrv", health=HealthStatus.OVERLOADED,
                  failover=True, replicas=2)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        overload_plans = [
            p for p in report.plans if "OVERLOADED" in p.issue_description
        ]
        assert len(overload_plans) == 1
        plan = overload_plans[0]
        assert plan.priority == RemediationPriority.IMMEDIATE
        assert plan.steps[0].action == RemediationAction.SCALE_UP
        target = plan.steps[0].parameters["target_replicas"]
        assert target == max(2 + 1, 2 * 2)  # max(3, 4) = 4

    def test_overloaded_single_replica(self):
        c = _comp("o2", "SingleSrv", health=HealthStatus.OVERLOADED,
                  replicas=1, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        plan = [p for p in report.plans if "OVERLOADED" in p.issue_description][0]
        target = plan.steps[0].parameters["target_replicas"]
        assert target == max(1 + 1, 1 * 2)  # 2


# ===========================================================================
# 4. CPU critical (>=90) -> immediate CPU remediation
# ===========================================================================

class TestCPUCritical:

    def test_cpu_critical_immediate_priority(self):
        c = _comp("c1", "HotCPU", cpu=95.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        cpu_plans = [
            p for p in report.plans if "CPU" in p.issue_description
        ]
        assert len(cpu_plans) >= 1
        plan = cpu_plans[0]
        assert plan.priority == RemediationPriority.IMMEDIATE
        assert "critical" in plan.issue_description
        assert not plan.requires_approval

    def test_cpu_critical_adds_2_replicas(self):
        c = _comp("c2", "CritCPU", cpu=92.0, replicas=2, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        plan = [p for p in report.plans if "CPU" in p.issue_description][0]
        target = plan.steps[0].parameters["target_replicas"]
        # critical: replicas + 2
        assert target == 2 + 2

    def test_cpu_critical_without_autoscaling_adds_autoscaling_step(self):
        c = _comp("c3", "NoAutoScale", cpu=91.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        plan = [p for p in report.plans if "CPU" in p.issue_description][0]
        actions = [s.action for s in plan.steps]
        assert RemediationAction.ENABLE_AUTOSCALING in actions

    def test_cpu_critical_with_autoscaling_no_extra_step(self):
        c = _comp("c4", "WithAutoScale", cpu=91.0, autoscaling=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        cpu_plans = [p for p in report.plans if "CPU" in p.issue_description]
        plan = cpu_plans[0]
        actions = [s.action for s in plan.steps]
        assert RemediationAction.ENABLE_AUTOSCALING not in actions


# ===========================================================================
# 5. CPU high (>=75) -> urgent CPU remediation
# ===========================================================================

class TestCPUHigh:

    def test_cpu_high_urgent_priority(self):
        c = _comp("ch1", "WarmCPU", cpu=80.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        cpu_plans = [
            p for p in report.plans if "CPU" in p.issue_description
        ]
        assert len(cpu_plans) >= 1
        plan = cpu_plans[0]
        assert plan.priority == RemediationPriority.URGENT
        assert "high" in plan.issue_description
        assert plan.requires_approval  # severity != "critical"

    def test_cpu_high_adds_1_replica(self):
        c = _comp("ch2", "HighCPU", cpu=78.0, replicas=3, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        plan = [p for p in report.plans if "CPU" in p.issue_description][0]
        target = plan.steps[0].parameters["target_replicas"]
        assert target == 3 + 1

    def test_cpu_below_threshold_no_plan(self):
        c = _comp("ch3", "CoolCPU", cpu=70.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        cpu_plans = [
            p for p in report.plans if "CPU" in p.issue_description
        ]
        assert len(cpu_plans) == 0


# ===========================================================================
# 6. Memory critical / high -> memory remediation
# ===========================================================================

class TestMemoryRemediation:

    def test_memory_critical(self):
        c = _comp("m1", "MemCrit", memory=95.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        mem_plans = [
            p for p in report.plans if "memory" in p.issue_description
        ]
        assert len(mem_plans) >= 1
        plan = mem_plans[0]
        assert plan.priority == RemediationPriority.IMMEDIATE
        assert "critical" in plan.issue_description
        assert not plan.requires_approval
        assert len(plan.steps) == 2
        assert plan.steps[0].action == RemediationAction.RESTART_COMPONENT
        assert plan.steps[0].risk_level == "medium"
        assert plan.steps[1].action == RemediationAction.ADD_REPLICA

    def test_memory_high(self):
        c = _comp("m2", "MemHigh", memory=85.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        mem_plans = [
            p for p in report.plans if "memory" in p.issue_description
        ]
        plan = mem_plans[0]
        assert plan.priority == RemediationPriority.URGENT
        assert "high" in plan.issue_description
        assert plan.requires_approval  # severity != "critical"
        assert plan.steps[0].risk_level == "low"

    def test_memory_below_threshold(self):
        c = _comp("m3", "MemOK", memory=75.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        mem_plans = [
            p for p in report.plans if "memory" in p.issue_description
        ]
        assert len(mem_plans) == 0


# ===========================================================================
# 7. Disk critical / high -> disk remediation
# ===========================================================================

class TestDiskRemediation:

    def test_disk_critical(self):
        c = _comp("dk1", "DiskCrit", disk=95.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        disk_plans = [
            p for p in report.plans if "disk" in p.issue_description
        ]
        plan = disk_plans[0]
        assert plan.priority == RemediationPriority.IMMEDIATE
        assert plan.requires_approval
        assert plan.estimated_duration_minutes == 30
        assert plan.steps[0].action == RemediationAction.SCALE_UP
        assert plan.steps[0].parameters["action"] == "expand_volume"

    def test_disk_high(self):
        c = _comp("dk2", "DiskHigh", disk=80.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        disk_plans = [
            p for p in report.plans if "disk" in p.issue_description
        ]
        plan = disk_plans[0]
        assert plan.priority == RemediationPriority.PLANNED
        assert plan.estimated_duration_minutes == 60

    def test_disk_below_threshold(self):
        c = _comp("dk3", "DiskOK", disk=70.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        disk_plans = [
            p for p in report.plans if "disk" in p.issue_description
        ]
        assert len(disk_plans) == 0


# ===========================================================================
# 8. Connection critical / high -> connection remediation
# ===========================================================================

class TestConnectionRemediation:

    def test_connection_critical(self):
        # ratio = 950/1000 = 0.95 >= 0.9
        c = _comp("cn1", "ConnCrit", max_connections=1000,
                  network_connections=950, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        conn_plans = [
            p for p in report.plans if "connections" in p.issue_description
        ]
        plan = conn_plans[0]
        assert plan.priority == RemediationPriority.URGENT
        assert "critical" in plan.issue_description
        assert len(plan.steps) == 2
        assert plan.steps[0].action == RemediationAction.ENABLE_RATE_LIMITING
        assert plan.steps[1].action == RemediationAction.ADD_REPLICA
        assert not plan.requires_approval

    def test_connection_high(self):
        # ratio = 750/1000 = 0.75 >= 0.7
        c = _comp("cn2", "ConnHigh", max_connections=1000,
                  network_connections=750, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        conn_plans = [
            p for p in report.plans if "connections" in p.issue_description
        ]
        plan = conn_plans[0]
        assert plan.priority == RemediationPriority.PLANNED
        assert "high" in plan.issue_description
        assert len(plan.steps) == 1
        assert plan.steps[0].action == RemediationAction.ENABLE_RATE_LIMITING

    def test_connection_below_threshold(self):
        c = _comp("cn3", "ConnOK", max_connections=1000,
                  network_connections=500, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        conn_plans = [
            p for p in report.plans if "connections" in p.issue_description
        ]
        assert len(conn_plans) == 0

    def test_zero_max_connections_no_plan(self):
        c = _comp("cn4", "ZeroMax", max_connections=0,
                  network_connections=100, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        conn_plans = [
            p for p in report.plans if "connections" in p.issue_description
        ]
        assert len(conn_plans) == 0


# ===========================================================================
# 9. Security: missing encryption (DB/STORAGE) -> encryption plan
# ===========================================================================

class TestSecurityEncryption:

    def test_db_missing_encryption(self):
        c = _comp("se1", "MainDB", ctype=ComponentType.DATABASE,
                  encryption=False, backup=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        enc_plans = [
            p for p in report.plans if "encryption" in p.issue_description
        ]
        assert len(enc_plans) == 1
        plan = enc_plans[0]
        assert plan.plan_id.startswith("SEC-")
        assert plan.priority == RemediationPriority.PLANNED
        assert plan.requires_approval
        assert plan.steps[0].action == RemediationAction.ENABLE_ENCRYPTION
        assert plan.steps[0].parameters["algorithm"] == "AES-256"

    def test_storage_missing_encryption(self):
        c = _comp("se2", "BlobStore", ctype=ComponentType.STORAGE,
                  encryption=False, backup=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        enc_plans = [
            p for p in report.plans if "encryption" in p.issue_description
        ]
        assert len(enc_plans) == 1

    def test_db_with_encryption_no_plan(self):
        c = _comp("se3", "EncDB", ctype=ComponentType.DATABASE,
                  encryption=True, backup=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        enc_plans = [
            p for p in report.plans if "encryption" in p.issue_description
        ]
        assert len(enc_plans) == 0

    def test_non_db_missing_encryption_no_plan(self):
        c = _comp("se4", "AppSrv", ctype=ComponentType.APP_SERVER,
                  encryption=False, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        enc_plans = [
            p for p in report.plans if "encryption" in p.issue_description
        ]
        assert len(enc_plans) == 0


# ===========================================================================
# 10. Security: missing backup (DB/STORAGE) -> backup plan
# ===========================================================================

class TestSecurityBackup:

    def test_db_missing_backup(self):
        c = _comp("sb1", "NoBkDB", ctype=ComponentType.DATABASE,
                  backup=False, encryption=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        bk_plans = [
            p for p in report.plans if "backup" in p.issue_description
        ]
        assert len(bk_plans) == 1
        plan = bk_plans[0]
        assert plan.plan_id.startswith("SEC-")
        assert not plan.requires_approval
        assert plan.steps[0].action == RemediationAction.ENABLE_BACKUP
        assert plan.steps[0].parameters["frequency"] == "daily"

    def test_storage_missing_backup(self):
        c = _comp("sb2", "NoBkStore", ctype=ComponentType.STORAGE,
                  backup=False, encryption=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        bk_plans = [
            p for p in report.plans if "backup" in p.issue_description
        ]
        assert len(bk_plans) == 1

    def test_db_with_backup_no_plan(self):
        c = _comp("sb3", "BkDB", ctype=ComponentType.DATABASE,
                  backup=True, encryption=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        bk_plans = [
            p for p in report.plans if "backup" in p.issue_description
        ]
        assert len(bk_plans) == 0


# ===========================================================================
# 11. HA: single replica, no failover, with dependents -> HA plan
# ===========================================================================

class TestHARemediation:

    def test_ha_single_replica_with_dependents(self):
        dep_target = _comp("ha1", "CoreSvc", replicas=1)
        dependent = _comp("ha2", "FrontEnd", replicas=2, failover=True)
        g = _graph(dep_target, dependent)
        g.add_dependency(Dependency(source_id="ha2", target_id="ha1"))
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        ha_plans = [
            p for p in report.plans
            if p.plan_id.startswith("HA-")
        ]
        assert len(ha_plans) == 1
        plan = ha_plans[0]
        assert "1 dependents" in plan.issue_description
        assert len(plan.steps) == 2
        assert plan.steps[0].action == RemediationAction.ADD_REPLICA
        assert plan.steps[1].action == RemediationAction.ENABLE_FAILOVER
        # 1 dependent <= 2 → PLANNED & requires_approval
        assert plan.priority == RemediationPriority.PLANNED
        assert plan.requires_approval

    def test_ha_many_dependents_urgent(self):
        target = _comp("ha3", "SharedDB", replicas=1)
        deps = []
        for i in range(3):
            d = _comp(f"dep{i}", f"Dep{i}", replicas=2, failover=True)
            deps.append(d)
        g = _graph(target, *deps)
        for d in deps:
            g.add_dependency(Dependency(source_id=d.id, target_id="ha3"))
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        ha_plans = [
            p for p in report.plans if p.plan_id.startswith("HA-")
        ]
        assert len(ha_plans) == 1
        plan = ha_plans[0]
        assert plan.priority == RemediationPriority.URGENT
        assert not plan.requires_approval  # >2 dependents

    def test_ha_no_dependents_no_plan(self):
        c = _comp("ha4", "Lonely", replicas=1)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        ha_plans = [
            p for p in report.plans if p.plan_id.startswith("HA-")
        ]
        assert len(ha_plans) == 0

    def test_ha_multiple_replicas_no_plan(self):
        c = _comp("ha5", "Multi", replicas=3)
        dep = _comp("ha6", "DepSvc", replicas=2, failover=True)
        g = _graph(c, dep)
        g.add_dependency(Dependency(source_id="ha6", target_id="ha5"))
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        ha_plans = [
            p for p in report.plans if p.plan_id.startswith("HA-")
        ]
        assert len(ha_plans) == 0

    def test_ha_with_failover_no_plan(self):
        c = _comp("ha7", "FOEnabled", replicas=1, failover=True)
        dep = _comp("ha8", "DepSvc2", replicas=2, failover=True)
        g = _graph(c, dep)
        g.add_dependency(Dependency(source_id="ha8", target_id="ha7"))
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        ha_plans = [
            p for p in report.plans if p.plan_id.startswith("HA-")
        ]
        assert len(ha_plans) == 0


# ===========================================================================
# 12. Topology: SPOF chains, autoscaling gaps
# ===========================================================================

class TestTopologyAnalysis:

    def test_spof_chain_detection(self):
        # comp depends on 2+ SPOFs (single-replica, no failover)
        main = _comp("t1", "MainApp", replicas=2, failover=True)
        spof1 = _comp("t2", "SPOF1", replicas=1)
        spof2 = _comp("t3", "SPOF2", replicas=1)
        g = _graph(main, spof1, spof2)
        g.add_dependency(Dependency(source_id="t1", target_id="t2"))
        g.add_dependency(Dependency(source_id="t1", target_id="t3"))
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        topo_plans = [
            p for p in report.plans if p.plan_id.startswith("TOPO-")
        ]
        assert len(topo_plans) >= 1
        spof_plan = topo_plans[0]
        assert spof_plan.priority == RemediationPriority.URGENT
        assert spof_plan.requires_approval
        assert len(spof_plan.steps) == 2
        for step in spof_plan.steps:
            assert step.action == RemediationAction.ADD_REPLICA
            assert step.parameters["target_replicas"] == 2
        assert "SPOF1" in spof_plan.issue_description
        assert "SPOF2" in spof_plan.issue_description

    def test_no_spof_chain_single_dep(self):
        main = _comp("ns1", "Main", replicas=2, failover=True)
        dep = _comp("ns2", "SingleDep", replicas=1)
        g = _graph(main, dep)
        g.add_dependency(Dependency(source_id="ns1", target_id="ns2"))
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        topo_plans = [
            p for p in report.plans
            if p.plan_id.startswith("TOPO-") and "SPOF" in p.issue_description
        ]
        assert len(topo_plans) == 0

    def test_autoscaling_gap_detection(self):
        # CPU > 60 and no autoscaling
        c = _comp("ag1", "NoAutoSrv", cpu=65.0, autoscaling=False,
                  failover=True, replicas=2)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        topo_plans = [
            p for p in report.plans
            if p.plan_id.startswith("TOPO-") and "autoscaling" in p.issue_description
        ]
        assert len(topo_plans) == 1
        plan = topo_plans[0]
        assert plan.priority == RemediationPriority.PLANNED
        assert not plan.requires_approval
        step = plan.steps[0]
        assert step.action == RemediationAction.ENABLE_AUTOSCALING
        assert step.parameters["min_replicas"] == 2
        assert step.parameters["max_replicas"] == 6  # replicas * 3
        assert step.parameters["target_cpu"] == 70

    def test_autoscaling_gap_not_triggered_below_60(self):
        c = _comp("ag2", "LowCPU", cpu=55.0, autoscaling=False,
                  failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        topo_plans = [
            p for p in report.plans
            if p.plan_id.startswith("TOPO-") and "autoscaling" in p.issue_description
        ]
        assert len(topo_plans) == 0

    def test_autoscaling_gap_not_triggered_with_autoscaling(self):
        c = _comp("ag3", "AutoSrv", cpu=65.0, autoscaling=True,
                  failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        topo_plans = [
            p for p in report.plans
            if p.plan_id.startswith("TOPO-") and "autoscaling" in p.issue_description
        ]
        assert len(topo_plans) == 0


# ===========================================================================
# 13. Execute plan: dry_run mode -> DRY-RUN results
# ===========================================================================

class TestExecutePlanDryRun:

    def test_dry_run_returns_dry_run_result(self):
        c = _comp("dr1", "DryComp", health=HealthStatus.DOWN, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=True)
        report = engine.analyze_and_plan()
        plan = [p for p in report.plans if "DOWN" in p.issue_description][0]
        executed = engine.execute_plan(plan)
        for step in executed.steps:
            assert step.execution_status == ExecutionStatus.COMPLETED
            assert "DRY-RUN" in step.execution_result
        assert len(engine._execution_log) > 0


# ===========================================================================
# 14. Execute plan: actual mode -> graph mutations
# ===========================================================================

class TestExecutePlanActual:

    def test_scale_up_modifies_replicas(self):
        c = _comp("ex1", "ScaleMe", health=HealthStatus.OVERLOADED,
                  replicas=2, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=False)
        report = engine.analyze_and_plan()
        plan = [p for p in report.plans if "OVERLOADED" in p.issue_description][0]
        engine.execute_plan(plan)
        comp = g.get_component("ex1")
        assert comp.replicas == 4  # max(3, 4)

    def test_restart_resets_health(self):
        c = _comp("ex2", "RestartMe", health=HealthStatus.DOWN, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=False)
        report = engine.analyze_and_plan()
        plan = [p for p in report.plans if "DOWN" in p.issue_description][0]
        engine.execute_plan(plan)
        comp = g.get_component("ex2")
        assert comp.health == HealthStatus.HEALTHY

    def test_enable_failover(self):
        target = _comp("ex3", "NoFO", replicas=1)
        dep1 = _comp("dep_ex3_1", "DepA", replicas=2, failover=True)
        dep2 = _comp("dep_ex3_2", "DepB", replicas=2, failover=True)
        dep3 = _comp("dep_ex3_3", "DepC", replicas=2, failover=True)
        g = _graph(target, dep1, dep2, dep3)
        for d in [dep1, dep2, dep3]:
            g.add_dependency(Dependency(source_id=d.id, target_id="ex3"))
        engine = RemediationEngine(g, dry_run=False)
        report = engine.analyze_and_plan()
        ha_plans = [p for p in report.plans if p.plan_id.startswith("HA-")]
        assert len(ha_plans) == 1
        engine.execute_plan(ha_plans[0])
        comp = g.get_component("ex3")
        assert comp.failover.enabled
        assert comp.replicas == 2

    def test_enable_backup(self):
        c = _comp("ex4", "NoBkDB", ctype=ComponentType.DATABASE,
                  backup=False, encryption=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=False)
        report = engine.analyze_and_plan()
        bk_plans = [p for p in report.plans if "backup" in p.issue_description]
        engine.execute_plan(bk_plans[0])
        comp = g.get_component("ex4")
        assert comp.security.backup_enabled

    def test_enable_encryption(self):
        c = _comp("ex5", "NoEncDB", ctype=ComponentType.DATABASE,
                  encryption=False, backup=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=False)
        report = engine.analyze_and_plan()
        enc_plans = [p for p in report.plans if "encryption" in p.issue_description]
        # This plan requires_approval, so it will be skipped by execute_plan
        # Test the raw _execute_step instead
        plan = enc_plans[0]
        # Override requires_approval for testing actual execution
        plan.requires_approval = False
        engine.execute_plan(plan)
        comp = g.get_component("ex5")
        assert comp.security.encryption_at_rest

    def test_enable_autoscaling(self):
        c = _comp("ex6", "NoAuto", cpu=65.0, autoscaling=False,
                  failover=True, replicas=2)
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=False)
        report = engine.analyze_and_plan()
        topo_plans = [
            p for p in report.plans
            if p.plan_id.startswith("TOPO-") and "autoscaling" in p.issue_description
        ]
        engine.execute_plan(topo_plans[0])
        comp = g.get_component("ex6")
        assert comp.autoscaling.enabled


# ===========================================================================
# 15. Execute plan: requires_approval -> skipped
# ===========================================================================

class TestRequiresApproval:

    def test_approval_required_skips(self):
        c = _comp("ap1", "ApprDB", ctype=ComponentType.DATABASE,
                  encryption=False, backup=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        enc_plans = [
            p for p in report.plans if "encryption" in p.issue_description
        ]
        plan = enc_plans[0]
        assert plan.requires_approval
        executed = engine.execute_plan(plan)
        for step in executed.steps:
            assert step.execution_status == ExecutionStatus.SKIPPED
            assert "approval" in step.execution_result.lower()
        assert any("Skipped" in log for log in engine._execution_log)

    def test_approval_skips_only_pending_steps(self):
        plan = RemediationPlan(
            plan_id="TEST-001",
            issue_description="test",
            priority=RemediationPriority.PLANNED,
            steps=[
                RemediationStep(
                    step_number=1,
                    action=RemediationAction.ENABLE_ENCRYPTION,
                    component_id="x",
                    component_name="X",
                    description="test",
                    parameters={},
                    estimated_impact="test",
                    rollback_action="test",
                    risk_level="low",
                    execution_status=ExecutionStatus.COMPLETED,
                    execution_result="Already done",
                ),
                RemediationStep(
                    step_number=2,
                    action=RemediationAction.ENABLE_BACKUP,
                    component_id="x",
                    component_name="X",
                    description="test",
                    parameters={},
                    estimated_impact="test",
                    rollback_action="test",
                    risk_level="low",
                ),
            ],
            estimated_duration_minutes=10,
            requires_approval=True,
            rollback_plan=[],
            affected_components=["x"],
        )
        g = InfraGraph()
        engine = RemediationEngine(g)
        engine.execute_plan(plan)
        assert plan.steps[0].execution_status == ExecutionStatus.COMPLETED
        assert plan.steps[1].execution_status == ExecutionStatus.SKIPPED


# ===========================================================================
# 16. Execute plan: step failure -> rollback
# ===========================================================================

class TestExecutionFailureRollback:

    def test_failure_triggers_rollback(self):
        # First step succeeds on a valid component, second step fails on invalid
        c = _comp("fb1", "ValidComp")
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=False)
        plan = RemediationPlan(
            plan_id="FAIL-001",
            issue_description="test failure",
            priority=RemediationPriority.IMMEDIATE,
            steps=[
                RemediationStep(
                    step_number=1,
                    action=RemediationAction.ADD_REPLICA,
                    component_id="fb1",
                    component_name="ValidComp",
                    description="Scale up",
                    parameters={"target_replicas": 3},
                    estimated_impact="test",
                    rollback_action="Remove replica",
                    risk_level="low",
                ),
                RemediationStep(
                    step_number=2,
                    action=RemediationAction.ADD_REPLICA,
                    component_id="nonexistent",
                    component_name="Ghost",
                    description="This will fail",
                    parameters={"target_replicas": 2},
                    estimated_impact="test",
                    rollback_action="Nothing",
                    risk_level="low",
                ),
            ],
            estimated_duration_minutes=5,
            requires_approval=False,
            rollback_plan=["Rollback all"],
            affected_components=["fb1"],
        )
        engine.execute_plan(plan)
        assert plan.steps[0].execution_status == ExecutionStatus.ROLLED_BACK
        assert "[ROLLED BACK]" in plan.steps[0].execution_result
        assert plan.steps[1].execution_status == ExecutionStatus.FAILED
        assert any("FAILED" in log for log in engine._execution_log)
        assert any("Rolled back" in log for log in engine._execution_log)

    def test_failure_does_not_rollback_later_steps(self):
        # Steps after the failed step should remain PENDING (break on failure)
        c = _comp("fb2", "Comp2")
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=False)
        plan = RemediationPlan(
            plan_id="FAIL-002",
            issue_description="test",
            priority=RemediationPriority.IMMEDIATE,
            steps=[
                RemediationStep(
                    step_number=1,
                    action=RemediationAction.ADD_REPLICA,
                    component_id="nonexistent",
                    component_name="Ghost",
                    description="Fails first",
                    parameters={},
                    estimated_impact="",
                    rollback_action="",
                    risk_level="low",
                ),
                RemediationStep(
                    step_number=2,
                    action=RemediationAction.ADD_REPLICA,
                    component_id="fb2",
                    component_name="Comp2",
                    description="Never reached",
                    parameters={},
                    estimated_impact="",
                    rollback_action="",
                    risk_level="low",
                ),
            ],
            estimated_duration_minutes=5,
            requires_approval=False,
            rollback_plan=[],
            affected_components=["fb2"],
        )
        engine.execute_plan(plan)
        assert plan.steps[0].execution_status == ExecutionStatus.FAILED
        # Step 2 was never started, stays PENDING (loop breaks before it)
        assert plan.steps[1].execution_status == ExecutionStatus.PENDING


# ===========================================================================
# 17. Execute all plans
# ===========================================================================

class TestExecuteAll:

    def test_execute_all_processes_all_plans(self):
        c1 = _comp("ea1", "DownSrv", health=HealthStatus.DOWN, failover=True)
        c2 = _comp("ea2", "OverSrv", health=HealthStatus.OVERLOADED,
                    replicas=2, failover=True)
        g = _graph(c1, c2)
        engine = RemediationEngine(g, dry_run=True)
        report = engine.analyze_and_plan()
        assert report.total_issues_found >= 2
        updated_report = engine.execute_all(report)
        assert len(updated_report.execution_log) > 0
        for plan in updated_report.plans:
            for step in plan.steps:
                assert step.execution_status in (
                    ExecutionStatus.COMPLETED,
                    ExecutionStatus.SKIPPED,
                )


# ===========================================================================
# 18. Risk summary generation
# ===========================================================================

class TestRiskSummary:

    def test_risk_summary_empty(self):
        result = RemediationEngine._build_risk_summary([])
        assert "healthy" in result.lower()

    def test_risk_summary_with_immediate(self):
        plans = [
            RemediationPlan(
                plan_id="R1", issue_description="t",
                priority=RemediationPriority.IMMEDIATE,
                steps=[], estimated_duration_minutes=5,
                requires_approval=False, rollback_plan=[],
                affected_components=[],
            )
        ]
        result = RemediationEngine._build_risk_summary(plans)
        assert "IMMEDIATE" in result
        assert "P0" in result
        assert "1 issues" in result or "1 issue" in result

    def test_risk_summary_with_all_priorities(self):
        plans = []
        for p in [
            RemediationPriority.IMMEDIATE,
            RemediationPriority.URGENT,
            RemediationPriority.PLANNED,
            RemediationPriority.ADVISORY,
        ]:
            plans.append(
                RemediationPlan(
                    plan_id=f"R-{p.value}", issue_description="t",
                    priority=p, steps=[],
                    estimated_duration_minutes=5,
                    requires_approval=False, rollback_plan=[],
                    affected_components=[],
                )
            )
        result = RemediationEngine._build_risk_summary(plans)
        assert "IMMEDIATE" in result
        assert "URGENT" in result
        assert "PLANNED" in result
        assert "ADVISORY" in result
        assert "P0" in result
        assert "P1" in result
        assert "P2" in result
        assert "P3" in result
        assert "4 issues" in result

    def test_risk_summary_only_urgent(self):
        plans = [
            RemediationPlan(
                plan_id="U1", issue_description="t",
                priority=RemediationPriority.URGENT,
                steps=[], estimated_duration_minutes=5,
                requires_approval=False, rollback_plan=[],
                affected_components=[],
            )
        ]
        result = RemediationEngine._build_risk_summary(plans)
        assert "URGENT" in result
        assert "IMMEDIATE" not in result


# ===========================================================================
# 19. Priority ordering in report
# ===========================================================================

class TestPriorityOrdering:

    def test_plans_sorted_by_priority(self):
        c1 = _comp("po1", "CritCPU", cpu=95.0, failover=True)
        c2 = _comp("po2", "EncDB", ctype=ComponentType.DATABASE,
                    encryption=False, backup=True, failover=True)
        g = _graph(c1, c2)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        priorities = [p.priority for p in report.plans]
        priority_order = {
            RemediationPriority.IMMEDIATE: 0,
            RemediationPriority.URGENT: 1,
            RemediationPriority.PLANNED: 2,
            RemediationPriority.ADVISORY: 3,
        }
        sorted_priorities = sorted(
            priorities, key=lambda p: priority_order.get(p, 99)
        )
        assert priorities == sorted_priorities


# ===========================================================================
# 20. All RemediationAction match branches in _execute_step
# ===========================================================================

class TestAllExecuteStepBranches:

    def _make_step(self, action, component_id="x1", params=None):
        return RemediationStep(
            step_number=1,
            action=action,
            component_id=component_id,
            component_name="TestComp",
            description="test",
            parameters=params or {},
            estimated_impact="test",
            rollback_action="test",
            risk_level="low",
        )

    def _make_engine(self, dry_run=False):
        c = _comp("x1", "TestComp")
        g = _graph(c)
        return RemediationEngine(g, dry_run=dry_run), g

    def test_add_replica(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ADD_REPLICA,
                               params={"target_replicas": 5})
        result = engine._execute_step(step)
        assert g.get_component("x1").replicas == 5
        assert "5 replicas" in result

    def test_add_replica_default(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ADD_REPLICA, params={})
        result = engine._execute_step(step)
        assert g.get_component("x1").replicas == 2  # 1 + 1

    def test_scale_up(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.SCALE_UP,
                               params={"target_replicas": 4})
        result = engine._execute_step(step)
        assert g.get_component("x1").replicas == 4
        assert "Scaled" in result

    def test_remove_replica(self):
        engine, g = self._make_engine()
        comp = g.get_component("x1")
        comp.replicas = 3
        step = self._make_step(RemediationAction.REMOVE_REPLICA,
                               params={"target_replicas": 2})
        result = engine._execute_step(step)
        assert comp.replicas == 2
        assert "down to 2" in result

    def test_remove_replica_default(self):
        engine, g = self._make_engine()
        comp = g.get_component("x1")
        comp.replicas = 3
        step = self._make_step(RemediationAction.REMOVE_REPLICA, params={})
        result = engine._execute_step(step)
        assert comp.replicas == 2  # max(1, 3-1)

    def test_remove_replica_minimum_1(self):
        engine, g = self._make_engine()
        comp = g.get_component("x1")
        comp.replicas = 1
        step = self._make_step(RemediationAction.REMOVE_REPLICA, params={})
        result = engine._execute_step(step)
        assert comp.replicas == 1  # max(1, 1-1) = 1

    def test_scale_down(self):
        engine, g = self._make_engine()
        comp = g.get_component("x1")
        comp.replicas = 5
        step = self._make_step(RemediationAction.SCALE_DOWN,
                               params={"target_replicas": 2})
        result = engine._execute_step(step)
        assert comp.replicas == 2
        assert "down to 2" in result

    def test_enable_failover(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ENABLE_FAILOVER,
                               params={"promotion_time_seconds": 15})
        result = engine._execute_step(step)
        comp = g.get_component("x1")
        assert comp.failover.enabled
        assert comp.failover.promotion_time_seconds == 15
        assert "promotion: 15s" in result

    def test_enable_failover_default_promo(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ENABLE_FAILOVER, params={})
        result = engine._execute_step(step)
        comp = g.get_component("x1")
        assert comp.failover.enabled
        assert comp.failover.promotion_time_seconds == 30
        assert "promotion: 30s" in result

    def test_enable_autoscaling(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ENABLE_AUTOSCALING,
                               params={"min_replicas": 2, "max_replicas": 8})
        result = engine._execute_step(step)
        comp = g.get_component("x1")
        assert comp.autoscaling.enabled
        assert comp.autoscaling.min_replicas == 2
        assert comp.autoscaling.max_replicas == 8
        assert "autoscaling" in result.lower()

    def test_enable_autoscaling_defaults(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ENABLE_AUTOSCALING, params={})
        result = engine._execute_step(step)
        comp = g.get_component("x1")
        assert comp.autoscaling.enabled
        assert comp.autoscaling.min_replicas == 1
        assert comp.autoscaling.max_replicas == 10

    def test_enable_backup(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ENABLE_BACKUP)
        result = engine._execute_step(step)
        assert g.get_component("x1").security.backup_enabled
        assert "backup" in result.lower()

    def test_enable_encryption(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ENABLE_ENCRYPTION)
        result = engine._execute_step(step)
        assert g.get_component("x1").security.encryption_at_rest
        assert "encryption" in result.lower()

    def test_restart_component(self):
        engine, g = self._make_engine()
        comp = g.get_component("x1")
        comp.health = HealthStatus.DOWN
        step = self._make_step(RemediationAction.RESTART_COMPONENT)
        result = engine._execute_step(step)
        assert comp.health == HealthStatus.HEALTHY
        assert "HEALTHY" in result

    def test_enable_rate_limiting(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ENABLE_RATE_LIMITING)
        result = engine._execute_step(step)
        assert "rate limiting" in result.lower()

    def test_enable_circuit_breaker(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ENABLE_CIRCUIT_BREAKER)
        result = engine._execute_step(step)
        assert "circuit breaker" in result.lower()

    def test_drain_and_replace(self):
        engine, g = self._make_engine()
        comp = g.get_component("x1")
        comp.health = HealthStatus.DOWN
        step = self._make_step(RemediationAction.DRAIN_AND_REPLACE)
        result = engine._execute_step(step)
        assert comp.health == HealthStatus.HEALTHY
        assert "replaced" in result.lower()

    def test_rebalance_load(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.REBALANCE_LOAD)
        result = engine._execute_step(step)
        assert "rebalanced" in result.lower()

    def test_quarantine(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.QUARANTINE)
        result = engine._execute_step(step)
        assert g.get_component("x1").health == HealthStatus.DOWN
        assert "quarantined" in result.lower()

    def test_increase_timeout(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.INCREASE_TIMEOUT,
                               params={"timeout_seconds": 120})
        result = engine._execute_step(step)
        assert g.get_component("x1").capacity.timeout_seconds == 120
        assert "120s" in result

    def test_increase_timeout_default_doubles(self):
        engine, g = self._make_engine()
        comp = g.get_component("x1")
        original = comp.capacity.timeout_seconds
        step = self._make_step(RemediationAction.INCREASE_TIMEOUT, params={})
        result = engine._execute_step(step)
        assert comp.capacity.timeout_seconds == original * 2

    def test_component_not_found_raises(self):
        engine, g = self._make_engine()
        step = self._make_step(RemediationAction.ADD_REPLICA,
                               component_id="missing")
        with pytest.raises(ValueError, match="not found"):
            engine._execute_step(step)

    def test_dry_run_all_actions(self):
        engine, g = self._make_engine(dry_run=True)
        for action in RemediationAction:
            step = self._make_step(action)
            result = engine._execute_step(step)
            assert "DRY-RUN" in result


# ===========================================================================
# 21. Edge cases: 0 connections, DB with encryption already enabled, etc.
# ===========================================================================

class TestEdgeCases:

    def test_db_with_all_security_enabled(self):
        c = _comp("ec1", "SecureDB", ctype=ComponentType.DATABASE,
                  encryption=True, backup=True, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        sec_plans = [
            p for p in report.plans
            if p.plan_id.startswith("SEC-")
        ]
        assert len(sec_plans) == 0

    def test_multiple_issues_same_component(self):
        c = _comp("ec2", "MultiIssue", cpu=95.0, memory=92.0, disk=95.0,
                  health=HealthStatus.DOWN, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        assert report.total_issues_found >= 4  # DOWN + CPU + Memory + Disk

    def test_report_counts(self):
        c1 = _comp("ec3", "AppSrv", health=HealthStatus.DOWN, failover=True)
        c2 = _comp("ec4", "DB", ctype=ComponentType.DATABASE,
                   encryption=False, failover=True)  # requires_approval = True
        g = _graph(c1, c2)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        assert report.auto_remediable_count + report.manual_required_count == report.total_issues_found
        assert report.estimated_total_duration_minutes > 0

    def test_plan_counter_increments(self):
        c1 = _comp("pc1", "A", health=HealthStatus.DOWN, failover=True)
        c2 = _comp("pc2", "B", health=HealthStatus.DOWN, failover=True)
        g = _graph(c1, c2)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        ids = [p.plan_id for p in report.plans]
        assert len(ids) == len(set(ids))  # all unique

    def test_created_at_auto_populated(self):
        c = _comp("ca1", "TimeComp", health=HealthStatus.DOWN, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        for plan in report.plans:
            assert plan.created_at  # not empty

    def test_degraded_health_no_down_plan(self):
        c = _comp("dg1", "Degraded", health=HealthStatus.DEGRADED,
                  failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        down_plans = [
            p for p in report.plans if "DOWN" in p.issue_description
        ]
        assert len(down_plans) == 0

    def test_connection_ratio_boundary_exactly_at_threshold(self):
        # ratio = 900/1000 = 0.9 exactly = CONNECTION_CRITICAL
        c = _comp("bd1", "ExactCrit", max_connections=1000,
                  network_connections=900, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        conn_plans = [
            p for p in report.plans if "connections" in p.issue_description
        ]
        assert len(conn_plans) == 1
        assert "critical" in conn_plans[0].issue_description

    def test_connection_ratio_exactly_at_high_threshold(self):
        # ratio = 700/1000 = 0.7 exactly = CONNECTION_HIGH
        c = _comp("bd2", "ExactHigh", max_connections=1000,
                  network_connections=700, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        conn_plans = [
            p for p in report.plans if "connections" in p.issue_description
        ]
        assert len(conn_plans) == 1
        assert "high" in conn_plans[0].issue_description

    def test_cpu_exactly_at_critical_boundary(self):
        c = _comp("bd3", "CPU90", cpu=90.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        cpu_plans = [
            p for p in report.plans if "CPU" in p.issue_description
        ]
        assert len(cpu_plans) >= 1
        assert "critical" in cpu_plans[0].issue_description

    def test_cpu_exactly_at_high_boundary(self):
        c = _comp("bd4", "CPU75", cpu=75.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        cpu_plans = [
            p for p in report.plans if "CPU" in p.issue_description
        ]
        assert len(cpu_plans) >= 1
        assert "high" in cpu_plans[0].issue_description

    def test_memory_exactly_at_critical_boundary(self):
        c = _comp("bd5", "Mem90", memory=90.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        mem_plans = [
            p for p in report.plans if "memory" in p.issue_description
        ]
        assert len(mem_plans) >= 1
        assert "critical" in mem_plans[0].issue_description

    def test_memory_exactly_at_high_boundary(self):
        c = _comp("bd6", "Mem80", memory=80.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        mem_plans = [
            p for p in report.plans if "memory" in p.issue_description
        ]
        assert len(mem_plans) >= 1
        assert "high" in mem_plans[0].issue_description

    def test_disk_exactly_at_critical_boundary(self):
        c = _comp("bd7", "Disk90", disk=90.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        disk_plans = [
            p for p in report.plans if "disk" in p.issue_description
        ]
        assert len(disk_plans) >= 1
        assert "critical" in disk_plans[0].issue_description

    def test_disk_exactly_at_high_boundary(self):
        c = _comp("bd8", "Disk75", disk=75.0, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        disk_plans = [
            p for p in report.plans if "disk" in p.issue_description
        ]
        assert len(disk_plans) >= 1
        assert "high" in disk_plans[0].issue_description


# ===========================================================================
# Additional: Rollback edge cases and enum values
# ===========================================================================

class TestRollbackEdgeCases:

    def test_rollback_only_completed_prior_steps(self):
        c = _comp("rb1", "Comp1")
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=False)

        plan = RemediationPlan(
            plan_id="RB-001",
            issue_description="test rollback",
            priority=RemediationPriority.IMMEDIATE,
            steps=[
                RemediationStep(
                    step_number=1,
                    action=RemediationAction.ADD_REPLICA,
                    component_id="rb1",
                    component_name="Comp1",
                    description="First",
                    parameters={"target_replicas": 3},
                    estimated_impact="",
                    rollback_action="Scale down",
                    risk_level="low",
                ),
                RemediationStep(
                    step_number=2,
                    action=RemediationAction.ADD_REPLICA,
                    component_id="rb1",
                    component_name="Comp1",
                    description="Second",
                    parameters={"target_replicas": 5},
                    estimated_impact="",
                    rollback_action="Scale down",
                    risk_level="low",
                ),
                RemediationStep(
                    step_number=3,
                    action=RemediationAction.ADD_REPLICA,
                    component_id="nonexistent",
                    component_name="Ghost",
                    description="Fails",
                    parameters={},
                    estimated_impact="",
                    rollback_action="",
                    risk_level="low",
                ),
            ],
            estimated_duration_minutes=5,
            requires_approval=False,
            rollback_plan=[],
            affected_components=["rb1"],
        )
        engine.execute_plan(plan)
        assert plan.steps[0].execution_status == ExecutionStatus.ROLLED_BACK
        assert plan.steps[1].execution_status == ExecutionStatus.ROLLED_BACK
        assert plan.steps[2].execution_status == ExecutionStatus.FAILED


class TestEnumValues:

    def test_remediation_action_values(self):
        assert RemediationAction.SCALE_UP.value == "scale_up"
        assert RemediationAction.QUARANTINE.value == "quarantine"

    def test_remediation_priority_values(self):
        assert RemediationPriority.IMMEDIATE.value == "immediate"
        assert RemediationPriority.ADVISORY.value == "advisory"

    def test_execution_status_values(self):
        assert ExecutionStatus.PENDING.value == "pending"
        assert ExecutionStatus.ROLLED_BACK.value == "rolled_back"
        assert ExecutionStatus.SKIPPED.value == "skipped"


class TestConnectionRemediationRatioCalc:
    """Test that connection ratio is computed correctly in the plan description."""

    def test_connection_plan_ratio_in_description(self):
        c = _comp("cr1", "ConnSrv", max_connections=200,
                  network_connections=180, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        conn_plans = [
            p for p in report.plans if "connections" in p.issue_description
        ]
        plan = conn_plans[0]
        # 180/200 = 90%
        assert "90%" in plan.issue_description
        assert "90% capacity" in plan.steps[0].description


class TestTopologySpofChainEstimatedDuration:

    def test_spof_duration_proportional(self):
        main = _comp("sd1", "MainApp", replicas=2, failover=True)
        spofs = [
            _comp(f"sd{i+2}", f"SPOF{i}", replicas=1)
            for i in range(3)
        ]
        g = _graph(main, *spofs)
        for s in spofs:
            g.add_dependency(Dependency(source_id="sd1", target_id=s.id))
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        topo_plans = [
            p for p in report.plans
            if p.plan_id.startswith("TOPO-") and "SPOF" in p.issue_description
        ]
        assert len(topo_plans) == 1
        assert topo_plans[0].estimated_duration_minutes == 15 * 3


class TestSpofChainAffectedComponents:

    def test_affected_components_include_main_and_spofs(self):
        main = _comp("ac1", "MainApp", replicas=2, failover=True)
        spof1 = _comp("ac2", "SPOF1", replicas=1)
        spof2 = _comp("ac3", "SPOF2", replicas=1)
        g = _graph(main, spof1, spof2)
        g.add_dependency(Dependency(source_id="ac1", target_id="ac2"))
        g.add_dependency(Dependency(source_id="ac1", target_id="ac3"))
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        # Filter for the TOPO plan with the specific SPOF chain description
        topo = [
            p for p in report.plans
            if p.plan_id.startswith("TOPO-") and "SPOFs" in p.issue_description
        ]
        assert len(topo) == 1
        assert "ac1" in topo[0].affected_components
        assert "ac2" in topo[0].affected_components
        assert "ac3" in topo[0].affected_components


class TestAutoscalingGapMultipleComponents:

    def test_multiple_components_single_plan(self):
        c1 = _comp("agm1", "Srv1", cpu=70.0, autoscaling=False,
                    failover=True, replicas=1)
        c2 = _comp("agm2", "Srv2", cpu=80.0, autoscaling=False,
                    failover=True, replicas=2)
        g = _graph(c1, c2)
        engine = RemediationEngine(g)
        report = engine.analyze_and_plan()
        topo_plans = [
            p for p in report.plans
            if p.plan_id.startswith("TOPO-") and "autoscaling" in p.issue_description
        ]
        assert len(topo_plans) == 1
        plan = topo_plans[0]
        assert len(plan.steps) == 2
        assert plan.estimated_duration_minutes == 20
        assert "2 components" in plan.issue_description


class TestExecutionLog:

    def test_execution_log_records_all_steps(self):
        c = _comp("el1", "LogComp", health=HealthStatus.DOWN, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=True)
        report = engine.analyze_and_plan()
        plan = [p for p in report.plans if "DOWN" in p.issue_description][0]
        engine.execute_plan(plan)
        # 2 steps in restart/replace plan
        log_entries = [l for l in engine._execution_log if plan.plan_id in l]
        assert len(log_entries) == 2

    def test_execution_log_in_report_after_execute_all(self):
        c = _comp("el2", "Comp", health=HealthStatus.DOWN, failover=True)
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=True)
        report = engine.analyze_and_plan()
        assert report.execution_log == []
        updated = engine.execute_all(report)
        assert len(updated.execution_log) > 0


class TestUnknownActionFallback:
    """Cover the unreachable 'Unknown action' return on line 962 using mock."""

    def test_unknown_action_returns_unknown_message(self):
        from unittest.mock import patch

        c = _comp("uk1", "Comp")
        g = _graph(c)
        engine = RemediationEngine(g, dry_run=False)

        # Create a step with a valid action, but patch the action value
        # to something the if-chain won't match by using a novel Enum member
        step = RemediationStep(
            step_number=1,
            action=RemediationAction.ADD_REPLICA,
            component_id="uk1",
            component_name="Comp",
            description="test",
            parameters={},
            estimated_impact="",
            rollback_action="",
            risk_level="low",
        )
        # Patch the action attribute after creation to a mock that won't
        # match any of the if-branches
        import enum

        class FakeAction(str, enum.Enum):
            FAKE = "fake_action"

        step.action = FakeAction.FAKE
        result = engine._execute_step(step)
        assert "Unknown action" in result
        assert "fake_action" in result


class TestDataclassDefaults:

    def test_remediation_step_defaults(self):
        step = RemediationStep(
            step_number=1,
            action=RemediationAction.ADD_REPLICA,
            component_id="x",
            component_name="X",
            description="test",
            parameters={},
            estimated_impact="test",
            rollback_action="test",
            risk_level="low",
        )
        assert step.execution_status == ExecutionStatus.PENDING
        assert step.execution_result == ""

    def test_remediation_plan_created_at(self):
        plan = RemediationPlan(
            plan_id="T1",
            issue_description="t",
            priority=RemediationPriority.PLANNED,
            steps=[],
            estimated_duration_minutes=5,
            requires_approval=False,
            rollback_plan=[],
            affected_components=[],
        )
        assert plan.created_at is not None
        assert len(plan.created_at) > 0
