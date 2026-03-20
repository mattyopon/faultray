# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""DORA RTS/ITS-Compliant Output Formatters for Regulatory Submissions.

Provides structured formatters aligned with the following regulatory standards:

- **ITS 2024/2956** — Register of Information on ICT third-party service providers
- **RTS 2025/301** — Incident reporting format and timelines
- **RTS 2024/1774** — ICT Risk Management Framework report structure
- **Regulatory Package Exporter** — Bundle all outputs into a compliance package

Reference regulations:
  - DORA Regulation (EU) 2022/2554
  - Commission Implementing Regulation (EU) 2024/2956
  - Commission Delegated Regulation (EU) 2025/301
  - Commission Delegated Regulation (EU) 2024/1774
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ===========================================================================
# ITS 2024/2956 — Register of Information Template
# ===========================================================================


class CriticalityAssessment(str, Enum):
    """Criticality of the ICT service per DORA Art. 28(2)."""

    CRITICAL = "critical"
    IMPORTANT = "important"
    NON_CRITICAL = "non_critical"


class SubContractingInfo(BaseModel):
    """Sub-contracting chain information for a third-party provider."""

    sub_contractor_name: str = ""
    sub_contractor_lei: str = ""
    sub_contractor_country: str = ""
    service_description: str = ""
    data_processing_location: str = ""


class ExitStrategy(BaseModel):
    """Exit strategy details for a third-party ICT service arrangement."""

    exit_plan_documented: bool = False
    estimated_transition_months: int = 0
    alternative_providers_identified: int = 0
    data_portability_tested: bool = False
    last_exit_drill_date: str = ""  # ISO date string
    key_risks: list[str] = Field(default_factory=list)


class ThirdPartyProviderRecord(BaseModel):
    """Single entry in the Register of Information per ITS 2024/2956.

    Maps to the standardised template for reporting ICT third-party service
    provider arrangements to competent authorities.
    """

    # --- Identification ---
    record_id: str = ""
    provider_lei: str = ""  # Legal Entity Identifier (ISO 17442)
    provider_name: str = ""
    provider_country: str = ""  # ISO 3166-1 alpha-2
    provider_type: str = ""  # e.g., cloud, SaaS, IaaS, BPO, data_centre

    # --- Service details ---
    service_type: str = ""  # e.g., hosting, data_storage, payments, communication
    service_description: str = ""
    function_supported: str = ""  # critical/important function name
    criticality_assessment: CriticalityAssessment = CriticalityAssessment.NON_CRITICAL

    # --- Contractual information ---
    contract_reference: str = ""
    contract_start_date: str = ""  # ISO date
    contract_end_date: str = ""  # ISO date (empty = indefinite)
    contract_renewal_date: str = ""
    governing_law: str = ""
    dispute_resolution: str = ""

    # --- Data and processing ---
    data_processing_locations: list[str] = Field(default_factory=list)
    data_storage_locations: list[str] = Field(default_factory=list)
    personal_data_processed: bool = False
    data_classification: str = ""  # public/internal/confidential/restricted

    # --- Sub-contracting ---
    sub_contracting_allowed: bool = False
    sub_contractors: list[SubContractingInfo] = Field(default_factory=list)

    # --- Audit and oversight ---
    audit_rights_contractual: bool = False
    last_audit_date: str = ""
    last_audit_result: str = ""  # compliant, partially_compliant, non_compliant
    right_of_access: bool = False  # right of access for competent authorities

    # --- Exit strategy ---
    exit_strategy: ExitStrategy = Field(default_factory=ExitStrategy)

    # --- Risk assessment ---
    concentration_risk_flag: bool = False
    concentration_risk_description: str = ""
    substitutability: str = ""  # easy, moderate, difficult, very_difficult

    # --- Metadata ---
    last_updated: str = ""
    reporting_entity_lei: str = ""
    reporting_entity_name: str = ""


class RegisterOfInformationFormatter:
    """Format the Register of Information per ITS 2024/2956.

    Accepts a list of :class:`ThirdPartyProviderRecord` entries and exports
    them in JSON and CSV formats suitable for regulatory submission.
    """

    SCHEMA_ID = "ITS_2024_2956"
    SCHEMA_VERSION = "1.0"

    def __init__(self, records: list[ThirdPartyProviderRecord] | None = None) -> None:
        self._records: list[ThirdPartyProviderRecord] = records or []

    @property
    def records(self) -> list[ThirdPartyProviderRecord]:
        return list(self._records)

    def add_record(self, record: ThirdPartyProviderRecord) -> None:
        self._records.append(record)

    def to_json(self, indent: int = 2) -> str:
        """Export as JSON matching the ITS 2024/2956 template structure."""
        payload = {
            "schema": self.SCHEMA_ID,
            "version": self.SCHEMA_VERSION,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_records": len(self._records),
            "summary": self._summary(),
            "records": [r.model_dump(mode="json") for r in self._records],
        }
        return json.dumps(payload, indent=indent, ensure_ascii=False)

    def to_csv(self) -> str:
        """Export as CSV with one row per provider record.

        Nested fields (sub_contractors, exit_strategy) are serialised as JSON
        strings within their respective columns.
        """
        if not self._records:
            return ""

        buffer = io.StringIO()
        # Flatten field names from the model
        fieldnames = list(ThirdPartyProviderRecord.model_fields.keys())
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()

        for record in self._records:
            row = record.model_dump(mode="json")
            # Serialise complex fields as JSON strings
            for key in ("sub_contractors", "exit_strategy", "data_processing_locations",
                        "data_storage_locations"):
                if key in row and not isinstance(row[key], str):
                    row[key] = json.dumps(row[key], ensure_ascii=False)
            writer.writerow(row)

        return buffer.getvalue()

    def _summary(self) -> dict[str, Any]:
        """Produce a summary block for the register."""
        critical_count = sum(
            1
            for r in self._records
            if r.criticality_assessment == CriticalityAssessment.CRITICAL
        )
        important_count = sum(
            1
            for r in self._records
            if r.criticality_assessment == CriticalityAssessment.IMPORTANT
        )
        concentration_flags = sum(1 for r in self._records if r.concentration_risk_flag)
        countries: set[str] = set()
        for r in self._records:
            if r.provider_country:
                countries.add(r.provider_country)

        return {
            "total_providers": len(self._records),
            "critical_services": critical_count,
            "important_services": important_count,
            "non_critical_services": len(self._records) - critical_count - important_count,
            "concentration_risk_flags": concentration_flags,
            "provider_countries": sorted(countries),
            "providers_with_sub_contracting": sum(
                1 for r in self._records if r.sub_contracting_allowed
            ),
            "providers_with_audit_rights": sum(
                1 for r in self._records if r.audit_rights_contractual
            ),
            "providers_with_exit_strategy": sum(
                1 for r in self._records if r.exit_strategy.exit_plan_documented
            ),
        }


# ===========================================================================
# RTS 2025/301 — Incident Reporting Format
# ===========================================================================


class IncidentReportStage(str, Enum):
    """The three mandatory reporting stages."""

    INITIAL = "initial"
    INTERMEDIATE = "intermediate"
    FINAL = "final"


class IncidentReportFieldRequirement(BaseModel):
    """Describes a required field in a stage report and its applicability."""

    field_name: str
    description: str
    required_in: list[IncidentReportStage] = Field(default_factory=list)
    data_type: str = "string"
    example: str = ""


# Master list of fields per RTS 2025/301
_INCIDENT_REPORT_FIELDS: list[dict[str, Any]] = [
    # --- Fields required in all stages ---
    {"field_name": "incident_id", "description": "Unique incident identifier", "required_in": ["initial", "intermediate", "final"], "data_type": "string", "example": "INC-2025-00042"},
    {"field_name": "reporting_entity_lei", "description": "LEI of the reporting entity", "required_in": ["initial", "intermediate", "final"], "data_type": "string", "example": "529900T8BM49AURSDO55"},
    {"field_name": "reporting_entity_name", "description": "Name of the reporting entity", "required_in": ["initial", "intermediate", "final"], "data_type": "string", "example": "Acme Bank AG"},
    {"field_name": "competent_authority", "description": "Competent authority receiving the report", "required_in": ["initial", "intermediate", "final"], "data_type": "string", "example": "BaFin"},
    {"field_name": "incident_title", "description": "Brief title describing the incident", "required_in": ["initial", "intermediate", "final"], "data_type": "string", "example": "Core banking database outage"},
    {"field_name": "incident_description", "description": "Narrative description of the incident", "required_in": ["initial", "intermediate", "final"], "data_type": "text", "example": "Primary database cluster became unresponsive..."},
    {"field_name": "detection_timestamp", "description": "When the incident was first detected", "required_in": ["initial", "intermediate", "final"], "data_type": "datetime", "example": "2025-03-15T08:30:00Z"},
    {"field_name": "classification_level", "description": "Incident classification level (1-5)", "required_in": ["initial", "intermediate", "final"], "data_type": "integer", "example": "4"},
    {"field_name": "major_incident", "description": "Whether classified as a major incident", "required_in": ["initial", "intermediate", "final"], "data_type": "boolean", "example": "true"},
    {"field_name": "affected_services", "description": "List of ICT services affected", "required_in": ["initial", "intermediate", "final"], "data_type": "array[string]", "example": "['core_banking', 'payments']"},
    {"field_name": "estimated_clients_affected", "description": "Estimated number of clients impacted", "required_in": ["initial", "intermediate", "final"], "data_type": "integer", "example": "15000"},
    {"field_name": "geographic_areas_affected", "description": "Geographic areas impacted", "required_in": ["initial", "intermediate", "final"], "data_type": "array[string]", "example": "['DE', 'AT', 'CH']"},
    {"field_name": "cross_border", "description": "Whether the incident has cross-border impact", "required_in": ["initial", "intermediate", "final"], "data_type": "boolean", "example": "true"},
    {"field_name": "data_impact_level", "description": "Level of data loss or compromise", "required_in": ["initial", "intermediate", "final"], "data_type": "string", "example": "significant"},

    # --- Fields required from intermediate stage onward ---
    {"field_name": "determination_timestamp", "description": "When the incident was determined as major", "required_in": ["intermediate", "final"], "data_type": "datetime", "example": "2025-03-15T09:00:00Z"},
    {"field_name": "root_cause_category", "description": "Category of root cause", "required_in": ["intermediate", "final"], "data_type": "string", "example": "hardware"},
    {"field_name": "root_cause_description", "description": "Detailed root cause description", "required_in": ["intermediate", "final"], "data_type": "text", "example": "SSD firmware bug causing write amplification..."},
    {"field_name": "mitigation_actions", "description": "Actions taken to contain the incident", "required_in": ["intermediate", "final"], "data_type": "array[string]", "example": "['Failover to secondary DB', 'Rate limiting enabled']"},
    {"field_name": "recovery_actions", "description": "Actions for service recovery", "required_in": ["intermediate", "final"], "data_type": "array[string]", "example": "['Restored from backup', 'Firmware patched']"},
    {"field_name": "client_communication_issued", "description": "Whether clients were notified (Art. 21)", "required_in": ["intermediate", "final"], "data_type": "boolean", "example": "true"},

    # --- Fields required only in final stage ---
    {"field_name": "root_cause_confirmed", "description": "Whether root cause analysis is complete", "required_in": ["final"], "data_type": "boolean", "example": "true"},
    {"field_name": "recovery_timestamp", "description": "When full service was restored", "required_in": ["final"], "data_type": "datetime", "example": "2025-03-15T14:00:00Z"},
    {"field_name": "full_recovery_confirmed", "description": "Whether full recovery is confirmed", "required_in": ["final"], "data_type": "boolean", "example": "true"},
    {"field_name": "total_incident_duration_hours", "description": "Total duration of the incident", "required_in": ["final"], "data_type": "float", "example": "5.5"},
    {"field_name": "total_economic_impact_eur", "description": "Total economic impact in EUR", "required_in": ["final"], "data_type": "float", "example": "2500000.00"},
    {"field_name": "lessons_learned", "description": "Key lessons from the incident", "required_in": ["final"], "data_type": "array[string]", "example": "['Need automated failover', 'Improve firmware testing']"},
    {"field_name": "preventive_measures", "description": "Measures to prevent recurrence", "required_in": ["final"], "data_type": "array[string]", "example": "['Deploy active-active DB', 'Add firmware canary']"},
]


def _build_field_requirements() -> list[IncidentReportFieldRequirement]:
    """Build typed field requirement objects from the static definition."""
    results: list[IncidentReportFieldRequirement] = []
    for f in _INCIDENT_REPORT_FIELDS:
        stages = [IncidentReportStage(s) for s in f["required_in"]]
        results.append(
            IncidentReportFieldRequirement(
                field_name=f["field_name"],
                description=f["description"],
                required_in=stages,
                data_type=f.get("data_type", "string"),
                example=f.get("example", ""),
            )
        )
    return results


class IncidentReportingDeadlines(BaseModel):
    """Deadline tracking for the 3-stage process per RTS 2025/301."""

    incident_id: str
    discovery_timestamp: datetime
    determination_timestamp: datetime | None = None

    initial_deadline: datetime | None = None
    intermediate_deadline: datetime | None = None
    final_deadline: datetime | None = None

    initial_submitted: bool = False
    intermediate_submitted: bool = False
    final_submitted: bool = False

    def compute(self) -> None:
        """Compute deadlines from determination timestamp."""
        if self.determination_timestamp is None:
            return
        # Initial: min(determination + 4h, discovery + 24h)
        d4 = self.determination_timestamp + timedelta(hours=4)
        d24 = self.discovery_timestamp + timedelta(hours=24)
        self.initial_deadline = min(d4, d24)
        # Intermediate: initial + 72h
        self.intermediate_deadline = self.initial_deadline + timedelta(hours=72)
        # Final: initial + 30 days
        self.final_deadline = self.initial_deadline + timedelta(days=30)


class IncidentReportTemplate(BaseModel):
    """A structured incident report template for a specific stage."""

    schema_id: str = "RTS_2025_301"
    schema_version: str = "1.0"
    stage: IncidentReportStage
    required_fields: list[IncidentReportFieldRequirement] = Field(
        default_factory=list
    )
    field_values: dict[str, Any] = Field(default_factory=dict)
    deadlines: IncidentReportingDeadlines | None = None
    validation_errors: list[str] = Field(default_factory=list)

    def validate_completeness(self) -> list[str]:
        """Check that all required fields for this stage are populated.

        Returns a list of missing field names.
        """
        missing: list[str] = []
        for req in self.required_fields:
            if self.stage in req.required_in:
                val = self.field_values.get(req.field_name)
                if val is None or val == "" or val == []:
                    missing.append(req.field_name)
        self.validation_errors = missing
        return missing


class IncidentReportingFormatter:
    """Generate RTS 2025/301 compliant incident report templates.

    Produces stage-specific templates with required fields, deadline tracking,
    and completeness validation.
    """

    FIELD_REQUIREMENTS = _build_field_requirements()

    @classmethod
    def create_template(
        cls,
        stage: IncidentReportStage,
        field_values: dict[str, Any] | None = None,
        deadlines: IncidentReportingDeadlines | None = None,
    ) -> IncidentReportTemplate:
        """Create a report template for the given stage.

        Only fields required for the specified stage are included.
        """
        stage_fields = [
            f for f in cls.FIELD_REQUIREMENTS if stage in f.required_in
        ]
        template = IncidentReportTemplate(
            stage=stage,
            required_fields=stage_fields,
            field_values=field_values or {},
            deadlines=deadlines,
        )
        return template

    @classmethod
    def create_all_templates(
        cls,
        incident_id: str,
        discovery_timestamp: datetime | None = None,
        determination_timestamp: datetime | None = None,
        base_values: dict[str, Any] | None = None,
    ) -> dict[str, IncidentReportTemplate]:
        """Create templates for all three stages with shared deadline tracking."""
        now = datetime.now(timezone.utc)
        deadlines = IncidentReportingDeadlines(
            incident_id=incident_id,
            discovery_timestamp=discovery_timestamp or now,
            determination_timestamp=determination_timestamp,
        )
        if determination_timestamp:
            deadlines.compute()

        values = dict(base_values or {})
        values.setdefault("incident_id", incident_id)

        return {
            "initial": cls.create_template(
                IncidentReportStage.INITIAL, field_values=dict(values), deadlines=deadlines
            ),
            "intermediate": cls.create_template(
                IncidentReportStage.INTERMEDIATE, field_values=dict(values), deadlines=deadlines
            ),
            "final": cls.create_template(
                IncidentReportStage.FINAL, field_values=dict(values), deadlines=deadlines
            ),
        }

    @classmethod
    def to_json(cls, template: IncidentReportTemplate, indent: int = 2) -> str:
        """Export a single stage template as JSON."""
        return json.dumps(
            template.model_dump(mode="json"),
            indent=indent,
            ensure_ascii=False,
        )


# ===========================================================================
# RTS 2024/1774 — ICT Risk Management Framework Report
# ===========================================================================


class RiskManagementDomain(str, Enum):
    """Domains of the ICT Risk Management Framework per RTS 2024/1774."""

    GOVERNANCE = "governance"
    RISK_IDENTIFICATION = "risk_identification"
    PROTECTION_PREVENTION = "protection_prevention"
    DETECTION = "detection"
    RESPONSE_RECOVERY = "response_recovery"
    LEARNING_EVOLVING = "learning_evolving"
    COMMUNICATION = "communication"


class RiskManagementControl(BaseModel):
    """A single control within the ICT Risk Management Framework."""

    domain: RiskManagementDomain
    control_id: str
    rts_article_reference: str = ""
    description: str = ""
    status: str = "not_assessed"  # compliant, partially_compliant, non_compliant, not_assessed
    evidence: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    risk_score: float = 0.0  # 0.0 (no risk) to 1.0 (critical)


class RiskManagementDomainReport(BaseModel):
    """Assessment of a single domain within the framework."""

    domain: RiskManagementDomain
    domain_label: str = ""
    rts_articles: list[str] = Field(default_factory=list)
    controls: list[RiskManagementControl] = Field(default_factory=list)
    domain_status: str = "not_assessed"
    domain_score: float = 0.0  # 0-100
    key_findings: list[str] = Field(default_factory=list)


class RiskManagementFrameworkReport(BaseModel):
    """Complete ICT Risk Management Framework report per RTS 2024/1774."""

    schema_id: str = "RTS_2024_1774"
    schema_version: str = "1.0"
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    reporting_entity_lei: str = ""
    reporting_entity_name: str = ""
    assessment_period_start: str = ""
    assessment_period_end: str = ""

    overall_status: str = "not_assessed"
    overall_score: float = 0.0  # 0-100

    domains: list[RiskManagementDomainReport] = Field(default_factory=list)

    executive_summary: str = ""
    key_risks: list[str] = Field(default_factory=list)
    remediation_plan: list[str] = Field(default_factory=list)


# Pre-defined framework structure mapping to RTS articles
_RTS_1774_FRAMEWORK: list[dict[str, Any]] = [
    {
        "domain": "governance",
        "domain_label": "ICT Risk Management Governance",
        "rts_articles": ["Art. 5", "Art. 6"],
        "controls": [
            {"control_id": "GOV-01", "rts_article_reference": "Art. 5(1)", "description": "Management body approval of ICT risk management framework"},
            {"control_id": "GOV-02", "rts_article_reference": "Art. 5(2)", "description": "Roles and responsibilities for ICT risk management defined"},
            {"control_id": "GOV-03", "rts_article_reference": "Art. 5(3)", "description": "ICT risk management integrated into enterprise risk management"},
            {"control_id": "GOV-04", "rts_article_reference": "Art. 6(1)", "description": "ICT risk management policy documented and approved"},
            {"control_id": "GOV-05", "rts_article_reference": "Art. 6(2)", "description": "Regular review and update of ICT risk management framework"},
        ],
    },
    {
        "domain": "risk_identification",
        "domain_label": "ICT Risk Identification",
        "rts_articles": ["Art. 7", "Art. 8"],
        "controls": [
            {"control_id": "RID-01", "rts_article_reference": "Art. 7(1)", "description": "ICT asset inventory maintained and up-to-date"},
            {"control_id": "RID-02", "rts_article_reference": "Art. 7(2)", "description": "ICT risk identification and assessment performed regularly"},
            {"control_id": "RID-03", "rts_article_reference": "Art. 8(1)", "description": "Business impact analysis covering all critical functions"},
            {"control_id": "RID-04", "rts_article_reference": "Art. 8(2)", "description": "ICT dependency mapping including third-party services"},
            {"control_id": "RID-05", "rts_article_reference": "Art. 8(3)", "description": "Risk appetite and tolerance levels defined"},
        ],
    },
    {
        "domain": "protection_prevention",
        "domain_label": "ICT Protection and Prevention",
        "rts_articles": ["Art. 9", "Art. 10"],
        "controls": [
            {"control_id": "PRO-01", "rts_article_reference": "Art. 9(1)", "description": "Access control policies implemented and enforced"},
            {"control_id": "PRO-02", "rts_article_reference": "Art. 9(2)", "description": "Encryption at rest and in transit for sensitive data"},
            {"control_id": "PRO-03", "rts_article_reference": "Art. 9(3)", "description": "Network segmentation and perimeter security"},
            {"control_id": "PRO-04", "rts_article_reference": "Art. 10(1)", "description": "Patch management and vulnerability remediation"},
            {"control_id": "PRO-05", "rts_article_reference": "Art. 10(2)", "description": "Change management process for ICT systems"},
        ],
    },
    {
        "domain": "detection",
        "domain_label": "ICT Anomaly Detection",
        "rts_articles": ["Art. 11"],
        "controls": [
            {"control_id": "DET-01", "rts_article_reference": "Art. 11(1)", "description": "Continuous monitoring of ICT systems and networks"},
            {"control_id": "DET-02", "rts_article_reference": "Art. 11(2)", "description": "Anomaly detection mechanisms in place"},
            {"control_id": "DET-03", "rts_article_reference": "Art. 11(3)", "description": "Security event logging and correlation"},
            {"control_id": "DET-04", "rts_article_reference": "Art. 11(4)", "description": "Alerting thresholds defined and operational"},
        ],
    },
    {
        "domain": "response_recovery",
        "domain_label": "ICT Response and Recovery",
        "rts_articles": ["Art. 12", "Art. 13"],
        "controls": [
            {"control_id": "RES-01", "rts_article_reference": "Art. 12(1)", "description": "Incident response plan documented and tested"},
            {"control_id": "RES-02", "rts_article_reference": "Art. 12(2)", "description": "Business continuity plans with defined RTO/RPO"},
            {"control_id": "RES-03", "rts_article_reference": "Art. 13(1)", "description": "Backup and restoration procedures validated"},
            {"control_id": "RES-04", "rts_article_reference": "Art. 13(2)", "description": "Disaster recovery capabilities tested regularly"},
            {"control_id": "RES-05", "rts_article_reference": "Art. 13(3)", "description": "Communication plan for crisis management"},
        ],
    },
    {
        "domain": "learning_evolving",
        "domain_label": "Learning and Evolving",
        "rts_articles": ["Art. 14"],
        "controls": [
            {"control_id": "LEV-01", "rts_article_reference": "Art. 14(1)", "description": "Post-incident review process established"},
            {"control_id": "LEV-02", "rts_article_reference": "Art. 14(2)", "description": "Lessons learned integrated into risk management"},
            {"control_id": "LEV-03", "rts_article_reference": "Art. 14(3)", "description": "ICT risk management training for staff"},
        ],
    },
    {
        "domain": "communication",
        "domain_label": "ICT Risk Communication",
        "rts_articles": ["Art. 15"],
        "controls": [
            {"control_id": "COM-01", "rts_article_reference": "Art. 15(1)", "description": "Internal ICT risk reporting to management body"},
            {"control_id": "COM-02", "rts_article_reference": "Art. 15(2)", "description": "External communication framework for ICT incidents"},
            {"control_id": "COM-03", "rts_article_reference": "Art. 15(3)", "description": "Information sharing arrangements with peers/authorities"},
        ],
    },
]


class RiskManagementFrameworkFormatter:
    """Generate RTS 2024/1774 compliant ICT Risk Management Framework reports.

    Provides the regulatory structure and allows populating controls with
    assessment results from infrastructure analysis.
    """

    @classmethod
    def create_blank_report(
        cls,
        reporting_entity_lei: str = "",
        reporting_entity_name: str = "",
        assessment_period_start: str = "",
        assessment_period_end: str = "",
    ) -> RiskManagementFrameworkReport:
        """Create a blank framework report with all domains and controls."""
        domains: list[RiskManagementDomainReport] = []

        for domain_def in _RTS_1774_FRAMEWORK:
            controls = [
                RiskManagementControl(
                    domain=RiskManagementDomain(domain_def["domain"]),
                    **ctrl,
                )
                for ctrl in domain_def["controls"]
            ]
            domains.append(
                RiskManagementDomainReport(
                    domain=RiskManagementDomain(domain_def["domain"]),
                    domain_label=domain_def["domain_label"],
                    rts_articles=domain_def["rts_articles"],
                    controls=controls,
                )
            )

        return RiskManagementFrameworkReport(
            reporting_entity_lei=reporting_entity_lei,
            reporting_entity_name=reporting_entity_name,
            assessment_period_start=assessment_period_start,
            assessment_period_end=assessment_period_end,
            domains=domains,
        )

    @classmethod
    def compute_scores(cls, report: RiskManagementFrameworkReport) -> None:
        """Compute domain and overall scores from control statuses.

        Mutates the report in place, updating domain_score, domain_status,
        overall_score, and overall_status.
        """
        status_scores = {
            "compliant": 100.0,
            "partially_compliant": 50.0,
            "non_compliant": 0.0,
            "not_assessed": 0.0,
        }

        domain_scores: list[float] = []
        for domain_report in report.domains:
            if not domain_report.controls:
                domain_report.domain_score = 0.0
                domain_report.domain_status = "not_assessed"
                continue

            ctrl_scores = [
                status_scores.get(c.status, 0.0) for c in domain_report.controls
            ]
            domain_report.domain_score = round(
                sum(ctrl_scores) / len(ctrl_scores), 1
            )
            domain_scores.append(domain_report.domain_score)

            if all(c.status == "compliant" for c in domain_report.controls):
                domain_report.domain_status = "compliant"
            elif any(c.status == "non_compliant" for c in domain_report.controls):
                domain_report.domain_status = "non_compliant"
            elif all(
                c.status in ("compliant", "partially_compliant")
                for c in domain_report.controls
            ):
                domain_report.domain_status = "partially_compliant"
            else:
                domain_report.domain_status = "not_assessed"

        if domain_scores:
            report.overall_score = round(
                sum(domain_scores) / len(domain_scores), 1
            )
        else:
            report.overall_score = 0.0

        statuses = [d.domain_status for d in report.domains]
        if all(s == "compliant" for s in statuses):
            report.overall_status = "compliant"
        elif any(s == "non_compliant" for s in statuses):
            report.overall_status = "non_compliant"
        elif all(s in ("compliant", "partially_compliant") for s in statuses):
            report.overall_status = "partially_compliant"
        else:
            report.overall_status = "not_assessed"

    @classmethod
    def to_json(
        cls, report: RiskManagementFrameworkReport, indent: int = 2
    ) -> str:
        """Export the framework report as JSON."""
        return json.dumps(
            report.model_dump(mode="json"),
            indent=indent,
            ensure_ascii=False,
        )


# ===========================================================================
# Regulatory Package Exporter
# ===========================================================================


class PackageManifestEntry(BaseModel):
    """A single entry in the compliance submission package manifest."""

    filename: str
    schema_id: str
    schema_version: str
    description: str
    checksum_sha256: str = ""
    size_bytes: int = 0
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class CompliancePackageManifest(BaseModel):
    """Manifest for a DORA compliance submission package."""

    package_id: str = ""
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    reporting_entity_lei: str = ""
    reporting_entity_name: str = ""
    reporting_period_start: str = ""
    reporting_period_end: str = ""
    total_files: int = 0
    entries: list[PackageManifestEntry] = Field(default_factory=list)
    package_checksum_sha256: str = ""


class RegulatoryPackageExporter:
    """Bundle all DORA regulatory outputs into a compliance submission package.

    Combines:
    - Register of Information (ITS 2024/2956)
    - Incident Reports (RTS 2025/301)
    - ICT Risk Management Framework Report (RTS 2024/1774)

    Produces a dict-based package with checksums, timestamps, and metadata
    suitable for regulatory submission.
    """

    def __init__(
        self,
        reporting_entity_lei: str = "",
        reporting_entity_name: str = "",
        reporting_period_start: str = "",
        reporting_period_end: str = "",
    ) -> None:
        self.reporting_entity_lei = reporting_entity_lei
        self.reporting_entity_name = reporting_entity_name
        self.reporting_period_start = reporting_period_start
        self.reporting_period_end = reporting_period_end
        self._files: dict[str, str] = {}  # filename -> content

    @staticmethod
    def _sha256(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def add_register_of_information(
        self, formatter: RegisterOfInformationFormatter
    ) -> None:
        """Add the Register of Information (ITS 2024/2956) to the package."""
        json_content = formatter.to_json()
        csv_content = formatter.to_csv()
        self._files["register_of_information.json"] = json_content
        if csv_content:
            self._files["register_of_information.csv"] = csv_content

    def add_incident_reports(
        self, templates: dict[str, IncidentReportTemplate]
    ) -> None:
        """Add incident report templates (RTS 2025/301) to the package."""
        for stage_name, template in templates.items():
            content = IncidentReportingFormatter.to_json(template)
            self._files[f"incident_report_{stage_name}.json"] = content

    def add_risk_management_report(
        self, report: RiskManagementFrameworkReport
    ) -> None:
        """Add the ICT Risk Management Framework report (RTS 2024/1774)."""
        content = RiskManagementFrameworkFormatter.to_json(report)
        self._files["risk_management_framework.json"] = content

    def add_custom_file(self, filename: str, content: str) -> None:
        """Add a custom file to the package."""
        self._files[filename] = content

    def build_manifest(self) -> CompliancePackageManifest:
        """Build the package manifest with checksums and metadata."""
        now = datetime.now(timezone.utc)
        timestamp_str = now.strftime("%Y%m%d%H%M%S")
        package_id = f"DORA-PKG-{timestamp_str}-{self._sha256(timestamp_str)[:8].upper()}"

        entries: list[PackageManifestEntry] = []
        for filename, content in sorted(self._files.items()):
            # Determine schema from filename
            if "register_of_information" in filename:
                schema_id = "ITS_2024_2956"
                schema_version = "1.0"
                description = "Register of Information on ICT third-party service providers"
            elif "incident_report" in filename:
                schema_id = "RTS_2025_301"
                schema_version = "1.0"
                stage = filename.replace("incident_report_", "").replace(".json", "")
                description = f"Incident report — {stage} stage"
            elif "risk_management" in filename:
                schema_id = "RTS_2024_1774"
                schema_version = "1.0"
                description = "ICT Risk Management Framework report"
            else:
                schema_id = "custom"
                schema_version = "1.0"
                description = filename

            entries.append(
                PackageManifestEntry(
                    filename=filename,
                    schema_id=schema_id,
                    schema_version=schema_version,
                    description=description,
                    checksum_sha256=self._sha256(content),
                    size_bytes=len(content.encode("utf-8")),
                    generated_at=now,
                )
            )

        manifest = CompliancePackageManifest(
            package_id=package_id,
            generated_at=now,
            reporting_entity_lei=self.reporting_entity_lei,
            reporting_entity_name=self.reporting_entity_name,
            reporting_period_start=self.reporting_period_start,
            reporting_period_end=self.reporting_period_end,
            total_files=len(entries),
            entries=entries,
        )

        # Compute package-level checksum over all file checksums
        all_checksums = "|".join(e.checksum_sha256 for e in entries)
        manifest.package_checksum_sha256 = self._sha256(all_checksums)

        return manifest

    def export(self) -> dict[str, Any]:
        """Export the complete compliance package as a dict.

        Returns a dict with:
        - ``manifest``: the package manifest (checksums, metadata)
        - ``files``: dict mapping filename to content string

        This can be serialised to JSON or written to disk.
        """
        manifest = self.build_manifest()
        return {
            "manifest": manifest.model_dump(mode="json"),
            "files": dict(self._files),
        }

    def export_json(self, indent: int = 2) -> str:
        """Export the complete package as a JSON string."""
        package = self.export()
        return json.dumps(package, indent=indent, ensure_ascii=False)
