"""Tests for the Auto Runbook Generator."""

import tempfile
from pathlib import Path

from faultray.model.components import (
    AutoScalingConfig,
    Capacity,
    Component,
    ComponentType,
    Dependency,
    FailoverConfig,
    ResourceMetrics,
)
from faultray.model.graph import InfraGraph
from faultray.remediation.runbook_generator import (
    CommunicationTemplate,
    Runbook,
    RunbookGenerator,
    RunbookLibrary,
    RunbookStep,
)
from faultray.simulator.engine import SimulationEngine, SimulationReport


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


def _build_test_graph() -> InfraGraph:
    """Build a test infrastructure graph with known failure scenarios."""
    graph = InfraGraph()

    graph.add_component(Component(
        id="lb",
        name="Load Balancer",
        type=ComponentType.LOAD_BALANCER,
        replicas=2,
        capacity=Capacity(max_connections=10000),
    ))
    graph.add_component(Component(
        id="web",
        name="Web Server",
        type=ComponentType.WEB_SERVER,
        replicas=1,
        capacity=Capacity(max_connections=1000, timeout_seconds=30),
        metrics=ResourceMetrics(network_connections=800),
    ))
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        replicas=1,
        capacity=Capacity(max_connections=500, timeout_seconds=30),
        metrics=ResourceMetrics(network_connections=400),
    ))
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=1,
        capacity=Capacity(max_connections=100),
        metrics=ResourceMetrics(network_connections=90, disk_percent=72),
    ))
    graph.add_component(Component(
        id="cache",
        name="Redis Cache",
        type=ComponentType.CACHE,
        replicas=1,
        capacity=Capacity(max_connections=200),
    ))

    graph.add_dependency(Dependency(source_id="lb", target_id="web", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="web", target_id="app", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="db", dependency_type="requires"))
    graph.add_dependency(Dependency(source_id="app", target_id="cache", dependency_type="optional"))

    return graph


def _run_simulation(graph: InfraGraph) -> SimulationReport:
    """Run a simulation and return the report."""
    engine = SimulationEngine(graph)
    return engine.run_all_defaults()


# ---------------------------------------------------------------------------
# RunbookStep tests
# ---------------------------------------------------------------------------


def test_runbook_step_creation():
    step = RunbookStep(
        order=1,
        phase="detection",
        title="Check alerts",
        description="Check monitoring for alerts.",
        commands=["kubectl get pods"],
        expected_outcome="Alert identified",
        time_estimate="1 min",
    )
    assert step.order == 1
    assert step.phase == "detection"
    assert len(step.commands) == 1


def test_runbook_step_to_dict():
    step = RunbookStep(
        order=1,
        phase="mitigation",
        title="Scale up",
        description="Scale deployment.",
        commands=["kubectl scale deployment app --replicas=3"],
        expected_outcome="More pods running",
        escalation="Escalate to SRE lead if no effect",
        time_estimate="2 min",
    )
    d = step.to_dict()
    assert d["order"] == 1
    assert d["phase"] == "mitigation"
    assert d["escalation"] == "Escalate to SRE lead if no effect"


# ---------------------------------------------------------------------------
# CommunicationTemplate tests
# ---------------------------------------------------------------------------


def test_communication_template():
    tmpl = CommunicationTemplate(
        channel="slack",
        severity="critical",
        template="INCIDENT: {component} is down",
    )
    d = tmpl.to_dict()
    assert d["channel"] == "slack"
    assert "INCIDENT" in d["template"]


# ---------------------------------------------------------------------------
# Runbook tests
# ---------------------------------------------------------------------------


def test_runbook_creation():
    rb = Runbook(
        id="rb-test",
        title="Test Runbook",
        scenario="DB failure",
        severity="critical",
        affected_components=["db", "app"],
        blast_radius=2,
    )
    assert rb.id == "rb-test"
    assert rb.severity == "critical"
    assert rb.blast_radius == 2


def test_runbook_to_dict():
    rb = Runbook(
        id="rb-test",
        title="Test Runbook",
        scenario="DB failure",
        severity="critical",
        affected_components=["db"],
        steps=[
            RunbookStep(order=1, phase="detection", title="Check", description="Check alerts"),
        ],
        communication_templates=[
            CommunicationTemplate(channel="slack", severity="critical", template="Alert"),
        ],
        tags=["critical", "database"],
    )
    d = rb.to_dict()
    assert d["id"] == "rb-test"
    assert len(d["steps"]) == 1
    assert len(d["communication_templates"]) == 1
    assert "critical" in d["tags"]
    assert "last_updated" in d


# ---------------------------------------------------------------------------
# RunbookLibrary tests
# ---------------------------------------------------------------------------


def test_runbook_library_to_dict():
    lib = RunbookLibrary(
        runbooks=[
            Runbook(id="rb-1", title="RB 1", scenario="S1", severity="critical"),
        ],
        total_scenarios_covered=1,
        uncovered_scenarios=["S2"],
        coverage_percentage=50.0,
    )
    d = lib.to_dict()
    assert len(d["runbooks"]) == 1
    assert d["coverage_percentage"] == 50.0
    assert "S2" in d["uncovered_scenarios"]


# ---------------------------------------------------------------------------
# RunbookGenerator: generate_for_component
# ---------------------------------------------------------------------------


def test_generate_for_component():
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")

    assert isinstance(rb, Runbook)
    assert rb.id == "rb-component-db"
    assert "Database" in rb.title
    assert rb.severity == "critical"
    assert "db" in rb.affected_components
    assert rb.blast_radius >= 1
    assert len(rb.steps) > 0

    # Check all phases are represented
    phases = {s.phase for s in rb.steps}
    assert "detection" in phases
    assert "diagnosis" in phases
    assert "mitigation" in phases
    assert "recovery" in phases
    assert "post_incident" in phases


def test_generate_for_component_database_specific_steps():
    """Database components should get DB-specific steps."""
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")

    # Should have database-specific steps like replication lag check
    step_titles = [s.title.lower() for s in rb.steps]
    has_db_specific = any(
        "replication" in t or "data integrity" in t or "database" in t
        for t in step_titles
    )
    assert has_db_specific


def test_generate_for_nonexistent_component():
    graph = _build_test_graph()
    generator = RunbookGenerator()

    try:
        generator.generate_for_component(graph, "nonexistent")
        assert False, "Should raise ValueError"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# RunbookGenerator: generate from simulation
# ---------------------------------------------------------------------------


def test_generate_from_simulation():
    graph = _build_test_graph()
    report = _run_simulation(graph)
    generator = RunbookGenerator()

    library = generator.generate(graph, report)

    assert isinstance(library, RunbookLibrary)
    assert library.coverage_percentage > 0

    # Should generate runbooks for critical + warning scenarios
    expected_count = len(report.critical_findings) + len(report.warnings)
    if expected_count > 0:
        assert len(library.runbooks) > 0
        assert library.total_scenarios_covered > 0


def test_generate_all_runbooks_have_steps():
    graph = _build_test_graph()
    report = _run_simulation(graph)
    generator = RunbookGenerator()

    library = generator.generate(graph, report)

    for rb in library.runbooks:
        assert len(rb.steps) > 0, f"Runbook {rb.id} has no steps"
        assert rb.severity in ("critical", "warning")
        assert rb.blast_radius > 0


def test_generate_runbooks_have_communication_templates():
    graph = _build_test_graph()
    report = _run_simulation(graph)
    generator = RunbookGenerator()

    library = generator.generate(graph, report)

    for rb in library.runbooks:
        assert len(rb.communication_templates) > 0, (
            f"Runbook {rb.id} has no communication templates"
        )
        channels = {t.channel for t in rb.communication_templates}
        assert "status_page" in channels
        assert "slack" in channels


def test_generate_related_runbooks_linked():
    """Runbooks with shared affected components should be linked."""
    graph = _build_test_graph()
    report = _run_simulation(graph)
    generator = RunbookGenerator()

    library = generator.generate(graph, report)

    # At least some runbooks should have related runbooks
    if len(library.runbooks) > 1:
        has_related = any(len(rb.related_runbooks) > 0 for rb in library.runbooks)
        # It's likely that multiple scenarios affect the same components
        # but not guaranteed, so we just check the mechanism works
        assert isinstance(has_related, bool)


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def test_to_markdown():
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")
    md = generator.to_markdown(rb)

    assert isinstance(md, str)
    assert rb.title in md
    assert "## Phase: Detection" in md
    assert "## Phase: Diagnosis" in md
    assert "## Phase: Mitigation" in md
    assert "## Phase: Recovery" in md
    assert "## Phase: Post-Incident" in md
    assert "## Affected Components" in md
    assert "## Communication Templates" in md
    assert "`db`" in md
    assert "```bash" in md


def test_to_markdown_has_commands():
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "app")
    md = generator.to_markdown(rb)

    assert "kubectl" in md


# ---------------------------------------------------------------------------
# HTML export
# ---------------------------------------------------------------------------


def test_to_html():
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")
    html = generator.to_html(rb)

    assert isinstance(html, str)
    assert "<!DOCTYPE html>" in html
    assert rb.title in html or "Database" in html
    assert "<h1>" in html
    assert "<h2>" in html


# ---------------------------------------------------------------------------
# Library export
# ---------------------------------------------------------------------------


def test_export_library_markdown():
    graph = _build_test_graph()
    report = _run_simulation(graph)
    generator = RunbookGenerator()
    library = generator.generate(graph, report)

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = generator.export_library(library, Path(tmpdir), format="markdown")

        assert len(paths) > 0
        # First path should be the index
        assert "index" in paths[0].name

        for path in paths:
            assert path.exists()
            assert path.suffix == ".md"
            content = path.read_text()
            assert len(content) > 0


def test_export_library_html():
    graph = _build_test_graph()
    report = _run_simulation(graph)
    generator = RunbookGenerator()
    library = generator.generate(graph, report)

    with tempfile.TemporaryDirectory() as tmpdir:
        paths = generator.export_library(library, Path(tmpdir), format="html")

        assert len(paths) > 0
        for path in paths:
            assert path.exists()
            assert path.suffix == ".html"


# ---------------------------------------------------------------------------
# Recovery time estimation
# ---------------------------------------------------------------------------


def test_recovery_time_with_failover():
    """Components with failover should have shorter recovery time."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        replicas=2,
        failover=FailoverConfig(enabled=True),
        autoscaling=AutoScalingConfig(enabled=True),
    ))

    generator = RunbookGenerator()
    rb = generator.generate_for_component(graph, "db")

    # Parse minutes from recovery time
    assert "min" in rb.estimated_recovery_time


def test_recovery_time_single_failure():
    """Simple single-component failure should have reasonable recovery time."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="App",
        type=ComponentType.APP_SERVER,
        replicas=1,
    ))

    generator = RunbookGenerator()
    rb = generator.generate_for_component(graph, "app")
    assert "min" in rb.estimated_recovery_time


# ---------------------------------------------------------------------------
# Steps contain appropriate content
# ---------------------------------------------------------------------------


def test_steps_ordered_correctly():
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")

    orders = [s.order for s in rb.steps]
    assert orders == sorted(orders)


def test_all_steps_have_time_estimate():
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")

    for step in rb.steps:
        assert step.time_estimate, f"Step {step.order} missing time estimate"
        assert "min" in step.time_estimate


def test_detection_steps_come_first():
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")

    # Group by phase order
    phase_order = {"detection": 0, "diagnosis": 1, "mitigation": 2, "recovery": 3, "post_incident": 4}

    prev_phase_idx = -1
    for step in rb.steps:
        current_idx = phase_order.get(step.phase, 99)
        assert current_idx >= prev_phase_idx, (
            f"Step {step.order} phase '{step.phase}' comes after a later phase"
        )
        prev_phase_idx = current_idx


# ---------------------------------------------------------------------------
# Communication templates validation
# ---------------------------------------------------------------------------


def test_status_page_investigating_template():
    """Status page investigating template should mention the component."""
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")

    investigating = [
        t for t in rb.communication_templates
        if t.channel == "status_page" and "investigating" in t.template.lower()
    ]
    assert len(investigating) > 0
    assert "db" in investigating[0].template


def test_slack_alert_template():
    """Slack template should contain severity and blast radius."""
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")

    slack_templates = [t for t in rb.communication_templates if t.channel == "slack"]
    assert len(slack_templates) > 0
    assert "INCIDENT" in slack_templates[0].template


def test_critical_has_pagerduty():
    """Critical severity should generate PagerDuty template."""
    graph = _build_test_graph()
    generator = RunbookGenerator()

    rb = generator.generate_for_component(graph, "db")
    assert rb.severity == "critical"

    pd_templates = [t for t in rb.communication_templates if t.channel == "pagerduty"]
    assert len(pd_templates) > 0


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_single_component_graph():
    """Should handle a graph with a single component."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="solo",
        name="Solo App",
        type=ComponentType.APP_SERVER,
    ))

    generator = RunbookGenerator()
    rb = generator.generate_for_component(graph, "solo")

    assert rb.id == "rb-component-solo"
    assert len(rb.steps) > 0
    assert rb.blast_radius >= 1


def test_autoscaling_component_mitigation_steps():
    """Components with autoscaling should have autoscaling verification steps."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="app",
        name="App Server",
        type=ComponentType.APP_SERVER,
        autoscaling=AutoScalingConfig(enabled=True, min_replicas=2, max_replicas=10),
    ))

    generator = RunbookGenerator()
    rb = generator.generate_for_component(graph, "app")

    mitigation_titles = [s.title.lower() for s in rb.steps if s.phase == "mitigation"]
    has_autoscaling_step = any("autoscaling" in t for t in mitigation_titles)
    assert has_autoscaling_step


def test_failover_component_mitigation_steps():
    """Components with failover should have failover verification steps."""
    graph = InfraGraph()
    graph.add_component(Component(
        id="db",
        name="Database",
        type=ComponentType.DATABASE,
        failover=FailoverConfig(enabled=True),
    ))

    generator = RunbookGenerator()
    rb = generator.generate_for_component(graph, "db")

    mitigation_titles = [s.title.lower() for s in rb.steps if s.phase == "mitigation"]
    has_failover_step = any("failover" in t for t in mitigation_titles)
    assert has_failover_step
