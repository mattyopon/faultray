# Copyright (c) 2025-2026 Yutaro Maeda. All rights reserved.
# Licensed under the Apache License 2.0. See LICENSE file for details.

"""Multi-Region Disaster Recovery Engine.

Simulate cross-region failover scenarios, evaluate DR strategies,
and calculate Recovery Time Objective (RTO) / Recovery Point Objective (RPO).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum


class DRStrategy(str, Enum):
    ACTIVE_ACTIVE = "active_active"       # Both regions serve traffic
    ACTIVE_PASSIVE = "active_passive"     # Standby region for failover
    PILOT_LIGHT = "pilot_light"           # Minimal standby, scale on failover
    BACKUP_RESTORE = "backup_restore"     # Cold standby from backups


class FailoverTrigger(str, Enum):
    REGION_OUTAGE = "region_outage"
    AZ_OUTAGE = "az_outage"
    SERVICE_DEGRADATION = "service_degradation"
    MANUAL = "manual"
    DNS_HEALTH_CHECK = "dns_health_check"


class ReplicationMode(str, Enum):
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"
    SEMI_SYNCHRONOUS = "semi_synchronous"


@dataclass
class Region:
    name: str
    is_primary: bool = True
    latency_ms: float = 0.0  # inter-region latency
    services: list[str] = field(default_factory=list)
    capacity_percent: float = 100.0  # % of primary capacity


@dataclass
class DRConfig:
    strategy: DRStrategy = DRStrategy.ACTIVE_PASSIVE
    regions: list[Region] = field(default_factory=list)
    replication_mode: ReplicationMode = ReplicationMode.ASYNCHRONOUS
    replication_lag_seconds: float = 1.0
    failover_automation: bool = True
    dns_ttl_seconds: float = 60.0
    health_check_interval_seconds: float = 30.0


@dataclass
class DRAssessment:
    rto_seconds: float  # Recovery Time Objective
    rpo_seconds: float  # Recovery Point Objective
    rto_met: bool
    rpo_met: bool
    failover_steps: list[str] = field(default_factory=list)
    data_loss_risk: str = "none"  # none, minimal, moderate, significant
    cost_multiplier: float = 1.0  # cost vs single region
    availability_nines: float = 0.0
    risks: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class FailoverSimulation:
    trigger: FailoverTrigger
    detection_time_seconds: float
    decision_time_seconds: float
    execution_time_seconds: float
    total_time_seconds: float
    dns_propagation_seconds: float
    data_loss_seconds: float
    success: bool
    degraded_period_seconds: float = 0.0
    steps_log: list[str] = field(default_factory=list)


class MultiRegionDREngine:
    """Evaluate disaster recovery strategies and simulate failover."""

    # Base RTO components by strategy
    STRATEGY_BASE_RTO = {
        DRStrategy.ACTIVE_ACTIVE: 0,       # Near-zero, just DNS
        DRStrategy.ACTIVE_PASSIVE: 60,     # Standby warmup
        DRStrategy.PILOT_LIGHT: 600,       # Scale up + warmup
        DRStrategy.BACKUP_RESTORE: 3600,   # Full restore
    }

    STRATEGY_COST_MULTIPLIER = {
        DRStrategy.ACTIVE_ACTIVE: 2.0,
        DRStrategy.ACTIVE_PASSIVE: 1.6,
        DRStrategy.PILOT_LIGHT: 1.2,
        DRStrategy.BACKUP_RESTORE: 1.05,
    }

    def __init__(self, config: DRConfig, target_rto: float = 300, target_rpo: float = 60):
        self.config = config
        self.target_rto = target_rto  # seconds
        self.target_rpo = target_rpo  # seconds

    def assess(self) -> DRAssessment:
        """Assess the DR configuration against RTO/RPO targets."""
        # RTO calculation
        base_rto = self.STRATEGY_BASE_RTO[self.config.strategy]
        dns_time = self.config.dns_ttl_seconds if self.config.strategy != DRStrategy.ACTIVE_ACTIVE else 0
        detection_time = self.config.health_check_interval_seconds * 2 if self.config.failover_automation else 300
        rto = base_rto + dns_time + detection_time

        # RPO calculation
        if self.config.replication_mode == ReplicationMode.SYNCHRONOUS:
            rpo: float = 0.0
        elif self.config.replication_mode == ReplicationMode.SEMI_SYNCHRONOUS:
            rpo = self.config.replication_lag_seconds
        else:
            rpo = self.config.replication_lag_seconds * 2

        # Data loss risk
        if rpo == 0:
            data_loss = "none"
        elif rpo < 5:
            data_loss = "minimal"
        elif rpo < 60:
            data_loss = "moderate"
        else:
            data_loss = "significant"

        # Availability calculation
        nines = self._calculate_availability(rto)

        # Cost
        cost_mult = self.STRATEGY_COST_MULTIPLIER[self.config.strategy]

        # Risks
        risks = []
        recs = []
        if not self.config.failover_automation:
            risks.append("Manual failover increases RTO significantly")
            recs.append("Enable automated failover to reduce RTO")
        if self.config.dns_ttl_seconds > 300:
            risks.append(f"High DNS TTL ({self.config.dns_ttl_seconds}s) delays failover")
            recs.append("Reduce DNS TTL to 60s or lower")
        if self.config.replication_mode == ReplicationMode.ASYNCHRONOUS and self.config.replication_lag_seconds > 30:
            risks.append(f"High replication lag ({self.config.replication_lag_seconds}s) risks data loss")
            recs.append("Switch to synchronous or semi-synchronous replication")
        if len(self.config.regions) < 2:
            risks.append("Single region provides no DR capability")
            recs.append("Add at least one secondary region")

        # Capacity check
        secondary = [r for r in self.config.regions if not r.is_primary]
        if secondary and any(r.capacity_percent < 100 for r in secondary):
            risks.append("Secondary region has reduced capacity - may degrade during failover")

        # Failover steps
        steps = self._generate_failover_steps()

        return DRAssessment(
            rto_seconds=rto,
            rpo_seconds=rpo,
            rto_met=rto <= self.target_rto,
            rpo_met=rpo <= self.target_rpo,
            failover_steps=steps,
            data_loss_risk=data_loss,
            cost_multiplier=cost_mult,
            availability_nines=nines,
            risks=risks,
            recommendations=recs,
        )

    def simulate_failover(self, trigger: FailoverTrigger = FailoverTrigger.REGION_OUTAGE) -> FailoverSimulation:
        """Simulate a failover event and return detailed timeline."""
        detection = self.config.health_check_interval_seconds * 2 if self.config.failover_automation else 300
        decision = 5 if self.config.failover_automation else 120
        base_exec = self.STRATEGY_BASE_RTO[self.config.strategy]
        dns_prop = self.config.dns_ttl_seconds if self.config.strategy != DRStrategy.ACTIVE_ACTIVE else 0

        total = detection + decision + base_exec + dns_prop

        data_loss = 0.0
        if self.config.replication_mode != ReplicationMode.SYNCHRONOUS:
            data_loss = self.config.replication_lag_seconds

        steps = [
            f"T+0s: {trigger.value} detected",
            f"T+{detection}s: Health check confirms failure",
            f"T+{detection + decision}s: Failover decision made ({'auto' if self.config.failover_automation else 'manual'})",
        ]
        if base_exec > 0:
            steps.append(f"T+{detection + decision + base_exec}s: Secondary region ready")
        steps.append(f"T+{total}s: DNS propagation complete, traffic redirected")

        degraded = 0.0
        secondary = [r for r in self.config.regions if not r.is_primary]
        if secondary and secondary[0].capacity_percent < 100:
            degraded = 300  # 5 min scaling period

        return FailoverSimulation(
            trigger=trigger,
            detection_time_seconds=detection,
            decision_time_seconds=decision,
            execution_time_seconds=base_exec,
            total_time_seconds=total,
            dns_propagation_seconds=dns_prop,
            data_loss_seconds=data_loss,
            success=len(self.config.regions) >= 2,
            degraded_period_seconds=degraded,
            steps_log=steps,
        )

    def compare_strategies(self) -> list[DRAssessment]:
        """Compare all DR strategies for current config."""
        results = []
        for strategy in DRStrategy:
            config_copy = DRConfig(
                strategy=strategy,
                regions=self.config.regions,
                replication_mode=self.config.replication_mode,
                replication_lag_seconds=self.config.replication_lag_seconds,
                failover_automation=self.config.failover_automation,
                dns_ttl_seconds=self.config.dns_ttl_seconds,
                health_check_interval_seconds=self.config.health_check_interval_seconds,
            )
            engine = MultiRegionDREngine(config_copy, self.target_rto, self.target_rpo)
            results.append(engine.assess())
        return results

    def _calculate_availability(self, rto_seconds: float) -> float:
        """Calculate availability nines from RTO."""
        annual_downtime_hours = (rto_seconds / 3600) * 12  # assume 12 incidents/year
        if annual_downtime_hours <= 0:
            return 6.0
        availability = 1 - (annual_downtime_hours / 8760)
        if availability >= 1:
            return 6.0
        if availability <= 0:
            return 0.0
        nines = -math.log10(1 - availability)
        return round(min(nines, 6.0), 2)

    def _generate_failover_steps(self) -> list[str]:
        steps = ["Detect failure via health checks"]
        if self.config.failover_automation:
            steps.append("Automated failover triggered")
        else:
            steps.append("Alert on-call engineer for manual failover")

        if self.config.strategy == DRStrategy.ACTIVE_ACTIVE:
            steps.append("Traffic already distributed - remove unhealthy region from pool")
        elif self.config.strategy == DRStrategy.ACTIVE_PASSIVE:
            steps.append("Promote standby region to active")
            steps.append("Update DNS to point to secondary")
        elif self.config.strategy == DRStrategy.PILOT_LIGHT:
            steps.append("Scale up pilot light infrastructure")
            steps.append("Restore recent data from replication")
            steps.append("Update DNS to point to DR region")
        else:
            steps.append("Restore from latest backup")
            steps.append("Provision full infrastructure")
            steps.append("Validate data integrity")
            steps.append("Update DNS to point to DR region")

        steps.append("Verify application health in new region")
        return steps
