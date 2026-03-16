"""Conversational Infrastructure Analysis Engine.

Provides a chat-like interface for asking questions about infrastructure.
Uses rule-based NLP (no external LLM required) to understand questions
and generate informative answers from the infrastructure graph.

Example questions:
- "What are my single points of failure?"
- "Which components would be affected if postgres goes down?"
- "What's my most critical component?"
- "How many nines can I achieve?"
- "Show me all components without circuit breakers"
- "What happens during an AWS us-east-1 outage?"
- "SPOFはどこにある？"
- "一番リスクの高いコンポーネントは？"
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from enum import Enum

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums and dataclasses
# ---------------------------------------------------------------------------

class ChatIntent(str, Enum):
    """Recognised intents from user questions."""

    LIST_SPOF = "list_spof"
    CASCADE_ANALYSIS = "cascade_analysis"
    COMPONENT_INFO = "component_info"
    AVAILABILITY_QUERY = "availability_query"
    RISK_ASSESSMENT = "risk_assessment"
    CONFIGURATION_CHECK = "configuration_check"
    COMPARISON = "comparison"
    RECOMMENDATION = "recommendation"
    INCIDENT_IMPACT = "incident_impact"
    GENERAL_STATUS = "general_status"
    HELP = "help"
    UNKNOWN = "unknown"


@dataclass
class ChatResponse:
    """Response from the chat engine."""

    text: str  # Markdown-formatted response text
    intent: ChatIntent
    data: dict | None = None  # Structured data if available
    suggestions: list[str] = field(default_factory=list)
    visualization: str | None = None  # "table", "graph", "chart"


# ---------------------------------------------------------------------------
# Intent detection patterns
# ---------------------------------------------------------------------------

INTENT_PATTERNS: dict[ChatIntent, list[str]] = {
    ChatIntent.LIST_SPOF: [
        r"(?:single\s+point|spof|単一障害点|SPOF)",
        r"(?:what|which|show|list).+(?:spof|single.*point|vulnerable)",
        r"(?:spof|単一障害|脆弱)",
    ],
    ChatIntent.INCIDENT_IMPACT: [
        r"(?:incident|outage|failure|障害|アウテージ)",
        r"(?:region|az|zone|リージョン).+(?:outage|fail|down)",
    ],
    ChatIntent.CONFIGURATION_CHECK: [
        r"(?:without|missing|no|lack).+(?:circuit.?breaker|autoscal|failover|health.?check|replica)",
        r"(?:which|show|list).+(?:don't\s+have|without|missing)",
        r"(?:show|list).+(?:without|missing|no)\s+(?:autoscal|circuit|failover|replica|health)",
        r"(?:設定されていない|ない|不足|未設定)",
    ],
    ChatIntent.CASCADE_ANALYSIS: [
        r"(?:what|which).+(?:affected|impact|cascade)",
        r"(?:if|when).+(?:goes?\s+down|fails?|crashes?|dies?)",
        r"(?:落ちたら|障害が起きたら|止まったら)",
        r"(?:cascade|連鎖)",
        r"(?:blast\s*radius|爆発範囲)",
        r"(?:what).+(?:happen).+(?:if|when)",
    ],
    ChatIntent.COMPONENT_INFO: [
        r"(?:tell|show|info|details?|about).+(?:component|service|server|database|cache)",
        r"(?:tell\s+me\s+about|describe|what\s+is)\s+\S+",
        r"(?:について|詳細|情報)",
    ],
    ChatIntent.AVAILABILITY_QUERY: [
        r"(?:nines|availability|uptime|SLA|可用性)",
        r"(?:how\s+many\s+nines|what.*availability)",
        r"(?:稼働率|アップタイム|ダウンタイム)",
    ],
    ChatIntent.RISK_ASSESSMENT: [
        r"(?:risk|danger|critical|most.*(?:risky|critical|important))",
        r"(?:リスク|危険|重要|クリティカル)",
        r"(?:highest\s+risk|most\s+(?:vulnerable|dangerous))",
    ],
    ChatIntent.COMPARISON: [
        r"(?:compare|versus|vs\.?|difference|より)",
        r"(?:better|worse|比較)",
    ],
    ChatIntent.RECOMMENDATION: [
        r"(?:recommend|suggest|improve|how.*(?:improve|fix|better))",
        r"(?:改善|おすすめ|どうすれば|提案)",
        r"(?:what\s+should|how\s+(?:can|do)\s+(?:i|we))",
    ],
    ChatIntent.GENERAL_STATUS: [
        r"(?:status|overview|summary|how.*(?:doing|looking)|dashboard)",
        r"(?:状態|概要|サマリー|ステータス)",
        r"^(?:hi|hello|hey|こんにちは|やあ)$",
    ],
    ChatIntent.HELP: [
        r"(?:help|what\s+can\s+you|how\s+do\s+i|ヘルプ|使い方|何ができる)",
        r"^\?$",
    ],
}


# ---------------------------------------------------------------------------
# SLA math helpers (inline to avoid circular import)
# ---------------------------------------------------------------------------

_COMPONENT_AVAILABILITY: dict[ComponentType, float] = {
    ComponentType.LOAD_BALANCER: 0.9999,
    ComponentType.WEB_SERVER: 0.999,
    ComponentType.APP_SERVER: 0.999,
    ComponentType.DATABASE: 0.9995,
    ComponentType.CACHE: 0.999,
    ComponentType.QUEUE: 0.9999,
    ComponentType.DNS: 0.99999,
    ComponentType.STORAGE: 0.99999,
    ComponentType.EXTERNAL_API: 0.999,
    ComponentType.CUSTOM: 0.999,
}


def _component_base_availability(comp: Component) -> float:
    """Get base availability for a single component instance."""
    mtbf_hours = comp.operational_profile.mtbf_hours
    mttr_hours = comp.operational_profile.mttr_minutes / 60.0
    if mtbf_hours > 0 and mttr_hours > 0:
        return mtbf_hours / (mtbf_hours + mttr_hours)
    return _COMPONENT_AVAILABILITY.get(comp.type, 0.999)


def _component_effective_availability(comp: Component) -> float:
    """Effective availability considering replicas."""
    a_single = _component_base_availability(comp)
    if comp.replicas <= 1:
        return a_single
    # Parallel redundancy: A_eff = 1 - (1 - A_single)^n
    return 1.0 - (1.0 - a_single) ** comp.replicas


def _to_nines(availability: float) -> float:
    """Convert availability fraction (0-1) to nines count."""
    if availability >= 1.0:
        return float("inf")
    if availability <= 0.0:
        return 0.0
    return -math.log10(1.0 - availability)


def _system_availability(graph: InfraGraph) -> float:
    """Calculate approximate system availability by multiplying serial paths."""
    if not graph.components:
        return 0.0
    avail = 1.0
    for comp in graph.components.values():
        avail *= _component_effective_availability(comp)
    return avail


# ---------------------------------------------------------------------------
# ChatEngine
# ---------------------------------------------------------------------------

class ChatEngine:
    """Rule-based conversational engine for infrastructure analysis.

    No external LLM required.  Uses regex-based intent detection and
    graph analysis to answer questions about the loaded infrastructure.
    """

    # ---- public API --------------------------------------------------------

    def ask(self, question: str, graph: InfraGraph) -> ChatResponse:
        """Process a natural-language question and return a response."""
        if not graph.components:
            return ChatResponse(
                text=(
                    "No infrastructure is currently loaded. "
                    "Please load a model first using the demo button or by "
                    "importing a YAML/JSON file."
                ),
                intent=ChatIntent.UNKNOWN,
                suggestions=["Load the demo infrastructure"],
            )

        intent = self.detect_intent(question)

        handler = {
            ChatIntent.LIST_SPOF: self._handle_spof,
            ChatIntent.CASCADE_ANALYSIS: self._handle_cascade,
            ChatIntent.COMPONENT_INFO: self._handle_component_info,
            ChatIntent.AVAILABILITY_QUERY: self._handle_availability,
            ChatIntent.RISK_ASSESSMENT: self._handle_risk,
            ChatIntent.CONFIGURATION_CHECK: self._handle_config_check,
            ChatIntent.COMPARISON: self._handle_comparison,
            ChatIntent.RECOMMENDATION: self._handle_recommendation,
            ChatIntent.INCIDENT_IMPACT: self._handle_incident,
            ChatIntent.GENERAL_STATUS: self._handle_status,
            ChatIntent.HELP: self._handle_help,
            ChatIntent.UNKNOWN: self._handle_unknown,
        }.get(intent, self._handle_unknown)

        return handler(question, graph)

    def detect_intent(self, question: str) -> ChatIntent:
        """Detect the user's intent from their question text."""
        q = question.strip().lower()
        for intent, patterns in INTENT_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, q, re.IGNORECASE):
                    return intent
        return ChatIntent.UNKNOWN

    def extract_component_reference(
        self, question: str, graph: InfraGraph
    ) -> str | None:
        """Try to find a component name/id referenced in the question."""
        q_lower = question.lower()
        # Try exact id match first, then name match
        best_match: str | None = None
        best_len = 0
        for comp in graph.components.values():
            for candidate in [comp.id.lower(), comp.name.lower()]:
                if candidate in q_lower and len(candidate) > best_len:
                    best_match = comp.id
                    best_len = len(candidate)
        return best_match

    def get_suggestions(self, graph: InfraGraph) -> list[str]:
        """Generate starter suggestions for the current graph."""
        suggestions = [
            "What are my single points of failure?",
            "Show me an overview of my infrastructure",
            "How many nines can I achieve?",
        ]
        if graph.components:
            first_comp = next(iter(graph.components.values()))
            suggestions.append(f"What happens if {first_comp.name} goes down?")
        suggestions.append("What improvements do you recommend?")
        return suggestions

    # ---- intent handlers ---------------------------------------------------

    def _handle_spof(self, question: str, graph: InfraGraph) -> ChatResponse:
        spofs: list[dict] = []
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            if comp.replicas <= 1 and len(dependents) > 0:
                spofs.append({
                    "id": comp.id,
                    "name": comp.name,
                    "type": comp.type.value,
                    "dependents_count": len(dependents),
                    "dependents": [d.name for d in dependents],
                })

        if not spofs:
            return ChatResponse(
                text="No single points of failure detected. All components with dependents have redundancy (replicas > 1).",
                intent=ChatIntent.LIST_SPOF,
                data={"spofs": []},
                suggestions=[
                    "Show me an infrastructure overview",
                    "How many nines can I achieve?",
                    "What improvements do you recommend?",
                ],
            )

        # Sort by dependents count (most impactful first)
        spofs.sort(key=lambda s: s["dependents_count"], reverse=True)

        lines = [f"**Found {len(spofs)} single point(s) of failure:**\n"]
        lines.append("| Component | Type | Dependents |")
        lines.append("|-----------|------|------------|")
        for s in spofs:
            dep_list = ", ".join(s["dependents"][:3])
            if len(s["dependents"]) > 3:
                dep_list += f" (+{len(s['dependents']) - 3} more)"
            lines.append(f"| {s['name']} | {s['type']} | {dep_list} |")

        lines.append("\nThese components have **no redundancy** (replicas=1) but other components depend on them.")

        suggestions = []
        if spofs:
            top = spofs[0]
            suggestions.append(f"What happens if {top['name']} goes down?")
        suggestions.append("How can I fix these SPOFs?")
        suggestions.append("What's my current availability?")

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.LIST_SPOF,
            data={"spofs": spofs},
            suggestions=suggestions,
            visualization="table",
        )

    def _handle_cascade(self, question: str, graph: InfraGraph) -> ChatResponse:
        comp_ref = self.extract_component_reference(question, graph)
        if comp_ref is None:
            # Try to find any component name in the question
            comp_names = [(c.id, c.name) for c in graph.components.values()]
            return ChatResponse(
                text=(
                    "I need to know which component to analyse. "
                    "Please mention a component name in your question.\n\n"
                    "**Available components:** "
                    + ", ".join(f"`{n}`" for _, n in comp_names[:10])
                ),
                intent=ChatIntent.CASCADE_ANALYSIS,
                suggestions=[
                    f"What happens if {comp_names[0][1]} goes down?"
                    if comp_names else "Show me my components"
                ],
            )

        comp = graph.get_component(comp_ref)
        if comp is None:
            return ChatResponse(
                text=f"Component `{comp_ref}` not found in the infrastructure graph.",
                intent=ChatIntent.CASCADE_ANALYSIS,
            )

        affected = graph.get_all_affected(comp_ref)

        lines = [f"**Cascade analysis for `{comp.name}` failure:**\n"]

        if not affected:
            lines.append(f"If `{comp.name}` goes down, **no other components** would be directly affected.")
            lines.append("This component has no upstream dependents.")
        else:
            lines.append(f"If `{comp.name}` fails, **{len(affected)} component(s)** would be affected:\n")
            lines.append("| Affected Component | Type |")
            lines.append("|-------------------|------|")
            for aid in sorted(affected):
                acomp = graph.get_component(aid)
                if acomp:
                    lines.append(f"| {acomp.name} | {acomp.type.value} |")

            total = len(graph.components)
            pct = len(affected) / total * 100 if total > 0 else 0
            lines.append(f"\n**Impact:** {pct:.0f}% of infrastructure ({len(affected)}/{total} components)")

            if pct > 50:
                lines.append("\n**CRITICAL**: This failure would affect more than half of your infrastructure!")

        suggestions = [
            "What are my single points of failure?",
            "How can I mitigate this risk?",
        ]
        if affected:
            for aid in list(affected)[:2]:
                acomp = graph.get_component(aid)
                if acomp:
                    suggestions.append(f"What happens if {acomp.name} goes down?")

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.CASCADE_ANALYSIS,
            data={"component": comp_ref, "affected": list(affected)},
            suggestions=suggestions,
            visualization="table" if affected else None,
        )

    def _handle_component_info(self, question: str, graph: InfraGraph) -> ChatResponse:
        comp_ref = self.extract_component_reference(question, graph)

        if comp_ref is None:
            # List all components
            lines = ["**Infrastructure Components:**\n"]
            lines.append("| Name | Type | Replicas | Health |")
            lines.append("|------|------|----------|--------|")
            for comp in graph.components.values():
                lines.append(
                    f"| {comp.name} | {comp.type.value} | {comp.replicas} | {comp.health.value} |"
                )
            return ChatResponse(
                text="\n".join(lines),
                intent=ChatIntent.COMPONENT_INFO,
                suggestions=["Tell me about " + next(iter(graph.components.values())).name],
                visualization="table",
            )

        comp = graph.get_component(comp_ref)
        if comp is None:
            return ChatResponse(
                text=f"Component `{comp_ref}` not found.",
                intent=ChatIntent.COMPONENT_INFO,
            )

        deps = graph.get_dependencies(comp.id)
        dependents = graph.get_dependents(comp.id)
        avail = _component_effective_availability(comp)
        nines = _to_nines(avail)

        lines = [f"**Component: {comp.name}**\n"]
        lines.append(f"- **Type:** {comp.type.value}")
        lines.append(f"- **Replicas:** {comp.replicas}")
        lines.append(f"- **Health:** {comp.health.value}")
        lines.append(f"- **Estimated Availability:** {avail * 100:.4f}% ({nines:.1f} nines)")
        if comp.host:
            lines.append(f"- **Host:** {comp.host}:{comp.port}")
        lines.append(f"- **Autoscaling:** {'enabled' if comp.autoscaling.enabled else 'disabled'}")
        lines.append(f"- **Failover:** {'enabled' if comp.failover.enabled else 'disabled'}")
        lines.append(f"- **Utilization:** {comp.utilization():.1f}%")

        if deps:
            lines.append(f"\n**Depends on:** {', '.join(d.name for d in deps)}")
        if dependents:
            lines.append(f"**Depended on by:** {', '.join(d.name for d in dependents)}")

        suggestions = [f"What happens if {comp.name} goes down?"]
        if not comp.autoscaling.enabled:
            suggestions.append(f"Why doesn't {comp.name} have autoscaling?")
        suggestions.append("What are my single points of failure?")

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.COMPONENT_INFO,
            data={
                "component_id": comp.id,
                "type": comp.type.value,
                "replicas": comp.replicas,
                "availability": avail,
            },
            suggestions=suggestions,
        )

    def _handle_availability(self, question: str, graph: InfraGraph) -> ChatResponse:
        sys_avail = _system_availability(graph)
        sys_nines = _to_nines(sys_avail)

        lines = ["**System Availability Analysis**\n"]
        lines.append(f"- **Estimated System Availability:** {sys_avail * 100:.4f}%")
        lines.append(f"- **Nines:** {sys_nines:.2f}")

        # Monthly downtime
        monthly_seconds = 30.44 * 24 * 3600
        downtime_seconds = (1.0 - sys_avail) * monthly_seconds
        if downtime_seconds < 60:
            downtime_str = f"{downtime_seconds:.1f} seconds"
        elif downtime_seconds < 3600:
            downtime_str = f"{downtime_seconds / 60:.1f} minutes"
        else:
            downtime_str = f"{downtime_seconds / 3600:.1f} hours"
        lines.append(f"- **Estimated Monthly Downtime:** {downtime_str}")

        # Per-component breakdown
        lines.append("\n**Per-Component Availability:**\n")
        lines.append("| Component | Replicas | Availability | Nines |")
        lines.append("|-----------|----------|-------------|-------|")
        for comp in graph.components.values():
            a = _component_effective_availability(comp)
            n = _to_nines(a)
            lines.append(f"| {comp.name} | {comp.replicas} | {a * 100:.4f}% | {n:.2f} |")

        # Bottleneck identification
        worst_comp = min(
            graph.components.values(),
            key=lambda c: _component_effective_availability(c),
        )
        worst_avail = _component_effective_availability(worst_comp)
        lines.append(
            f"\n**Bottleneck:** `{worst_comp.name}` with {worst_avail * 100:.4f}% availability"
        )

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.AVAILABILITY_QUERY,
            data={
                "system_availability": sys_avail,
                "system_nines": sys_nines,
                "monthly_downtime_seconds": downtime_seconds,
            },
            suggestions=[
                "What are my single points of failure?",
                f"How can I improve {worst_comp.name}?",
                "What target SLA should I aim for?",
            ],
            visualization="table",
        )

    def _handle_risk(self, question: str, graph: InfraGraph) -> ChatResponse:
        scored = graph.resilience_score_v2()
        score = scored["score"]
        breakdown = scored["breakdown"]

        lines = ["**Risk Assessment**\n"]
        lines.append(f"**Overall Resilience Score: {score}/100**\n")

        # Score breakdown
        lines.append("| Category | Score (0-20) |")
        lines.append("|----------|-------------|")
        for cat, val in breakdown.items():
            label = cat.replace("_", " ").title()
            indicator = "OK" if val >= 15 else ("WARNING" if val >= 10 else "CRITICAL")
            lines.append(f"| {label} | {val} ({indicator}) |")

        # Identify most critical component (most dependents, fewest replicas)
        risk_scores: list[tuple[float, Component]] = []
        for comp in graph.components.values():
            dependents = graph.get_dependents(comp.id)
            affected = graph.get_all_affected(comp.id)
            # Risk = dependents * (1/replicas) * affected_size
            r = len(dependents) * (1.0 / max(comp.replicas, 1)) * (len(affected) + 1)
            risk_scores.append((r, comp))

        risk_scores.sort(key=lambda x: x[0], reverse=True)

        if risk_scores:
            lines.append("\n**Highest Risk Components:**\n")
            lines.append("| Component | Type | Replicas | Risk Factor |")
            lines.append("|-----------|------|----------|------------|")
            for risk_val, comp in risk_scores[:5]:
                lines.append(f"| {comp.name} | {comp.type.value} | {comp.replicas} | {risk_val:.1f} |")

        suggestions = ["What are my single points of failure?"]
        if risk_scores:
            top = risk_scores[0][1]
            suggestions.append(f"What happens if {top.name} goes down?")
        suggestions.append("What improvements do you recommend?")

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.RISK_ASSESSMENT,
            data={"score": score, "breakdown": breakdown},
            suggestions=suggestions,
            visualization="table",
        )

    def _handle_config_check(self, question: str, graph: InfraGraph) -> ChatResponse:
        q_lower = question.lower()

        issues: list[dict] = []

        for comp in graph.components.values():
            # Check for missing circuit breakers on edges
            edges = graph.all_dependency_edges()
            for edge in edges:
                if edge.source_id == comp.id and not edge.circuit_breaker.enabled:
                    target = graph.get_component(edge.target_id)
                    tname = target.name if target else edge.target_id
                    issues.append({
                        "component": comp.name,
                        "issue": f"No circuit breaker on dependency to {tname}",
                        "category": "circuit_breaker",
                    })

            if not comp.autoscaling.enabled and comp.type in (
                ComponentType.APP_SERVER, ComponentType.WEB_SERVER
            ):
                issues.append({
                    "component": comp.name,
                    "issue": "Autoscaling not enabled",
                    "category": "autoscaling",
                })

            if not comp.failover.enabled and comp.replicas <= 1:
                dependents = graph.get_dependents(comp.id)
                if dependents:
                    issues.append({
                        "component": comp.name,
                        "issue": "No failover and single replica with dependents",
                        "category": "failover",
                    })

        # Filter if question mentions a specific category
        if "circuit" in q_lower or "breaker" in q_lower or "サーキット" in q_lower:
            issues = [i for i in issues if i["category"] == "circuit_breaker"]
        elif "autoscal" in q_lower or "スケール" in q_lower:
            issues = [i for i in issues if i["category"] == "autoscaling"]
        elif "failover" in q_lower or "フェイルオーバー" in q_lower:
            issues = [i for i in issues if i["category"] == "failover"]

        # Deduplicate
        seen: set[str] = set()
        unique: list[dict] = []
        for iss in issues:
            key = f"{iss['component']}:{iss['issue']}"
            if key not in seen:
                seen.add(key)
                unique.append(iss)
        issues = unique

        if not issues:
            return ChatResponse(
                text="All components have the checked configurations in place.",
                intent=ChatIntent.CONFIGURATION_CHECK,
                data={"issues": []},
                suggestions=["Show me my infrastructure overview", "What's my availability?"],
            )

        lines = [f"**Found {len(issues)} configuration issue(s):**\n"]
        lines.append("| Component | Issue | Category |")
        lines.append("|-----------|-------|----------|")
        for iss in issues:
            lines.append(f"| {iss['component']} | {iss['issue']} | {iss['category']} |")

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.CONFIGURATION_CHECK,
            data={"issues": issues},
            suggestions=[
                "How can I fix these issues?",
                "What are my single points of failure?",
            ],
            visualization="table",
        )

    def _handle_comparison(self, question: str, graph: InfraGraph) -> ChatResponse:
        # Try to find two components to compare
        refs: list[str] = []
        q_lower = question.lower()
        for comp in graph.components.values():
            for candidate in [comp.id.lower(), comp.name.lower()]:
                if candidate in q_lower and comp.id not in refs:
                    refs.append(comp.id)
                    break

        if len(refs) < 2:
            return ChatResponse(
                text=(
                    "Please mention two components to compare. For example:\n"
                    "*\"Compare web-server and app-server\"*"
                ),
                intent=ChatIntent.COMPARISON,
                suggestions=[
                    "Show me my components",
                    "What's my infrastructure overview?",
                ],
            )

        comp_a = graph.get_component(refs[0])
        comp_b = graph.get_component(refs[1])
        if not comp_a or not comp_b:
            return ChatResponse(
                text="Could not find both components.",
                intent=ChatIntent.COMPARISON,
            )

        avail_a = _component_effective_availability(comp_a)
        avail_b = _component_effective_availability(comp_b)

        lines = [f"**Comparing `{comp_a.name}` vs `{comp_b.name}`**\n"]
        lines.append(f"| Attribute | {comp_a.name} | {comp_b.name} |")
        lines.append("|-----------|---|---|")
        lines.append(f"| Type | {comp_a.type.value} | {comp_b.type.value} |")
        lines.append(f"| Replicas | {comp_a.replicas} | {comp_b.replicas} |")
        lines.append(f"| Availability | {avail_a * 100:.4f}% | {avail_b * 100:.4f}% |")
        lines.append(f"| Autoscaling | {'Yes' if comp_a.autoscaling.enabled else 'No'} | {'Yes' if comp_b.autoscaling.enabled else 'No'} |")
        lines.append(f"| Failover | {'Yes' if comp_a.failover.enabled else 'No'} | {'Yes' if comp_b.failover.enabled else 'No'} |")
        lines.append(f"| Dependents | {len(graph.get_dependents(comp_a.id))} | {len(graph.get_dependents(comp_b.id))} |")

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.COMPARISON,
            data={"components": [comp_a.id, comp_b.id]},
            suggestions=[
                f"What happens if {comp_a.name} goes down?",
                f"What happens if {comp_b.name} goes down?",
            ],
            visualization="table",
        )

    def _handle_recommendation(self, question: str, graph: InfraGraph) -> ChatResponse:
        scored = graph.resilience_score_v2()
        recs = scored.get("recommendations", [])

        if not recs:
            return ChatResponse(
                text="Your infrastructure looks well-configured. No urgent recommendations at this time.",
                intent=ChatIntent.RECOMMENDATION,
                data={"score": scored["score"]},
                suggestions=[
                    "Show me my availability",
                    "What's my infrastructure status?",
                ],
            )

        lines = [f"**Recommendations for improving resilience (score: {scored['score']}/100):**\n"]
        for i, rec in enumerate(recs[:10], 1):
            lines.append(f"{i}. {rec}")

        suggestions = [
            "What are my single points of failure?",
            "What's my current availability?",
        ]

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.RECOMMENDATION,
            data={"score": scored["score"], "recommendations": recs[:10]},
            suggestions=suggestions,
        )

    def _handle_incident(self, question: str, graph: InfraGraph) -> ChatResponse:
        # Check if a specific region/zone is mentioned
        q_lower = question.lower()

        region_match = re.search(
            r"(us-east-1|us-west-2|eu-west-1|ap-northeast-1|ap-southeast-1)", q_lower
        )

        if region_match:
            region = region_match.group(1)
            affected_comps = [
                comp for comp in graph.components.values()
                if comp.region.region.lower() == region or comp.region.availability_zone.lower().startswith(region)
            ]
            if affected_comps:
                lines = [f"**Impact of `{region}` outage:**\n"]
                lines.append(f"{len(affected_comps)} component(s) in this region:\n")
                for comp in affected_comps:
                    lines.append(f"- `{comp.name}` ({comp.type.value})")
            else:
                lines = [f"No components found in region `{region}`."]
        else:
            # General incident analysis - find most impactful failures
            impacts: list[tuple[int, Component]] = []
            for comp in graph.components.values():
                affected = graph.get_all_affected(comp.id)
                impacts.append((len(affected), comp))
            impacts.sort(key=lambda x: x[0], reverse=True)

            lines = ["**Potential Incident Impact Analysis:**\n"]
            lines.append("The following components would cause the largest cascading failures:\n")
            lines.append("| Component | Affected Components | Impact % |")
            lines.append("|-----------|-------------------|----------|")
            total = len(graph.components)
            for count, comp in impacts[:5]:
                pct = count / total * 100 if total > 0 else 0
                lines.append(f"| {comp.name} | {count} | {pct:.0f}% |")

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.INCIDENT_IMPACT,
            suggestions=[
                "What are my single points of failure?",
                "How can I improve my disaster recovery?",
            ],
            visualization="table",
        )

    def _handle_status(self, question: str, graph: InfraGraph) -> ChatResponse:
        summary = graph.summary()
        scored = graph.resilience_score_v2()
        sys_avail = _system_availability(graph)
        sys_nines = _to_nines(sys_avail)

        # Count SPOFs
        spof_count = sum(
            1 for comp in graph.components.values()
            if comp.replicas <= 1 and len(graph.get_dependents(comp.id)) > 0
        )

        score = scored["score"]
        if score >= 80:
            health_emoji = "Good"
        elif score >= 60:
            health_emoji = "Moderate"
        else:
            health_emoji = "Needs Attention"

        lines = ["**Infrastructure Overview**\n"]
        lines.append(f"- **Total Components:** {summary['total_components']}")
        lines.append(f"- **Total Dependencies:** {summary['total_dependencies']}")
        lines.append(f"- **Resilience Score:** {score}/100 ({health_emoji})")
        lines.append(f"- **System Availability:** {sys_avail * 100:.4f}% ({sys_nines:.2f} nines)")
        lines.append(f"- **Single Points of Failure:** {spof_count}")

        if summary.get("component_types"):
            lines.append("\n**Component Types:**\n")
            for ctype, count in summary["component_types"].items():
                lines.append(f"- {ctype}: {count}")

        return ChatResponse(
            text="\n".join(lines),
            intent=ChatIntent.GENERAL_STATUS,
            data={"summary": summary, "score": score},
            suggestions=[
                "What are my single points of failure?",
                "How many nines can I achieve?",
                "What improvements do you recommend?",
            ],
        )

    def _handle_help(self, question: str, graph: InfraGraph) -> ChatResponse:
        text = textwrap.dedent("""\
            **FaultZero Infrastructure Chat**

            I can answer questions about your infrastructure. Here are some things you can ask:

            **Single Points of Failure:**
            - "What are my SPOFs?"
            - "Show me single points of failure"

            **Cascade Analysis:**
            - "What happens if [component] goes down?"
            - "Which components are affected if [component] fails?"

            **Availability:**
            - "How many nines can I achieve?"
            - "What's my system availability?"

            **Risk Assessment:**
            - "What's my most critical component?"
            - "Show me a risk assessment"

            **Configuration:**
            - "Which components don't have circuit breakers?"
            - "Show me components without autoscaling"

            **Recommendations:**
            - "How can I improve my infrastructure?"
            - "What do you recommend?"

            **Japanese is also supported:**
            - "SPOFはどこにある？"
            - "一番リスクの高いコンポーネントは？"
        """)

        return ChatResponse(
            text=text,
            intent=ChatIntent.HELP,
            suggestions=self.get_suggestions(graph),
        )

    def _handle_unknown(self, question: str, graph: InfraGraph) -> ChatResponse:
        return ChatResponse(
            text=(
                "I'm not sure how to answer that. "
                "Try asking about single points of failure, availability, "
                "cascade analysis, or type **help** to see what I can do."
            ),
            intent=ChatIntent.UNKNOWN,
            suggestions=self.get_suggestions(graph),
        )


# Avoid importing textwrap at module level only when needed inside methods
import textwrap as textwrap  # noqa: E402 — already imported at top
