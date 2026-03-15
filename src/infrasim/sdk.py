"""FaultZero Python SDK - Simple, developer-friendly API.

The SDK provides a clean, high-level interface for integrating FaultZero
into existing tools, CI/CD pipelines, and custom applications.

Example usage:
    from infrasim import FaultZero

    fz = FaultZero("infrastructure.yaml")

    # Quick resilience check
    score = fz.resilience_score
    print(f"Score: {score}/100")

    # Run simulation
    report = fz.simulate()
    for finding in report.critical_findings:
        print(f"CRITICAL: {finding.scenario.name}")

    # Check SLA
    sla = fz.validate_sla(target_nines=4.0)
    print(f"SLA achievable: {sla.achievable}")

    # Get genome
    genome = fz.genome()
    print(f"Grade: {genome.resilience_grade}")

    # Compare environments
    diff = FaultZero.compare("prod.yaml", "staging.yaml")
    print(f"Parity: {diff.parity_score}%")

    # Natural language
    fz2 = FaultZero.from_text("3 web servers behind ALB with Aurora and Redis")
    print(fz2.resilience_score)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class FaultZero:
    """Main SDK entry point for FaultZero infrastructure analysis.

    Provides a clean, high-level API wrapping the various analysis engines,
    reporters, and exporters in a single unified interface.
    """

    def __init__(
        self,
        yaml_path: str | Path | None = None,
        graph: "InfraGraph | None" = None,
    ) -> None:
        """Initialize from a YAML file or an existing InfraGraph.

        Args:
            yaml_path: Path to an infrastructure YAML definition file.
            graph: A pre-built InfraGraph instance. If both ``yaml_path``
                and ``graph`` are provided, the graph takes precedence.

        Raises:
            ValueError: If neither ``yaml_path`` nor ``graph`` is provided.
        """
        from infrasim.model.graph import InfraGraph

        if graph is not None:
            self._graph = graph
        elif yaml_path is not None:
            from infrasim.model.loader import load_yaml

            self._graph = load_yaml(yaml_path)
        else:
            raise ValueError(
                "FaultZero requires either a yaml_path or a graph argument."
            )

        self._yaml_path = str(yaml_path) if yaml_path else None

    # ------------------------------------------------------------------
    # Class-level factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_text(cls, description: str) -> "FaultZero":
        """Create a FaultZero instance from a natural language description.

        Uses rule-based NLP to parse component descriptions. Supports
        English and Japanese input without any external API dependency.

        Args:
            description: Plain-text description such as
                ``"3 web servers behind ALB with Aurora and Redis"``.

        Returns:
            A new ``FaultZero`` instance backed by the parsed infrastructure.
        """
        from infrasim.ai.nl_to_infra import NLInfraParser

        parser = NLInfraParser()
        parsed = parser.parse(description)
        graph = parser.to_graph(parsed)
        instance = cls(graph=graph)
        instance._yaml_path = None
        return instance

    @classmethod
    def from_dict(cls, data: dict) -> "FaultZero":
        """Create a FaultZero instance from a dictionary.

        The dictionary should follow the standard FaultZero model format
        with ``components`` and ``dependencies`` keys.

        Args:
            data: Dictionary matching the FaultZero YAML/JSON schema.

        Returns:
            A new ``FaultZero`` instance.
        """
        from infrasim.model.components import Component, Dependency
        from infrasim.model.graph import InfraGraph

        graph = InfraGraph()
        for c in data.get("components", []):
            graph.add_component(Component(**c))
        for d in data.get("dependencies", []):
            graph.add_dependency(Dependency(**d))
        return cls(graph=graph)

    @classmethod
    def demo(cls) -> "FaultZero":
        """Create a FaultZero instance with the built-in demo infrastructure.

        The demo stack includes nginx LB, two app servers, PostgreSQL,
        Redis cache, and RabbitMQ -- a realistic web application topology.

        Returns:
            A new ``FaultZero`` instance with demo infrastructure loaded.
        """
        from infrasim.model.demo import create_demo_graph

        return cls(graph=create_demo_graph())

    @classmethod
    def compare(cls, *yaml_paths: str) -> "ComparisonMatrix":
        """Compare multiple infrastructure YAML files.

        Args:
            *yaml_paths: Two or more paths to infrastructure YAML files.

        Returns:
            A ``ComparisonMatrix`` with parity scores, deltas, and
            recommendations for aligning environments.

        Raises:
            ValueError: If fewer than two paths are provided.
        """
        from infrasim.simulator.multi_env import (
            ComparisonMatrix,
            MultiEnvComparator,
        )

        if len(yaml_paths) < 2:
            raise ValueError("compare() requires at least two YAML paths.")

        env_configs: dict[str, Path] = {}
        for p in yaml_paths:
            path = Path(p)
            env_configs[path.stem] = path

        comparator = MultiEnvComparator()
        return comparator.compare(env_configs)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def resilience_score(self) -> float:
        """Overall resilience score from 0 to 100."""
        return round(self._graph.resilience_score(), 1)

    @property
    def component_count(self) -> int:
        """Number of components in the infrastructure."""
        return len(self._graph.components)

    @property
    def spof_count(self) -> int:
        """Count of single-points-of-failure in the infrastructure."""
        return len(self.find_spofs())

    @property
    def components(self) -> list:
        """List of all Component objects in the infrastructure."""
        return list(self._graph.components.values())

    @property
    def graph(self) -> "InfraGraph":
        """The underlying InfraGraph instance."""
        return self._graph

    # ------------------------------------------------------------------
    # Analysis methods
    # ------------------------------------------------------------------

    def simulate(self, **kwargs: Any) -> "SimulationReport":
        """Run chaos simulation with all default scenarios.

        Keyword Args:
            include_feed: Whether to include feed-generated scenarios.
                Defaults to ``True``.
            include_plugins: Whether to include plugin-generated scenarios.
                Defaults to ``True``.
            max_scenarios: Override the truncation limit. ``0`` uses the
                module default.

        Returns:
            A ``SimulationReport`` with all scenario results sorted by risk.
        """
        from infrasim.simulator.engine import SimulationEngine

        engine = SimulationEngine(self._graph)
        return engine.run_all_defaults(**kwargs)

    def validate_sla(self, target_nines: float = 4.0) -> "SLAValidationResult":
        """Mathematically validate whether an SLA target is achievable.

        Args:
            target_nines: Target availability expressed as nines
                (e.g. ``4.0`` for 99.99%).

        Returns:
            An ``SLAValidationResult`` with achievability verdict,
            gap analysis, and improvement suggestions.
        """
        from infrasim.simulator.sla_validator import (
            SLATarget,
            SLAValidatorEngine,
        )

        target = SLATarget(name="SDK SLA Validation", target_nines=target_nines)
        engine = SLAValidatorEngine()
        results = engine.validate(self._graph, [target])
        return results[0]

    def genome(self) -> "GenomeProfile":
        """Extract the resilience genome -- a multi-dimensional DNA fingerprint.

        Returns:
            A ``GenomeProfile`` with traits, resilience grade, weakness genes,
            and benchmark percentile.
        """
        from infrasim.simulator.chaos_genome import ChaosGenomeEngine

        engine = ChaosGenomeEngine()
        return engine.analyze(self._graph)

    def benchmark(self, industry: str = "saas") -> "BenchmarkResult":
        """Benchmark infrastructure resilience against industry peers.

        Args:
            industry: Industry vertical to compare against. Supported
                values include ``"saas"``, ``"fintech"``, ``"ecommerce"``,
                ``"healthcare"``, ``"media"``, ``"gaming"``.

        Returns:
            A ``BenchmarkResult`` with percentile ranking, strengths,
            weaknesses, and improvement priorities.
        """
        from infrasim.simulator.benchmarking import BenchmarkEngine

        engine = BenchmarkEngine()
        return engine.benchmark(self._graph, industry)

    def risk_heatmap(self) -> "HeatMapData":
        """Generate a multi-dimensional risk heat map.

        Scores each component across blast radius, SPOF risk, utilization,
        dependency depth, recovery difficulty, and security posture.

        Returns:
            A ``HeatMapData`` with per-component risk profiles, risk zones,
            and identified hotspots.
        """
        from infrasim.simulator.risk_heatmap import RiskHeatMapEngine

        engine = RiskHeatMapEngine()
        return engine.analyze(self._graph)

    def check_contract(self, contract_path: str) -> "ContractValidationResult":
        """Validate infrastructure against a resilience contract file.

        Args:
            contract_path: Path to a YAML resilience contract.

        Returns:
            A ``ContractValidationResult`` indicating whether the
            infrastructure meets all contract rules.
        """
        from infrasim.contracts import ContractEngine

        engine = ContractEngine()
        contract = engine.load_contract(Path(contract_path))
        return engine.validate(self._graph, contract)

    # ------------------------------------------------------------------
    # Export methods
    # ------------------------------------------------------------------

    def to_yaml(self) -> str:
        """Export infrastructure as a YAML string.

        Returns:
            YAML representation of the infrastructure graph.
        """
        import yaml

        return yaml.dump(self._graph.to_dict(), default_flow_style=False, sort_keys=False)

    def to_mermaid(self) -> str:
        """Export infrastructure as a Mermaid.js diagram.

        Returns:
            Mermaid diagram string suitable for embedding in Markdown.
        """
        from infrasim.reporter.graph_exporter import (
            DiagramFormat,
            DiagramOptions,
            GraphExporter,
        )

        exporter = GraphExporter()
        return exporter.export(self._graph, DiagramFormat.MERMAID, DiagramOptions())

    def to_json(self) -> str:
        """Export infrastructure as a JSON string.

        Returns:
            JSON representation of the infrastructure model.
        """
        return json.dumps(self._graph.to_dict(), indent=2, default=str)

    def to_terraform(self) -> dict[str, str]:
        """Generate Terraform remediation code.

        Produces IaC files that fix detected infrastructure issues,
        organized into phased remediation plans.

        Returns:
            Dictionary mapping file paths to Terraform code content.
        """
        from infrasim.remediation.iac_generator import IaCGenerator

        generator = IaCGenerator(self._graph)
        plan = generator.generate()
        return {f.path: f.content for f in plan.files}

    # ------------------------------------------------------------------
    # Report methods
    # ------------------------------------------------------------------

    def executive_report(self, company_name: str = "") -> str:
        """Generate a C-level executive summary.

        Args:
            company_name: Optional company name for the report header.

        Returns:
            HTML string with a traffic-light executive summary including
            top risks, ROI analysis, and key availability metrics.
        """
        from infrasim.reporter.executive_report import generate_executive_summary

        summary = generate_executive_summary(self._graph)
        return str(summary)

    def compliance_report(self, framework: str = "dora") -> str:
        """Generate a compliance report for a regulatory framework.

        Args:
            framework: Compliance framework to target. Currently supports
                ``"dora"`` (Digital Operational Resilience Act).

        Returns:
            HTML string with compliance mapping and gap analysis.
        """
        from infrasim.reporter.compliance import generate_dora_report
        from infrasim.ai.analyzer import AIAnalysisReport
        from infrasim.simulator.engine import SimulationEngine

        import tempfile

        engine = SimulationEngine(self._graph)
        report = engine.run_all_defaults(include_feed=False)
        ai_report = AIAnalysisReport(recommendations=[], summary="", risk_score=0.0)

        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as f:
            output_path = Path(f.name)

        generate_dora_report(self._graph, report, ai_report, output_path)
        html_content = output_path.read_text()
        output_path.unlink(missing_ok=True)
        return html_content

    # ------------------------------------------------------------------
    # Utility methods
    # ------------------------------------------------------------------

    def replay_incident(self, incident_id: str) -> "ReplayResult":
        """Replay a specific historical incident on this infrastructure.

        Args:
            incident_id: Identifier of the historical incident
                (e.g. ``"aws-us-east-1-2021"``).

        Returns:
            A ``ReplayResult`` with survival verdict, impact score,
            affected components, and recommendations.

        Raises:
            KeyError: If the incident ID is not found.
        """
        from infrasim.simulator.incident_replay import IncidentReplayEngine

        engine = IncidentReplayEngine()
        incident = engine.get_incident(incident_id)
        if incident is None:
            raise KeyError(f"Incident '{incident_id}' not found.")
        return engine.replay(self._graph, incident)

    def replay_all_incidents(self) -> list:
        """Replay ALL known historical incidents on this infrastructure.

        Returns:
            List of ``ReplayResult`` for each known incident.
        """
        from infrasim.simulator.incident_replay import IncidentReplayEngine

        engine = IncidentReplayEngine()
        return engine.replay_all(self._graph)

    def find_spofs(self) -> list:
        """Find all single-points-of-failure in the infrastructure.

        A component is a SPOF if it has only one replica, no failover,
        and at least one dependent component with a ``requires`` dependency.

        Returns:
            List of ``Component`` objects that are SPOFs.
        """
        spofs = []
        for comp in self._graph.components.values():
            if comp.replicas <= 1 and not comp.failover.enabled:
                dependents = self._graph.get_dependents(comp.id)
                for dep_comp in dependents:
                    edge = self._graph.get_dependency_edge(dep_comp.id, comp.id)
                    if edge and edge.dependency_type == "requires":
                        spofs.append(comp)
                        break
        return spofs

    def quick_wins(self) -> list:
        """Get quick-win architecture changes to improve resilience.

        Returns:
            List of ``ArchitectureChange`` proposals that can be
            implemented with minimal effort for maximum impact.
        """
        from infrasim.ai.architecture_advisor import ArchitectureAdvisor

        advisor = ArchitectureAdvisor()
        report = advisor.advise(self._graph)
        return report.quick_wins

    def chat(self, question: str) -> str:
        """Ask a natural language question about the infrastructure.

        Uses rule-based NLP to interpret questions like "What happens
        if the database goes down?" and runs appropriate simulations.

        Args:
            question: Natural language question about the infrastructure.

        Returns:
            Natural language answer string.
        """
        from infrasim.nl_query import NaturalLanguageEngine

        engine = NaturalLanguageEngine(self._graph)
        result = engine.query(question)
        return result.answer

    # ------------------------------------------------------------------
    # Dunder methods
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        source = self._yaml_path or "in-memory"
        return (
            f"FaultZero(source={source!r}, "
            f"components={self.component_count}, "
            f"score={self.resilience_score})"
        )

    def __str__(self) -> str:
        return (
            f"FaultZero Infrastructure Analysis\n"
            f"  Source: {self._yaml_path or 'in-memory'}\n"
            f"  Components: {self.component_count}\n"
            f"  Resilience Score: {self.resilience_score}/100\n"
            f"  SPOFs: {self.spof_count}"
        )
