# Engine/Analyzer Classes Beyond the Patent's 36 Engines

Generated: 2026-03-17
Purpose: Patent attorney review - additional IP not yet covered in provisional patent draft

## Summary

- Patent draft claims: **36 engines**
- Actually implemented engine/analyzer classes: **~160 additional classes**
- All implemented in `/src/faultray/simulator/`
- All pure Python (no external ML dependencies)

---

## Categories

### Agent-Based & Advanced Simulation (5 classes)

| Class | File | Description |
|---|---|---|
| `ABMEngine` | `abm_engine.py` | Agent-Based Model engine for infrastructure resilience simulation |
| `GNNCascadePredictor` | `gnn_engine.py` | Graph Neural Network (MPNN) that predicts failure cascade patterns |
| `MLFailurePredictor` | `ml_failure_predictor.py` | Logistic regression model for component failure prediction |
| `PredictiveEngine` | `predictive_engine.py` | Predicts future failures from degradation trends and MTBF data |
| `PredictiveFailureEngine` | `predictive_failure.py` | Leading-indicator analysis for failure prediction |

### API & Gateway Resilience (7 classes)

| Class | File | Description |
|---|---|---|
| `APIGatewayResilienceAnalyzer` | `api_gateway_resilience.py` | API gateway configuration resilience analysis |
| `ApiVersioningImpactEngine` | `api_versioning_impact.py` | Resilience impact of API versioning strategies |
| `IdempotencyAnalyzer` | `idempotency_analyzer.py` | Idempotency pattern analysis across distributed services |
| `RateLimiterSimulator` | `rate_limiter_simulator.py` | Rate-limiter behaviour simulation |
| `ThrottleCascadeAnalyzer` | `throttle_cascade_analyzer.py` | Throttle-triggered cascade propagation analysis |
| `TimeoutBudgetAnalyzer` | `timeout_budget_analyzer.py` | Timeout configuration optimization across service chains |
| `WebhookResilienceAnalyzer` | `webhook_resilience_analyzer.py` | Webhook delivery resilience analysis |

### Backup, Recovery & Disaster Recovery (6 classes)

| Class | File | Description |
|---|---|---|
| `BackupRecoveryPlanner` | `backup_recovery_planner.py` | Backup and DR strategy evaluation |
| `DatabaseFailoverAnalyzer` | `database_failover_analyzer.py` | Database failover strategy reliability analysis |
| `DBFailoverSimulator` | `db_failover.py` | Database failover scenario simulation |
| `DisasterRecoveryEngine` | `disaster_recovery.py` | DR scenario simulation with RTO/RPO validation |
| `DREngine` | `dr_engine.py` | DR scenario simulation |
| `MultiRegionDREngine` | `multi_region_dr.py` | Multi-region failover evaluation |

### Cache, Queue & Messaging (5 classes)

| Class | File | Description |
|---|---|---|
| `CacheInvalidationEngine` | `cache_invalidation_strategy.py` | Cache invalidation strategy resilience analysis |
| `EventStormSimulatorEngine` | `event_storm_simulator.py` | Event storm impact simulation |
| `LoadSheddingEngine` | `load_shedding.py` | Load shedding and backpressure simulation |
| `QueueBackpressureAnalyzer` | `queue_backpressure_analyzer.py` | Queue backpressure cascade analysis |
| `QueueResilienceSimulator` | `queue_resilience.py` | Queue/event-stream failure simulation |

### Chaos Engineering Lifecycle (11 classes)

| Class | File | Description |
|---|---|---|
| `ChaosCorrelationEngine` | `chaos_correlation.py` | Cross-experiment pattern correlation |
| `ChaosCoverageEngine` | `chaos_coverage.py` | Chaos-test coverage tracking |
| `ChaosExperimentLibraryEngine` | `chaos_experiment_library.py` | Curated experiment template library |
| `ChaosGameDayPlanner` | `chaos_game_day_planner.py` | Game day exercise planning |
| `ChaosMaturityEngine` | `chaos_maturity.py` | Chaos engineering maturity assessment |
| `ChaosScheduleEngine` | `chaos_schedule.py` | Risk-based experiment scheduling |
| `FailureInjectionPlanner` | `failure_injection_planner.py` | Intelligent failure-injection sequence planning |
| `GameDayEngine` | `gameday_engine.py` | Game day exercise execution |
| `GameDayScoringEngine` | `gameday_scoring.py` | Game day exercise scoring |
| `GameDaySimulator` | `game_day.py` | Automated game day runner with multi-team support |
| `StateMachineChaosEngine` | `state_machine_chaos.py` | State machine chaos injection |

### Compliance & Regulatory (10 classes)

| Class | File | Description |
|---|---|---|
| `ComplianceDriftEngine` | `compliance_drift.py` | Compliance drift detection over time |
| `ComplianceEngine` | `compliance_engine.py` | SOC 2, PCI DSS, HIPAA compliance checking |
| `ComplianceFrameworksEngine` | `compliance_frameworks.py` | Multi-framework simultaneous evaluation |
| `ComplianceGapAnalyzer` | `compliance_gap.py` | Compliance gap analysis |
| `ComplianceMonitor` | `compliance_monitor.py` | Continuous compliance monitoring with alerting |
| `CompliancePostureEngine` | `compliance_posture.py` | Compliance posture assessment |
| `ComplianceScorecardEngine` | `compliance_scorecard.py` | Compliance scoring with actionable gaps |
| `DORAEvidenceEngine` | `dora_evidence.py` | EU DORA compliance evidence generation |
| `IaCResilienceValidatorEngine` | `infra_as_code_validator.py` | Infrastructure-as-Code resilience validation |
| `DataSovereigntyAnalyzer` | `data_sovereignty_analyzer.py` | Data sovereignty and residency compliance |

### Cost Analysis & FinOps (11 classes)

| Class | File | Description |
|---|---|---|
| `CostAnomalyDetector` | `cost_anomaly.py` | Cost anomaly detection |
| `CostAnomalyDetectorEngine` | `cost_anomaly_detector.py` | Cost anomaly and optimization analysis |
| `CostAttributionEngine` | `cost_attribution.py` | Failure cost attribution to teams/services |
| `CostImpactEngine` | `cost_engine.py` | Monetary cost impact calculation |
| `CostImpactEngine` | `cost_impact.py` | Business impact in financial terms |
| `CostOptimizer` | `cost_optimizer.py` | Cost savings while maintaining resilience |
| `CostResilienceOptimizer` | `cost_resilience_optimizer.py` | Cost-resilience tradeoff optimization |
| `FinOpsResilienceEngine` | `finops_resilience.py` | FinOps cost analysis tied to resilience |
| `InfrastructureCostOptimizer` | `infrastructure_cost_optimizer.py` | Multi-dimensional cost optimization |
| `ObservabilityCostEngine` | `observability_cost.py` | Observability tooling cost optimization |
| `StorageTierOptimizer` | `storage_tier_optimizer.py` | Storage tier placement optimization |

### Dependency & Topology Analysis (8 classes)

| Class | File | Description |
|---|---|---|
| `AntiPatternDetector` | `antipattern_detector.py` | Architectural anti-pattern detection |
| `ConnectionPoolAnalyzer` | `connection_pool_analyzer.py` | Connection pool saturation and failover risk |
| `ConsensusProtocolAnalyzer` | `consensus_protocol_analyzer.py` | Distributed consensus protocol resilience |
| `DependencyHealthEngine` | `dependency_health.py` | Health propagation through dependency graph |
| `DependencyInjectionAnalyzer` | `dependency_injection_analyzer.py` | DI pattern resilience risk |
| `DependencyRiskAnalyzer` | `dependency_risk.py` | Circular deps, SPOFs, high fan-in analysis |
| `ImpactAnalyzer` | `impact_matrix.py` | Cross-component dependency impact |
| `TopologyIntelligenceEngine` | `topology_intelligence.py` | Hidden dependency and risk discovery |

### Deployment & Release Engineering (9 classes)

| Class | File | Description |
|---|---|---|
| `CanaryAnalyzer` | `canary_analysis.py` | Canary analysis report generation |
| `CanaryRollbackEngine` | `canary_rollback.py` | Canary deployment and rollback simulation |
| `ChangeRiskPredictor` | `change_risk_predictor.py` | Change resilience impact prediction |
| `ChangeVelocityAnalyzer` | `change_velocity.py` | Change velocity impact on stability |
| `DeploymentStrategyAnalyzer` | `deployment_strategy_analyzer.py` | Blue/green, canary, rolling strategy evaluation |
| `DeploymentWindowEngine` | `deployment_window.py` | Deployment window risk analysis |
| `FeatureFlagInteractionEngine` | `feature_flag_interaction.py` | Feature-flag interaction analysis |
| `FeatureFlagRiskAnalyzer` | `feature_flag_risk_analyzer.py` | Feature flag blast radius analysis |
| `MigrationRiskEngine` | `migration_risk.py` | Cloud/platform migration risk assessment |

### Incident Management (7 classes)

| Class | File | Description |
|---|---|---|
| `IncidentCorrelationEngine` | `incident_correlation.py` | Cross-incident common cause identification |
| `IncidentCostEngine` | `incident_cost_model.py` | Incident financial cost modeling |
| `IncidentLearningEngine` | `incident_learning.py` | Incident history to chaos scenario conversion |
| `IncidentReplayEngine` | `incident_replay.py` | Historical outage replay |
| `IncidentResponseSimulator` | `incident_response_simulator.py` | Incident response process simulation |
| `RemediationEngine` | `remediation_engine.py` | Autonomous fix recommendation generation |
| `RemediationPlanner` | `planner.py` | Phased remediation plan generation |

### Observability & Monitoring (10 classes)

| Class | File | Description |
|---|---|---|
| `AlertFatigueEngine` | `alert_fatigue.py` | Alert fatigue risk analysis |
| `AnomalyDetector` | `anomaly_detector.py` | Infrastructure configuration anomaly detection |
| `DistributedTracingEngine` | `distributed_tracing_resilience.py` | Tracing pipeline resilience |
| `FreshnessAlertEngine` | `freshness_alert.py` | Data staleness alerting |
| `GoldenSignalAnalyzer` | `golden_signal_analyzer.py` | SRE 4 Golden Signals analysis |
| `HealthCheckStrategyOptimizer` | `health_check_strategy.py` | Health check strategy optimization |
| `HealthCheckValidationEngine` | `health_check_validator.py` | Health check configuration validation |
| `LogPipelineResilienceEngine` | `log_pipeline_resilience.py` | Log pipeline SPOF analysis |
| `ObservabilityGapAnalyzer` | `observability_gap_analyzer.py` | Observability coverage gap analysis |
| `SyntheticMonitorEngine` | `synthetic_monitor.py` | Synthetic monitoring probe simulation |

### Reliability & SLO/SLA (14 classes)

| Class | File | Description |
|---|---|---|
| `ErrorBudgetPolicyEngine` | `error_budget_policy.py` | Error budget policy compliance |
| `ReliabilityBudgetEngine` | `reliability_budget.py` | Cross-service reliability budget management |
| `ReliabilityContractEngine` | `reliability_contract.py` | Inter-service reliability contract verification |
| `ResilienceBenchmarkEngine` | `resilience_benchmark.py` | Industry peer benchmarking |
| `ResilienceForecastEngine` | `resilience_forecast.py` | Future resilience score prediction |
| `ResilienceRegressionEngine` | `resilience_regression.py` | Resilience regression detection |
| `RiskHeatMapEngine` | `risk_heatmap.py` | Multi-dimensional risk heat map |
| `SLACascadeEngine` | `sla_cascade.py` | Composite SLA and breach cascade modeling |
| `SLAContractAnalyzer` | `sla_contract_analyzer.py` | SLA contract vs topology capability analysis |
| `SLAValidatorEngine` | `sla_validator.py` | Mathematical SLA achievability validation |
| `SLAValidator` | `sla_contract_validator.py` | SLA contract commitment validation |
| `SLOBudgetSimulator` | `slo_budget.py` | Chaos risk vs SLO error budget simulation |
| `SLOBurnRateEngine` | `slo_burn_rate.py` | Multi-window burn-rate SLO alerting simulation |
| `SREMaturityEngine` | `sre_maturity.py` | SRE maturity assessment |

### Security (7 classes)

| Class | File | Description |
|---|---|---|
| `AIInfraResilienceAnalyzer` | `ai_infra_resilience.py` | AI/LLM infrastructure resilience analysis |
| `AttackSurfaceAnalyzer` | `attack_surface.py` | Attack surface analysis across entry points |
| `CertificateExpiryAnalyzer` | `certificate_expiry_analyzer.py` | TLS/SSL certificate lifecycle analysis |
| `SecretRotationEngine` | `secret_rotation.py` | Secret-rotation resilience impact analysis |
| `SecretRotationAnalyzer` | `secret_rotation_analyzer.py` | Comprehensive secret rotation analysis |
| `SecurityChaosEngine` | `security_chaos.py` | Compound failure + attack scenario simulation |
| `SupplyChainEngine` | `supply_chain_engine.py` | Software supply chain vulnerability mapping |

### Other (misc)

| Class | File | Description |
|---|---|---|
| `ServiceMeshAnalyzer` | `service_mesh.py` | Service mesh perspective analysis |
| `ServiceMeshConfigAnalyzer` | `service_mesh_analyzer.py` | Deep service mesh config analysis |
| `ServiceMeshResilienceEngine` | `service_mesh_resilience.py` | Service mesh resilience (retry storms, sidecar failures) |
| `TeamTopologyResilienceEngine` | `team_topology_resilience.py` | Conway's Law impact on resilience |
| `ExecutiveDashboardEngine` | `executive_dashboard.py` | Executive-level resilience KPI dashboard |
| `MultiCloudResilienceAnalyzer` | `multi_cloud_resilience.py` | Multi-cloud/hybrid deployment resilience |
| `MultiEnvAnalyzer` | `multi_env.py` | Cross-environment resilience comparison |
| `MultiTenantIsolationEngine` | `multi_tenant_isolation.py` | Multi-tenant isolation verification |
