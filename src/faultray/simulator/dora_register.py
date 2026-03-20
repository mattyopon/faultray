# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Business Source License 1.1. See LICENSE file for details.

"""DORA Article 28 Register of Information — ITS 2024/2956 compliant.

This module provides a production-quality implementation of the Register of
Information required under DORA Article 28 and the associated Implementing
Technical Standards (ITS 2024/2956).

Architecture
------------
The register is built in two passes:

1. **Auto-population**: An :class:`InfraGraph` is scanned for
   ``ComponentType.EXTERNAL_API`` nodes.  Each external API becomes a
   candidate provider entry with fields inferred from the graph topology.

2. **Manual overlay**: A supplementary YAML or JSON file (or dict) containing
   contractual and administrative data that cannot be auto-detected (LEI codes,
   contract dates, legal names, audit rights, etc.) is merged on top.

After both passes the register performs:

* **Concentration risk analysis** (DORA Art. 29) using the
  Herfindahl-Hirschman Index (HHI) and several complementary checks.
* **Export** to JSON (API consumption) or CSV (regulatory submission per the
  ITS template column layout).

Typical usage
-------------
.. code-block:: python

    from faultray.model.graph import InfraGraph
    from faultray.simulator.dora_register import DORARegister

    register = DORARegister(graph)
    register.load_overlay("contractual_data.yaml")
    entries = register.build()

    report = register.concentration_risk_report()
    register.export_json(Path("register.json"))
    register.export_csv(Path("register.csv"))
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from faultray.model.components import Component, ComponentType
from faultray.model.graph import InfraGraph

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — ITS 2024/2956 column mapping
# ---------------------------------------------------------------------------

# ICT service types per ITS Annex I Table 1
ICT_SERVICE_TYPES = {
    ComponentType.EXTERNAL_API: "ICT Application Service",
    ComponentType.DATABASE: "ICT Data Management Service",
    ComponentType.CACHE: "ICT Infrastructure Service",
    ComponentType.QUEUE: "ICT Messaging Service",
    ComponentType.STORAGE: "ICT Storage Service",
    ComponentType.DNS: "ICT Network Service",
    ComponentType.LLM_ENDPOINT: "AI/ML Platform Service",
    ComponentType.AI_AGENT: "AI/ML Application Service",
    ComponentType.TOOL_SERVICE: "ICT Application Service",
    ComponentType.AGENT_ORCHESTRATOR: "ICT Orchestration Service",
}

# HHI thresholds (US DoJ scale applied to provider concentration)
HHI_CONCENTRATED = 2500       # Highly concentrated market
HHI_MODERATELY_CONCENTRATED = 1500

# Geographic concentration risk threshold
GEO_CONCENTRATION_THRESHOLD = 0.6    # >60% of providers in one country = high risk

# Service-type concentration: single type covers >50% of providers
SERVICE_TYPE_CONCENTRATION_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Data models — ITS 2024/2956 fields
# ---------------------------------------------------------------------------


@dataclass
class SubContractor:
    """A sub-contractor in the ICT supply chain (ITS 2024/2956 §3.4)."""

    name: str
    lei: str = ""                               # Legal Entity Identifier
    country_of_incorporation: str = "Unknown"
    services_provided: list[str] = field(default_factory=list)
    is_intra_group: bool = False                # True if part of the same corporate group


@dataclass
class AuditRights:
    """Contractual audit rights granted to the regulated entity."""

    scope: str = ""                             # e.g. "Full ICT systems access"
    frequency: str = ""                         # e.g. "Annual", "Biennial"
    last_audit_date: str = ""                   # ISO date or empty
    right_to_inspect: bool = False
    right_to_request_third_party_audit: bool = False
    pooled_audit_allowed: bool = False          # Art. 28(3)(d) — shared audit


@dataclass
class ExitStrategy:
    """Exit / transition strategy for a provider relationship."""

    documented: bool = False
    last_tested_date: str = ""                  # ISO date or empty
    estimated_transition_days: int = 0          # Business days for transition
    alternative_provider_identified: bool = False
    transition_plan_path: str = ""              # Reference to external doc


@dataclass
class DataHandling:
    """Data storage and transfer characteristics for the service."""

    data_locations: list[str] = field(default_factory=list)     # Country codes / regions
    cross_border_transfers: bool = False
    transfer_mechanism: str = ""                # e.g. "Standard Contractual Clauses"
    encryption_at_rest: bool = False
    encryption_in_transit: bool = False
    data_residency_requirements: list[str] = field(default_factory=list)


@dataclass
class RegisterEntry:
    """A single entry in the DORA Article 28 Register of Information.

    Field names map to the column layout specified in ITS 2024/2956 Annex I.
    """

    # ---------- Entity identification (the regulated financial entity) ----------
    entity_name: str = ""
    entity_lei: str = ""                        # ISO 17442 LEI of the reporting entity
    entity_country: str = ""                    # ISO 3166-1 alpha-2

    # ---------- Provider identification ----------
    provider_id: str = ""                       # Internal FaultRay component ID
    provider_name: str = ""
    provider_lei: str = ""                      # LEI of the ICT provider
    provider_country_of_incorporation: str = "Unknown"
    provider_parent_company: str = ""           # Ultimate parent entity

    # ---------- Service description ----------
    ict_service_type: str = ""                  # From ITS Annex I Table 1
    service_description: str = ""
    criticality: str = "standard"               # critical | important | standard
    business_functions_supported: list[str] = field(default_factory=list)

    # ---------- Contract details ----------
    contract_reference: str = ""
    contract_start_date: str = ""               # ISO date (YYYY-MM-DD)
    contract_end_date: str = ""                 # ISO date or ""
    renewal_terms: str = ""                     # e.g. "Auto-renew annually"
    termination_notice_period_days: int = 0

    # ---------- Sub-contracting ----------
    sub_contractors: list[SubContractor] = field(default_factory=list)

    # ---------- Audit rights ----------
    audit_rights: AuditRights = field(default_factory=AuditRights)

    # ---------- Exit strategy ----------
    exit_strategy: ExitStrategy = field(default_factory=ExitStrategy)

    # ---------- Data handling ----------
    data_handling: DataHandling = field(default_factory=DataHandling)

    # ---------- Risk flags (auto-computed) ----------
    concentration_risk: bool = False
    single_provider_dependency: bool = False    # Sole provider for a critical function
    geographic_concentration_risk: bool = False

    # ---------- Auto-population provenance ----------
    auto_populated: bool = True                 # True if derived from InfraGraph
    last_assessed: str = ""                     # ISO date of last assessment


# ---------------------------------------------------------------------------
# Concentration risk results
# ---------------------------------------------------------------------------


@dataclass
class ConcentrationRiskReport:
    """Summary of concentration risk analysis per DORA Article 29."""

    hhi: float                                  # Herfindahl-Hirschman Index (0–10000)
    hhi_interpretation: str                     # "unconcentrated" | "moderate" | "highly_concentrated"
    total_providers: int
    critical_provider_count: int

    # Provider share breakdown {provider_name: share_percent}
    provider_shares: dict[str, float] = field(default_factory=dict)

    # Single-provider dependencies: {function_name: provider_name}
    single_provider_dependencies: dict[str, str] = field(default_factory=dict)

    # Geographic concentration {country: share_percent}
    geographic_distribution: dict[str, float] = field(default_factory=dict)
    geographic_concentration_risk: bool = False
    dominant_country: str = ""

    # Service-type concentration {service_type: share_percent}
    service_type_distribution: dict[str, float] = field(default_factory=dict)
    service_type_concentration_risk: bool = False
    dominant_service_type: str = ""

    # Overall risk level
    overall_risk_level: str = "low"             # low | medium | high | critical
    risk_indicators: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# DORARegister
# ---------------------------------------------------------------------------


class DORARegister:
    """Builds and manages the DORA Article 28 Register of Information.

    Two-phase construction:

    Phase 1 — Auto-population from :class:`InfraGraph`
        External API components are mapped to provider entries.  All fields
        that can be inferred from topology data (criticality, dependencies,
        failover config) are populated automatically.

    Phase 2 — Manual overlay
        Call :meth:`load_overlay` with a path to a YAML/JSON file, or pass a
        dict directly to :meth:`apply_overlay`.  The overlay merges
        contractual and administrative data onto the auto-populated entries.
        Overlay keys are matched by ``provider_id`` (component ID in the graph).

    Overlay file format (YAML or JSON):
    .. code-block:: yaml

        entity:
          name: "ACME Financial SA"
          lei: "XKZZ1234567890"
          country: "DE"

        providers:
          - provider_id: "payment-api"
            provider_lei: "LEI12345"
            provider_country_of_incorporation: "US"
            provider_parent_company: "ACME Corp"
            contract_start_date: "2023-01-01"
            contract_end_date: "2025-12-31"
            renewal_terms: "Auto-renew annually"
            termination_notice_period_days: 90
            audit_rights:
              scope: "Full system access"
              frequency: "Annual"
              right_to_inspect: true
            exit_strategy:
              documented: true
              estimated_transition_days: 120
              alternative_provider_identified: true
            data_handling:
              data_locations: ["US", "EU"]
              cross_border_transfers: true
              encryption_at_rest: true
              encryption_in_transit: true
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph
        self._entity_name: str = "Financial Institution"
        self._entity_lei: str = ""
        self._entity_country: str = ""
        self._overlay: dict[str, dict] = {}         # keyed by provider_id
        self._entries: list[RegisterEntry] | None = None   # cached result

    # ------------------------------------------------------------------
    # Overlay management
    # ------------------------------------------------------------------

    def load_overlay(self, path: Path | str) -> "DORARegister":
        """Load supplementary contractual data from a YAML or JSON file.

        Supports both ``.yaml``/``.yml`` and ``.json`` extensions.

        Args:
            path: Path to the overlay file.

        Returns:
            ``self`` for method chaining.

        Raises:
            ValueError: If the file extension is not recognised.
            FileNotFoundError: If the file does not exist.
        """
        p = Path(path)
        suffix = p.suffix.lower()

        if suffix in (".yaml", ".yml"):
            try:
                import yaml  # type: ignore[import]
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
            except ImportError:
                # pyyaml not available — parse as JSON fallback or raise
                raise ImportError(
                    "Install PyYAML ('pip install pyyaml') to load YAML overlays."
                ) from None
        elif suffix == ".json":
            data = json.loads(p.read_text(encoding="utf-8"))
        else:
            raise ValueError(
                f"Unsupported overlay file extension: {suffix!r}. "
                "Use .yaml, .yml, or .json."
            )

        self.apply_overlay(data)
        return self

    def apply_overlay(self, data: dict) -> "DORARegister":
        """Apply a supplementary data dictionary directly.

        Args:
            data: Dict with optional ``entity`` key (entity-level fields) and
                ``providers`` list (provider-level overrides keyed by ``provider_id``).

        Returns:
            ``self`` for method chaining.
        """
        # Entity-level fields
        entity = data.get("entity", {})
        if entity.get("name"):
            self._entity_name = entity["name"]
        if entity.get("lei"):
            self._entity_lei = entity["lei"]
        if entity.get("country"):
            self._entity_country = entity["country"]

        # Provider-level overrides, indexed by provider_id
        for provider_data in data.get("providers", []):
            pid = provider_data.get("provider_id")
            if pid:
                self._overlay[pid] = provider_data

        # Invalidate cached entries
        self._entries = None
        return self

    # ------------------------------------------------------------------
    # Register construction
    # ------------------------------------------------------------------

    def build(self) -> list[RegisterEntry]:
        """Build the full register, merging auto-populated and overlay data.

        This method is idempotent: repeated calls return the same list unless
        the graph or overlay has been modified.

        Returns:
            List of :class:`RegisterEntry` objects, one per identified provider.
        """
        if self._entries is not None:
            return self._entries

        entries = self._auto_populate()

        for entry in entries:
            overlay = self._overlay.get(entry.provider_id, {})
            if overlay:
                self._apply_provider_overlay(entry, overlay)

        self._entries = entries
        logger.info(
            "DORA register built: %d provider entries (%d with overlay data)",
            len(entries),
            sum(1 for e in entries if e.provider_id in self._overlay),
        )
        return entries

    # ------------------------------------------------------------------
    # Concentration risk analysis (DORA Art. 29)
    # ------------------------------------------------------------------

    def concentration_risk_report(self) -> ConcentrationRiskReport:
        """Compute concentration risk metrics per DORA Article 29.

        Metrics computed:

        * **HHI** (Herfindahl-Hirschman Index): sum of squared market shares.
          Shares are based on the number of internal components that depend on
          each provider.  A higher HHI indicates greater concentration.
        * **Single-provider dependency**: a critical business function depends
          on exactly one external provider with no documented alternative.
        * **Geographic concentration**: >60% of providers are incorporated in
          a single country.
        * **Service-type concentration**: >50% of providers supply the same
          ICT service type.

        Returns:
            A :class:`ConcentrationRiskReport` with all computed metrics.
        """
        entries = self.build()
        if not entries:
            return ConcentrationRiskReport(
                hhi=0.0,
                hhi_interpretation="unconcentrated",
                total_providers=0,
                critical_provider_count=0,
                overall_risk_level="low",
            )

        total = len(entries)
        critical_count = sum(1 for e in entries if e.criticality == "critical")

        # ---- Dependency-weighted provider shares ----
        dependency_counts: dict[str, int] = {}
        for entry in entries:
            dep_count = len(entry.business_functions_supported)
            dependency_counts[entry.provider_name] = max(dep_count, 1)

        total_deps = sum(dependency_counts.values())
        provider_shares: dict[str, float] = {
            name: round(count / total_deps * 100, 2)
            for name, count in dependency_counts.items()
        }

        # HHI = sum of squared percentage shares
        hhi = sum(s ** 2 for s in provider_shares.values())

        if hhi >= HHI_CONCENTRATED:
            hhi_interpretation = "highly_concentrated"
        elif hhi >= HHI_MODERATELY_CONCENTRATED:
            hhi_interpretation = "moderately_concentrated"
        else:
            hhi_interpretation = "unconcentrated"

        # ---- Single-provider dependency detection ----
        # A business function is "single-provider" when exactly one entry
        # lists it in business_functions_supported and no exit strategy exists.
        function_to_providers: dict[str, list[str]] = {}
        function_to_exit: dict[str, bool] = {}

        for entry in entries:
            for func in entry.business_functions_supported:
                function_to_providers.setdefault(func, []).append(entry.provider_name)
                function_to_exit[func] = (
                    function_to_exit.get(func, False)
                    or entry.exit_strategy.alternative_provider_identified
                )

        single_provider_deps: dict[str, str] = {
            func: providers[0]
            for func, providers in function_to_providers.items()
            if len(providers) == 1 and not function_to_exit.get(func, False)
        }

        # ---- Geographic concentration ----
        country_counts: dict[str, int] = {}
        for entry in entries:
            c = entry.provider_country_of_incorporation or "Unknown"
            country_counts[c] = country_counts.get(c, 0) + 1

        geo_dist: dict[str, float] = {
            country: round(count / total * 100, 2)
            for country, count in country_counts.items()
        }
        dominant_country = max(geo_dist, key=lambda c: geo_dist[c])
        geo_concentration_risk = geo_dist[dominant_country] / 100 > GEO_CONCENTRATION_THRESHOLD

        # ---- Service-type concentration ----
        type_counts: dict[str, int] = {}
        for entry in entries:
            t = entry.ict_service_type or "Unknown"
            type_counts[t] = type_counts.get(t, 0) + 1

        type_dist: dict[str, float] = {
            t: round(count / total * 100, 2)
            for t, count in type_counts.items()
        }
        dominant_type = max(type_dist, key=lambda t: type_dist[t])
        type_concentration_risk = type_dist[dominant_type] / 100 > SERVICE_TYPE_CONCENTRATION_THRESHOLD

        # ---- Overall risk level ----
        risk_indicators: list[str] = []
        recommendations: list[str] = []

        if hhi >= HHI_CONCENTRATED:
            risk_indicators.append(f"HHI {hhi:.0f} — highly concentrated provider landscape")
            recommendations.append(
                "Diversify ICT providers: current concentration exceeds DoJ highly-concentrated "
                "threshold (HHI ≥ 2500).  Engage at least one alternative for critical services."
            )
        elif hhi >= HHI_MODERATELY_CONCENTRATED:
            risk_indicators.append(f"HHI {hhi:.0f} — moderately concentrated")
            recommendations.append(
                "Monitor provider concentration and consider diversification strategy."
            )

        if single_provider_deps:
            funcs = ", ".join(list(single_provider_deps.keys())[:5])
            risk_indicators.append(
                f"{len(single_provider_deps)} business function(s) depend on a single provider "
                f"with no documented alternative: {funcs}"
            )
            recommendations.append(
                "Document and test exit strategies for all single-provider critical functions "
                "per DORA Art. 28(4)(j)."
            )

        if geo_concentration_risk:
            risk_indicators.append(
                f"Geographic concentration: {geo_dist[dominant_country]:.0f}% of providers "
                f"incorporated in {dominant_country}"
            )
            recommendations.append(
                f"Reduce geographic concentration in {dominant_country}: "
                "consider providers incorporated in other jurisdictions to mitigate "
                "country-specific regulatory or geopolitical risk."
            )

        if type_concentration_risk:
            risk_indicators.append(
                f"Service-type concentration: {type_dist[dominant_type]:.0f}% of providers "
                f"supply '{dominant_type}'"
            )
            recommendations.append(
                f"Diversify '{dominant_type}' provision: multiple providers of the same service "
                "type increases correlated failure risk."
            )

        if critical_count > total * 0.5:
            risk_indicators.append(
                f"High criticality ratio: {critical_count} of {total} providers are 'critical'"
            )
            recommendations.append(
                "Review criticality classifications to ensure they reflect actual business impact.  "
                "Over-classifying providers as critical can mask the true risk profile."
            )

        # Determine overall risk level
        critical_issues = sum([
            hhi >= HHI_CONCENTRATED,
            bool(single_provider_deps) and any(
                e.criticality == "critical" and f in single_provider_deps
                for e in entries
                for f in e.business_functions_supported
            ),
        ])
        medium_issues = sum([
            hhi >= HHI_MODERATELY_CONCENTRATED,
            geo_concentration_risk,
            type_concentration_risk,
        ])

        if critical_issues >= 1:
            overall_risk = "critical"
        elif medium_issues >= 2:
            overall_risk = "high"
        elif medium_issues >= 1 or bool(single_provider_deps):
            overall_risk = "medium"
        else:
            overall_risk = "low"

        return ConcentrationRiskReport(
            hhi=round(hhi, 2),
            hhi_interpretation=hhi_interpretation,
            total_providers=total,
            critical_provider_count=critical_count,
            provider_shares=provider_shares,
            single_provider_dependencies=single_provider_deps,
            geographic_distribution=geo_dist,
            geographic_concentration_risk=geo_concentration_risk,
            dominant_country=dominant_country,
            service_type_distribution=type_dist,
            service_type_concentration_risk=type_concentration_risk,
            dominant_service_type=dominant_type,
            overall_risk_level=overall_risk,
            risk_indicators=risk_indicators,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_json(self, output_path: Path) -> None:
        """Export the register and concentration risk report to a JSON file.

        Args:
            output_path: Destination path for the JSON file.
        """
        entries = self.build()
        risk_report = self.concentration_risk_report()

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "regulatory_framework": "DORA Article 28, EU 2022/2554",
            "its_reference": "ITS 2024/2956",
            "reporting_entity": {
                "name": self._entity_name,
                "lei": self._entity_lei,
                "country": self._entity_country,
            },
            "total_providers": len(entries),
            "register_of_information": [self._entry_to_dict(e) for e in entries],
            "concentration_risk_analysis": asdict(risk_report),
        }

        output_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Register exported to JSON: %s", output_path)

    def export_csv(self, output_path: Path) -> None:
        """Export the register to CSV using the ITS 2024/2956 column layout.

        Columns follow the Annex I table in ITS 2024/2956.  Nested objects
        (sub-contractors, data locations, etc.) are serialised as
        semicolon-delimited strings to fit the flat CSV format.

        Args:
            output_path: Destination path for the CSV file.
        """
        entries = self.build()

        # ITS 2024/2956 Annex I column names (abbreviated to fit the CSV format)
        fieldnames = [
            # Entity
            "entity_name",
            "entity_lei",
            "entity_country",
            # Provider
            "provider_id",
            "provider_name",
            "provider_lei",
            "provider_country_of_incorporation",
            "provider_parent_company",
            # Service
            "ict_service_type",
            "service_description",
            "criticality",
            "business_functions_supported",
            # Contract
            "contract_reference",
            "contract_start_date",
            "contract_end_date",
            "renewal_terms",
            "termination_notice_period_days",
            # Sub-contracting
            "sub_contractor_names",
            "sub_contractor_countries",
            # Audit
            "audit_scope",
            "audit_frequency",
            "audit_last_date",
            "audit_right_to_inspect",
            "audit_pooled_allowed",
            # Exit
            "exit_strategy_documented",
            "exit_last_tested",
            "exit_transition_days",
            "exit_alternative_identified",
            # Data
            "data_locations",
            "cross_border_transfers",
            "data_encryption_at_rest",
            "data_encryption_in_transit",
            # Risk flags
            "concentration_risk",
            "single_provider_dependency",
            "geographic_concentration_risk",
            # Meta
            "auto_populated",
            "last_assessed",
        ]

        rows = []
        for e in entries:
            rows.append({
                "entity_name": e.entity_name,
                "entity_lei": e.entity_lei,
                "entity_country": e.entity_country,
                "provider_id": e.provider_id,
                "provider_name": e.provider_name,
                "provider_lei": e.provider_lei,
                "provider_country_of_incorporation": e.provider_country_of_incorporation,
                "provider_parent_company": e.provider_parent_company,
                "ict_service_type": e.ict_service_type,
                "service_description": e.service_description,
                "criticality": e.criticality,
                "business_functions_supported": "; ".join(e.business_functions_supported),
                "contract_reference": e.contract_reference,
                "contract_start_date": e.contract_start_date,
                "contract_end_date": e.contract_end_date,
                "renewal_terms": e.renewal_terms,
                "termination_notice_period_days": e.termination_notice_period_days,
                "sub_contractor_names": "; ".join(
                    sc.name for sc in e.sub_contractors
                ),
                "sub_contractor_countries": "; ".join(
                    sc.country_of_incorporation for sc in e.sub_contractors
                ),
                "audit_scope": e.audit_rights.scope,
                "audit_frequency": e.audit_rights.frequency,
                "audit_last_date": e.audit_rights.last_audit_date,
                "audit_right_to_inspect": e.audit_rights.right_to_inspect,
                "audit_pooled_allowed": e.audit_rights.pooled_audit_allowed,
                "exit_strategy_documented": e.exit_strategy.documented,
                "exit_last_tested": e.exit_strategy.last_tested_date,
                "exit_transition_days": e.exit_strategy.estimated_transition_days,
                "exit_alternative_identified": e.exit_strategy.alternative_provider_identified,
                "data_locations": "; ".join(e.data_handling.data_locations),
                "cross_border_transfers": e.data_handling.cross_border_transfers,
                "data_encryption_at_rest": e.data_handling.encryption_at_rest,
                "data_encryption_in_transit": e.data_handling.encryption_in_transit,
                "concentration_risk": e.concentration_risk,
                "single_provider_dependency": e.single_provider_dependency,
                "geographic_concentration_risk": e.geographic_concentration_risk,
                "auto_populated": e.auto_populated,
                "last_assessed": e.last_assessed,
            })

        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        logger.info("Register exported to CSV: %s (%d rows)", output_path, len(rows))

    def summary_report(self) -> dict[str, Any]:
        """Generate a human-readable summary with risk indicators.

        Returns:
            A JSON-serialisable dict suitable for inclusion in a DORA audit
            package or display in a dashboard.
        """
        entries = self.build()
        risk_report = self.concentration_risk_report()

        critical = [e for e in entries if e.criticality == "critical"]
        important = [e for e in entries if e.criticality == "important"]
        standard = [e for e in entries if e.criticality == "standard"]

        providers_without_exit = [
            e.provider_name for e in entries if not e.exit_strategy.documented
        ]
        providers_without_audit = [
            e.provider_name for e in entries if not e.audit_rights.right_to_inspect
        ]
        providers_without_lei = [
            e.provider_name for e in entries if not e.provider_lei
        ]
        providers_with_cross_border = [
            e.provider_name for e in entries if e.data_handling.cross_border_transfers
        ]

        return {
            "section": "DORA Article 28 Register of Information — Summary",
            "regulatory_reference": "DORA Article 28, EU 2022/2554 | ITS 2024/2956",
            "reporting_entity": {
                "name": self._entity_name,
                "lei": self._entity_lei,
                "country": self._entity_country,
            },
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "provider_count": {
                "total": len(entries),
                "critical": len(critical),
                "important": len(important),
                "standard": len(standard),
            },
            "completeness_indicators": {
                "providers_without_exit_strategy": providers_without_exit,
                "providers_without_audit_rights": providers_without_audit,
                "providers_without_lei": providers_without_lei,
                "providers_with_cross_border_transfers": providers_with_cross_border,
                "auto_populated_count": sum(1 for e in entries if e.auto_populated),
                "overlay_enriched_count": sum(1 for e in entries if e.provider_id in self._overlay),
            },
            "concentration_risk": {
                "overall_risk_level": risk_report.overall_risk_level,
                "hhi": risk_report.hhi,
                "hhi_interpretation": risk_report.hhi_interpretation,
                "single_provider_dependencies": len(risk_report.single_provider_dependencies),
                "geographic_concentration_risk": risk_report.geographic_concentration_risk,
                "service_type_concentration_risk": risk_report.service_type_concentration_risk,
                "risk_indicators": risk_report.risk_indicators,
                "recommendations": risk_report.recommendations,
            },
            "required_actions": self._compute_required_actions(entries),
        }

    # ------------------------------------------------------------------
    # Private — auto-population
    # ------------------------------------------------------------------

    def _auto_populate(self) -> list[RegisterEntry]:
        """Build register entries from the InfraGraph."""
        graph = self._graph
        now_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        total_components = len(graph.components)
        all_external = [
            c for c in graph.components.values()
            if c.type in (
                ComponentType.EXTERNAL_API,
                ComponentType.LLM_ENDPOINT,
                ComponentType.AI_AGENT,
                ComponentType.TOOL_SERVICE,
                ComponentType.AGENT_ORCHESTRATOR,
            )
        ]
        internal_count = total_components - len(all_external)

        entries: list[RegisterEntry] = []

        for comp in all_external:
            dependents = graph.get_dependents(comp.id)
            dep_names = [d.name for d in dependents]
            dep_count = len(dependents)

            # Infer ICT service type
            ict_type = ICT_SERVICE_TYPES.get(comp.type, "ICT Application Service")

            # Infer criticality
            ext_ratio = len(all_external) / max(internal_count, 1)
            if dep_count >= 3 or (internal_count > 0 and ext_ratio > 0.4):
                criticality = "critical"
            elif dep_count >= 1:
                criticality = "important"
            else:
                criticality = "standard"

            # Concentration risk: external providers dominate the topology
            concentration_risk = len(all_external) > total_components * 0.5

            # Single-provider dependency: this is the only provider for a function
            # For auto-population we mark it as True if dep_count >= 1 and no failover
            # (a manual overlay can provide more precise function-level info)
            single_provider_dep = dep_count >= 1 and not comp.failover.enabled

            # Exit strategy: infer from failover config
            exit_strategy = ExitStrategy(
                documented=comp.failover.enabled,
                estimated_transition_days=(
                    int(comp.failover.promotion_time_seconds / 86400)
                    if comp.failover.enabled else 0
                ),
                alternative_provider_identified=comp.failover.enabled,
            )

            # Data handling: infer from security profile
            data_handling = DataHandling(
                encryption_at_rest=comp.security.encryption_at_rest,
                encryption_in_transit=comp.security.encryption_in_transit,
                data_locations=_infer_data_locations(comp),
            )

            entry = RegisterEntry(
                # Entity fields will be filled from overlay/default
                entity_name=self._entity_name,
                entity_lei=self._entity_lei,
                entity_country=self._entity_country,
                # Provider
                provider_id=comp.id,
                provider_name=comp.name,
                provider_lei="",           # Requires manual overlay
                provider_country_of_incorporation=(
                    comp.region.region or "Unknown"
                ),
                # Service
                ict_service_type=ict_type,
                service_description=(
                    f"External {ict_type} '{comp.name}' providing ICT capabilities "
                    f"to {dep_count} internal component(s): "
                    + (", ".join(dep_names[:5]) or "none")
                    + ("…" if len(dep_names) > 5 else "")
                ),
                criticality=criticality,
                business_functions_supported=dep_names,
                # Contract — requires overlay
                contract_reference="",
                contract_start_date="",
                contract_end_date="",
                renewal_terms="",
                termination_notice_period_days=0,
                # Sub-contracting — requires overlay
                sub_contractors=[],
                # Audit rights — requires overlay
                audit_rights=AuditRights(),
                # Exit strategy
                exit_strategy=exit_strategy,
                # Data handling
                data_handling=data_handling,
                # Risk flags
                concentration_risk=concentration_risk,
                single_provider_dependency=single_provider_dep,
                geographic_concentration_risk=False,  # computed at register level
                # Meta
                auto_populated=True,
                last_assessed=now_date,
            )
            entries.append(entry)

        return entries

    # ------------------------------------------------------------------
    # Private — overlay merging
    # ------------------------------------------------------------------

    def _apply_provider_overlay(self, entry: RegisterEntry, overlay: dict) -> None:
        """Merge overlay data into an existing :class:`RegisterEntry` in place."""
        # Scalar fields — direct overwrite
        scalar_fields = [
            "provider_lei",
            "provider_country_of_incorporation",
            "provider_parent_company",
            "ict_service_type",
            "service_description",
            "criticality",
            "contract_reference",
            "contract_start_date",
            "contract_end_date",
            "renewal_terms",
            "termination_notice_period_days",
        ]
        for f in scalar_fields:
            if f in overlay:
                setattr(entry, f, overlay[f])

        # Business functions (additive or replacement)
        if "business_functions_supported" in overlay:
            entry.business_functions_supported = overlay["business_functions_supported"]

        # Audit rights
        audit_data = overlay.get("audit_rights", {})
        if audit_data:
            entry.audit_rights = AuditRights(
                scope=audit_data.get("scope", entry.audit_rights.scope),
                frequency=audit_data.get("frequency", entry.audit_rights.frequency),
                last_audit_date=audit_data.get("last_audit_date", entry.audit_rights.last_audit_date),
                right_to_inspect=audit_data.get("right_to_inspect", entry.audit_rights.right_to_inspect),
                right_to_request_third_party_audit=audit_data.get(
                    "right_to_request_third_party_audit",
                    entry.audit_rights.right_to_request_third_party_audit,
                ),
                pooled_audit_allowed=audit_data.get(
                    "pooled_audit_allowed", entry.audit_rights.pooled_audit_allowed
                ),
            )

        # Exit strategy
        exit_data = overlay.get("exit_strategy", {})
        if exit_data:
            entry.exit_strategy = ExitStrategy(
                documented=exit_data.get("documented", entry.exit_strategy.documented),
                last_tested_date=exit_data.get("last_tested_date", entry.exit_strategy.last_tested_date),
                estimated_transition_days=exit_data.get(
                    "estimated_transition_days", entry.exit_strategy.estimated_transition_days
                ),
                alternative_provider_identified=exit_data.get(
                    "alternative_provider_identified",
                    entry.exit_strategy.alternative_provider_identified,
                ),
                transition_plan_path=exit_data.get(
                    "transition_plan_path", entry.exit_strategy.transition_plan_path
                ),
            )

        # Data handling
        dh_data = overlay.get("data_handling", {})
        if dh_data:
            entry.data_handling = DataHandling(
                data_locations=dh_data.get("data_locations", entry.data_handling.data_locations),
                cross_border_transfers=dh_data.get(
                    "cross_border_transfers", entry.data_handling.cross_border_transfers
                ),
                transfer_mechanism=dh_data.get(
                    "transfer_mechanism", entry.data_handling.transfer_mechanism
                ),
                encryption_at_rest=dh_data.get(
                    "encryption_at_rest", entry.data_handling.encryption_at_rest
                ),
                encryption_in_transit=dh_data.get(
                    "encryption_in_transit", entry.data_handling.encryption_in_transit
                ),
                data_residency_requirements=dh_data.get(
                    "data_residency_requirements",
                    entry.data_handling.data_residency_requirements,
                ),
            )

        # Sub-contractors
        sc_list = overlay.get("sub_contractors", [])
        if sc_list:
            entry.sub_contractors = [
                SubContractor(
                    name=sc.get("name", ""),
                    lei=sc.get("lei", ""),
                    country_of_incorporation=sc.get("country_of_incorporation", "Unknown"),
                    services_provided=sc.get("services_provided", []),
                    is_intra_group=sc.get("is_intra_group", False),
                )
                for sc in sc_list
            ]

        # Risk flag overrides
        if "concentration_risk" in overlay:
            entry.concentration_risk = bool(overlay["concentration_risk"])
        if "single_provider_dependency" in overlay:
            entry.single_provider_dependency = bool(overlay["single_provider_dependency"])

        entry.auto_populated = False   # Now enriched with manual data

    # ------------------------------------------------------------------
    # Private — misc helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _entry_to_dict(entry: RegisterEntry) -> dict:
        """Serialise a :class:`RegisterEntry` to a plain dict."""
        return asdict(entry)

    @staticmethod
    def _compute_required_actions(entries: list[RegisterEntry]) -> list[str]:
        """Derive a list of required regulatory actions from the current register state."""
        actions: list[str] = []

        providers_without_lei = [e.provider_name for e in entries if not e.provider_lei]
        if providers_without_lei:
            actions.append(
                f"Obtain LEI codes for {len(providers_without_lei)} provider(s): "
                + ", ".join(providers_without_lei[:3])
                + ("…" if len(providers_without_lei) > 3 else "")
            )

        providers_without_contract = [
            e.provider_name for e in entries if not e.contract_start_date
        ]
        if providers_without_contract:
            actions.append(
                f"Record contract dates for {len(providers_without_contract)} provider(s): "
                + ", ".join(providers_without_contract[:3])
                + ("…" if len(providers_without_contract) > 3 else "")
            )

        providers_without_exit = [
            e.provider_name for e in entries if not e.exit_strategy.documented
        ]
        if providers_without_exit:
            actions.append(
                f"Document exit strategies for {len(providers_without_exit)} provider(s) "
                "(required per Art. 28(4)(j)): "
                + ", ".join(providers_without_exit[:3])
                + ("…" if len(providers_without_exit) > 3 else "")
            )

        providers_without_audit = [
            e.provider_name for e in entries
            if not e.audit_rights.right_to_inspect and e.criticality in ("critical", "important")
        ]
        if providers_without_audit:
            actions.append(
                f"Negotiate audit rights for {len(providers_without_audit)} critical/important "
                "provider(s) (required per Art. 28(3)(d)): "
                + ", ".join(providers_without_audit[:3])
                + ("…" if len(providers_without_audit) > 3 else "")
            )

        unencrypted_cross_border = [
            e.provider_name for e in entries
            if e.data_handling.cross_border_transfers
            and not e.data_handling.encryption_in_transit
        ]
        if unencrypted_cross_border:
            actions.append(
                f"Verify encryption for cross-border data transfers at "
                f"{len(unencrypted_cross_border)} provider(s): "
                + ", ".join(unencrypted_cross_border[:3])
            )

        return actions


# ---------------------------------------------------------------------------
# Module-level utility
# ---------------------------------------------------------------------------


def _infer_data_locations(comp: Component) -> list[str]:
    """Infer data location country codes from a component's region config."""
    locations: list[str] = []

    # Use region string if present (e.g. "us-east-1", "eu-west-2", "ap-southeast-1")
    region = comp.region.region
    if region:
        # Map cloud provider region prefixes to ISO 3166-1 alpha-2 country codes
        _REGION_TO_COUNTRY = {
            "us-": "US",
            "eu-": "EU",
            "ap-southeast-1": "SG",
            "ap-southeast-2": "AU",
            "ap-northeast-1": "JP",
            "ap-northeast-2": "KR",
            "ap-south-1": "IN",
            "sa-east-1": "BR",
            "ca-central-1": "CA",
            "me-south-1": "BH",
            "af-south-1": "ZA",
        }
        matched = False
        for prefix, country in _REGION_TO_COUNTRY.items():
            if region.startswith(prefix):
                locations.append(country)
                matched = True
                break
        if not matched and region:
            locations.append(region)  # Use raw region as placeholder

    # Use host field for domain-based inference (e.g. "api.example.de" → "DE")
    if comp.host:
        tld = comp.host.rsplit(".", 1)[-1].upper()
        if len(tld) == 2 and tld.isalpha() and tld not in ("CO", "IO", "AI"):
            locations.append(tld)

    return list(dict.fromkeys(locations))  # deduplicate preserving order
