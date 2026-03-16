"""Natural Language Query Engine for FaultRay.

Parse natural language questions about infrastructure resilience and
execute appropriate simulations. Rule-based NLP -- no LLM dependency.

Usage:
    from faultray.nl_query import NaturalLanguageEngine
    engine = NaturalLanguageEngine(graph)
    result = engine.query("What happens if the database goes down?")
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from faultray.model.components import HealthStatus
from faultray.model.graph import InfraGraph
from faultray.simulator.engine import ScenarioResult, SimulationEngine
from faultray.simulator.scenarios import Fault, FaultType, Scenario


@dataclass
class QueryResult:
    """Result of a natural language query."""

    query: str
    interpreted_as: str  # e.g. "Simulate: database down"
    scenario: Scenario | None = None
    result: ScenarioResult | None = None
    answer: str = ""  # Natural language answer
    components_matched: list[str] = field(default_factory=list)
    query_type: str = ""  # e.g. "component_down", "traffic_spike", etc.


class NaturalLanguageEngine:
    """Parse natural language questions and execute infrastructure simulations.

    Uses rule-based pattern matching -- no LLM or external API required.

    Supported query types:
        - "What happens if <component> goes down?"
        - "What happens if traffic spikes?"
        - "How resilient is the system?"
        - "What are the risks?"
        - "Can we survive a <component> outage?"
        - "What is the cost of a <component> outage?"
        - "What is the availability?"
    """

    # Patterns are checked in order -- more specific patterns first.
    PATTERNS: list[tuple[str, str]] = [
        (r"what.*(happen|if).*traffic.*(spike|increase|surge|ddos|flood|10x|100x)", "traffic_spike"),
        (r"what.*(cascade|propagat|spread|chain|domino)", "cascade_check"),
        (r"what.*(happen|if).*(down|fail|crash|die|stop|break|outage|kill)", "component_down"),
        (r"how.*resilient", "resilience_check"),
        (r"resilien(ce|t).*score", "resilience_check"),
        (r"what.*(risk|danger|threat|vulnerabilit)", "risk_assessment"),
        (r"(biggest|top|worst|most).*(risk|danger|threat)", "risk_assessment"),
        (r"can.*(survive|handle|withstand|tolerate).*(outage|failure|crash|down)", "survival_check"),
        (r"what.*(cost|price|expense|impact).*(outage|downtime|failure)", "cost_query"),
        (r"how.*much.*(cost|lose|spend).*(outage|down|fail)", "cost_query"),
        (r"what.*(availability|uptime|sla|slo)", "availability_query"),
        (r"(show|list|tell).*(component|service|system|node)", "list_components"),
        (r"(single.*point|spof|no.*redundanc)", "spof_check"),
    ]

    # Traffic multiplier patterns
    TRAFFIC_MULTIPLIER_PATTERNS: list[tuple[str, float]] = [
        (r"(\d+)\s*x", 0),  # Nx -- captured group
        (r"double", 2.0),
        (r"triple", 3.0),
        (r"10\s*times", 10.0),
        (r"100\s*times", 100.0),
        (r"ddos", 50.0),
        (r"flood", 20.0),
    ]

    def __init__(self, graph: InfraGraph) -> None:
        self.graph = graph
        self._engine = SimulationEngine(graph)
        self._component_names = {
            comp_id: comp.name for comp_id, comp in graph.components.items()
        }

    def query(self, question: str) -> QueryResult:
        """Parse a natural language question and run the appropriate simulation.

        Args:
            question: A natural language question about the infrastructure.

        Returns:
            A QueryResult containing the interpreted query, scenario,
            simulation result, and a natural language answer.
        """
        question_lower = question.lower().strip()

        # Match against patterns
        query_type = self._match_pattern(question_lower)
        if not query_type:
            return QueryResult(
                query=question,
                interpreted_as="Unknown query type",
                answer=(
                    "I could not understand that question. Try asking things like:\n"
                    "- 'What happens if the database goes down?'\n"
                    "- 'How resilient is the system?'\n"
                    "- 'What are the biggest risks?'\n"
                    "- 'Can we survive a cache outage?'\n"
                    "- 'What is the availability?'"
                ),
                query_type="unknown",
            )

        # Route to appropriate handler
        handler = getattr(self, f"_handle_{query_type}", None)
        if handler is None:
            return QueryResult(
                query=question,
                interpreted_as=f"Matched pattern: {query_type} (no handler)",
                answer=f"Query type '{query_type}' is recognized but not yet implemented.",
                query_type=query_type,
            )

        return handler(question, question_lower)

    def _match_pattern(self, question_lower: str) -> str | None:
        """Match a question against known patterns and return the query type."""
        for pattern, query_type in self.PATTERNS:
            if re.search(pattern, question_lower):
                return query_type
        return None

    def _find_component(self, text: str) -> str | None:
        """Find the best matching component ID from the question text.

        Uses word-boundary matching and fuzzy matching against component
        IDs and names. Prefers longer matches to avoid false positives
        (e.g., "app" matching inside "happens").
        """
        text_lower = text.lower()
        words = re.findall(r'\b\w+\b', text_lower)
        best_match: str | None = None
        best_score = 0.0

        for comp_id, comp_name in self._component_names.items():
            comp_id_lower = comp_id.lower()
            comp_name_lower = comp_name.lower()

            # Check word-boundary match for component ID
            # Use \b to avoid "app" matching in "happens"
            id_pattern = r'\b' + re.escape(comp_id_lower) + r'\b'
            if re.search(id_pattern, text_lower):
                score = len(comp_id_lower) + 100  # Strong bonus for exact word match
                if score > best_score:
                    best_match = comp_id
                    best_score = score
                continue

            # Check word-boundary match for component name
            name_pattern = r'\b' + re.escape(comp_name_lower) + r'\b'
            if re.search(name_pattern, text_lower):
                score = len(comp_name_lower) + 100
                if score > best_score:
                    best_match = comp_id
                    best_score = score
                continue

            # Fuzzy match against words in the text
            for word in words:
                if len(word) < 3:
                    continue
                id_score = SequenceMatcher(None, word, comp_id_lower).ratio()
                name_score = SequenceMatcher(None, word, comp_name_lower).ratio()
                score = max(id_score, name_score)
                if score > best_score and score >= 0.6:
                    # Scale to be less than word-boundary matches
                    best_match = comp_id
                    best_score = score

        return best_match

    def _find_all_components(self, text: str) -> list[str]:
        """Find all matching component IDs from the question text."""
        text_lower = text.lower()
        matches = []
        for comp_id, comp_name in self._component_names.items():
            if comp_id.lower() in text_lower or comp_name.lower() in text_lower:
                matches.append(comp_id)
        return matches

    def _extract_traffic_multiplier(self, text: str) -> float:
        """Extract traffic multiplier from text (e.g., '10x', 'double')."""
        text_lower = text.lower()
        for pattern, default_value in self.TRAFFIC_MULTIPLIER_PATTERNS:
            m = re.search(pattern, text_lower)
            if m:
                if default_value == 0 and m.groups():
                    # Dynamic value from capture group
                    try:
                        return float(m.group(1))
                    except (ValueError, IndexError):
                        continue
                elif default_value > 0:
                    return default_value
        return 5.0  # Default multiplier for generic traffic spike

    # ---- Query Handlers ----

    def _handle_component_down(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'what happens if X goes down' queries."""
        comp_id = self._find_component(question_lower)

        if not comp_id:
            return QueryResult(
                query=question,
                interpreted_as="Component down (no component matched)",
                answer=(
                    "I could not identify which component you mean. "
                    f"Available components: {', '.join(sorted(self._component_names.keys()))}"
                ),
                query_type="component_down",
            )

        comp = self.graph.get_component(comp_id)
        comp_display = comp.name if comp else comp_id

        scenario = Scenario(
            id=f"nlq-{comp_id}-down",
            name=f"{comp_display} failure",
            description=f"Simulated failure of {comp_display}",
            faults=[
                Fault(
                    target_component_id=comp_id,
                    fault_type=FaultType.COMPONENT_DOWN,
                    severity=1.0,
                )
            ],
        )

        result = self._engine.run_scenario(scenario)
        answer = self._format_component_down_answer(comp_display, result)

        return QueryResult(
            query=question,
            interpreted_as=f"Simulate: {comp_display} down",
            scenario=scenario,
            result=result,
            answer=answer,
            components_matched=[comp_id],
            query_type="component_down",
        )

    def _handle_traffic_spike(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'what happens if traffic spikes' queries."""
        multiplier = self._extract_traffic_multiplier(question_lower)
        comp_ids = list(self.graph.components.keys())

        scenario = Scenario(
            id="nlq-traffic-spike",
            name=f"Traffic spike {multiplier}x",
            description=f"Simulated {multiplier}x traffic increase across all components",
            faults=[],
            traffic_multiplier=multiplier,
        )

        result = self._engine.run_scenario(scenario)
        answer = self._format_traffic_spike_answer(multiplier, result)

        return QueryResult(
            query=question,
            interpreted_as=f"Simulate: {multiplier}x traffic spike",
            scenario=scenario,
            result=result,
            answer=answer,
            components_matched=comp_ids,
            query_type="traffic_spike",
        )

    def _handle_resilience_check(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'how resilient is the system' queries."""
        score = self.graph.resilience_score()
        score_v2 = self.graph.resilience_score_v2()
        breakdown = score_v2.get("breakdown", {})
        recommendations = score_v2.get("recommendations", [])

        if score >= 80:
            assessment = "The system is well-architected with strong resilience."
        elif score >= 60:
            assessment = "The system has moderate resilience but has areas for improvement."
        elif score >= 40:
            assessment = "The system has significant resilience gaps that need attention."
        else:
            assessment = "The system has critical resilience weaknesses."

        parts = [
            f"Resilience Score: {score:.1f}/100",
            f"Assessment: {assessment}",
            "",
            "Breakdown:",
        ]
        for category, value in breakdown.items():
            label = category.replace("_", " ").title()
            parts.append(f"  - {label}: {value:.1f}/20")

        if recommendations:
            parts.append("")
            parts.append("Recommendations:")
            for i, rec in enumerate(recommendations[:5], 1):
                parts.append(f"  {i}. {rec}")

        return QueryResult(
            query=question,
            interpreted_as="Check: system resilience score",
            answer="\n".join(parts),
            query_type="resilience_check",
        )

    def _handle_risk_assessment(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'what are the risks' queries."""
        engine = SimulationEngine(self.graph)
        report = engine.run_all_defaults(include_feed=False, include_plugins=False)

        critical = report.critical_findings
        warnings = report.warnings

        parts = [f"Risk Assessment ({len(report.results)} scenarios tested):"]

        if critical:
            parts.append(f"\nCritical Risks ({len(critical)}):")
            for i, finding in enumerate(critical[:5], 1):
                parts.append(f"  {i}. {finding.scenario.name} (severity: {finding.risk_score:.1f})")
                for effect in finding.cascade.effects[:3]:
                    parts.append(f"     - {effect.component_name}: {effect.health.value} ({effect.reason})")
        else:
            parts.append("\nNo critical risks found.")

        if warnings:
            parts.append(f"\nWarnings ({len(warnings)}):")
            for i, warning in enumerate(warnings[:5], 1):
                parts.append(f"  {i}. {warning.scenario.name} (severity: {warning.risk_score:.1f})")
        else:
            parts.append("\nNo warnings found.")

        parts.append(f"\nOverall resilience score: {report.resilience_score:.1f}/100")

        return QueryResult(
            query=question,
            interpreted_as="Assess: infrastructure risks",
            answer="\n".join(parts),
            query_type="risk_assessment",
        )

    def _handle_survival_check(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'can we survive X outage' queries."""
        comp_id = self._find_component(question_lower)

        if not comp_id:
            return QueryResult(
                query=question,
                interpreted_as="Survival check (no component matched)",
                answer=(
                    "I could not identify which component you mean. "
                    f"Available components: {', '.join(sorted(self._component_names.keys()))}"
                ),
                query_type="survival_check",
            )

        comp = self.graph.get_component(comp_id)
        comp_display = comp.name if comp else comp_id

        scenario = Scenario(
            id=f"nlq-survive-{comp_id}",
            name=f"Survive {comp_display} outage",
            description=f"Can the system survive {comp_display} going down?",
            faults=[
                Fault(
                    target_component_id=comp_id,
                    fault_type=FaultType.COMPONENT_DOWN,
                    severity=1.0,
                )
            ],
        )

        result = self._engine.run_scenario(scenario)

        # Determine if the system can survive
        cascade_effects = result.cascade.effects
        down_count = sum(1 for e in cascade_effects if e.health == HealthStatus.DOWN)
        total = len(self.graph.components)
        down_ratio = down_count / total if total > 0 else 0

        if down_ratio == 0 or (down_count <= 1 and total > 1):
            verdict = "YES - the system can survive this outage."
            if comp and comp.replicas > 1:
                verdict += f" {comp_display} has {comp.replicas} replicas for redundancy."
            if comp and comp.failover.enabled:
                verdict += f" Failover is enabled (promotion time: {comp.failover.promotion_time_seconds}s)."
        elif down_ratio < 0.3:
            verdict = (
                f"PARTIALLY - the system degrades but core functionality may survive. "
                f"{down_count}/{total} components affected."
            )
        else:
            verdict = (
                f"NO - the system cannot survive this outage. "
                f"{down_count}/{total} components would go down (cascade failure)."
            )

        parts = [
            f"Survival Check: {comp_display} outage",
            f"Verdict: {verdict}",
            f"Risk score: {result.risk_score:.1f}/10",
        ]

        if cascade_effects:
            parts.append(f"\nAffected components ({len(cascade_effects)}):")
            for effect in cascade_effects:
                parts.append(f"  - {effect.component_name}: {effect.health.value}")

        return QueryResult(
            query=question,
            interpreted_as=f"Check: can survive {comp_display} outage",
            scenario=scenario,
            result=result,
            answer="\n".join(parts),
            components_matched=[comp_id],
            query_type="survival_check",
        )

    def _handle_cost_query(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'what is the cost of an outage' queries."""
        comp_id = self._find_component(question_lower)

        if not comp_id:
            # Calculate total system cost
            total_hourly = sum(
                c.cost_profile.hourly_infra_cost for c in self.graph.components.values()
            )
            total_revenue_per_min = sum(
                c.cost_profile.revenue_per_minute for c in self.graph.components.values()
            )
            parts = [
                "System-wide cost impact of outage:",
                f"  Total infrastructure cost: ${total_hourly:.2f}/hour",
                f"  Total revenue at risk: ${total_revenue_per_min:.2f}/minute",
                f"  1-hour outage cost: ${total_revenue_per_min * 60:.2f}",
            ]
            return QueryResult(
                query=question,
                interpreted_as="Query: system-wide outage cost",
                answer="\n".join(parts),
                query_type="cost_query",
            )

        comp = self.graph.get_component(comp_id)
        comp_display = comp.name if comp else comp_id
        cost = comp.cost_profile if comp else None

        parts = [f"Cost impact of {comp_display} outage:"]
        if cost:
            parts.append(f"  Infrastructure cost: ${cost.hourly_infra_cost:.2f}/hour")
            parts.append(f"  Revenue at risk: ${cost.revenue_per_minute:.2f}/minute")
            parts.append(f"  1-hour outage cost: ${cost.revenue_per_minute * 60 + cost.recovery_engineer_cost:.2f}")
            parts.append(f"  Recovery engineer cost: ${cost.recovery_engineer_cost:.2f}")
        else:
            parts.append("  No cost profile configured for this component.")

        return QueryResult(
            query=question,
            interpreted_as=f"Query: cost of {comp_display} outage",
            answer="\n".join(parts),
            components_matched=[comp_id],
            query_type="cost_query",
        )

    def _handle_availability_query(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'what is the availability' queries."""
        score = self.graph.resilience_score()
        total = len(self.graph.components)
        spof_count = sum(
            1 for comp in self.graph.components.values()
            if comp.replicas <= 1 and not comp.failover.enabled
            and len(self.graph.get_dependents(comp.id)) > 0
        )

        # Estimate nines from resilience score
        if score >= 95:
            nines = "99.99% (four nines)"
        elif score >= 85:
            nines = "99.9% (three nines)"
        elif score >= 70:
            nines = "99.5% (two and a half nines)"
        elif score >= 50:
            nines = "99% (two nines)"
        else:
            nines = "< 99% (below two nines)"

        parts = [
            "Availability Assessment:",
            f"  Estimated availability: {nines}",
            f"  Resilience score: {score:.1f}/100",
            f"  Total components: {total}",
            f"  Single points of failure: {spof_count}",
        ]

        if spof_count > 0:
            parts.append("\n  Components without redundancy:")
            for comp in self.graph.components.values():
                if (comp.replicas <= 1 and not comp.failover.enabled
                        and len(self.graph.get_dependents(comp.id)) > 0):
                    parts.append(f"    - {comp.name} ({comp.id})")

        return QueryResult(
            query=question,
            interpreted_as="Query: system availability",
            answer="\n".join(parts),
            query_type="availability_query",
        )

    def _handle_list_components(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'show/list components' queries."""
        parts = [f"Infrastructure Components ({len(self.graph.components)}):"]
        for comp_id, comp in sorted(self.graph.components.items()):
            deps = self.graph.get_dependencies(comp_id)
            dep_list = ", ".join(d.id for d in deps) if deps else "none"
            parts.append(
                f"  - {comp.name} ({comp_id}): type={comp.type.value}, "
                f"replicas={comp.replicas}, depends_on=[{dep_list}]"
            )
        return QueryResult(
            query=question,
            interpreted_as="List: all components",
            answer="\n".join(parts),
            query_type="list_components",
        )

    def _handle_spof_check(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'single point of failure' queries."""
        spofs = []
        for comp in self.graph.components.values():
            dependents = self.graph.get_dependents(comp.id)
            if comp.replicas <= 1 and not comp.failover.enabled and len(dependents) > 0:
                spofs.append((comp, dependents))

        if not spofs:
            answer = "No single points of failure detected. All critical components have redundancy."
        else:
            parts = [f"Single Points of Failure ({len(spofs)} found):"]
            for comp, dependents in spofs:
                dep_names = ", ".join(d.name for d in dependents)
                parts.append(
                    f"  - {comp.name} ({comp.id}): {len(dependents)} dependent(s) [{dep_names}], "
                    f"replicas={comp.replicas}, failover={comp.failover.enabled}"
                )
            parts.append("\nRecommendation: Add replicas or enable failover for these components.")
            answer = "\n".join(parts)

        return QueryResult(
            query=question,
            interpreted_as="Check: single points of failure (SPOF)",
            answer=answer,
            query_type="spof_check",
        )

    def _handle_cascade_check(self, question: str, question_lower: str) -> QueryResult:
        """Handle 'what cascades' queries."""
        worst_cascade = None
        worst_score = 0.0

        for comp_id in self.graph.components:
            scenario = Scenario(
                id=f"cascade-check-{comp_id}",
                name=f"Cascade from {comp_id}",
                description=f"Check cascade from {comp_id} failure",
                faults=[
                    Fault(
                        target_component_id=comp_id,
                        fault_type=FaultType.COMPONENT_DOWN,
                    )
                ],
            )
            result = self._engine.run_scenario(scenario)
            if result.risk_score > worst_score:
                worst_score = result.risk_score
                worst_cascade = result

        if worst_cascade is None or worst_score == 0:
            return QueryResult(
                query=question,
                interpreted_as="Check: cascade failure analysis",
                answer="No significant cascade failures detected.",
                query_type="cascade_check",
            )

        effects = worst_cascade.cascade.effects
        trigger = worst_cascade.cascade.trigger
        parts = [
            "Worst Cascade Failure Analysis:",
            f"  Trigger: {trigger}",
            f"  Risk score: {worst_score:.1f}/10",
            f"  Components affected: {len(effects)}",
            "",
        ]
        for effect in effects:
            parts.append(f"  - {effect.component_name}: {effect.health.value} ({effect.reason})")

        return QueryResult(
            query=question,
            interpreted_as="Check: cascade failure analysis",
            result=worst_cascade,
            answer="\n".join(parts),
            query_type="cascade_check",
        )

    # ---- Answer Formatters ----

    def _format_component_down_answer(self, comp_name: str, result: ScenarioResult) -> str:
        """Format a natural language answer for a component-down scenario."""
        effects = result.cascade.effects
        score = result.risk_score

        parts = [f"If {comp_name} goes down (risk score: {score:.1f}/10):"]

        if not effects:
            parts.append("  No cascading effects detected.")
            return "\n".join(parts)

        down = [e for e in effects if e.health == HealthStatus.DOWN]
        degraded = [e for e in effects if e.health == HealthStatus.DEGRADED]
        overloaded = [e for e in effects if e.health == HealthStatus.OVERLOADED]

        if down:
            parts.append(f"\n  Components that go DOWN ({len(down)}):")
            for e in down:
                parts.append(f"    - {e.component_name}: {e.reason}")

        if degraded:
            parts.append(f"\n  Components that DEGRADE ({len(degraded)}):")
            for e in degraded:
                parts.append(f"    - {e.component_name}: {e.reason}")

        if overloaded:
            parts.append(f"\n  Components that become OVERLOADED ({len(overloaded)}):")
            for e in overloaded:
                parts.append(f"    - {e.component_name}: {e.reason}")

        if score >= 7:
            parts.append("\n  CRITICAL: This is a high-risk scenario. Consider adding redundancy.")
        elif score >= 4:
            parts.append("\n  WARNING: This scenario causes notable degradation.")
        else:
            parts.append("\n  This is a low-risk scenario with limited impact.")

        return "\n".join(parts)

    def _format_traffic_spike_answer(self, multiplier: float, result: ScenarioResult) -> str:
        """Format a natural language answer for a traffic spike scenario."""
        effects = result.cascade.effects
        score = result.risk_score

        parts = [f"Under a {multiplier}x traffic spike (risk score: {score:.1f}/10):"]

        if not effects:
            parts.append("  The system handles the traffic increase without issues.")
            return "\n".join(parts)

        down = [e for e in effects if e.health == HealthStatus.DOWN]
        degraded = [e for e in effects if e.health == HealthStatus.DEGRADED]
        overloaded = [e for e in effects if e.health == HealthStatus.OVERLOADED]

        if down:
            parts.append(f"\n  Components that would FAIL ({len(down)}):")
            for e in down:
                parts.append(f"    - {e.component_name}: {e.reason}")

        if overloaded:
            parts.append(f"\n  Components that become OVERLOADED ({len(overloaded)}):")
            for e in overloaded:
                parts.append(f"    - {e.component_name}: {e.reason}")

        if degraded:
            parts.append(f"\n  Components with DEGRADED performance ({len(degraded)}):")
            for e in degraded:
                parts.append(f"    - {e.component_name}: {e.reason}")

        return "\n".join(parts)
