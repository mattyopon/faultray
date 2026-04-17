# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Secret Rotation Resilience Simulator.

Simulates secret/credential rotation scenarios and their impact on service
availability.  Covers rotation strategies, expired secret detection, leaked
secret response, shared-secret risk analysis, and blast-radius estimation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field

from faultray.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SecretType(str, Enum):
    """Types of secrets / credentials managed by an organisation."""

    DATABASE_PASSWORD = "database_password"
    API_KEY = "api_key"
    TLS_CERTIFICATE = "tls_certificate"
    OAUTH_TOKEN = "oauth_token"
    ENCRYPTION_KEY = "encryption_key"
    SSH_KEY = "ssh_key"
    JWT_SIGNING_KEY = "jwt_signing_key"
    SERVICE_ACCOUNT = "service_account"
    CONNECTION_STRING = "connection_string"
    WEBHOOK_SECRET = "webhook_secret"


class RotationStrategy(str, Enum):
    """Strategies for rotating a secret with minimal disruption."""

    BLUE_GREEN = "blue_green"
    ROLLING = "rolling"
    DUAL_WRITE = "dual_write"
    GRACE_PERIOD = "grace_period"
    IMMEDIATE = "immediate"
    SCHEDULED_MAINTENANCE = "scheduled_maintenance"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class Secret(BaseModel):
    """A secret / credential that requires periodic rotation."""

    id: str
    name: str
    secret_type: SecretType
    component_ids: list[str] = Field(default_factory=list)
    rotation_strategy: RotationStrategy = RotationStrategy.GRACE_PERIOD
    rotation_interval_days: int = Field(default=90, ge=1)
    last_rotated: str = ""
    expiry_date: str = ""
    auto_rotation: bool = False


class RotationImpact(BaseModel):
    """Impact assessment of rotating a single secret."""

    secret_id: str
    affected_services: list[str] = Field(default_factory=list)
    downtime_seconds: float = Field(default=0.0, ge=0.0)
    connection_reset_count: int = Field(default=0, ge=0)
    cache_invalidation_needed: bool = False
    rollback_possible: bool = True
    risk_level: str = "low"
    recommendations: list[str] = Field(default_factory=list)


class RotationReadinessReport(BaseModel):
    """Readiness assessment for rotating all secrets in a graph."""

    total_secrets: int = 0
    ready_count: int = 0
    not_ready_count: int = 0
    expired_count: int = 0
    auto_rotation_count: int = 0
    readiness_score: float = Field(default=0.0, ge=0.0, le=100.0)
    recommendations: list[str] = Field(default_factory=list)


class LeakedSecretResponse(BaseModel):
    """Response plan for a leaked / compromised secret."""

    secret_id: str
    severity: str = "critical"
    affected_services: list[str] = Field(default_factory=list)
    immediate_actions: list[str] = Field(default_factory=list)
    rotation_time_seconds: float = Field(default=0.0, ge=0.0)
    service_disruption_seconds: float = Field(default=0.0, ge=0.0)
    requires_maintenance_window: bool = False
    rollback_possible: bool = True
    recommendations: list[str] = Field(default_factory=list)


class SharedSecretRisk(BaseModel):
    """Risk assessment for a secret shared across multiple components."""

    secret_id: str
    shared_component_ids: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    blast_radius: int = 0
    recommendations: list[str] = Field(default_factory=list)


class BlastRadiusResult(BaseModel):
    """Blast radius of rotating or losing a specific secret."""

    secret_id: str
    total_services: int = 0
    directly_affected: list[str] = Field(default_factory=list)
    transitively_affected: list[str] = Field(default_factory=list)
    affected_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    estimated_downtime_seconds: float = Field(default=0.0, ge=0.0)
    risk_level: str = "low"
    recommendations: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Base downtime per rotation strategy (seconds)
_STRATEGY_BASE_DOWNTIME: dict[RotationStrategy, float] = {
    RotationStrategy.BLUE_GREEN: 0.0,
    RotationStrategy.ROLLING: 5.0,
    RotationStrategy.DUAL_WRITE: 0.0,
    RotationStrategy.GRACE_PERIOD: 2.0,
    RotationStrategy.IMMEDIATE: 30.0,
    RotationStrategy.SCHEDULED_MAINTENANCE: 60.0,
}

# Rollback feasibility per strategy
_STRATEGY_ROLLBACK: dict[RotationStrategy, bool] = {
    RotationStrategy.BLUE_GREEN: True,
    RotationStrategy.ROLLING: True,
    RotationStrategy.DUAL_WRITE: True,
    RotationStrategy.GRACE_PERIOD: True,
    RotationStrategy.IMMEDIATE: False,
    RotationStrategy.SCHEDULED_MAINTENANCE: True,
}

# Secret type severity when leaked (higher = worse)
_SECRET_LEAK_SEVERITY: dict[SecretType, float] = {
    SecretType.DATABASE_PASSWORD: 0.95,
    SecretType.API_KEY: 0.6,
    SecretType.TLS_CERTIFICATE: 0.85,
    SecretType.OAUTH_TOKEN: 0.7,
    SecretType.ENCRYPTION_KEY: 0.95,
    SecretType.SSH_KEY: 0.9,
    SecretType.JWT_SIGNING_KEY: 0.85,
    SecretType.SERVICE_ACCOUNT: 0.8,
    SecretType.CONNECTION_STRING: 0.9,
    SecretType.WEBHOOK_SECRET: 0.5,
}

# Connection resets per component for each secret type
_SECRET_CONNECTION_RESETS: dict[SecretType, int] = {
    SecretType.DATABASE_PASSWORD: 50,
    SecretType.API_KEY: 10,
    SecretType.TLS_CERTIFICATE: 100,
    SecretType.OAUTH_TOKEN: 20,
    SecretType.ENCRYPTION_KEY: 5,
    SecretType.SSH_KEY: 15,
    SecretType.JWT_SIGNING_KEY: 30,
    SecretType.SERVICE_ACCOUNT: 25,
    SecretType.CONNECTION_STRING: 50,
    SecretType.WEBHOOK_SECRET: 5,
}

# Whether cache invalidation is needed per secret type
_SECRET_CACHE_INVALIDATION: dict[SecretType, bool] = {
    SecretType.DATABASE_PASSWORD: True,
    SecretType.API_KEY: True,
    SecretType.TLS_CERTIFICATE: True,
    SecretType.OAUTH_TOKEN: True,
    SecretType.ENCRYPTION_KEY: False,
    SecretType.SSH_KEY: False,
    SecretType.JWT_SIGNING_KEY: True,
    SecretType.SERVICE_ACCOUNT: True,
    SecretType.CONNECTION_STRING: True,
    SecretType.WEBHOOK_SECRET: False,
}


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* between *lo* and *hi*."""
    return max(lo, min(hi, value))


def _risk_level(score: float) -> str:
    """Map a 0-1 risk score to a human-readable level."""
    if score >= 0.8:
        return "critical"
    if score >= 0.6:
        return "high"
    if score >= 0.4:
        return "medium"
    return "low"


def _parse_iso(date_str: str) -> datetime | None:
    """Best-effort ISO-8601 date parsing (stdlib only)."""
    if not date_str:
        return None
    try:
        # Handle both timezone-aware and naive
        if date_str.endswith("Z"):
            date_str = date_str[:-1] + "+00:00"
        return datetime.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class SecretRotationEngine:
    """Stateless engine for secret-rotation resilience analysis."""

    # -- simulate rotation --------------------------------------------------

    def simulate_rotation(
        self,
        graph: InfraGraph,
        secret: Secret,
    ) -> RotationImpact:
        """Simulate rotating *secret* and assess the impact on services."""
        affected = self._resolve_affected_services(graph, secret)
        base_downtime = _STRATEGY_BASE_DOWNTIME[secret.rotation_strategy]
        resets_per_comp = _SECRET_CONNECTION_RESETS[secret.secret_type]
        cache_invalidation = _SECRET_CACHE_INVALIDATION[secret.secret_type]
        rollback = _STRATEGY_ROLLBACK[secret.rotation_strategy]
        recommendations: list[str] = []

        # Scale downtime by number of affected components
        num_affected = len(affected)
        downtime = base_downtime * max(1, num_affected)

        # Strategy-specific adjustments
        if secret.rotation_strategy == RotationStrategy.BLUE_GREEN:
            downtime = 0.0
            recommendations.append("Blue-green provides zero-downtime rotation")
        elif secret.rotation_strategy == RotationStrategy.ROLLING:
            downtime = base_downtime * max(1, num_affected)
            recommendations.append(
                "Rolling rotation introduces brief per-component downtime"
            )
        elif secret.rotation_strategy == RotationStrategy.DUAL_WRITE:
            downtime = 0.0
            recommendations.append(
                "Dual-write avoids downtime but increases complexity"
            )
        elif secret.rotation_strategy == RotationStrategy.GRACE_PERIOD:
            downtime = base_downtime * max(1, num_affected) * 0.5
            recommendations.append(
                "Grace period reduces disruption; ensure old secret is revoked after transition"
            )
        elif secret.rotation_strategy == RotationStrategy.IMMEDIATE:
            downtime = base_downtime * max(1, num_affected)
            recommendations.append(
                "Immediate rotation causes full service disruption; consider blue-green instead"
            )
        elif secret.rotation_strategy == RotationStrategy.SCHEDULED_MAINTENANCE:
            downtime = base_downtime
            recommendations.append(
                "Schedule rotation during low-traffic maintenance windows"
            )

        # Auto-rotation reduces risk
        if secret.auto_rotation:
            downtime *= 0.5
            recommendations.append("Auto-rotation is enabled, reducing manual error risk")
        else:
            recommendations.append("Enable auto-rotation to reduce human error")

        connection_resets = resets_per_comp * num_affected

        # Risk level based on strategy and number of affected components
        risk_score = 0.2
        if secret.rotation_strategy == RotationStrategy.IMMEDIATE:
            risk_score += 0.4
        elif secret.rotation_strategy == RotationStrategy.SCHEDULED_MAINTENANCE:
            risk_score += 0.2
        if num_affected > 5:
            risk_score += 0.3
        elif num_affected > 2:
            risk_score += 0.15
        if not secret.auto_rotation:
            risk_score += 0.1

        risk = _risk_level(min(1.0, risk_score))

        return RotationImpact(
            secret_id=secret.id,
            affected_services=affected,
            downtime_seconds=round(max(0.0, downtime), 2),
            connection_reset_count=max(0, connection_resets),
            cache_invalidation_needed=cache_invalidation,
            rollback_possible=rollback,
            risk_level=risk,
            recommendations=recommendations,
        )

    # -- detect expired secrets ---------------------------------------------

    def detect_expired_secrets(
        self,
        secrets: list[Secret],
    ) -> list[str]:
        """Return IDs of secrets whose expiry_date is in the past."""
        now = datetime.now(timezone.utc)
        expired: list[str] = []
        for s in secrets:
            expiry = _parse_iso(s.expiry_date)
            if expiry is not None:
                # Make timezone-aware if naive
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if expiry <= now:
                    expired.append(s.id)
        return expired

    # -- rotation readiness -------------------------------------------------

    def assess_rotation_readiness(
        self,
        graph: InfraGraph,
        secrets: list[Secret],
    ) -> RotationReadinessReport:
        """Assess overall readiness to rotate all *secrets*."""
        if not secrets:
            return RotationReadinessReport(
                readiness_score=100.0,
                recommendations=["No secrets to assess"],
            )

        expired_ids = set(self.detect_expired_secrets(secrets))
        ready = 0
        not_ready = 0
        auto_count = 0
        recommendations: list[str] = []

        for s in secrets:
            is_ready = True

            if s.id in expired_ids:
                is_ready = False

            # Check that all component_ids exist in the graph
            for cid in s.component_ids:
                if graph.get_component(cid) is None:
                    is_ready = False
                    break

            # Check rotation strategy readiness
            if s.rotation_strategy == RotationStrategy.IMMEDIATE:
                is_ready = False

            if s.auto_rotation:
                auto_count += 1

            if is_ready:
                ready += 1
            else:
                not_ready += 1

        # Score
        total = len(secrets)
        score = (ready / total) * 70.0

        # Bonus for auto-rotation
        if total > 0:
            auto_ratio = auto_count / total
            score += auto_ratio * 20.0

        # Bonus for no expired secrets
        if not expired_ids:
            score += 10.0
        else:
            recommendations.append(
                f"{len(expired_ids)} secret(s) have expired and require immediate rotation"
            )

        if auto_count < total:
            recommendations.append(
                f"{total - auto_count} secret(s) lack auto-rotation; enable it to reduce risk"
            )

        if not_ready > 0:
            recommendations.append(
                f"{not_ready} secret(s) are not ready for rotation"
            )

        # Check for IMMEDIATE strategy
        immediate_count = sum(
            1 for s in secrets
            if s.rotation_strategy == RotationStrategy.IMMEDIATE
        )
        if immediate_count > 0:
            recommendations.append(
                f"{immediate_count} secret(s) use immediate rotation strategy; "
                "consider switching to blue-green or grace-period"
            )

        return RotationReadinessReport(
            total_secrets=total,
            ready_count=ready,
            not_ready_count=not_ready,
            expired_count=len(expired_ids),
            auto_rotation_count=auto_count,
            readiness_score=round(_clamp(score), 2),
            recommendations=recommendations,
        )

    # -- leaked secret response ---------------------------------------------

    def simulate_leaked_secret(
        self,
        graph: InfraGraph,
        secret: Secret,
    ) -> LeakedSecretResponse:
        """Simulate the response to a leaked secret."""
        affected = self._resolve_affected_services(graph, secret)
        severity_score = _SECRET_LEAK_SEVERITY[secret.secret_type]
        severity = _risk_level(severity_score)
        recommendations: list[str] = []
        immediate_actions: list[str] = []

        # Immediate actions
        immediate_actions.append(f"Revoke compromised secret '{secret.name}' immediately")
        immediate_actions.append("Audit access logs for unauthorised usage")
        immediate_actions.append("Notify security team and initiate incident response")

        if secret.secret_type == SecretType.DATABASE_PASSWORD:
            immediate_actions.append("Force disconnect all active database sessions")
            immediate_actions.append("Rotate database password and update connection strings")
        elif secret.secret_type == SecretType.TLS_CERTIFICATE:
            immediate_actions.append("Revoke the compromised certificate via CRL/OCSP")
            immediate_actions.append("Issue and deploy a new certificate")
        elif secret.secret_type == SecretType.SSH_KEY:
            immediate_actions.append("Remove compromised public key from all authorized_keys")
            immediate_actions.append("Generate and deploy new SSH key pair")
        elif secret.secret_type == SecretType.API_KEY:
            immediate_actions.append("Invalidate the API key at the provider")
            immediate_actions.append("Generate and distribute a new API key")
        elif secret.secret_type == SecretType.ENCRYPTION_KEY:
            immediate_actions.append("Assess scope of data encrypted with compromised key")
            immediate_actions.append("Re-encrypt affected data with a new key")
        elif secret.secret_type == SecretType.JWT_SIGNING_KEY:
            immediate_actions.append("Invalidate all tokens signed with the compromised key")
            immediate_actions.append("Deploy new signing key and re-issue tokens")
        elif secret.secret_type == SecretType.OAUTH_TOKEN:
            immediate_actions.append("Revoke the OAuth token at the provider")
        elif secret.secret_type == SecretType.SERVICE_ACCOUNT:
            immediate_actions.append("Disable the compromised service account")
            immediate_actions.append("Create and configure a new service account")
        elif secret.secret_type == SecretType.CONNECTION_STRING:
            immediate_actions.append("Rotate all credentials embedded in the connection string")
        elif secret.secret_type == SecretType.WEBHOOK_SECRET:
            immediate_actions.append("Regenerate the webhook secret at the provider")

        # Rotation time estimate
        base_rotation_time = 60.0  # seconds
        if secret.auto_rotation:
            rotation_time = base_rotation_time
        else:
            rotation_time = base_rotation_time * 5.0  # manual is slower

        # Service disruption
        disruption = _STRATEGY_BASE_DOWNTIME[secret.rotation_strategy] * max(1, len(affected))

        # For immediate strategy with leaked secret, must act fast
        if secret.rotation_strategy == RotationStrategy.IMMEDIATE:
            disruption *= 1.5

        # Maintenance window needed for some secret types and strategies
        requires_maintenance = (
            secret.rotation_strategy == RotationStrategy.SCHEDULED_MAINTENANCE
            or (
                secret.secret_type in (SecretType.ENCRYPTION_KEY, SecretType.DATABASE_PASSWORD)
                and not secret.auto_rotation
            )
        )

        rollback = _STRATEGY_ROLLBACK[secret.rotation_strategy]

        # Recommendations
        if not secret.auto_rotation:
            recommendations.append("Enable auto-rotation to speed up emergency response")
        if secret.rotation_strategy == RotationStrategy.IMMEDIATE:
            recommendations.append(
                "Switch to blue-green or grace-period strategy for safer emergency rotation"
            )
        if len(affected) > 3:
            recommendations.append(
                "High number of affected services; consider secret per-service isolation"
            )
        recommendations.append("Implement secret scanning in CI/CD pipeline to prevent leaks")
        recommendations.append("Enable audit logging for all secret access")

        return LeakedSecretResponse(
            secret_id=secret.id,
            severity=severity,
            affected_services=affected,
            immediate_actions=immediate_actions,
            rotation_time_seconds=round(max(0.0, rotation_time), 2),
            service_disruption_seconds=round(max(0.0, disruption), 2),
            requires_maintenance_window=requires_maintenance,
            rollback_possible=rollback,
            recommendations=recommendations,
        )

    # -- recommend rotation strategy ----------------------------------------

    def recommend_rotation_strategy(
        self,
        graph: InfraGraph,
        secret: Secret,
    ) -> RotationStrategy:
        """Recommend the best rotation strategy for *secret* given the graph."""
        affected = self._resolve_affected_services(graph, secret)
        num_affected = len(affected)

        # High-impact secrets with many dependents -> blue-green
        if num_affected > 5:
            return RotationStrategy.BLUE_GREEN

        # TLS certificates and encryption keys need careful handling
        if secret.secret_type in (SecretType.TLS_CERTIFICATE, SecretType.ENCRYPTION_KEY):
            return RotationStrategy.DUAL_WRITE

        # Database passwords and connection strings -> grace period
        if secret.secret_type in (
            SecretType.DATABASE_PASSWORD,
            SecretType.CONNECTION_STRING,
        ):
            return RotationStrategy.GRACE_PERIOD

        # JWT and OAuth tokens -> rolling
        if secret.secret_type in (
            SecretType.JWT_SIGNING_KEY,
            SecretType.OAUTH_TOKEN,
        ):
            return RotationStrategy.ROLLING

        # Low-impact secrets -> grace period
        if num_affected <= 1:
            return RotationStrategy.GRACE_PERIOD

        # Default: rolling for moderate impact
        return RotationStrategy.ROLLING

    # -- find shared secrets ------------------------------------------------

    def find_shared_secrets(
        self,
        secrets: list[Secret],
    ) -> list[SharedSecretRisk]:
        """Find secrets shared across multiple components and assess risk."""
        results: list[SharedSecretRisk] = []
        for s in secrets:
            if len(s.component_ids) <= 1:
                continue

            blast = len(s.component_ids)
            risk_score = 0.2
            if blast >= 5:
                risk_score += 0.5
            elif blast >= 3:
                risk_score += 0.3
            elif blast >= 2:
                risk_score += 0.15

            # High-severity secret types amplify risk
            type_severity = _SECRET_LEAK_SEVERITY[s.secret_type]
            risk_score += type_severity * 0.3

            risk = _risk_level(min(1.0, risk_score))
            recommendations: list[str] = []

            if blast >= 3:
                recommendations.append(
                    f"Secret '{s.name}' is shared across {blast} components; "
                    "use per-service credentials to limit blast radius"
                )
            if blast >= 2:
                recommendations.append(
                    "Implement secret versioning to allow phased rotation"
                )
            if not s.auto_rotation:
                recommendations.append("Enable auto-rotation for shared secrets")

            results.append(
                SharedSecretRisk(
                    secret_id=s.id,
                    shared_component_ids=list(s.component_ids),
                    risk_level=risk,
                    blast_radius=blast,
                    recommendations=recommendations,
                )
            )
        return results

    # -- blast radius -------------------------------------------------------

    def calculate_rotation_blast_radius(
        self,
        graph: InfraGraph,
        secret: Secret,
    ) -> BlastRadiusResult:
        """Calculate the blast radius of rotating (or losing) *secret*."""
        total_services = len(graph.components)
        if total_services == 0:
            return BlastRadiusResult(
                secret_id=secret.id,
                recommendations=["No services found in graph"],
            )

        # Directly affected: components that use this secret
        directly_affected: list[str] = []
        for cid in secret.component_ids:
            if graph.get_component(cid) is not None:
                directly_affected.append(cid)

        # Transitively affected: components that depend on directly affected ones
        transitively_affected_set: set[str] = set()
        for cid in directly_affected:
            for dep_id in graph.get_all_affected(cid):
                if dep_id not in directly_affected:
                    transitively_affected_set.add(dep_id)

        transitively_affected = sorted(transitively_affected_set)
        all_affected = set(directly_affected) | transitively_affected_set
        affected_pct = _clamp((len(all_affected) / total_services) * 100.0)

        # Downtime estimation
        base_downtime = _STRATEGY_BASE_DOWNTIME[secret.rotation_strategy]
        downtime = base_downtime * max(1, len(directly_affected))

        if secret.auto_rotation:
            downtime *= 0.5

        # Risk level
        risk_score = 0.1
        if affected_pct > 50.0:
            risk_score += 0.5
        elif affected_pct > 25.0:
            risk_score += 0.3
        elif affected_pct > 10.0:
            risk_score += 0.15

        if len(directly_affected) > 3:
            risk_score += 0.2

        type_severity = _SECRET_LEAK_SEVERITY[secret.secret_type]
        risk_score += type_severity * 0.2

        risk = _risk_level(min(1.0, risk_score))

        # Recommendations
        recommendations: list[str] = []
        if affected_pct > 50.0:
            recommendations.append(
                "Over 50% of services affected; implement per-service secrets"
            )
        if len(transitively_affected) > 0:
            recommendations.append(
                f"{len(transitively_affected)} service(s) transitively affected; "
                "add circuit breakers to limit cascade"
            )
        if not secret.auto_rotation:
            recommendations.append("Enable auto-rotation to reduce blast radius duration")
        if secret.rotation_strategy == RotationStrategy.IMMEDIATE:
            recommendations.append(
                "Avoid immediate rotation for high-blast-radius secrets"
            )
        if len(directly_affected) > 3:
            recommendations.append(
                "Consider splitting this secret into per-service credentials"
            )

        return BlastRadiusResult(
            secret_id=secret.id,
            total_services=total_services,
            directly_affected=directly_affected,
            transitively_affected=transitively_affected,
            affected_percent=round(affected_pct, 2),
            estimated_downtime_seconds=round(max(0.0, downtime), 2),
            risk_level=risk,
            recommendations=recommendations,
        )

    # -- private helpers ----------------------------------------------------

    def _resolve_affected_services(
        self,
        graph: InfraGraph,
        secret: Secret,
    ) -> list[str]:
        """Return component IDs affected by *secret*, validated against *graph*."""
        affected: list[str] = []
        for cid in secret.component_ids:
            if graph.get_component(cid) is not None:
                affected.append(cid)
        return affected
