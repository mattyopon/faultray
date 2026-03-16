"""Data Sovereignty and Residency Compliance Analyzer.

Analyzes data sovereignty compliance risks in infrastructure by mapping data
residency requirements per component and region, detecting cross-border data
flows, mapping jurisdiction requirements (GDPR/CCPA/LGPD), classifying data
types (PII/PHI/financial), verifying replication target region compliance,
analyzing CDN edge location residency, checking backup storage location
compliance, identifying data processing vs storage location gaps, analyzing
third-party data processor jurisdictions, verifying failover target region
compliance, assessing sovereignty impact on architecture, and producing
compliance violation risk scores.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from faultray.model.components import Component, ComponentType, Dependency
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Jurisdiction(str, Enum):
    """Data protection jurisdictions."""

    GDPR = "gdpr"
    CCPA = "ccpa"
    LGPD = "lgpd"
    PIPEDA = "pipeda"
    PDPA = "pdpa"
    APPI = "appi"
    POPIA = "popia"
    NONE = "none"


class DataClassification(str, Enum):
    """Data sensitivity classification levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    PII = "pii"
    PHI = "phi"
    FINANCIAL = "financial"
    PCI = "pci"


class ViolationType(str, Enum):
    """Types of data sovereignty violations."""

    CROSS_BORDER_TRANSFER = "cross_border_transfer"
    RESIDENCY_REQUIREMENT = "residency_requirement"
    REPLICATION_TARGET = "replication_target"
    CDN_EDGE_LOCATION = "cdn_edge_location"
    BACKUP_LOCATION = "backup_location"
    PROCESSING_LOCATION = "processing_location"
    THIRD_PARTY_PROCESSOR = "third_party_processor"
    FAILOVER_TARGET = "failover_target"
    MISSING_DPA = "missing_dpa"
    DATA_CLASSIFICATION_GAP = "data_classification_gap"


class Severity(str, Enum):
    """Violation severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ComplianceStatus(str, Enum):
    """Overall compliance status."""

    COMPLIANT = "compliant"
    PARTIAL = "partial"
    NON_COMPLIANT = "non_compliant"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Region-to-jurisdiction mapping
# ---------------------------------------------------------------------------

_REGION_JURISDICTION: dict[str, list[Jurisdiction]] = {
    # EU / EEA
    "eu-west-1": [Jurisdiction.GDPR],
    "eu-west-2": [Jurisdiction.GDPR],
    "eu-west-3": [Jurisdiction.GDPR],
    "eu-central-1": [Jurisdiction.GDPR],
    "eu-central-2": [Jurisdiction.GDPR],
    "eu-north-1": [Jurisdiction.GDPR],
    "eu-south-1": [Jurisdiction.GDPR],
    "eu-south-2": [Jurisdiction.GDPR],
    "europe-west1": [Jurisdiction.GDPR],
    "europe-west2": [Jurisdiction.GDPR],
    "europe-west3": [Jurisdiction.GDPR],
    "europe-west4": [Jurisdiction.GDPR],
    "europe-north1": [Jurisdiction.GDPR],
    "westeurope": [Jurisdiction.GDPR],
    "northeurope": [Jurisdiction.GDPR],
    # US — California
    "us-west-1": [Jurisdiction.CCPA],
    "us-west-2": [Jurisdiction.CCPA],
    "us-east-1": [Jurisdiction.CCPA],
    "us-east-2": [Jurisdiction.CCPA],
    "us-central1": [Jurisdiction.CCPA],
    "eastus": [Jurisdiction.CCPA],
    "westus": [Jurisdiction.CCPA],
    "centralus": [Jurisdiction.CCPA],
    # Brazil
    "sa-east-1": [Jurisdiction.LGPD],
    "southamerica-east1": [Jurisdiction.LGPD],
    "brazilsouth": [Jurisdiction.LGPD],
    # Canada
    "ca-central-1": [Jurisdiction.PIPEDA],
    "northamerica-northeast1": [Jurisdiction.PIPEDA],
    "canadacentral": [Jurisdiction.PIPEDA],
    # Singapore / Southeast Asia
    "ap-southeast-1": [Jurisdiction.PDPA],
    "asia-southeast1": [Jurisdiction.PDPA],
    "southeastasia": [Jurisdiction.PDPA],
    # Japan
    "ap-northeast-1": [Jurisdiction.APPI],
    "ap-northeast-3": [Jurisdiction.APPI],
    "asia-northeast1": [Jurisdiction.APPI],
    "japaneast": [Jurisdiction.APPI],
    "japanwest": [Jurisdiction.APPI],
    # South Africa
    "af-south-1": [Jurisdiction.POPIA],
    "southafricanorth": [Jurisdiction.POPIA],
    # Other Asia-Pacific
    "ap-south-1": [],
    "ap-southeast-2": [],
    "asia-south1": [],
    "australiaeast": [],
}

# Jurisdiction pairs where cross-border transfer is restricted
_RESTRICTED_TRANSFERS: set[tuple[Jurisdiction, Jurisdiction]] = {
    (Jurisdiction.GDPR, Jurisdiction.CCPA),
    (Jurisdiction.GDPR, Jurisdiction.LGPD),
    (Jurisdiction.GDPR, Jurisdiction.PDPA),
    (Jurisdiction.GDPR, Jurisdiction.APPI),
    (Jurisdiction.GDPR, Jurisdiction.POPIA),
    (Jurisdiction.GDPR, Jurisdiction.PIPEDA),
    (Jurisdiction.GDPR, Jurisdiction.NONE),
    (Jurisdiction.LGPD, Jurisdiction.NONE),
    (Jurisdiction.LGPD, Jurisdiction.CCPA),
    (Jurisdiction.PIPEDA, Jurisdiction.NONE),
    (Jurisdiction.APPI, Jurisdiction.NONE),
    (Jurisdiction.PDPA, Jurisdiction.NONE),
    (Jurisdiction.POPIA, Jurisdiction.NONE),
}

# Severity per violation type
_VIOLATION_SEVERITY: dict[ViolationType, Severity] = {
    ViolationType.CROSS_BORDER_TRANSFER: Severity.CRITICAL,
    ViolationType.RESIDENCY_REQUIREMENT: Severity.CRITICAL,
    ViolationType.REPLICATION_TARGET: Severity.HIGH,
    ViolationType.CDN_EDGE_LOCATION: Severity.MEDIUM,
    ViolationType.BACKUP_LOCATION: Severity.HIGH,
    ViolationType.PROCESSING_LOCATION: Severity.HIGH,
    ViolationType.THIRD_PARTY_PROCESSOR: Severity.MEDIUM,
    ViolationType.FAILOVER_TARGET: Severity.HIGH,
    ViolationType.MISSING_DPA: Severity.MEDIUM,
    ViolationType.DATA_CLASSIFICATION_GAP: Severity.LOW,
}

# Severity weight for risk scoring
_SEVERITY_WEIGHT: dict[Severity, float] = {
    Severity.CRITICAL: 10.0,
    Severity.HIGH: 7.0,
    Severity.MEDIUM: 4.0,
    Severity.LOW: 2.0,
    Severity.INFO: 0.5,
}

# Jurisdiction display names
_JURISDICTION_NAMES: dict[Jurisdiction, str] = {
    Jurisdiction.GDPR: "EU General Data Protection Regulation",
    Jurisdiction.CCPA: "California Consumer Privacy Act",
    Jurisdiction.LGPD: "Lei Geral de Protecao de Dados (Brazil)",
    Jurisdiction.PIPEDA: "Personal Information Protection (Canada)",
    Jurisdiction.PDPA: "Personal Data Protection Act (Singapore)",
    Jurisdiction.APPI: "Act on Protection of Personal Information (Japan)",
    Jurisdiction.POPIA: "Protection of Personal Information Act (South Africa)",
    Jurisdiction.NONE: "No specific data protection regulation",
}

# Remediation suggestions per violation type
_REMEDIATION_SUGGESTIONS: dict[ViolationType, str] = {
    ViolationType.CROSS_BORDER_TRANSFER: (
        "Implement Standard Contractual Clauses (SCCs) or "
        "use region-local endpoints to avoid cross-border data transfers."
    ),
    ViolationType.RESIDENCY_REQUIREMENT: (
        "Move data storage to a region that satisfies the residency "
        "requirement for the applicable jurisdiction."
    ),
    ViolationType.REPLICATION_TARGET: (
        "Configure replication targets within the same jurisdiction "
        "or establish a lawful transfer mechanism."
    ),
    ViolationType.CDN_EDGE_LOCATION: (
        "Restrict CDN edge cache distribution to jurisdictionally "
        "compliant regions or enable geo-fencing."
    ),
    ViolationType.BACKUP_LOCATION: (
        "Store backups in regions that satisfy data residency "
        "requirements; encrypt with jurisdiction-local keys."
    ),
    ViolationType.PROCESSING_LOCATION: (
        "Ensure data processing occurs in the same jurisdiction as "
        "data storage, or obtain explicit consent for remote processing."
    ),
    ViolationType.THIRD_PARTY_PROCESSOR: (
        "Execute a Data Processing Agreement (DPA) with the third-party "
        "processor and verify their jurisdictional compliance."
    ),
    ViolationType.FAILOVER_TARGET: (
        "Configure DR / failover targets within the same jurisdiction "
        "or pre-approve cross-border transfers for disaster recovery."
    ),
    ViolationType.MISSING_DPA: (
        "Establish a Data Processing Agreement covering data handling, "
        "security measures, and breach notification obligations."
    ),
    ViolationType.DATA_CLASSIFICATION_GAP: (
        "Classify all data handled by the component to enable accurate "
        "jurisdiction mapping and compliance assessment."
    ),
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class DataResidencyRequirement:
    """Data residency requirement for a component."""

    component_id: str
    required_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    allowed_regions: list[str] = field(default_factory=list)
    restricted_regions: list[str] = field(default_factory=list)
    data_classifications: list[DataClassification] = field(default_factory=list)
    requires_encryption: bool = True
    requires_dpa: bool = False


@dataclass
class CrossBorderFlow:
    """A detected cross-border data flow between components."""

    source_component_id: str
    target_component_id: str
    source_region: str
    target_region: str
    source_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    target_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    is_restricted: bool = False
    data_classifications: list[DataClassification] = field(default_factory=list)
    transfer_mechanism: str = ""


@dataclass
class SovereigntyViolation:
    """A data sovereignty compliance violation."""

    violation_id: str
    violation_type: ViolationType
    severity: Severity
    component_id: str
    description: str
    jurisdiction: Jurisdiction = Jurisdiction.NONE
    affected_region: str = ""
    remediation: str = ""
    risk_score: float = 0.0


@dataclass
class JurisdictionMapping:
    """Jurisdiction mapping for a component."""

    component_id: str
    region: str
    jurisdictions: list[Jurisdiction] = field(default_factory=list)
    data_classifications: list[DataClassification] = field(default_factory=list)
    compliant: bool = True
    gaps: list[str] = field(default_factory=list)


@dataclass
class CDNEdgeAnalysis:
    """CDN edge location residency analysis."""

    component_id: str
    edge_regions: list[str] = field(default_factory=list)
    compliant_edges: list[str] = field(default_factory=list)
    non_compliant_edges: list[str] = field(default_factory=list)
    required_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    compliance_ratio: float = 1.0


@dataclass
class BackupComplianceResult:
    """Backup storage location compliance result."""

    component_id: str
    primary_region: str
    backup_region: str
    primary_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    backup_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    is_compliant: bool = True
    violation_details: str = ""


@dataclass
class ProcessingLocationGap:
    """Gap between data processing and storage locations."""

    component_id: str
    storage_region: str
    processing_region: str
    storage_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    processing_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    has_gap: bool = False
    gap_description: str = ""


@dataclass
class ThirdPartyProcessorInfo:
    """Third-party data processor jurisdiction analysis."""

    processor_name: str
    component_id: str
    processor_region: str
    processor_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    has_dpa: bool = False
    data_classifications: list[DataClassification] = field(default_factory=list)
    compliance_status: ComplianceStatus = ComplianceStatus.UNKNOWN


@dataclass
class FailoverComplianceResult:
    """Failover target region compliance result."""

    component_id: str
    primary_region: str
    failover_region: str
    primary_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    failover_jurisdictions: list[Jurisdiction] = field(default_factory=list)
    is_compliant: bool = True
    requires_pre_approval: bool = False
    violation_details: str = ""


@dataclass
class ArchitectureImpact:
    """Impact of data sovereignty on architecture decisions."""

    component_id: str
    constraint_type: str
    description: str
    severity: Severity = Severity.MEDIUM
    recommendation: str = ""
    affected_jurisdictions: list[Jurisdiction] = field(default_factory=list)


@dataclass
class SovereigntyRiskScore:
    """Compliance violation risk score for a component or system."""

    entity_id: str
    total_score: float = 0.0
    max_possible: float = 0.0
    normalized_score: float = 0.0
    violation_count: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    info_count: int = 0
    status: ComplianceStatus = ComplianceStatus.UNKNOWN
    timestamp: str = ""


@dataclass
class DataSovereigntyReport:
    """Full data sovereignty analysis report."""

    report_id: str
    timestamp: str
    total_components: int = 0
    total_violations: int = 0
    overall_status: ComplianceStatus = ComplianceStatus.UNKNOWN
    overall_risk_score: float = 0.0
    residency_requirements: list[DataResidencyRequirement] = field(default_factory=list)
    cross_border_flows: list[CrossBorderFlow] = field(default_factory=list)
    violations: list[SovereigntyViolation] = field(default_factory=list)
    jurisdiction_mappings: list[JurisdictionMapping] = field(default_factory=list)
    cdn_analyses: list[CDNEdgeAnalysis] = field(default_factory=list)
    backup_results: list[BackupComplianceResult] = field(default_factory=list)
    processing_gaps: list[ProcessingLocationGap] = field(default_factory=list)
    third_party_processors: list[ThirdPartyProcessorInfo] = field(default_factory=list)
    failover_results: list[FailoverComplianceResult] = field(default_factory=list)
    architecture_impacts: list[ArchitectureImpact] = field(default_factory=list)
    risk_scores: list[SovereigntyRiskScore] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def resolve_jurisdictions(region: str) -> list[Jurisdiction]:
    """Resolve a region string to its applicable jurisdictions."""
    if not region:
        return [Jurisdiction.NONE]
    region_lower = region.lower().strip()
    jurisdictions = _REGION_JURISDICTION.get(region_lower, None)
    if jurisdictions is not None:
        return jurisdictions if jurisdictions else [Jurisdiction.NONE]
    # Heuristic: check if region contains known substrings
    if "eu" in region_lower or "europe" in region_lower:
        return [Jurisdiction.GDPR]
    if "us" in region_lower or "america" in region_lower and "south" not in region_lower:
        return [Jurisdiction.CCPA]
    if "brazil" in region_lower or "sa-" in region_lower:
        return [Jurisdiction.LGPD]
    if "canada" in region_lower or "ca-" in region_lower:
        return [Jurisdiction.PIPEDA]
    if "japan" in region_lower or "jp" in region_lower:
        return [Jurisdiction.APPI]
    if "singapore" in region_lower:
        return [Jurisdiction.PDPA]
    if "africa" in region_lower or "af-" in region_lower:
        return [Jurisdiction.POPIA]
    return [Jurisdiction.NONE]


def is_transfer_restricted(
    source_jurisdictions: list[Jurisdiction],
    target_jurisdictions: list[Jurisdiction],
) -> bool:
    """Check if data transfer between two sets of jurisdictions is restricted."""
    for sj in source_jurisdictions:
        for tj in target_jurisdictions:
            if sj == tj:
                continue
            if (sj, tj) in _RESTRICTED_TRANSFERS or (tj, sj) in _RESTRICTED_TRANSFERS:
                return True
    return False


def classify_component_data(comp: Component) -> list[DataClassification]:
    """Derive data classifications from component compliance tags and type."""
    classifications: list[DataClassification] = []
    if comp.compliance_tags.contains_pii:
        classifications.append(DataClassification.PII)
    if comp.compliance_tags.contains_phi:
        classifications.append(DataClassification.PHI)
    if comp.compliance_tags.pci_scope:
        classifications.append(DataClassification.PCI)
        classifications.append(DataClassification.FINANCIAL)
    dc = comp.compliance_tags.data_classification.lower()
    mapping: dict[str, DataClassification] = {
        "public": DataClassification.PUBLIC,
        "internal": DataClassification.INTERNAL,
        "confidential": DataClassification.CONFIDENTIAL,
        "restricted": DataClassification.RESTRICTED,
    }
    if dc in mapping:
        classifications.append(mapping[dc])
    if not classifications:
        classifications.append(DataClassification.INTERNAL)
    return classifications


def compute_violation_risk(violations: list[SovereigntyViolation]) -> float:
    """Compute aggregate risk score from a list of violations."""
    if not violations:
        return 0.0
    total = 0.0
    for v in violations:
        total += _SEVERITY_WEIGHT.get(v.severity, 1.0)
    return round(total, 2)


def _make_violation_id(vtype: ViolationType, comp_id: str, extra: str = "") -> str:
    """Generate a deterministic violation ID."""
    base = f"{vtype.value}:{comp_id}"
    if extra:
        base += f":{extra}"
    return base


def determine_compliance_status(
    normalized_score: float,
) -> ComplianceStatus:
    """Map a normalized risk score (0-100) to compliance status."""
    if normalized_score <= 0.0:
        return ComplianceStatus.COMPLIANT
    if normalized_score < 30.0:
        return ComplianceStatus.PARTIAL
    return ComplianceStatus.NON_COMPLIANT


def get_component_region(comp: Component) -> str:
    """Extract the effective region from a component."""
    region_cfg = getattr(comp, "region", None)
    if region_cfg and region_cfg.region:
        return region_cfg.region
    # Fallback: check tags for region hints
    for tag in comp.tags:
        tag_lower = tag.lower()
        if tag_lower.startswith("region:"):
            return tag_lower.split(":", 1)[1].strip()
    return ""


def _sensitive_data(classifications: list[DataClassification]) -> bool:
    """Return True if any classification is sensitive."""
    sensitive = {
        DataClassification.PII,
        DataClassification.PHI,
        DataClassification.FINANCIAL,
        DataClassification.PCI,
        DataClassification.CONFIDENTIAL,
        DataClassification.RESTRICTED,
    }
    return bool(set(classifications) & sensitive)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class DataSovereigntyAnalyzer:
    """Analyze data sovereignty and residency compliance across infrastructure.

    Inspects an :class:`InfraGraph` to detect cross-border data flows,
    jurisdiction compliance gaps, replication / backup / failover target
    issues, CDN edge residency problems, and third-party processor risks.
    """

    def __init__(
        self,
        graph: InfraGraph,
        *,
        residency_requirements: list[DataResidencyRequirement] | None = None,
        third_party_processors: list[ThirdPartyProcessorInfo] | None = None,
        cdn_edge_regions: dict[str, list[str]] | None = None,
        processing_regions: dict[str, str] | None = None,
        backup_regions: dict[str, str] | None = None,
    ) -> None:
        self.graph = graph
        self._residency_reqs: dict[str, DataResidencyRequirement] = {}
        if residency_requirements:
            for req in residency_requirements:
                self._residency_reqs[req.component_id] = req
        self._third_party: list[ThirdPartyProcessorInfo] = third_party_processors or []
        self._cdn_edges: dict[str, list[str]] = cdn_edge_regions or {}
        self._processing_regions: dict[str, str] = processing_regions or {}
        self._backup_regions: dict[str, str] = backup_regions or {}

    # ------------------------------------------------------------------
    # Jurisdiction mapping
    # ------------------------------------------------------------------

    def map_jurisdictions(self) -> list[JurisdictionMapping]:
        """Map each component to its applicable jurisdictions."""
        mappings: list[JurisdictionMapping] = []
        for comp in self.graph.components.values():
            region = get_component_region(comp)
            jurisdictions = resolve_jurisdictions(region)
            classifications = classify_component_data(comp)
            gaps: list[str] = []
            compliant = True
            # Check against residency requirements
            req = self._residency_reqs.get(comp.id)
            if req and req.required_jurisdictions:
                for rj in req.required_jurisdictions:
                    if rj not in jurisdictions:
                        gaps.append(
                            f"Required jurisdiction {rj.value} not satisfied "
                            f"by region '{region}'"
                        )
                        compliant = False
            if req and req.allowed_regions:
                if region and region not in req.allowed_regions:
                    gaps.append(
                        f"Region '{region}' is not in allowed regions "
                        f"{req.allowed_regions}"
                    )
                    compliant = False
            if req and req.restricted_regions:
                if region and region in req.restricted_regions:
                    gaps.append(
                        f"Region '{region}' is in restricted regions list"
                    )
                    compliant = False
            # If sensitive data but no specific jurisdiction, flag it
            if _sensitive_data(classifications) and jurisdictions == [Jurisdiction.NONE]:
                gaps.append(
                    "Component handles sensitive data but is in an "
                    "unregulated or unknown region"
                )
                compliant = False
            mappings.append(JurisdictionMapping(
                component_id=comp.id,
                region=region,
                jurisdictions=jurisdictions,
                data_classifications=classifications,
                compliant=compliant,
                gaps=gaps,
            ))
        return mappings

    # ------------------------------------------------------------------
    # Cross-border data flows
    # ------------------------------------------------------------------

    def detect_cross_border_flows(self) -> list[CrossBorderFlow]:
        """Detect data flows that cross jurisdictional borders."""
        flows: list[CrossBorderFlow] = []
        for edge in self.graph.all_dependency_edges():
            src = self.graph.get_component(edge.source_id)
            tgt = self.graph.get_component(edge.target_id)
            if not src or not tgt:
                continue
            src_region = get_component_region(src)
            tgt_region = get_component_region(tgt)
            if not src_region or not tgt_region:
                continue
            if src_region == tgt_region:
                continue
            src_j = resolve_jurisdictions(src_region)
            tgt_j = resolve_jurisdictions(tgt_region)
            # Same jurisdiction set is not cross-border
            if set(src_j) == set(tgt_j):
                continue
            restricted = is_transfer_restricted(src_j, tgt_j)
            classifications = classify_component_data(src) + classify_component_data(tgt)
            # De-duplicate classifications
            seen: set[DataClassification] = set()
            unique_cls: list[DataClassification] = []
            for c in classifications:
                if c not in seen:
                    seen.add(c)
                    unique_cls.append(c)
            flows.append(CrossBorderFlow(
                source_component_id=src.id,
                target_component_id=tgt.id,
                source_region=src_region,
                target_region=tgt_region,
                source_jurisdictions=src_j,
                target_jurisdictions=tgt_j,
                is_restricted=restricted,
                data_classifications=unique_cls,
            ))
        return flows

    # ------------------------------------------------------------------
    # Residency requirement analysis
    # ------------------------------------------------------------------

    def analyze_residency_requirements(self) -> list[DataResidencyRequirement]:
        """Build effective residency requirements for all components."""
        results: list[DataResidencyRequirement] = []
        for comp in self.graph.components.values():
            if comp.id in self._residency_reqs:
                results.append(self._residency_reqs[comp.id])
                continue
            # Auto-derive from component properties
            region = get_component_region(comp)
            classifications = classify_component_data(comp)
            jurisdictions = resolve_jurisdictions(region)
            needs_encryption = _sensitive_data(classifications)
            needs_dpa = comp.compliance_tags.contains_pii or comp.compliance_tags.contains_phi
            results.append(DataResidencyRequirement(
                component_id=comp.id,
                required_jurisdictions=jurisdictions,
                allowed_regions=[region] if region else [],
                restricted_regions=[],
                data_classifications=classifications,
                requires_encryption=needs_encryption,
                requires_dpa=needs_dpa,
            ))
        return results

    # ------------------------------------------------------------------
    # Replication target compliance
    # ------------------------------------------------------------------

    def verify_replication_targets(self) -> list[SovereigntyViolation]:
        """Verify that replication targets are in compliant regions."""
        violations: list[SovereigntyViolation] = []
        for comp in self.graph.components.values():
            region_cfg = getattr(comp, "region", None)
            if not region_cfg:
                continue
            primary_region = region_cfg.region
            dr_region = region_cfg.dr_target_region
            if not primary_region or not dr_region:
                continue
            if primary_region == dr_region:
                continue
            primary_j = resolve_jurisdictions(primary_region)
            dr_j = resolve_jurisdictions(dr_region)
            if set(primary_j) != set(dr_j):
                restricted = is_transfer_restricted(primary_j, dr_j)
                severity = Severity.CRITICAL if restricted else Severity.HIGH
                vid = _make_violation_id(ViolationType.REPLICATION_TARGET, comp.id, dr_region)
                violations.append(SovereigntyViolation(
                    violation_id=vid,
                    violation_type=ViolationType.REPLICATION_TARGET,
                    severity=severity,
                    component_id=comp.id,
                    description=(
                        f"Replication target region '{dr_region}' is in a different "
                        f"jurisdiction than primary region '{primary_region}'"
                    ),
                    jurisdiction=primary_j[0] if primary_j else Jurisdiction.NONE,
                    affected_region=dr_region,
                    remediation=_REMEDIATION_SUGGESTIONS[ViolationType.REPLICATION_TARGET],
                    risk_score=_SEVERITY_WEIGHT[severity],
                ))
        return violations

    # ------------------------------------------------------------------
    # CDN edge location analysis
    # ------------------------------------------------------------------

    def analyze_cdn_edges(self) -> list[CDNEdgeAnalysis]:
        """Analyze CDN edge locations for data residency compliance."""
        analyses: list[CDNEdgeAnalysis] = []
        for comp in self.graph.components.values():
            edge_regions = self._cdn_edges.get(comp.id)
            if edge_regions is None:
                continue
            comp_region = get_component_region(comp)
            required_j = resolve_jurisdictions(comp_region)
            classifications = classify_component_data(comp)
            compliant: list[str] = []
            non_compliant: list[str] = []
            for er in edge_regions:
                edge_j = resolve_jurisdictions(er)
                if set(edge_j) == set(required_j):
                    compliant.append(er)
                elif not _sensitive_data(classifications):
                    # Non-sensitive data can be served from any edge
                    compliant.append(er)
                else:
                    non_compliant.append(er)
            total = len(compliant) + len(non_compliant)
            ratio = len(compliant) / total if total > 0 else 1.0
            analyses.append(CDNEdgeAnalysis(
                component_id=comp.id,
                edge_regions=edge_regions,
                compliant_edges=compliant,
                non_compliant_edges=non_compliant,
                required_jurisdictions=required_j,
                compliance_ratio=round(ratio, 4),
            ))
        return analyses

    # ------------------------------------------------------------------
    # Backup storage compliance
    # ------------------------------------------------------------------

    def check_backup_compliance(self) -> list[BackupComplianceResult]:
        """Check backup storage locations for compliance."""
        results: list[BackupComplianceResult] = []
        for comp in self.graph.components.values():
            backup_region = self._backup_regions.get(comp.id)
            if backup_region is None:
                continue
            primary_region = get_component_region(comp)
            primary_j = resolve_jurisdictions(primary_region)
            backup_j = resolve_jurisdictions(backup_region)
            is_compliant = set(primary_j) == set(backup_j)
            violation_details = ""
            if not is_compliant:
                violation_details = (
                    f"Backup region '{backup_region}' ({', '.join(j.value for j in backup_j)}) "
                    f"differs from primary region '{primary_region}' "
                    f"({', '.join(j.value for j in primary_j)})"
                )
            results.append(BackupComplianceResult(
                component_id=comp.id,
                primary_region=primary_region,
                backup_region=backup_region,
                primary_jurisdictions=primary_j,
                backup_jurisdictions=backup_j,
                is_compliant=is_compliant,
                violation_details=violation_details,
            ))
        return results

    # ------------------------------------------------------------------
    # Processing vs storage location gaps
    # ------------------------------------------------------------------

    def detect_processing_gaps(self) -> list[ProcessingLocationGap]:
        """Detect gaps between data processing and storage locations."""
        gaps: list[ProcessingLocationGap] = []
        for comp in self.graph.components.values():
            processing_region = self._processing_regions.get(comp.id)
            if processing_region is None:
                continue
            storage_region = get_component_region(comp)
            if not storage_region:
                continue
            storage_j = resolve_jurisdictions(storage_region)
            processing_j = resolve_jurisdictions(processing_region)
            has_gap = set(storage_j) != set(processing_j)
            gap_desc = ""
            if has_gap:
                gap_desc = (
                    f"Data stored in '{storage_region}' "
                    f"({', '.join(j.value for j in storage_j)}) but processed "
                    f"in '{processing_region}' "
                    f"({', '.join(j.value for j in processing_j)})"
                )
            gaps.append(ProcessingLocationGap(
                component_id=comp.id,
                storage_region=storage_region,
                processing_region=processing_region,
                storage_jurisdictions=storage_j,
                processing_jurisdictions=processing_j,
                has_gap=has_gap,
                gap_description=gap_desc,
            ))
        return gaps

    # ------------------------------------------------------------------
    # Third-party processor analysis
    # ------------------------------------------------------------------

    def analyze_third_party_processors(self) -> list[ThirdPartyProcessorInfo]:
        """Analyze third-party data processor jurisdiction compliance."""
        results: list[ThirdPartyProcessorInfo] = []
        for tp in self._third_party:
            comp = self.graph.get_component(tp.component_id)
            if not comp:
                results.append(tp)
                continue
            comp_region = get_component_region(comp)
            comp_j = resolve_jurisdictions(comp_region)
            proc_j = resolve_jurisdictions(tp.processor_region)
            classifications = classify_component_data(comp)
            if not tp.data_classifications:
                tp.data_classifications = classifications
            if set(comp_j) == set(proc_j) and tp.has_dpa:
                tp.compliance_status = ComplianceStatus.COMPLIANT
            elif set(comp_j) == set(proc_j) and not tp.has_dpa:
                tp.compliance_status = ComplianceStatus.PARTIAL
            elif tp.has_dpa:
                tp.compliance_status = ComplianceStatus.PARTIAL
            else:
                tp.compliance_status = ComplianceStatus.NON_COMPLIANT
            results.append(tp)
        return results

    # ------------------------------------------------------------------
    # Failover target compliance
    # ------------------------------------------------------------------

    def check_failover_compliance(self) -> list[FailoverComplianceResult]:
        """Check failover target region compliance."""
        results: list[FailoverComplianceResult] = []
        for comp in self.graph.components.values():
            region_cfg = getattr(comp, "region", None)
            if not region_cfg:
                continue
            primary_region = region_cfg.region
            failover_region = region_cfg.dr_target_region
            if not primary_region or not failover_region:
                continue
            if not comp.failover.enabled:
                continue
            primary_j = resolve_jurisdictions(primary_region)
            failover_j = resolve_jurisdictions(failover_region)
            is_compliant = set(primary_j) == set(failover_j)
            requires_pre = False
            violation_details = ""
            if not is_compliant:
                restricted = is_transfer_restricted(primary_j, failover_j)
                requires_pre = restricted
                violation_details = (
                    f"Failover region '{failover_region}' is in jurisdiction "
                    f"({', '.join(j.value for j in failover_j)}) which differs "
                    f"from primary '{primary_region}' "
                    f"({', '.join(j.value for j in primary_j)})"
                )
            results.append(FailoverComplianceResult(
                component_id=comp.id,
                primary_region=primary_region,
                failover_region=failover_region,
                primary_jurisdictions=primary_j,
                failover_jurisdictions=failover_j,
                is_compliant=is_compliant,
                requires_pre_approval=requires_pre,
                violation_details=violation_details,
            ))
        return results

    # ------------------------------------------------------------------
    # Architecture impact assessment
    # ------------------------------------------------------------------

    def assess_architecture_impact(self) -> list[ArchitectureImpact]:
        """Assess how data sovereignty constrains architecture decisions."""
        impacts: list[ArchitectureImpact] = []
        for comp in self.graph.components.values():
            region = get_component_region(comp)
            jurisdictions = resolve_jurisdictions(region)
            classifications = classify_component_data(comp)
            is_sensitive = _sensitive_data(classifications)
            # GDPR constraints
            if Jurisdiction.GDPR in jurisdictions and is_sensitive:
                impacts.append(ArchitectureImpact(
                    component_id=comp.id,
                    constraint_type="data_locality",
                    description=(
                        "GDPR requires data to remain within EEA unless "
                        "adequate protection is ensured"
                    ),
                    severity=Severity.HIGH,
                    recommendation=(
                        "Use EU-only regions for storage and processing; "
                        "implement SCCs for any non-EU transfers"
                    ),
                    affected_jurisdictions=[Jurisdiction.GDPR],
                ))
            # LGPD constraints
            if Jurisdiction.LGPD in jurisdictions and is_sensitive:
                impacts.append(ArchitectureImpact(
                    component_id=comp.id,
                    constraint_type="data_locality",
                    description=(
                        "LGPD requires Brazilian data to be stored in "
                        "Brazil unless adequate protection is proven"
                    ),
                    severity=Severity.HIGH,
                    recommendation=(
                        "Use sa-east-1 or equivalent Brazilian region for "
                        "primary storage; obtain ANPD authorization for transfers"
                    ),
                    affected_jurisdictions=[Jurisdiction.LGPD],
                ))
            # Multi-region with sensitive data
            dr_region = ""
            region_cfg = getattr(comp, "region", None)
            if region_cfg:
                dr_region = region_cfg.dr_target_region
            if dr_region and is_sensitive:
                dr_j = resolve_jurisdictions(dr_region)
                if set(dr_j) != set(jurisdictions):
                    impacts.append(ArchitectureImpact(
                        component_id=comp.id,
                        constraint_type="dr_location",
                        description=(
                            f"DR target '{dr_region}' is in a different jurisdiction "
                            f"than primary '{region}'; may require transfer mechanisms"
                        ),
                        severity=Severity.MEDIUM,
                        recommendation=(
                            "Select DR regions within the same jurisdiction or "
                            "establish pre-approved transfer agreements"
                        ),
                        affected_jurisdictions=jurisdictions,
                    ))
            # Database replication constraints
            if comp.type == ComponentType.DATABASE and comp.replicas > 1 and is_sensitive:
                impacts.append(ArchitectureImpact(
                    component_id=comp.id,
                    constraint_type="replication",
                    description=(
                        f"Database with {comp.replicas} replicas handling sensitive "
                        f"data requires all replicas to be in compliant regions"
                    ),
                    severity=Severity.HIGH,
                    recommendation=(
                        "Ensure all database replicas are deployed in regions "
                        "that satisfy data residency requirements"
                    ),
                    affected_jurisdictions=jurisdictions,
                ))
            # Load balancer routing sensitive traffic
            if comp.type == ComponentType.LOAD_BALANCER and is_sensitive:
                impacts.append(ArchitectureImpact(
                    component_id=comp.id,
                    constraint_type="traffic_routing",
                    description=(
                        "Load balancer routing sensitive data must ensure "
                        "traffic stays within compliant regions"
                    ),
                    severity=Severity.MEDIUM,
                    recommendation=(
                        "Configure geo-based routing policies to prevent "
                        "sensitive data from being routed to non-compliant regions"
                    ),
                    affected_jurisdictions=jurisdictions,
                ))
        return impacts

    # ------------------------------------------------------------------
    # Violation collection
    # ------------------------------------------------------------------

    def _collect_cross_border_violations(
        self, flows: list[CrossBorderFlow],
    ) -> list[SovereigntyViolation]:
        """Generate violations from cross-border flows."""
        violations: list[SovereigntyViolation] = []
        for flow in flows:
            if not flow.is_restricted:
                continue
            vid = _make_violation_id(
                ViolationType.CROSS_BORDER_TRANSFER,
                flow.source_component_id,
                flow.target_component_id,
            )
            severity = _VIOLATION_SEVERITY[ViolationType.CROSS_BORDER_TRANSFER]
            if _sensitive_data(flow.data_classifications):
                severity = Severity.CRITICAL
            violations.append(SovereigntyViolation(
                violation_id=vid,
                violation_type=ViolationType.CROSS_BORDER_TRANSFER,
                severity=severity,
                component_id=flow.source_component_id,
                description=(
                    f"Restricted cross-border data transfer from "
                    f"'{flow.source_region}' to '{flow.target_region}'"
                ),
                jurisdiction=flow.source_jurisdictions[0] if flow.source_jurisdictions else Jurisdiction.NONE,
                affected_region=flow.target_region,
                remediation=_REMEDIATION_SUGGESTIONS[ViolationType.CROSS_BORDER_TRANSFER],
                risk_score=_SEVERITY_WEIGHT[severity],
            ))
        return violations

    def _collect_residency_violations(
        self, mappings: list[JurisdictionMapping],
    ) -> list[SovereigntyViolation]:
        """Generate violations from jurisdiction mapping gaps."""
        violations: list[SovereigntyViolation] = []
        for m in mappings:
            if m.compliant:
                continue
            for gap in m.gaps:
                vid = _make_violation_id(
                    ViolationType.RESIDENCY_REQUIREMENT,
                    m.component_id,
                    gap[:40],
                )
                severity = _VIOLATION_SEVERITY[ViolationType.RESIDENCY_REQUIREMENT]
                violations.append(SovereigntyViolation(
                    violation_id=vid,
                    violation_type=ViolationType.RESIDENCY_REQUIREMENT,
                    severity=severity,
                    component_id=m.component_id,
                    description=gap,
                    jurisdiction=m.jurisdictions[0] if m.jurisdictions else Jurisdiction.NONE,
                    affected_region=m.region,
                    remediation=_REMEDIATION_SUGGESTIONS[ViolationType.RESIDENCY_REQUIREMENT],
                    risk_score=_SEVERITY_WEIGHT[severity],
                ))
        return violations

    def _collect_cdn_violations(
        self, analyses: list[CDNEdgeAnalysis],
    ) -> list[SovereigntyViolation]:
        """Generate violations from CDN edge analysis."""
        violations: list[SovereigntyViolation] = []
        for a in analyses:
            for edge_r in a.non_compliant_edges:
                vid = _make_violation_id(
                    ViolationType.CDN_EDGE_LOCATION, a.component_id, edge_r,
                )
                severity = _VIOLATION_SEVERITY[ViolationType.CDN_EDGE_LOCATION]
                violations.append(SovereigntyViolation(
                    violation_id=vid,
                    violation_type=ViolationType.CDN_EDGE_LOCATION,
                    severity=severity,
                    component_id=a.component_id,
                    description=(
                        f"CDN edge location '{edge_r}' is outside the "
                        f"required jurisdiction for sensitive data"
                    ),
                    jurisdiction=a.required_jurisdictions[0] if a.required_jurisdictions else Jurisdiction.NONE,
                    affected_region=edge_r,
                    remediation=_REMEDIATION_SUGGESTIONS[ViolationType.CDN_EDGE_LOCATION],
                    risk_score=_SEVERITY_WEIGHT[severity],
                ))
        return violations

    def _collect_backup_violations(
        self, results: list[BackupComplianceResult],
    ) -> list[SovereigntyViolation]:
        """Generate violations from backup compliance results."""
        violations: list[SovereigntyViolation] = []
        for r in results:
            if r.is_compliant:
                continue
            vid = _make_violation_id(
                ViolationType.BACKUP_LOCATION, r.component_id, r.backup_region,
            )
            severity = _VIOLATION_SEVERITY[ViolationType.BACKUP_LOCATION]
            violations.append(SovereigntyViolation(
                violation_id=vid,
                violation_type=ViolationType.BACKUP_LOCATION,
                severity=severity,
                component_id=r.component_id,
                description=r.violation_details or (
                    f"Backup location '{r.backup_region}' is in a different "
                    f"jurisdiction than primary '{r.primary_region}'"
                ),
                jurisdiction=r.primary_jurisdictions[0] if r.primary_jurisdictions else Jurisdiction.NONE,
                affected_region=r.backup_region,
                remediation=_REMEDIATION_SUGGESTIONS[ViolationType.BACKUP_LOCATION],
                risk_score=_SEVERITY_WEIGHT[severity],
            ))
        return violations

    def _collect_processing_violations(
        self, gaps: list[ProcessingLocationGap],
    ) -> list[SovereigntyViolation]:
        """Generate violations from processing location gaps."""
        violations: list[SovereigntyViolation] = []
        for g in gaps:
            if not g.has_gap:
                continue
            vid = _make_violation_id(
                ViolationType.PROCESSING_LOCATION,
                g.component_id,
                g.processing_region,
            )
            severity = _VIOLATION_SEVERITY[ViolationType.PROCESSING_LOCATION]
            violations.append(SovereigntyViolation(
                violation_id=vid,
                violation_type=ViolationType.PROCESSING_LOCATION,
                severity=severity,
                component_id=g.component_id,
                description=g.gap_description or (
                    f"Data processing location '{g.processing_region}' differs "
                    f"from storage location '{g.storage_region}'"
                ),
                jurisdiction=g.storage_jurisdictions[0] if g.storage_jurisdictions else Jurisdiction.NONE,
                affected_region=g.processing_region,
                remediation=_REMEDIATION_SUGGESTIONS[ViolationType.PROCESSING_LOCATION],
                risk_score=_SEVERITY_WEIGHT[severity],
            ))
        return violations

    def _collect_third_party_violations(
        self, processors: list[ThirdPartyProcessorInfo],
    ) -> list[SovereigntyViolation]:
        """Generate violations from third-party processor analysis."""
        violations: list[SovereigntyViolation] = []
        for tp in processors:
            if tp.compliance_status == ComplianceStatus.COMPLIANT:
                continue
            if tp.compliance_status == ComplianceStatus.NON_COMPLIANT:
                vid = _make_violation_id(
                    ViolationType.THIRD_PARTY_PROCESSOR,
                    tp.component_id,
                    tp.processor_name,
                )
                severity = Severity.HIGH
                violations.append(SovereigntyViolation(
                    violation_id=vid,
                    violation_type=ViolationType.THIRD_PARTY_PROCESSOR,
                    severity=severity,
                    component_id=tp.component_id,
                    description=(
                        f"Third-party processor '{tp.processor_name}' in "
                        f"'{tp.processor_region}' is non-compliant — no DPA "
                        f"and jurisdiction mismatch"
                    ),
                    jurisdiction=tp.processor_jurisdictions[0] if tp.processor_jurisdictions else Jurisdiction.NONE,
                    affected_region=tp.processor_region,
                    remediation=_REMEDIATION_SUGGESTIONS[ViolationType.THIRD_PARTY_PROCESSOR],
                    risk_score=_SEVERITY_WEIGHT[severity],
                ))
            elif not tp.has_dpa:
                vid = _make_violation_id(
                    ViolationType.MISSING_DPA,
                    tp.component_id,
                    tp.processor_name,
                )
                severity = _VIOLATION_SEVERITY[ViolationType.MISSING_DPA]
                violations.append(SovereigntyViolation(
                    violation_id=vid,
                    violation_type=ViolationType.MISSING_DPA,
                    severity=severity,
                    component_id=tp.component_id,
                    description=(
                        f"Third-party processor '{tp.processor_name}' lacks "
                        f"a Data Processing Agreement (DPA)"
                    ),
                    jurisdiction=tp.processor_jurisdictions[0] if tp.processor_jurisdictions else Jurisdiction.NONE,
                    affected_region=tp.processor_region,
                    remediation=_REMEDIATION_SUGGESTIONS[ViolationType.MISSING_DPA],
                    risk_score=_SEVERITY_WEIGHT[severity],
                ))
        return violations

    def _collect_failover_violations(
        self, results: list[FailoverComplianceResult],
    ) -> list[SovereigntyViolation]:
        """Generate violations from failover compliance results."""
        violations: list[SovereigntyViolation] = []
        for r in results:
            if r.is_compliant:
                continue
            vid = _make_violation_id(
                ViolationType.FAILOVER_TARGET,
                r.component_id,
                r.failover_region,
            )
            severity = _VIOLATION_SEVERITY[ViolationType.FAILOVER_TARGET]
            if r.requires_pre_approval:
                severity = Severity.CRITICAL
            violations.append(SovereigntyViolation(
                violation_id=vid,
                violation_type=ViolationType.FAILOVER_TARGET,
                severity=severity,
                component_id=r.component_id,
                description=r.violation_details or (
                    f"Failover region '{r.failover_region}' is outside the "
                    f"required jurisdiction"
                ),
                jurisdiction=r.primary_jurisdictions[0] if r.primary_jurisdictions else Jurisdiction.NONE,
                affected_region=r.failover_region,
                remediation=_REMEDIATION_SUGGESTIONS[ViolationType.FAILOVER_TARGET],
                risk_score=_SEVERITY_WEIGHT[severity],
            ))
        return violations

    def _collect_data_classification_violations(self) -> list[SovereigntyViolation]:
        """Detect components with unclassified or under-classified data."""
        violations: list[SovereigntyViolation] = []
        for comp in self.graph.components.values():
            classifications = classify_component_data(comp)
            # If component is a data store with only INTERNAL classification
            if comp.type in (ComponentType.DATABASE, ComponentType.STORAGE, ComponentType.CACHE):
                if classifications == [DataClassification.INTERNAL]:
                    # Check if it has dependencies from components with sensitive data
                    dependents = self.graph.get_dependents(comp.id)
                    has_sensitive_upstream = False
                    for dep in dependents:
                        dep_cls = classify_component_data(dep)
                        if _sensitive_data(dep_cls):
                            has_sensitive_upstream = True
                            break
                    if has_sensitive_upstream:
                        vid = _make_violation_id(
                            ViolationType.DATA_CLASSIFICATION_GAP,
                            comp.id,
                        )
                        violations.append(SovereigntyViolation(
                            violation_id=vid,
                            violation_type=ViolationType.DATA_CLASSIFICATION_GAP,
                            severity=_VIOLATION_SEVERITY[ViolationType.DATA_CLASSIFICATION_GAP],
                            component_id=comp.id,
                            description=(
                                f"Data store '{comp.id}' classified as INTERNAL but "
                                f"receives data from components handling sensitive data"
                            ),
                            remediation=_REMEDIATION_SUGGESTIONS[ViolationType.DATA_CLASSIFICATION_GAP],
                            risk_score=_SEVERITY_WEIGHT[Severity.LOW],
                        ))
        return violations

    # ------------------------------------------------------------------
    # Risk scoring
    # ------------------------------------------------------------------

    def compute_risk_scores(
        self, violations: list[SovereigntyViolation],
    ) -> list[SovereigntyRiskScore]:
        """Compute per-component and overall risk scores."""
        now = datetime.now(timezone.utc).isoformat()
        # Group violations by component
        by_component: dict[str, list[SovereigntyViolation]] = {}
        for v in violations:
            by_component.setdefault(v.component_id, []).append(v)
        scores: list[SovereigntyRiskScore] = []
        for comp_id, comp_violations in by_component.items():
            total = compute_violation_risk(comp_violations)
            max_possible = len(comp_violations) * _SEVERITY_WEIGHT[Severity.CRITICAL]
            normalized = (total / max_possible * 100.0) if max_possible > 0 else 0.0
            normalized = min(100.0, normalized)
            counts = _count_severities(comp_violations)
            status = determine_compliance_status(normalized)
            scores.append(SovereigntyRiskScore(
                entity_id=comp_id,
                total_score=round(total, 2),
                max_possible=round(max_possible, 2),
                normalized_score=round(normalized, 2),
                violation_count=len(comp_violations),
                critical_count=counts[Severity.CRITICAL],
                high_count=counts[Severity.HIGH],
                medium_count=counts[Severity.MEDIUM],
                low_count=counts[Severity.LOW],
                info_count=counts[Severity.INFO],
                status=status,
                timestamp=now,
            ))
        return scores

    def compute_overall_risk(
        self, violations: list[SovereigntyViolation],
    ) -> SovereigntyRiskScore:
        """Compute a single overall system risk score."""
        now = datetime.now(timezone.utc).isoformat()
        if not violations:
            return SovereigntyRiskScore(
                entity_id="system",
                total_score=0.0,
                max_possible=0.0,
                normalized_score=0.0,
                violation_count=0,
                status=ComplianceStatus.COMPLIANT,
                timestamp=now,
            )
        total = compute_violation_risk(violations)
        max_possible = len(violations) * _SEVERITY_WEIGHT[Severity.CRITICAL]
        normalized = (total / max_possible * 100.0) if max_possible > 0 else 0.0
        normalized = min(100.0, normalized)
        counts = _count_severities(violations)
        status = determine_compliance_status(normalized)
        return SovereigntyRiskScore(
            entity_id="system",
            total_score=round(total, 2),
            max_possible=round(max_possible, 2),
            normalized_score=round(normalized, 2),
            violation_count=len(violations),
            critical_count=counts[Severity.CRITICAL],
            high_count=counts[Severity.HIGH],
            medium_count=counts[Severity.MEDIUM],
            low_count=counts[Severity.LOW],
            info_count=counts[Severity.INFO],
            status=status,
            timestamp=now,
        )

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def generate_recommendations(
        self,
        violations: list[SovereigntyViolation],
        architecture_impacts: list[ArchitectureImpact],
    ) -> list[str]:
        """Generate prioritised recommendations based on findings."""
        recs: list[str] = []
        seen: set[str] = set()
        # Sort violations by severity weight descending
        sorted_v = sorted(
            violations,
            key=lambda v: _SEVERITY_WEIGHT.get(v.severity, 0),
            reverse=True,
        )
        for v in sorted_v:
            if v.remediation and v.remediation not in seen:
                seen.add(v.remediation)
                recs.append(f"[{v.severity.value.upper()}] {v.remediation}")
        for ai in architecture_impacts:
            if ai.recommendation and ai.recommendation not in seen:
                seen.add(ai.recommendation)
                recs.append(f"[ARCHITECTURE] {ai.recommendation}")
        if not recs:
            recs.append("No data sovereignty issues detected.")
        return recs

    # ------------------------------------------------------------------
    # Full analysis
    # ------------------------------------------------------------------

    def analyze(self) -> DataSovereigntyReport:
        """Run the full data sovereignty analysis and return a report."""
        now = datetime.now(timezone.utc).isoformat()
        report_id = f"dsa-{now}"

        # Run all sub-analyses
        residency_reqs = self.analyze_residency_requirements()
        jurisdiction_mappings = self.map_jurisdictions()
        cross_border_flows = self.detect_cross_border_flows()
        replication_violations = self.verify_replication_targets()
        cdn_analyses = self.analyze_cdn_edges()
        backup_results = self.check_backup_compliance()
        processing_gaps = self.detect_processing_gaps()
        third_party = self.analyze_third_party_processors()
        failover_results = self.check_failover_compliance()
        architecture_impacts = self.assess_architecture_impact()

        # Collect all violations
        all_violations: list[SovereigntyViolation] = []
        all_violations.extend(self._collect_cross_border_violations(cross_border_flows))
        all_violations.extend(self._collect_residency_violations(jurisdiction_mappings))
        all_violations.extend(replication_violations)
        all_violations.extend(self._collect_cdn_violations(cdn_analyses))
        all_violations.extend(self._collect_backup_violations(backup_results))
        all_violations.extend(self._collect_processing_violations(processing_gaps))
        all_violations.extend(self._collect_third_party_violations(third_party))
        all_violations.extend(self._collect_failover_violations(failover_results))
        all_violations.extend(self._collect_data_classification_violations())

        # Risk scoring
        risk_scores = self.compute_risk_scores(all_violations)
        overall_risk = self.compute_overall_risk(all_violations)

        # Recommendations
        recommendations = self.generate_recommendations(all_violations, architecture_impacts)

        # Overall status
        overall_status = overall_risk.status

        return DataSovereigntyReport(
            report_id=report_id,
            timestamp=now,
            total_components=len(self.graph.components),
            total_violations=len(all_violations),
            overall_status=overall_status,
            overall_risk_score=overall_risk.normalized_score,
            residency_requirements=residency_reqs,
            cross_border_flows=cross_border_flows,
            violations=all_violations,
            jurisdiction_mappings=jurisdiction_mappings,
            cdn_analyses=cdn_analyses,
            backup_results=backup_results,
            processing_gaps=processing_gaps,
            third_party_processors=third_party,
            failover_results=failover_results,
            architecture_impacts=architecture_impacts,
            risk_scores=risk_scores,
            recommendations=recommendations,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _count_severities(violations: list[SovereigntyViolation]) -> dict[Severity, int]:
    """Count violations by severity level."""
    counts: dict[Severity, int] = {s: 0 for s in Severity}
    for v in violations:
        counts[v.severity] = counts.get(v.severity, 0) + 1
    return counts
