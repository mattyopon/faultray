# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""DORA Article 29 — ICT Third-Party Concentration Risk Analysis.

Provides quantitative concentration risk metrics, due diligence frameworks,
and substitutability assessment for ICT third-party providers per DORA
Article 29 requirements.

Regulatory references:
    DORA Regulation (EU) 2022/2554
    Article 28 — General principles of ICT third-party risk management
    Article 29 — Preliminary assessment of ICT concentration risk at entity level
    Article 30 — Key contractual provisions
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from faultray.model.graph import InfraGraph

from faultray.model.components import ComponentType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class RiskRating(str, Enum):
    """Overall risk rating for a provider or concentration dimension."""

    CRITICAL = "critical"    # Immediate action required
    HIGH = "high"            # Significant risk, remediation plan needed
    MEDIUM = "medium"        # Moderate risk, monitoring required
    LOW = "low"              # Acceptable risk level


class ConcentrationDimension(str, Enum):
    """Dimensions of concentration risk per DORA Art. 29."""

    PROVIDER = "provider"          # Single provider handles too many services
    GEOGRAPHIC = "geographic"      # Services concentrated in one jurisdiction
    SERVICE_TYPE = "service_type"  # Critical functions all depend on one provider
    SUBSTITUTABILITY = "substitutability"  # High lock-in, hard to replace


class DueDiligencePhase(str, Enum):
    """Phase in the provider due diligence lifecycle."""

    PRE_CONTRACT = "pre_contract"      # Before engaging a new provider
    ONGOING = "ongoing"                # Periodic monitoring of active providers
    EXIT_ASSESSMENT = "exit_assessment"  # Evaluating exit from a provider


class ChecklistStatus(str, Enum):
    """Status of a due diligence checklist item."""

    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    NOT_APPLICABLE = "not_applicable"
    IN_PROGRESS = "in_progress"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class ProviderServiceMapping(BaseModel):
    """Maps a single ICT provider to the components it supports.

    Used as the primary input to concentration risk calculation.
    If provider information is not set on components, the analyser infers
    providers from component IDs and types.
    """

    provider_name: str
    component_ids: list[str] = Field(default_factory=list)
    geographic_jurisdiction: str = ""  # e.g. "EU", "US", "APAC"
    service_types: list[str] = Field(default_factory=list)  # e.g. ["cloud", "SaaS"]
    is_critical_function_provider: bool = False


class ProviderRiskScore(BaseModel):
    """Risk scoring for a single ICT provider (DORA Art. 29)."""

    provider_name: str
    financial_stability_score: float = 0.0   # 0 (insolvent risk) to 1.0 (stable)
    security_posture_score: float = 0.0      # 0 (poor) to 1.0 (excellent)
    compliance_history_score: float = 0.0   # 0 (breaches) to 1.0 (clean)
    operational_track_record_score: float = 0.0  # 0 (incidents) to 1.0 (flawless)
    overall_risk_score: float = 0.0         # Weighted composite (higher = riskier)
    risk_rating: RiskRating = RiskRating.MEDIUM
    evidence: list[str] = Field(default_factory=list)
    last_assessed: date | None = None

    def compute_overall_score(
        self,
        weights: dict[str, float] | None = None,
    ) -> float:
        """Compute weighted overall risk score (0.0 = low risk, 1.0 = high risk).

        A higher score indicates higher risk (inverse of the individual dimension
        scores, which are rated 0=bad to 1=good).

        Args:
            weights: Optional dict with keys matching score fields. Defaults to
                     equal weighting across the four dimensions.

        Returns:
            Overall risk score in [0.0, 1.0].
        """
        default_weights = {
            "financial_stability_score": 0.30,
            "security_posture_score": 0.30,
            "compliance_history_score": 0.25,
            "operational_track_record_score": 0.15,
        }
        w = weights or default_weights
        total_weight = sum(w.values())
        raw = sum(
            (1.0 - getattr(self, field)) * weight
            for field, weight in w.items()
        ) / total_weight
        self.overall_risk_score = round(min(1.0, max(0.0, raw)), 3)
        # Map to rating
        if self.overall_risk_score >= 0.75:
            self.risk_rating = RiskRating.CRITICAL
        elif self.overall_risk_score >= 0.50:
            self.risk_rating = RiskRating.HIGH
        elif self.overall_risk_score >= 0.25:
            self.risk_rating = RiskRating.MEDIUM
        else:
            self.risk_rating = RiskRating.LOW
        return self.overall_risk_score


class SubstitutabilityAssessment(BaseModel):
    """Substitutability assessment for a single ICT provider (DORA Art. 29).

    Identifies lock-in risk and assesses how easily the provider could
    be replaced in an exit scenario.
    """

    provider_name: str
    ease_of_replacement: float = 0.0  # 0.0 = practically impossible, 1.0 = easy
    estimated_transition_time_months: float = 0.0
    transition_cost_estimate: str = ""  # Free-form cost narrative
    alternative_providers: list[str] = Field(default_factory=list)
    lock_in_factors: list[str] = Field(default_factory=list)
    exit_strategy_documented: bool = False
    is_non_substitutable: bool = False  # True if no viable replacement exists
    substitutability_risk_rating: RiskRating = RiskRating.MEDIUM
    notes: str = ""

    def compute_risk_rating(self) -> RiskRating:
        """Derive substitutability risk rating from ease_of_replacement score."""
        if self.is_non_substitutable or self.ease_of_replacement < 0.2:
            self.substitutability_risk_rating = RiskRating.CRITICAL
        elif self.ease_of_replacement < 0.4:
            self.substitutability_risk_rating = RiskRating.HIGH
        elif self.ease_of_replacement < 0.6:
            self.substitutability_risk_rating = RiskRating.MEDIUM
        else:
            self.substitutability_risk_rating = RiskRating.LOW
        return self.substitutability_risk_rating


class DueDiligenceChecklistItem(BaseModel):
    """A single item in the provider due diligence checklist."""

    item_id: str
    phase: DueDiligencePhase
    category: str  # "financial" | "security" | "operational" | "legal" | "exit"
    description: str
    dora_reference: str = ""
    status: ChecklistStatus = ChecklistStatus.INCOMPLETE
    evidence: str = ""
    notes: str = ""
    next_review_date: date | None = None


class DueDiligenceChecklist(BaseModel):
    """Complete due diligence checklist for a single provider."""

    provider_name: str
    phase: DueDiligencePhase
    items: list[DueDiligenceChecklistItem] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    last_updated: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def completion_rate(self) -> float:
        """Fraction of applicable items completed (0.0 – 1.0)."""
        applicable = [
            i for i in self.items if i.status != ChecklistStatus.NOT_APPLICABLE
        ]
        if not applicable:
            return 1.0
        complete = sum(1 for i in applicable if i.status == ChecklistStatus.COMPLETE)
        return round(complete / len(applicable), 3)


class ProviderRiskProfile(BaseModel):
    """Consolidated risk profile for a single ICT third-party provider.

    Combines provider risk scoring, substitutability assessment, and
    due diligence checklist into one record.
    """

    provider_name: str
    service_mapping: ProviderServiceMapping
    risk_score: ProviderRiskScore = Field(
        default_factory=lambda: ProviderRiskScore(provider_name="")
    )
    substitutability: SubstitutabilityAssessment = Field(
        default_factory=lambda: SubstitutabilityAssessment(provider_name="")
    )
    due_diligence: DueDiligenceChecklist | None = None
    last_reviewed: date | None = None
    next_review_due: date | None = None


class ConcentrationRiskMetrics(BaseModel):
    """Quantitative concentration risk metrics for the organisation.

    DORA Art. 29 requires entities to identify and manage ICT concentration
    risk. This model captures the key quantitative measures.
    """

    # Herfindahl-Hirschman Index (HHI): 0 (perfect competition) to 10000 (monopoly)
    # HHI > 2500 is considered highly concentrated
    hhi_provider_share: float = 0.0
    hhi_interpretation: str = ""

    # Single-provider dependency: % of all ICT services from one provider
    single_provider_dependency_score: float = 0.0  # 0.0 to 1.0
    top_provider: str = ""
    top_provider_service_share_percent: float = 0.0

    # Geographic concentration: % of services in single jurisdiction
    geographic_concentration_percent: float = 0.0
    dominant_jurisdiction: str = ""

    # Service-type concentration: % of critical functions relying on one provider
    critical_function_concentration_percent: float = 0.0
    critical_function_top_provider: str = ""

    # Per-dimension risk ratings
    provider_concentration_risk: RiskRating = RiskRating.LOW
    geographic_concentration_risk: RiskRating = RiskRating.LOW
    service_type_concentration_risk: RiskRating = RiskRating.LOW
    overall_concentration_risk: RiskRating = RiskRating.LOW

    calculated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ConcentrationRiskReport(BaseModel):
    """Complete DORA Art. 29 concentration risk report.

    Aggregates metrics, provider profiles, and recommendations into
    a single exportable report suitable for supervisory review.
    """

    report_id: str
    organisation_name: str = ""
    report_date: date = Field(default_factory=date.today)
    metrics: ConcentrationRiskMetrics = Field(
        default_factory=ConcentrationRiskMetrics
    )
    provider_profiles: list[ProviderRiskProfile] = Field(default_factory=list)
    high_risk_providers: list[str] = Field(default_factory=list)
    non_substitutable_providers: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    overall_risk_rating: RiskRating = RiskRating.LOW
    dora_article_references: list[str] = Field(
        default_factory=lambda: ["DORA Art. 28", "DORA Art. 29", "DORA Art. 30"]
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# ---------------------------------------------------------------------------
# Due diligence checklist definitions
# ---------------------------------------------------------------------------

_DUE_DILIGENCE_ITEMS: list[dict] = [
    # --- Pre-contract ---
    {
        "item_id": "PC-FIN-01",
        "phase": "pre_contract",
        "category": "financial",
        "description": "Provider's financial statements reviewed for last 3 years",
        "dora_reference": "DORA Art. 29(2)(a)",
    },
    {
        "item_id": "PC-FIN-02",
        "phase": "pre_contract",
        "category": "financial",
        "description": "Provider's credit rating and financial stability assessed",
        "dora_reference": "DORA Art. 29(2)(a)",
    },
    {
        "item_id": "PC-SEC-01",
        "phase": "pre_contract",
        "category": "security",
        "description": "Provider's security certifications verified (ISO 27001, SOC 2, or equivalent)",
        "dora_reference": "DORA Art. 29(2)(b)",
    },
    {
        "item_id": "PC-SEC-02",
        "phase": "pre_contract",
        "category": "security",
        "description": "Provider's vulnerability disclosure and incident history reviewed",
        "dora_reference": "DORA Art. 29(2)(b)",
    },
    {
        "item_id": "PC-SEC-03",
        "phase": "pre_contract",
        "category": "security",
        "description": "Provider's data handling and encryption practices assessed",
        "dora_reference": "DORA Art. 30(2)(e)",
    },
    {
        "item_id": "PC-OPS-01",
        "phase": "pre_contract",
        "category": "operational",
        "description": "Provider's operational resilience and SLA track record reviewed",
        "dora_reference": "DORA Art. 29(2)(c)",
    },
    {
        "item_id": "PC-OPS-02",
        "phase": "pre_contract",
        "category": "operational",
        "description": "Provider's business continuity plan reviewed and tested",
        "dora_reference": "DORA Art. 29(2)(c)",
    },
    {
        "item_id": "PC-OPS-03",
        "phase": "pre_contract",
        "category": "operational",
        "description": "Provider's sub-contractors and fourth-party risks identified",
        "dora_reference": "DORA Art. 29(2)(d)",
    },
    {
        "item_id": "PC-LEGAL-01",
        "phase": "pre_contract",
        "category": "legal",
        "description": "Contract includes DORA Art. 30 mandatory provisions (SLA, audit rights, etc.)",
        "dora_reference": "DORA Art. 30",
    },
    {
        "item_id": "PC-LEGAL-02",
        "phase": "pre_contract",
        "category": "legal",
        "description": "Data localisation and cross-border transfer requirements met",
        "dora_reference": "DORA Art. 30(2)(f)",
    },
    {
        "item_id": "PC-LEGAL-03",
        "phase": "pre_contract",
        "category": "legal",
        "description": "Termination and exit provisions are adequate and documented",
        "dora_reference": "DORA Art. 30(2)(j)",
    },
    {
        "item_id": "PC-EXIT-01",
        "phase": "pre_contract",
        "category": "exit",
        "description": "Exit strategy and transition plan documented before contract signing",
        "dora_reference": "DORA Art. 30(2)(j)",
    },
    {
        "item_id": "PC-EXIT-02",
        "phase": "pre_contract",
        "category": "exit",
        "description": "Substitutability assessment completed — alternative providers identified",
        "dora_reference": "DORA Art. 29(4)",
    },
    # --- Ongoing ---
    {
        "item_id": "ON-FIN-01",
        "phase": "ongoing",
        "category": "financial",
        "description": "Annual financial health check on provider completed",
        "dora_reference": "DORA Art. 29(2)(a)",
    },
    {
        "item_id": "ON-SEC-01",
        "phase": "ongoing",
        "category": "security",
        "description": "Provider's security certifications are current and have not lapsed",
        "dora_reference": "DORA Art. 29(2)(b)",
    },
    {
        "item_id": "ON-SEC-02",
        "phase": "ongoing",
        "category": "security",
        "description": "Provider's major incidents reviewed and impact on our services assessed",
        "dora_reference": "DORA Art. 29(2)(b)",
    },
    {
        "item_id": "ON-OPS-01",
        "phase": "ongoing",
        "category": "operational",
        "description": "Provider SLA performance reviewed against contractual targets",
        "dora_reference": "DORA Art. 29(2)(c)",
    },
    {
        "item_id": "ON-OPS-02",
        "phase": "ongoing",
        "category": "operational",
        "description": "Concentration risk metrics recalculated and within acceptable thresholds",
        "dora_reference": "DORA Art. 29",
    },
    {
        "item_id": "ON-EXIT-01",
        "phase": "ongoing",
        "category": "exit",
        "description": "Exit strategy reviewed and updated for material changes",
        "dora_reference": "DORA Art. 30(2)(j)",
    },
    # --- Exit assessment ---
    {
        "item_id": "EXIT-01",
        "phase": "exit_assessment",
        "category": "operational",
        "description": "Transition plan documented and tested via tabletop exercise",
        "dora_reference": "DORA Art. 30(2)(j)",
    },
    {
        "item_id": "EXIT-02",
        "phase": "exit_assessment",
        "category": "operational",
        "description": "Data portability and migration requirements assessed",
        "dora_reference": "DORA Art. 30(2)(i)",
    },
    {
        "item_id": "EXIT-03",
        "phase": "exit_assessment",
        "category": "exit",
        "description": "Alternative provider selection process initiated",
        "dora_reference": "DORA Art. 29(4)",
    },
    {
        "item_id": "EXIT-04",
        "phase": "exit_assessment",
        "category": "legal",
        "description": "Contract termination timeline and notice period confirmed",
        "dora_reference": "DORA Art. 30(2)(j)",
    },
]


def _build_due_diligence_checklist(
    provider_name: str,
    phase: DueDiligencePhase,
) -> DueDiligenceChecklist:
    """Build a due diligence checklist for *provider_name* in *phase*."""
    items = [
        DueDiligenceChecklistItem(provider_name=provider_name, **item)  # type: ignore[call-arg]
        for item in _DUE_DILIGENCE_ITEMS
        if item["phase"] == phase.value
    ]
    return DueDiligenceChecklist(
        provider_name=provider_name,
        phase=phase,
        items=items,
    )


# ---------------------------------------------------------------------------
# Concentration Risk Analyser
# ---------------------------------------------------------------------------


class ConcentrationRiskAnalyser:
    """Analyse DORA Art. 29 ICT third-party concentration risk from InfraGraph.

    Derives provider mappings from component metadata, computes HHI and
    other concentration metrics, and generates a full risk report with
    recommendations.

    Usage::

        from faultray.model.graph import InfraGraph
        from faultray.simulator.dora_concentration_risk import ConcentrationRiskAnalyser

        graph = InfraGraph.load(Path("infra.json"))
        analyser = ConcentrationRiskAnalyser(graph, organisation_name="Acme Bank")
        report = analyser.generate_report()
    """

    # HHI thresholds (US DOJ / competition authority standards)
    _HHI_LOW_THRESHOLD = 1500
    _HHI_MODERATE_THRESHOLD = 2500

    def __init__(
        self,
        graph: "InfraGraph",
        provider_mappings: list[ProviderServiceMapping] | None = None,
        organisation_name: str = "",
    ) -> None:
        """
        Args:
            graph: The InfraGraph to analyse.
            provider_mappings: Optional explicit provider→component mappings.
                If not provided, mappings are inferred from component metadata.
            organisation_name: Name of the financial entity (for report metadata).
        """
        self.graph = graph
        self.organisation_name = organisation_name
        self._provider_mappings = provider_mappings or self._infer_provider_mappings()

    def _infer_provider_mappings(self) -> list[ProviderServiceMapping]:
        """Infer provider mappings from component types when not explicitly provided.

        Groups EXTERNAL_API components by name prefix as separate providers.
        All non-external components are grouped under an internal provider.
        This is a best-effort inference; explicit mappings are preferred.
        """
        external_components: dict[str, list[str]] = {}
        internal_components: list[str] = []

        for comp in self.graph.components.values():
            if comp.type == ComponentType.EXTERNAL_API:
                # Use first word of name as provider proxy
                provider_key = comp.name.split()[0].lower() if comp.name else "external"
                external_components.setdefault(provider_key, []).append(comp.id)
            else:
                internal_components.append(comp.id)

        mappings: list[ProviderServiceMapping] = []
        for provider_key, comp_ids in external_components.items():
            mappings.append(
                ProviderServiceMapping(
                    provider_name=provider_key,
                    component_ids=comp_ids,
                    geographic_jurisdiction="unknown",
                    service_types=["external_api"],
                    is_critical_function_provider=False,
                )
            )
        if internal_components:
            mappings.append(
                ProviderServiceMapping(
                    provider_name="internal",
                    component_ids=internal_components,
                    geographic_jurisdiction="EU",  # Default assumption
                    service_types=["internal_ict"],
                    is_critical_function_provider=True,
                )
            )
        return mappings

    # ------------------------------------------------------------------
    # Metric computation
    # ------------------------------------------------------------------

    def compute_hhi(self) -> float:
        """Compute the Herfindahl-Hirschman Index for provider market share.

        HHI = Σ (s_i)^2  where s_i is the share of each provider in
        percentage points (0–100).

        Scale: 0 (perfect competition) to 10,000 (monopoly).
        Thresholds:
            < 1,500 : unconcentrated
            1,500–2,500 : moderately concentrated
            > 2,500 : highly concentrated
        """
        total_services = sum(
            len(m.component_ids) for m in self._provider_mappings
        )
        if total_services == 0:
            return 0.0
        hhi = sum(
            (len(m.component_ids) / total_services * 100) ** 2
            for m in self._provider_mappings
        )
        return round(hhi, 1)

    def _interpret_hhi(self, hhi: float) -> str:
        if hhi < self._HHI_LOW_THRESHOLD:
            return f"HHI={hhi:.0f}: Unconcentrated provider landscape (threshold <1500)."
        if hhi < self._HHI_MODERATE_THRESHOLD:
            return (
                f"HHI={hhi:.0f}: Moderately concentrated (1500–2500). "
                "Consider provider diversification."
            )
        return (
            f"HHI={hhi:.0f}: HIGHLY concentrated (>2500). "
            "Significant DORA Art. 29 concentration risk. Immediate diversification required."
        )

    def _compute_provider_share(self) -> dict[str, float]:
        """Return {provider_name: share_percent} for all providers."""
        total = sum(len(m.component_ids) for m in self._provider_mappings)
        if total == 0:
            return {}
        return {
            m.provider_name: round(len(m.component_ids) / total * 100.0, 1)
            for m in self._provider_mappings
        }

    def _compute_geographic_concentration(self) -> tuple[float, str]:
        """Return (concentration_percent, dominant_jurisdiction).

        Jurisdiction of 'unknown' components is excluded from the calculation.
        """
        total_known = sum(
            len(m.component_ids)
            for m in self._provider_mappings
            if m.geographic_jurisdiction and m.geographic_jurisdiction != "unknown"
        )
        if total_known == 0:
            return 0.0, "unknown"
        jurisdiction_counts: dict[str, int] = {}
        for m in self._provider_mappings:
            if m.geographic_jurisdiction and m.geographic_jurisdiction != "unknown":
                jur = m.geographic_jurisdiction
                jurisdiction_counts[jur] = jurisdiction_counts.get(jur, 0) + len(m.component_ids)
        if not jurisdiction_counts:
            return 0.0, "unknown"
        dominant = max(jurisdiction_counts, key=lambda j: jurisdiction_counts[j])
        pct = round(jurisdiction_counts[dominant] / total_known * 100.0, 1)
        return pct, dominant

    def _compute_critical_function_concentration(self) -> tuple[float, str]:
        """Return (concentration_percent, top_provider) for critical functions."""
        critical_mappings = [
            m for m in self._provider_mappings if m.is_critical_function_provider
        ]
        if not critical_mappings:
            return 0.0, ""
        total_critical = sum(len(m.component_ids) for m in critical_mappings)
        if total_critical == 0:
            return 0.0, ""
        top = max(critical_mappings, key=lambda m: len(m.component_ids))
        pct = round(len(top.component_ids) / total_critical * 100.0, 1)
        return pct, top.provider_name

    def _rate_concentration(self, pct: float) -> RiskRating:
        """Rate a concentration percentage as a RiskRating."""
        if pct >= 80.0:
            return RiskRating.CRITICAL
        if pct >= 60.0:
            return RiskRating.HIGH
        if pct >= 40.0:
            return RiskRating.MEDIUM
        return RiskRating.LOW

    def _rate_hhi(self, hhi: float) -> RiskRating:
        if hhi >= self._HHI_MODERATE_THRESHOLD:
            return RiskRating.HIGH
        if hhi >= self._HHI_LOW_THRESHOLD:
            return RiskRating.MEDIUM
        return RiskRating.LOW

    def compute_metrics(self) -> ConcentrationRiskMetrics:
        """Compute all concentration risk metrics."""
        hhi = self.compute_hhi()
        provider_shares = self._compute_provider_share()
        top_provider = max(provider_shares, key=lambda k: provider_shares[k], default="")
        top_share = provider_shares.get(top_provider, 0.0)
        geo_pct, dominant_jur = self._compute_geographic_concentration()
        crit_pct, crit_top = self._compute_critical_function_concentration()

        # Single-provider dependency: normalised top share (0–1)
        single_dep_score = round(top_share / 100.0, 3)

        provider_risk = self._rate_hhi(hhi)
        geo_risk = self._rate_concentration(geo_pct)
        svc_type_risk = self._rate_concentration(crit_pct)

        # Overall: take the worst of the three dimensions
        risk_order = [RiskRating.LOW, RiskRating.MEDIUM, RiskRating.HIGH, RiskRating.CRITICAL]
        overall = risk_order[
            max(risk_order.index(r) for r in [provider_risk, geo_risk, svc_type_risk])
        ]

        return ConcentrationRiskMetrics(
            hhi_provider_share=hhi,
            hhi_interpretation=self._interpret_hhi(hhi),
            single_provider_dependency_score=single_dep_score,
            top_provider=top_provider,
            top_provider_service_share_percent=top_share,
            geographic_concentration_percent=geo_pct,
            dominant_jurisdiction=dominant_jur,
            critical_function_concentration_percent=crit_pct,
            critical_function_top_provider=crit_top,
            provider_concentration_risk=provider_risk,
            geographic_concentration_risk=geo_risk,
            service_type_concentration_risk=svc_type_risk,
            overall_concentration_risk=overall,
        )

    # ------------------------------------------------------------------
    # Provider profiles
    # ------------------------------------------------------------------

    def build_provider_profile(
        self,
        mapping: ProviderServiceMapping,
        risk_scores: dict[str, ProviderRiskScore] | None = None,
        substitutability_data: dict[str, SubstitutabilityAssessment] | None = None,
    ) -> ProviderRiskProfile:
        """Build a ProviderRiskProfile for a single provider.

        Args:
            mapping: Provider service mapping.
            risk_scores: Optional pre-assessed risk scores keyed by provider_name.
            substitutability_data: Optional pre-assessed substitutability assessments.

        Returns:
            A ProviderRiskProfile with default scores if external data not provided.
        """
        provider_name = mapping.provider_name

        # Risk score — use provided or build a default
        risk_score = (risk_scores or {}).get(provider_name)
        if risk_score is None:
            risk_score = ProviderRiskScore(
                provider_name=provider_name,
                financial_stability_score=0.5,
                security_posture_score=0.5,
                compliance_history_score=0.5,
                operational_track_record_score=0.5,
                evidence=["Default scores — manual assessment required per DORA Art. 29."],
                last_assessed=None,
            )
            risk_score.compute_overall_score()

        # Substitutability — use provided or derive from mapping
        subst = (substitutability_data or {}).get(provider_name)
        if subst is None:
            alternatives = _default_alternatives_for_provider(mapping)
            ease = 0.7 if alternatives else 0.2
            subst = SubstitutabilityAssessment(
                provider_name=provider_name,
                ease_of_replacement=ease,
                estimated_transition_time_months=6.0 if ease < 0.5 else 3.0,
                alternative_providers=alternatives,
                lock_in_factors=_default_lock_in_factors(mapping),
                exit_strategy_documented=False,
                is_non_substitutable=ease < 0.15,
            )
            subst.compute_risk_rating()

        return ProviderRiskProfile(
            provider_name=provider_name,
            service_mapping=mapping,
            risk_score=risk_score,
            substitutability=subst,
            last_reviewed=None,
        )

    def build_due_diligence_checklist(
        self,
        provider_name: str,
        phase: DueDiligencePhase = DueDiligencePhase.PRE_CONTRACT,
    ) -> DueDiligenceChecklist:
        """Build a DORA Art. 29 due diligence checklist for a provider.

        Args:
            provider_name: Name of the third-party ICT provider.
            phase: The due diligence lifecycle phase.

        Returns:
            A DueDiligenceChecklist populated with items for the requested phase.
        """
        return _build_due_diligence_checklist(provider_name, phase)

    # ------------------------------------------------------------------
    # Substitutability analysis
    # ------------------------------------------------------------------

    def substitutability_analysis(self) -> list[SubstitutabilityAssessment]:
        """Run substitutability analysis for all providers.

        Returns a list of SubstitutabilityAssessment records, sorted by
        risk (most non-substitutable first).
        """
        assessments: list[SubstitutabilityAssessment] = []
        for mapping in self._provider_mappings:
            alternatives = _default_alternatives_for_provider(mapping)
            ease = 0.7 if alternatives else 0.2
            lock_in = _default_lock_in_factors(mapping)
            subst = SubstitutabilityAssessment(
                provider_name=mapping.provider_name,
                ease_of_replacement=ease,
                estimated_transition_time_months=6.0 if ease < 0.5 else 3.0,
                alternative_providers=alternatives,
                lock_in_factors=lock_in,
                exit_strategy_documented=False,
                is_non_substitutable=ease < 0.15,
            )
            subst.compute_risk_rating()
            assessments.append(subst)
        assessments.sort(key=lambda a: a.ease_of_replacement)
        return assessments

    # ------------------------------------------------------------------
    # Recommendations engine
    # ------------------------------------------------------------------

    def _generate_recommendations(
        self,
        metrics: ConcentrationRiskMetrics,
        profiles: list[ProviderRiskProfile],
    ) -> list[str]:
        recs: list[str] = []

        # HHI-based
        if metrics.hhi_provider_share >= self._HHI_MODERATE_THRESHOLD:
            recs.append(
                f"HHI of {metrics.hhi_provider_share:.0f} indicates HIGH concentration. "
                "Diversify ICT service providers to reduce dependency per DORA Art. 29."
            )
        elif metrics.hhi_provider_share >= self._HHI_LOW_THRESHOLD:
            recs.append(
                f"HHI of {metrics.hhi_provider_share:.0f} indicates moderate concentration. "
                "Monitor and plan diversification of providers."
            )

        # Single-provider dependency
        if metrics.top_provider_service_share_percent >= 60.0:
            recs.append(
                f"Provider '{metrics.top_provider}' handles "
                f"{metrics.top_provider_service_share_percent:.1f}% of ICT services. "
                "This exceeds recommended thresholds. Develop a multi-provider strategy."
            )

        # Geographic concentration
        if metrics.geographic_concentration_percent >= 70.0:
            recs.append(
                f"{metrics.geographic_concentration_percent:.1f}% of ICT services are "
                f"concentrated in '{metrics.dominant_jurisdiction}'. "
                "Consider geographic diversification to reduce jurisdictional risk."
            )

        # Critical function concentration
        if metrics.critical_function_concentration_percent >= 60.0:
            recs.append(
                f"{metrics.critical_function_concentration_percent:.1f}% of critical "
                f"ICT functions depend on '{metrics.critical_function_top_provider}'. "
                "Identify alternative providers for critical functions per DORA Art. 29."
            )

        # Per-provider recommendations
        for profile in profiles:
            if profile.risk_score.risk_rating in (RiskRating.CRITICAL, RiskRating.HIGH):
                recs.append(
                    f"Provider '{profile.provider_name}' has "
                    f"{profile.risk_score.risk_rating.value.upper()} risk score "
                    f"({profile.risk_score.overall_risk_score:.2f}). "
                    "Conduct detailed due diligence and consider remediation or replacement."
                )
            if profile.substitutability.is_non_substitutable:
                recs.append(
                    f"Provider '{profile.provider_name}' is assessed as NON-SUBSTITUTABLE. "
                    "Document exit strategy and escalate to risk committee per DORA Art. 29(4)."
                )
            if not profile.substitutability.exit_strategy_documented:
                recs.append(
                    f"Provider '{profile.provider_name}': exit strategy not documented. "
                    "Document per DORA Art. 30(2)(j)."
                )

        # Due diligence gaps
        profiles_without_dd = [p for p in profiles if p.due_diligence is None]
        if profiles_without_dd:
            names = [p.provider_name for p in profiles_without_dd[:3]]
            recs.append(
                f"{len(profiles_without_dd)} provider(s) lack due diligence records "
                f"(e.g. {names}). Complete pre-contract assessments per DORA Art. 29."
            )

        return recs

    # ------------------------------------------------------------------
    # Main report generator
    # ------------------------------------------------------------------

    def generate_report(
        self,
        report_id: str | None = None,
        risk_scores: dict[str, ProviderRiskScore] | None = None,
        substitutability_data: dict[str, SubstitutabilityAssessment] | None = None,
    ) -> ConcentrationRiskReport:
        """Generate a complete DORA Art. 29 concentration risk report.

        Args:
            report_id: Unique report identifier. Auto-generated if not provided.
            risk_scores: Optional pre-assessed ProviderRiskScore objects keyed
                by provider_name. If not provided, default scores are used.
            substitutability_data: Optional pre-assessed SubstitutabilityAssessment
                objects keyed by provider_name. If not provided, defaults are derived.

        Returns:
            ConcentrationRiskReport ready for export or supervisory submission.
        """
        metrics = self.compute_metrics()
        profiles: list[ProviderRiskProfile] = [
            self.build_provider_profile(mapping, risk_scores, substitutability_data)
            for mapping in self._provider_mappings
        ]

        high_risk = [
            p.provider_name
            for p in profiles
            if p.risk_score.risk_rating in (RiskRating.CRITICAL, RiskRating.HIGH)
        ]
        non_subst = [
            p.provider_name
            for p in profiles
            if p.substitutability.is_non_substitutable
        ]

        recommendations = self._generate_recommendations(metrics, profiles)

        auto_report_id = (
            report_id
            or f"CONC-RISK-{self.organisation_name.replace(' ', '-').upper() or 'ORG'}-"
               f"{date.today().strftime('%Y%m%d')}"
        )

        return ConcentrationRiskReport(
            report_id=auto_report_id,
            organisation_name=self.organisation_name,
            report_date=date.today(),
            metrics=metrics,
            provider_profiles=profiles,
            high_risk_providers=high_risk,
            non_substitutable_providers=non_subst,
            recommendations=recommendations,
            overall_risk_rating=metrics.overall_concentration_risk,
        )

    def export_report(self, report: ConcentrationRiskReport) -> dict:
        """Serialise a ConcentrationRiskReport to a flat dict for audit export."""
        return {
            "framework": "DORA",
            "article": "Article 29 — ICT Third-Party Concentration Risk",
            "report_id": report.report_id,
            "organisation": report.organisation_name,
            "report_date": report.report_date.isoformat(),
            "generated_at": report.generated_at.isoformat(),
            "overall_risk_rating": report.overall_risk_rating.value,
            "metrics": report.metrics.model_dump(),
            "provider_count": len(report.provider_profiles),
            "high_risk_providers": report.high_risk_providers,
            "non_substitutable_providers": report.non_substitutable_providers,
            "recommendations": report.recommendations,
            "provider_profiles": [
                {
                    "provider_name": p.provider_name,
                    "component_count": len(p.service_mapping.component_ids),
                    "jurisdiction": p.service_mapping.geographic_jurisdiction,
                    "is_critical_function_provider": p.service_mapping.is_critical_function_provider,
                    "risk_score": p.risk_score.model_dump(),
                    "substitutability": p.substitutability.model_dump(),
                    "due_diligence_completion": (
                        p.due_diligence.completion_rate() if p.due_diligence else None
                    ),
                    "last_reviewed": p.last_reviewed.isoformat() if p.last_reviewed else None,
                }
                for p in report.provider_profiles
            ],
        }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _default_alternatives_for_provider(mapping: ProviderServiceMapping) -> list[str]:
    """Suggest common alternative providers based on service type."""
    service_alternatives: dict[str, list[str]] = {
        "cloud": ["AWS", "Azure", "GCP", "OVHcloud"],
        "saas": ["Alternative SaaS vendor A", "Alternative SaaS vendor B"],
        "external_api": ["Alternative API provider"],
        "internal_ict": [],  # Internal providers have no direct external alternative
    }
    alternatives: list[str] = []
    for svc_type in mapping.service_types:
        alts = service_alternatives.get(svc_type.lower(), [])
        for alt in alts:
            if alt.lower() not in mapping.provider_name.lower() and alt not in alternatives:
                alternatives.append(alt)
    return alternatives[:3]  # Cap at 3 to avoid noise


def _default_lock_in_factors(mapping: ProviderServiceMapping) -> list[str]:
    """Derive common lock-in factors from the service type."""
    factors: list[str] = []
    for svc_type in mapping.service_types:
        if "cloud" in svc_type.lower():
            factors.extend([
                "Proprietary cloud APIs and managed services",
                "Data egress costs make migration expensive",
            ])
        if "saas" in svc_type.lower():
            factors.extend([
                "Data format and integration dependencies",
                "Custom configuration and workflow lock-in",
            ])
        if "internal" in svc_type.lower():
            factors.extend([
                "In-house expertise and tribal knowledge",
                "Bespoke integrations with other systems",
            ])
    return list(dict.fromkeys(factors))  # Deduplicate preserving order
