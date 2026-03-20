# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""DORA Article 45 — Information Sharing Arrangements Engine.

Implements the cyber threat intelligence sharing framework required by
DORA (Digital Operational Resilience Act) Article 45: financial entities
are encouraged to share cyber threat information and intelligence between
themselves voluntarily, within trusted communities, and with competent
authorities.

Key capabilities:
- Define and manage sharing arrangements (ISACs, bilateral, regulatory)
- TLP (Traffic Light Protocol) classification for shared information
- Import and map Threat Indicators (IOCs) to infrastructure components
- Assess exposure to shared threat intelligence
- Sharing readiness assessment against DORA Art. 45 requirements
- Anonymisation engine for outbound incident reports (GDPR-compliant)
"""

from __future__ import annotations

import hashlib
import re
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class TLPLevel(str, Enum):
    """Traffic Light Protocol (TLP) classification levels.

    Standardised colour-coded framework for controlling the distribution
    of sensitive information within the cybersecurity community.
    """

    WHITE = "white"      # Unrestricted; can be shared publicly
    GREEN = "green"      # Community-wide sharing within sector
    AMBER = "amber"      # Limited to recipient organisation and partners
    RED = "red"          # Strictly need-to-know; not for further sharing


class SharingChannelType(str, Enum):
    """Type of information sharing channel or arrangement."""

    ISAC = "isac"                     # Information Sharing and Analysis Center
    BILATERAL = "bilateral"           # Direct agreement with another entity
    REGULATORY = "regulatory"         # Mandatory reporting to competent authority
    CERT = "cert"                     # Computer Emergency Response Team
    SECTOR_GROUP = "sector_group"     # Sector-level working group


class ArrangementStatus(str, Enum):
    """Lifecycle state of a sharing arrangement."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    TERMINATED = "terminated"


class ThreatIndicatorType(str, Enum):
    """IOC (Indicator of Compromise) type taxonomy."""

    IP_ADDRESS = "ip_address"
    DOMAIN = "domain"
    URL = "url"
    FILE_HASH = "file_hash"
    EMAIL = "email"
    CVE = "cve"
    TECHNIQUE = "technique"       # MITRE ATT&CK technique ID
    MALWARE_FAMILY = "malware_family"
    VULNERABILITY = "vulnerability"


class ThreatSeverity(str, Enum):
    """Severity classification for a threat indicator."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class ReadinessStatus(str, Enum):
    """Compliance readiness level for DORA Art. 45."""

    COMPLIANT = "compliant"
    PARTIALLY_COMPLIANT = "partially_compliant"
    NON_COMPLIANT = "non_compliant"
    NOT_ASSESSED = "not_assessed"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class SharingArrangement(BaseModel):
    """A formal cyber threat information sharing arrangement.

    Represents the documented agreement governing what information is shared,
    with whom, under which protocol, and at which confidentiality level.
    This is the core artefact required to demonstrate DORA Art. 45 compliance.
    """

    arrangement_id: str = Field(default_factory=lambda: f"ARR-{uuid.uuid4().hex[:8].upper()}")
    name: str
    channel_type: SharingChannelType
    partner_name: str
    partner_contact: str = ""
    scope: str = ""                          # Free-text scope description
    tlp_level: TLPLevel = TLPLevel.AMBER
    status: ArrangementStatus = ArrangementStatus.ACTIVE

    # Information categories that may be shared
    shares_iocs: bool = True
    shares_incident_reports: bool = False
    shares_vulnerability_intel: bool = True
    shares_threat_actor_profiles: bool = False

    # Governance
    effective_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    effective_to: datetime | None = None
    approved_by: str = ""
    review_frequency_days: int = 365
    last_reviewed: datetime | None = None
    gdpr_dpa_reference: str = ""          # Data Processing Agreement reference

    @property
    def is_active(self) -> bool:
        if self.status != ArrangementStatus.ACTIVE:
            return False
        now = datetime.now(timezone.utc)
        if self.effective_to and now > self.effective_to:
            return False
        return True

    @property
    def is_overdue_review(self) -> bool:
        if self.last_reviewed is None:
            return True
        threshold = self.last_reviewed + timedelta(days=self.review_frequency_days)
        return datetime.now(timezone.utc) > threshold


class ThreatIndicator(BaseModel):
    """A single threat indicator (IOC) received from a sharing arrangement.

    Maps to the types of intelligence described in DORA Article 45(2):
    cyber threat tactics, techniques, procedures, alerts, and tooling.
    """

    indicator_id: str = Field(default_factory=lambda: f"IOC-{uuid.uuid4().hex[:8].upper()}")
    indicator_type: ThreatIndicatorType
    value: str                              # The actual indicator value (IP, hash, CVE ID, etc.)
    severity: ThreatSeverity = ThreatSeverity.MEDIUM
    tlp_level: TLPLevel = TLPLevel.AMBER
    source_arrangement_id: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: datetime | None = None
    mitre_technique_ids: list[str] = Field(default_factory=list)

    # Mapping to affected infra (populated by exposure analysis)
    affected_component_ids: list[str] = Field(default_factory=list)

    @property
    def is_expired(self) -> bool:
        if self.valid_until is None:
            return False
        return datetime.now(timezone.utc) > self.valid_until

    @property
    def is_active(self) -> bool:
        return not self.is_expired


class ExposureMapping(BaseModel):
    """Maps a threat indicator to specific infrastructure components."""

    indicator_id: str
    component_id: str
    component_name: str
    exposure_reason: str
    severity: ThreatSeverity


class SharingReadiness(BaseModel):
    """DORA Article 45 sharing readiness assessment for the organisation.

    Evaluates whether the organisation has the arrangements, documentation,
    and active participation required to comply with Art. 45.
    """

    assessment_id: str = Field(default_factory=lambda: f"SR-{uuid.uuid4().hex[:8].upper()}")
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    overall_status: ReadinessStatus = ReadinessStatus.NOT_ASSESSED

    # Arrangement coverage
    total_arrangements: int = 0
    active_arrangements: int = 0
    has_isac_membership: bool = False
    has_regulatory_reporting: bool = False
    has_documented_scope: bool = False
    has_approved_arrangements: bool = False
    has_tlp_policy: bool = False

    # Intelligence quality
    total_indicators_received: int = 0
    total_indicators_shared: int = 0
    active_indicators: int = 0
    exposure_count: int = 0

    # Compliance gaps and recommendations
    gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    compliance_score: float = Field(ge=0.0, le=1.0, default=0.0)


class AnonymizationRule(BaseModel):
    """A single rule in the anonymisation engine.

    Defines what data pattern to strip/replace before sharing incident
    information externally.
    """

    rule_id: str = Field(default_factory=lambda: f"ANON-{uuid.uuid4().hex[:8].upper()}")
    name: str
    pattern: str          # Regex pattern to match sensitive data
    replacement: str      # Replacement token (e.g. "[REDACTED_IP]")
    enabled: bool = True
    applies_to_fields: list[str] = Field(default_factory=list)  # Empty = all fields


class AnonymizedIncident(BaseModel):
    """An incident report that has been anonymised for external sharing.

    Produced by the anonymisation engine after stripping sensitive fields
    per the configured rules and GDPR obligations.
    """

    anonymized_id: str = Field(default_factory=lambda: f"ANON-INC-{uuid.uuid4().hex[:8].upper()}")
    source_incident_id: str
    shared_via_arrangement_id: str = ""
    tlp_level: TLPLevel = TLPLevel.AMBER
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Anonymised content
    incident_date: str = ""              # Date only, no time
    affected_sector: str = ""
    attack_vector: str = ""
    impact_description: str = ""
    indicators: list[ThreatIndicator] = Field(default_factory=list)
    lessons_for_community: list[str] = Field(default_factory=list)
    mitre_techniques: list[str] = Field(default_factory=list)

    # Provenance
    rules_applied: list[str] = Field(default_factory=list)
    gdpr_basis: str = "legitimate interest — threat information sharing (DORA Art. 45)"


# ---------------------------------------------------------------------------
# Default anonymisation rules
# ---------------------------------------------------------------------------

_DEFAULT_ANON_RULES: list[dict] = [
    {
        "name": "IPv4 addresses",
        "pattern": r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "replacement": "[REDACTED_IP]",
    },
    {
        "name": "IPv6 addresses",
        "pattern": r"\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b",
        "replacement": "[REDACTED_IPV6]",
    },
    {
        "name": "Hostnames and FQDNs",
        "pattern": r"\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}\b",
        "replacement": "[REDACTED_HOSTNAME]",
    },
    {
        "name": "Email addresses",
        "pattern": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b",
        "replacement": "[REDACTED_EMAIL]",
    },
    {
        "name": "AWS account IDs",
        "pattern": r"\b\d{12}\b",
        "replacement": "[REDACTED_AWS_ACCOUNT]",
    },
    {
        "name": "UUIDs",
        "pattern": r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b",
        "replacement": "[REDACTED_UUID]",
    },
    {
        "name": "API keys and tokens (generic)",
        "pattern": r"(?i)(?:api[_\-]?key|token|secret|password|passwd|pwd)\s*[:=]\s*\S+",
        "replacement": "[REDACTED_CREDENTIAL]",
    },
]


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


class DORAInfoSharingEngine:
    """DORA Article 45 Information Sharing Arrangements Engine.

    Manages the full lifecycle of cyber threat information sharing:
    - Arrangement registration and compliance checking
    - IOC ingestion and infrastructure exposure mapping
    - Sharing readiness assessment
    - Anonymised incident report generation

    Usage::

        engine = DORAInfoSharingEngine(graph)
        engine.add_arrangement(arrangement)
        engine.ingest_indicator(indicator)
        readiness = engine.assess_readiness()
        anon_report = engine.anonymize_incident(raw_incident)
    """

    def __init__(
        self,
        graph: InfraGraph,
        custom_anon_rules: list[AnonymizationRule] | None = None,
    ) -> None:
        self.graph = graph
        self._arrangements: list[SharingArrangement] = []
        self._indicators: list[ThreatIndicator] = []
        self._shared_indicators: list[ThreatIndicator] = []

        # Initialise anonymisation rules
        self._anon_rules: list[AnonymizationRule] = [
            AnonymizationRule(**r) for r in _DEFAULT_ANON_RULES
        ]
        if custom_anon_rules:
            self._anon_rules.extend(custom_anon_rules)

    # ------------------------------------------------------------------
    # Arrangement management
    # ------------------------------------------------------------------

    def add_arrangement(self, arrangement: SharingArrangement) -> None:
        """Register a sharing arrangement."""
        self._arrangements.append(arrangement)

    def get_active_arrangements(self) -> list[SharingArrangement]:
        """Return all currently active sharing arrangements."""
        return [a for a in self._arrangements if a.is_active]

    def get_arrangement(self, arrangement_id: str) -> SharingArrangement | None:
        return next(
            (a for a in self._arrangements if a.arrangement_id == arrangement_id), None
        )

    # ------------------------------------------------------------------
    # Threat indicator ingestion
    # ------------------------------------------------------------------

    def ingest_indicator(self, indicator: ThreatIndicator) -> None:
        """Ingest a threat indicator from a sharing arrangement.

        Automatically maps the indicator to affected infrastructure components.
        """
        self._indicators.append(indicator)
        self._map_indicator_to_components(indicator)

    def ingest_indicators(self, indicators: list[ThreatIndicator]) -> None:
        """Bulk ingest threat indicators."""
        for ind in indicators:
            self.ingest_indicator(ind)

    def _map_indicator_to_components(self, indicator: ThreatIndicator) -> None:
        """Determine which infrastructure components are exposed to this indicator.

        Mapping logic:
        - CVE indicators → check if any component name/tags reference the same tech
        - IP/Domain → check host fields of components
        - Technique → map to all components (organisation-wide exposure)
        """
        affected: list[str] = []

        for comp in self.graph.components.values():
            exposed = False

            if indicator.indicator_type == ThreatIndicatorType.IP_ADDRESS:
                if comp.host and comp.host == indicator.value:
                    exposed = True

            elif indicator.indicator_type == ThreatIndicatorType.DOMAIN:
                if comp.host and indicator.value.lower() in comp.host.lower():
                    exposed = True

            elif indicator.indicator_type in (
                ThreatIndicatorType.CVE,
                ThreatIndicatorType.VULNERABILITY,
            ):
                # Match against component name and tags for technology references
                combined = (comp.name + " " + " ".join(comp.tags)).lower()
                # Strip CVE- prefix to get the year/ID for tag matching
                cve_fragment = indicator.value.lower().replace("cve-", "")
                if cve_fragment in combined or any(
                    tag.lower() in indicator.description.lower()
                    for tag in comp.tags
                ):
                    exposed = True

            elif indicator.indicator_type == ThreatIndicatorType.TECHNIQUE:
                # Techniques are sector-wide — all components are potentially exposed
                if indicator.severity in (ThreatSeverity.CRITICAL, ThreatSeverity.HIGH):
                    exposed = True

            if exposed:
                affected.append(comp.id)

        indicator.affected_component_ids = affected

    def map_exposure(self) -> list[ExposureMapping]:
        """Return all component–indicator exposure mappings across active indicators."""
        mappings: list[ExposureMapping] = []
        for ind in self._indicators:
            if not ind.is_active:
                continue
            for comp_id in ind.affected_component_ids:
                comp = self.graph.get_component(comp_id)
                if comp is None:
                    continue
                mappings.append(ExposureMapping(
                    indicator_id=ind.indicator_id,
                    component_id=comp_id,
                    component_name=comp.name,
                    exposure_reason=f"{ind.indicator_type.value}: {ind.value}",
                    severity=ind.severity,
                ))
        return mappings

    def critical_exposures(self) -> list[ExposureMapping]:
        """Return only critical-severity exposures for immediate attention."""
        return [m for m in self.map_exposure() if m.severity == ThreatSeverity.CRITICAL]

    # ------------------------------------------------------------------
    # Readiness assessment
    # ------------------------------------------------------------------

    def assess_readiness(self) -> SharingReadiness:
        """Evaluate DORA Article 45 sharing readiness.

        Checks whether the organisation has:
        1. At least one active sharing arrangement
        2. ISAC or sector group membership
        3. A regulatory reporting channel
        4. Documented and approved arrangements
        5. A TLP classification policy
        6. Active intelligence exchange (IOCs received and shared)
        """
        active = self.get_active_arrangements()
        gaps: list[str] = []
        recommendations: list[str] = []
        score_components: list[float] = []

        # --- 1. Has any active arrangement? ---
        if not active:
            gaps.append("No active information sharing arrangements are registered.")
            recommendations.append(
                "Join a sector-level ISAC (e.g. FS-ISAC for financial services) "
                "and register the arrangement in the system."
            )
            score_components.append(0.0)
        else:
            score_components.append(1.0)

        # --- 2. ISAC membership ---
        has_isac = any(
            a.channel_type in (SharingChannelType.ISAC, SharingChannelType.SECTOR_GROUP)
            for a in active
        )
        if not has_isac:
            gaps.append("No ISAC or sector group membership detected.")
            recommendations.append(
                "Establish membership in a recognised ISAC aligned with your sector "
                "to fulfil DORA Art. 45(1) community sharing obligations."
            )
            score_components.append(0.0)
        else:
            score_components.append(1.0)

        # --- 3. Regulatory reporting channel ---
        has_regulatory = any(
            a.channel_type == SharingChannelType.REGULATORY for a in active
        )
        if not has_regulatory:
            gaps.append("No regulatory reporting arrangement detected.")
            recommendations.append(
                "Register a regulatory reporting channel for the competent authority "
                "(e.g. national financial supervisor) as required by DORA."
            )
            score_components.append(0.0)
        else:
            score_components.append(1.0)

        # --- 4. Documentation and approval ---
        has_documented = all(bool(a.scope) for a in active)
        has_approved = all(bool(a.approved_by) for a in active)
        if not has_documented:
            gaps.append("Some arrangements lack a documented scope.")
            recommendations.append("Define a clear scope for each sharing arrangement.")
            score_components.append(0.5)
        else:
            score_components.append(1.0)

        if not has_approved:
            gaps.append("Some arrangements have not been approved by management.")
            recommendations.append("Obtain management sign-off on all sharing arrangements.")
            score_components.append(0.5)
        else:
            score_components.append(1.0)

        # --- 5. TLP policy ---
        tlp_levels_used = {a.tlp_level for a in self._arrangements}
        has_tlp = len(tlp_levels_used) > 0
        if not has_tlp:
            gaps.append("No TLP classification has been applied to any arrangement.")
            recommendations.append(
                "Apply TLP classification to all arrangements per FIRST TLP standard."
            )
            score_components.append(0.0)
        else:
            score_components.append(1.0)

        # --- 6. Active intelligence exchange ---
        active_indicators = [i for i in self._indicators if i.is_active]
        if not active_indicators:
            gaps.append("No threat indicators have been received from sharing arrangements.")
            recommendations.append(
                "Configure automated feeds from ISACs/CERTs to receive threat intelligence."
            )
            score_components.append(0.0)
        else:
            score_components.append(1.0)

        if not self._shared_indicators:
            recommendations.append(
                "Begin contributing anonymised incident indicators to your sharing partners."
            )
            score_components.append(0.5)
        else:
            score_components.append(1.0)

        # --- 7. Overdue reviews ---
        overdue = [a for a in self._arrangements if a.is_overdue_review]
        if overdue:
            gaps.append(
                f"{len(overdue)} arrangement(s) are overdue for review "
                f"({', '.join(a.name for a in overdue)})."
            )
            recommendations.append("Review all sharing arrangements on the configured frequency.")

        # --- Aggregate score ---
        compliance_score = sum(score_components) / len(score_components) if score_components else 0.0

        if compliance_score >= 0.85:
            overall = ReadinessStatus.COMPLIANT
        elif compliance_score >= 0.50:
            overall = ReadinessStatus.PARTIALLY_COMPLIANT
        else:
            overall = ReadinessStatus.NON_COMPLIANT

        exposures = self.map_exposure()

        return SharingReadiness(
            overall_status=overall,
            total_arrangements=len(self._arrangements),
            active_arrangements=len(active),
            has_isac_membership=has_isac,
            has_regulatory_reporting=has_regulatory,
            has_documented_scope=has_documented,
            has_approved_arrangements=has_approved,
            has_tlp_policy=has_tlp,
            total_indicators_received=len(self._indicators),
            total_indicators_shared=len(self._shared_indicators),
            active_indicators=len(active_indicators),
            exposure_count=len(exposures),
            gaps=gaps,
            recommendations=recommendations,
            compliance_score=round(compliance_score, 4),
        )

    # ------------------------------------------------------------------
    # Anonymisation engine
    # ------------------------------------------------------------------

    def _apply_anon_rules(self, text: str) -> str:
        """Apply all enabled anonymisation rules to a text string."""
        result = text
        for rule in self._anon_rules:
            if not rule.enabled:
                continue
            try:
                result = re.sub(rule.pattern, rule.replacement, result)
            except re.error:
                pass  # Skip malformed patterns rather than crashing
        return result

    def anonymize_incident(
        self,
        incident_id: str,
        incident_date: datetime,
        affected_sector: str,
        attack_vector: str,
        impact_description: str,
        lessons_for_community: list[str],
        indicators_to_share: list[ThreatIndicator] | None = None,
        arrangement_id: str = "",
        tlp_level: TLPLevel = TLPLevel.AMBER,
    ) -> AnonymizedIncident:
        """Produce an anonymised incident report suitable for external sharing.

        All text fields are processed through the anonymisation engine.
        Sensitive identifiers (IPs, hostnames, credentials) are replaced
        with redaction tokens. GDPR compliance is maintained by design.

        Parameters
        ----------
        incident_id:
            Internal incident identifier (hashed in the output).
        incident_date:
            Datetime of the incident (date-only in output).
        affected_sector:
            Sector description (e.g. "retail banking").
        attack_vector:
            High-level attack vector description.
        impact_description:
            Description of business impact.
        lessons_for_community:
            Key takeaways suitable for sharing with peers.
        indicators_to_share:
            Optional list of IOCs to include (TLP permitting).
        arrangement_id:
            The sharing arrangement under which this report is sent.
        tlp_level:
            TLP classification for the shared report.
        """
        # Hash the internal incident ID so recipients cannot correlate back
        hashed_id = hashlib.sha256(incident_id.encode()).hexdigest()[:16]

        # Anonymise free-text fields
        anon_attack_vector = self._apply_anon_rules(attack_vector)
        anon_impact = self._apply_anon_rules(impact_description)
        anon_lessons = [self._apply_anon_rules(item) for item in lessons_for_community]
        anon_sector = self._apply_anon_rules(affected_sector)

        # Filter indicators by TLP: only share indicators at or below report TLP
        _tlp_order = [TLPLevel.WHITE, TLPLevel.GREEN, TLPLevel.AMBER, TLPLevel.RED]
        report_tlp_idx = _tlp_order.index(tlp_level)

        safe_indicators: list[ThreatIndicator] = []
        if indicators_to_share:
            for ind in indicators_to_share:
                ind_tlp_idx = _tlp_order.index(ind.tlp_level)
                if ind_tlp_idx <= report_tlp_idx:
                    safe_indicators.append(ind)

        # Collect MITRE technique IDs (non-sensitive)
        mitre_techniques = list({
            tid
            for ind in safe_indicators
            for tid in ind.mitre_technique_ids
        })

        # Track shared indicators for readiness metrics
        self._shared_indicators.extend(safe_indicators)

        rules_applied = [r.name for r in self._anon_rules if r.enabled]

        return AnonymizedIncident(
            source_incident_id=f"HASHED:{hashed_id}",
            shared_via_arrangement_id=arrangement_id,
            tlp_level=tlp_level,
            incident_date=incident_date.strftime("%Y-%m-%d"),
            affected_sector=anon_sector,
            attack_vector=anon_attack_vector,
            impact_description=anon_impact,
            indicators=safe_indicators,
            lessons_for_community=anon_lessons,
            mitre_techniques=mitre_techniques,
            rules_applied=rules_applied,
        )

    def add_anon_rule(self, rule: AnonymizationRule) -> None:
        """Register a custom anonymisation rule."""
        self._anon_rules.append(rule)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def export_report(self) -> dict:
        """Export a structured DORA Article 45 compliance report.

        Suitable for serialisation to JSON for regulator submission or
        internal audit purposes.
        """
        readiness = self.assess_readiness()
        exposures = self.map_exposure()
        critical_exp = self.critical_exposures()

        # Summarise indicators by type and severity
        indicator_summary: dict[str, int] = {}
        for ind in self._indicators:
            key = f"{ind.indicator_type.value}/{ind.severity.value}"
            indicator_summary[key] = indicator_summary.get(key, 0) + 1

        return {
            "framework": "DORA",
            "article": "Article 45 — Information Sharing Arrangements",
            "regulation": "EU 2022/2554",
            "export_timestamp": datetime.now(timezone.utc).isoformat(),
            "readiness": readiness.model_dump(),
            "arrangements": [a.model_dump() for a in self._arrangements],
            "threat_indicators": {
                "total": len(self._indicators),
                "active": sum(1 for i in self._indicators if i.is_active),
                "by_type_and_severity": indicator_summary,
            },
            "exposure_analysis": {
                "total_exposures": len(exposures),
                "critical_exposures": len(critical_exp),
                "exposed_components": list({m.component_id for m in exposures}),
            },
            "shared_indicators_count": len(self._shared_indicators),
            "anonymisation_rules": len([r for r in self._anon_rules if r.enabled]),
            "compliance_note": (
                "This report is generated in accordance with DORA Article 45 requirements "
                "for cyber threat information sharing arrangements between financial entities. "
                "All shared data has been anonymised per GDPR Article 6(1)(f) — legitimate "
                "interest — and ENISA TLP standards."
            ),
        }
