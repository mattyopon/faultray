# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""External SaaS Dependency Impact Analyzer.

Simulates "what happens if Stripe goes down?" by analyzing which components
depend on each external API and estimating blast radius + business impact.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultray.model.components import ComponentType
from faultray.model.graph import InfraGraph


@dataclass
class ExternalImpact:
    """Impact analysis for a single external service outage."""

    external_service: str          # e.g., "Stripe API"
    component_id: str              # the external_api component id
    affected_components: list[str] # cascade-affected component ids
    blast_radius_percent: float    # percentage of total infra affected
    estimated_downtime_minutes: float
    business_impact: str           # e.g., "payment processing stops"
    mitigation: str                # e.g., "circuit breaker + fallback queue"
    has_fallback: bool             # whether the dependency has a circuit breaker
    risk_level: str                # "critical", "high", "medium", "low"


@dataclass
class ExternalDependencyReport:
    """Aggregated report of all external SaaS dependency risks."""

    impacts: list[ExternalImpact] = field(default_factory=list)
    total_external_deps: int = 0
    unprotected_count: int = 0     # external deps with no circuit breaker
    risk_score: float = 0.0        # 0-100, higher = riskier
    summary: str = ""


# ---------------------------------------------------------------------------
# Business impact descriptions per known SaaS
# ---------------------------------------------------------------------------

_BUSINESS_IMPACT_MAP: dict[str, str] = {
    "stripe": "payment processing stops — no new revenue",
    "paypal": "payment processing stops — checkout disabled",
    "braintree": "payment processing stops — transaction failures",
    "s3": "object storage unavailable — file uploads/downloads fail",
    "aws s3": "object storage unavailable — file uploads/downloads fail",
    "sendgrid": "transactional email delivery halted — notifications fail",
    "mailgun": "email delivery halted — notifications fail",
    "twilio": "SMS and voice services unavailable",
    "auth0": "authentication fails — users cannot log in",
    "okta": "SSO and identity services unavailable",
    "datadog": "monitoring and alerting go dark",
    "pagerduty": "incident alerting unavailable",
    "github": "CI/CD pipelines and code collaboration unavailable",
    "gitlab": "CI/CD pipelines and code collaboration unavailable",
    "slack": "team communication and alerting integrations fail",
    "firebase": "real-time database and authentication unavailable",
    "supabase": "database and auth services unavailable",
    "cloudflare": "CDN and DDoS protection unavailable — global latency spikes",
    "algolia": "search functionality unavailable",
    "intercom": "customer chat and support unavailable",
    "zendesk": "customer support ticketing unavailable",
    "segment": "analytics event pipeline fails",
    "mixpanel": "product analytics unavailable",
    "amplitude": "product analytics unavailable",
    "openai": "AI features unavailable",
    "anthropic": "AI features unavailable",
}

_MITIGATION_MAP: dict[str, str] = {
    "stripe": "circuit breaker + fallback queue for async retry, show maintenance page",
    "paypal": "circuit breaker + fallback to alternative payment provider",
    "braintree": "circuit breaker + retry queue with exponential backoff",
    "s3": "circuit breaker + local disk buffer, CDN cache fallback",
    "aws s3": "circuit breaker + local disk buffer, CDN cache fallback",
    "sendgrid": "circuit breaker + secondary MTA fallback (SES/Mailgun)",
    "mailgun": "circuit breaker + secondary MTA fallback (SES/SendGrid)",
    "twilio": "circuit breaker + alternative SMS provider",
    "auth0": "circuit breaker + local JWT cache, graceful degradation",
    "okta": "circuit breaker + local session cache for existing users",
    "datadog": "circuit breaker + local log buffer, flush on recovery",
    "pagerduty": "circuit breaker + email/SMS fallback alerting",
    "github": "local git mirror, manual deploy fallback",
    "cloudflare": "multi-CDN failover, DNS TTL reduction",
    "openai": "circuit breaker + model fallback or degraded-mode response",
    "anthropic": "circuit breaker + model fallback or degraded-mode response",
}

_DEFAULT_BUSINESS_IMPACT = "service degradation — dependent features unavailable"
_DEFAULT_MITIGATION = "circuit breaker + graceful degradation or fallback queue"


def _classify_risk(
    blast_radius_percent: float,
    has_fallback: bool,
    dep_type: str,
) -> str:
    """Classify risk level based on blast radius and protection."""
    if dep_type == "optional":
        if blast_radius_percent >= 50:
            return "medium"
        return "low"

    if not has_fallback:
        if blast_radius_percent >= 50:
            return "critical"
        if blast_radius_percent >= 20:
            return "high"
        return "medium"
    else:
        if blast_radius_percent >= 50:
            return "high"
        if blast_radius_percent >= 20:
            return "medium"
        return "low"


def _estimate_downtime(
    has_fallback: bool,
    dep_type: str,
    affected_count: int,
) -> float:
    """Estimate downtime in minutes based on protection level."""
    if dep_type == "optional":
        return 0.0  # optional: feature degrades, core stays up
    if has_fallback:
        # Circuit breaker: fast fail, partial degradation only
        return 2.0 + affected_count * 0.5
    # No protection: full cascade until external service recovers
    # Typical SaaS incident: 30–120 min, use 60 as base
    return 60.0 + affected_count * 5.0


def _lookup_service_info(service_name: str) -> tuple[str, str]:
    """Look up business impact and mitigation for a known service."""
    key = service_name.lower()
    # Try direct match first, then prefix match
    if key in _BUSINESS_IMPACT_MAP:
        return _BUSINESS_IMPACT_MAP[key], _MITIGATION_MAP.get(key, _DEFAULT_MITIGATION)
    for k in _BUSINESS_IMPACT_MAP:
        if k in key or key in k:
            return _BUSINESS_IMPACT_MAP[k], _MITIGATION_MAP.get(k, _DEFAULT_MITIGATION)
    return _DEFAULT_BUSINESS_IMPACT, _DEFAULT_MITIGATION


class ExternalDependencyAnalyzer:
    """Analyze impact of external SaaS service outages on infrastructure."""

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    def analyze(
        self,
        service_filter: str | None = None,
    ) -> ExternalDependencyReport:
        """Run analysis for all (or a specific) external services.

        Args:
            service_filter: If provided, only analyze the matching service.
                            Matches against component name (case-insensitive).

        Returns:
            ExternalDependencyReport with per-service impacts and summary.
        """
        total_components = len(self._graph.components)
        if total_components == 0:
            return ExternalDependencyReport(
                summary="No components found in the infrastructure model.",
            )

        # Find all external_api components
        external_comps = [
            c for c in self._graph.components.values()
            if c.type == ComponentType.EXTERNAL_API
        ]

        if service_filter:
            sf = service_filter.lower()
            external_comps = [
                c for c in external_comps
                if sf in c.name.lower() or sf in c.id.lower()
            ]

        impacts: list[ExternalImpact] = []
        unprotected = 0

        for ext_comp in external_comps:
            # Find all components that directly depend on this external service
            direct_dependents = self._graph.get_dependents(ext_comp.id)

            # Determine if any direct dependency has a circuit breaker
            has_any_cb = False
            primary_dep_type = "requires"
            for dep_comp in direct_dependents:
                edge = self._graph.get_dependency_edge(dep_comp.id, ext_comp.id)
                if edge:
                    if edge.circuit_breaker.enabled:
                        has_any_cb = True
                    primary_dep_type = edge.dependency_type

            # Get all transitively affected components
            all_affected = self._graph.get_all_affected(ext_comp.id)
            # Exclude the external service itself from the count
            affected_ids = sorted(all_affected - {ext_comp.id})

            blast_radius_pct = (
                len(affected_ids) / total_components * 100.0
                if total_components > 0 else 0.0
            )

            business_impact, mitigation = _lookup_service_info(ext_comp.name)
            downtime = _estimate_downtime(has_any_cb, primary_dep_type, len(affected_ids))
            risk_level = _classify_risk(blast_radius_pct, has_any_cb, primary_dep_type)

            if not has_any_cb and primary_dep_type == "requires":
                unprotected += 1

            impacts.append(ExternalImpact(
                external_service=ext_comp.name,
                component_id=ext_comp.id,
                affected_components=affected_ids,
                blast_radius_percent=round(blast_radius_pct, 1),
                estimated_downtime_minutes=round(downtime, 1),
                business_impact=business_impact,
                mitigation=mitigation,
                has_fallback=has_any_cb,
                risk_level=risk_level,
            ))

        # Sort by risk level, then blast radius
        _risk_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        impacts.sort(key=lambda x: (_risk_order.get(x.risk_level, 4), -x.blast_radius_percent))

        # Compute overall risk score (0-100, higher = riskier)
        if impacts:
            risk_score = _compute_risk_score(impacts, total_components)
        else:
            risk_score = 0.0

        summary = _build_summary(impacts, unprotected, total_components)

        return ExternalDependencyReport(
            impacts=impacts,
            total_external_deps=len(impacts),
            unprotected_count=unprotected,
            risk_score=round(risk_score, 1),
            summary=summary,
        )


def _compute_risk_score(impacts: list[ExternalImpact], total_components: int) -> float:
    """Compute an aggregate risk score (0-100) from individual impacts."""
    _risk_weights = {"critical": 1.0, "high": 0.7, "medium": 0.4, "low": 0.1}
    weighted_sum = sum(
        _risk_weights.get(imp.risk_level, 0.2) * max(imp.blast_radius_percent, 1.0)
        for imp in impacts
    )
    # Normalise: max possible is 100 * num_impacts * 1.0
    max_possible = 100.0 * len(impacts)
    score = (weighted_sum / max_possible * 100.0) if max_possible > 0 else 0.0
    return min(100.0, score)


def _build_summary(
    impacts: list[ExternalImpact],
    unprotected: int,
    total_components: int,
) -> str:
    if not impacts:
        return "No external SaaS dependencies found."

    critical = sum(1 for i in impacts if i.risk_level == "critical")
    high = sum(1 for i in impacts if i.risk_level == "high")

    parts = [
        f"{len(impacts)} external service(s) analyzed.",
        f"{unprotected} unprotected (no circuit breaker).",
    ]
    if critical:
        parts.append(f"{critical} CRITICAL risk.")
    if high:
        parts.append(f"{high} HIGH risk.")
    return " ".join(parts)
