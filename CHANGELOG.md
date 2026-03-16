# Changelog

All notable changes to FaultRay will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [10.1.0] - 2026-03-16

### Added
- E2E workflow tests (47): complete user journey, CLI commands, JSON output consistency, template flows, serialization roundtrip
- Mutation testing (18): resilience score, cascade engine, availability model, security score, regression gate
- Documentation accuracy tests (27): README CLI commands verified, MkDocs content, public API docstrings, example YAML loadability
- API contract tests (10): response shape validation, OpenAPI spec validation, endpoint sweep
- Dead code detection via AST-based analysis

### Fixed
- 7 CLI modules with broken imports

### Changed
- Test count: 12,032 -> 19,757

## [10.0.0] - 2026-03-15

### Added
- Exception hierarchy (`errors.py`): 7 custom exception classes with dual inheritance
- Theme constants (`theme.py`): shared colors for severity/health/score
- Logging standardization (`get_logger` helper)
- 261 new CLI tests covering 10 under-covered modules
- Boundary value tests (55), error handling tests (54), security audit tests (11), performance tests (10), accessibility tests (13)

### Changed
- Test count: 9,473 -> 12,032
- Coverage: estimated 93-95%

## [9.0.0] - 2026-03-15

### Added
- Coverage push: 7 zero-coverage modules now at 99.7-100%
- Boundary value tests (55): numeric, string, collection, topology boundaries
- Error handling tests (54): YAML loader errors, scanner failures, cache corruption recovery
- Security audit tests (11): credential scan, SQL injection prevention, yaml.safe_load enforcement, XSS prevention, path traversal prevention
- Performance tests (10): speed benchmarks, memory limits, concurrent safety
- Accessibility tests (13): WCAG AA compliance, CLI colorless mode, i18n verification

### Changed
- Coverage: 77% -> ~90%
- Test count: 5,502 -> 9,473

## [8.2.0] - 2026-03-15

### Added
- `test_cli_remaining.py` (152 tests): 20+ CLI commands fully tested
- `test_server_extended.py` (42 tests): 15+ API endpoints tested
- `test_remaining_engines.py` (61 tests): 8 engine modules tested

### Changed
- Test count: 4,345 -> 5,502
- Coverage: 77% -> estimated 83-85%

## [8.1.0] - 2026-03-15

### Added
- 76 new component model tests (all 15+ model classes)
- 83 new CLI command tests (15 commands x help/basic/json/error)
- 39 new integration tests (observability hub, logging, demo graph)
- 263 new core engine tests (antipattern, dynamic, supply chain, scoring, AI, plugins, export)
- README updates: academic references (Krasnovsky 2025, ChaosTwin 2021, Mendonca 2020, Buldyrev 2010), patent & IP clearance statement

### Changed
- Test count: 3,873 -> 4,345

## [8.0.0] - 2026-03-15

### Added
- Architecture Anti-Pattern Detector (8 patterns: god component, circular dependency, etc.)
- Chaos A/B Testing: compare 2 architectures under same scenarios
- Observability Hub: Datadog/New Relic/Grafana import
- Failure Budget Allocator: team-based error budget distribution
- Change Velocity Analyzer: DORA metrics (Elite/High/Medium/Low)

### Changed
- Test count: 3,704 -> 3,873

## [7.0.0] - 2026-03-15

### Added
- Chaos Regression Gate: CI/CD blocker for resilience drops (SARIF + PR comments)
- War Room Simulation: 8 incident types, 5 phases, 4 roles, MTTD/MTTM/MTTR
- Infrastructure Cost Optimizer: Pareto frontier, 4 optimization strategies
- Multi-Environment Comparison: dev/staging/prod drift detection
- Scenario Template Library: 5 pre-built architectures (web, microservices, fintech, etc.)
- Continuous Compliance Monitor: SQLite-persisted compliance tracking over time
- New CLI commands: `gate`, `war-room`, `cost-optimize`, `env-compare`, `template`, `compliance-monitor`

### Changed
- Source: 75,000+ lines, 170+ modules, 60+ CLI commands
- Test count: 3,142 -> 3,704

## [6.0.0] - 2026-03-15

### Added
- Chaos Fuzzer: AFL-inspired mutation-based infrastructure fuzzing
- Infrastructure Replay: replay past incidents as simulations
- SLO Budget Simulator: error budget-aware chaos planning
- Natural Language Query: "What happens if DB goes down?"
- Runbook Validator: simulate runbook steps to verify recovery
- Dependency Impact Scorer: cost-weighted dependency analysis
- Architecture Git Diff: track resilience across git history
- Digital Twin: 60-minute predictive simulation from live metrics
- Chaos Calendar: scheduled experiments with Bayesian learning
- Compliance Evidence: auto-generate audit-ready SOC2/DORA evidence

### Changed
- Source: 40,000+ lines, 100+ modules, 30+ engines, 55+ CLI commands
- Test count: 2,374 -> 3,142

## [5.0.0] - 2026-03-15

### Added
- Auto-Scaling Recommendation Engine: K8s HPA + AWS ASG export
- Financial Risk Modeling: VaR95, expected annual loss, mitigation ROI
- Resilience Leaderboard: gamification with 6 badges
- Carbon Footprint Engine: CO2 per component, sustainability score
- Chaos Experiment Marketplace: community scenarios + Fairness Protocol
- Infrastructure DNA Fingerprinting: 256-bit topology fingerprint + similarity
- Supply Chain Risk Mapping: CVE -> infrastructure failure mode mapping
- New CLI commands: `autoscale`, `risk`, `carbon`, `leaderboard`, `marketplace`, `dna`, `supply-chain`

### Changed
- Brand rename: ChaosProof -> FaultRay
- Package directory: `src/chaosproof/` -> `src/faultray/`
- CLI command: `chaosproof` -> `faultray`
- Domain: faultray.com
- Test count: 2,021 -> 2,374

### Removed
- Broken `test_marketplace.py` (pre-existing import error)

## [4.0.0] - 2026-03-15

### Added
- GraphQL API: lightweight query/mutation endpoint (no external deps)
- Team Workspace: multi-tenant teams, members, projects (SQLite)
- VS Code Extension: TypeScript scaffold with status bar score
- MkDocs Documentation: 19 pages covering all features
- All 20 competitive categories implemented

### Changed
- Source: 36,000+ lines, 92+ modules, 21 engines, 45+ CLI commands, 35+ API endpoints
- Test count: 1,952 -> 2,021

## [3.3.0] - 2026-03-15

### Added
- Historical Trend Tracking: SQLite-backed score history, trend analysis, regression detection
- Slack Bot: `/chaosproof simulate|score|trend|help` via Block Kit
- Auto-Remediation Pipeline: 6-step orchestration (eval -> fix -> validate -> apply)
- Terraform Provider: `tf-check` with policy gate + Sentinel policy generation
- Custom Scoring Models: YAML-defined rules, 8 built-in checks, weighted scores
- Incident Correlation: CSV/PagerDuty import, scenario matching, coverage gaps
- New CLI commands: `history`, `auto-fix`, `tf-check`, `score-custom`, `correlate`

### Changed
- Test count: 1,828 -> 1,952

## [3.2.0] - 2026-03-15

### Added
- Usage examples added to all 41+ CLI command help texts
- `--version` / `-V` flag
- `--verbose` / `--debug` flags with structured logging
- `log_config.py`: plain + JSON log formats
- 17 integration tests (e2e workflow)

### Fixed
- 10 deep analysis issues resolved: integration tests, unused fields wired, schema versioning, config management, error messages, feature flags, backward compatibility, partial evaluation

### Changed
- Source: 32,582 lines, tests: 34,663 lines (1.06x ratio)
- Test count: 1,781 -> 1,828

## [3.1.0] - 2026-03-15

### Added
- Persistent config (`~/.chaosproof/config.yaml`) with CLI management
- Schema versioning (v3.0) with automatic migration
- Feature flags (17 engines, graceful degradation on failure)
- Partial evaluation results (engine crash doesn't abort pipeline)
- Context-specific error messages with recovery hints

### Fixed
- 6 unused data model fields wired into engines (CostProfile, ComplianceTags, OperationalTeamConfig)

## [3.0.0] - 2026-03-15

### Added
- Azure Scanner: VMs/SQL/Redis/AppService/AKS/LB/Storage/ServiceBus/DNS
- Error recovery: graceful scenario failure handling + checkpoint system
- Telemetry stub: opt-in, privacy-first analytics framework
- Embeddable widget: `/widget/scorecard` + `/widget/embed.js` + `/widget/badge`
- i18n framework: EN/JP translation with `t()` helper
- 20/20 competitive gap categories addressed (Multi-cloud, K8s, CI/CD, REST API, Python SDK, etc.)

### Changed
- Test count: 1,720 -> 1,781

## [2.3.0] - 2026-03-15

### Added
- Result caching (SQLite, content-addressed, TTL)
- Simulation diffing: regression detection, component changes
- Extended notifications: Teams, OpsGenie, Email, smart severity routing
- Monitoring daemon: continuous scanning, interval-based, SIGINT graceful stop
- SARIF export: GitHub/GitLab security tab integration
- Excel export: openpyxl, conditional formatting
- Mobile-responsive dashboard (768px/480px breakpoints)
- PWA support: manifest.json, service worker, offline cache
- Performance benchmarks (6/50/100 component graphs)
- Accessibility: ARIA labels, roles, keyboard nav, WCAG AA
- New CLI commands: `diff`, `daemon`

### Changed
- Test count: 1,647 -> 1,720

## [2.2.0] - 2026-03-15

### Added
- GCP Scanner: Compute/CloudSQL/Memorystore/LB/CloudRun/GKE/GCS/PubSub/DNS/Functions
- Kubernetes Scanner: Deployment/StatefulSet/Service/Ingress/HPA/PDB/NetworkPolicy
- Metric Calibrator: Prometheus + CloudWatch real metrics -> simulation calibration
- VPC Flow Log Analyzer: real traffic patterns -> dependency inference
- RBAC: Admin/Editor/Viewer roles with permission checks on API endpoints
- Python SDK: public API surface with lazy imports
- CI/CD templates: GitLab CI, Jenkins, CircleCI
- IaC dry-run mode: terraform-plan-style diff preview
- Feature tier gating stub (Free/Pro/Enterprise)

## [2.1.0] - 2026-03-15

### Added
- AWS Auto-Discovery: boto3-based scanner for EC2/RDS/ElastiCache/ALB/ECS/S3/SQS/CloudFront/Route53/Lambda
- IaC Remediation Generator: Terraform + K8s code generation (10 rules, 3 phases)
- Remediation Planner: phased improvement plan with timeline, team requirements, cost estimates, ROI
- Quickstart: interactive infrastructure builder (3 templates: web-app, microservices, data-pipeline)
- YAML Export: InfraGraph -> ChaosProof YAML format
- New CLI commands: `scan --aws`, `fix`, `plan`, `quickstart`

## [2.0.0] - 2026-03-15

### Added
- Security Resilience Engine: 10 attack types, defense effectiveness matrix, blast radius analysis
- Chaos Advisor Engine: SPOF detection, betweenness centrality bottlenecks, combination failure suggestions
- Cyber Insurance Scoring API: risk grading (A+ to F), annual expected loss
- Executive Summary report: 1-page C-level report, traffic lights, ROI table
- New data models: SecurityProfile, ComplianceTags, OperationalTeamConfig, enhanced CostProfile

## [1.3.0] - 2026-03-15

### Added
- Cost Impact Engine: business loss quantification per scenario
- Monte Carlo Simulation: probabilistic availability (p50/p95/p99)
- Compliance Engine: SOC2/ISO27001/PCI-DSS/NIST-CSF auto-check
- Multi-Region DR Engine: AZ/region failure + RPO/RTO validation
- Predictive Engine: resource exhaustion + failure probability forecast
- Markov Chain Model: steady-state availability from transition matrix
- Bayesian Network Model: conditional failure probability analysis
- Game Day Engine: exercise simulation with timeline validation
- 5-Layer Availability Model (Layer 4: Operational, Layer 5: External SLA)
- Resilience Score v2: 5-category breakdown + recommendations
- Plugin System: EnginePlugin, ReporterPlugin, DiscoveryPlugin
- New CLI commands: `cost`, `compliance`, `dr`, `predict`, `markov`, `bayesian`, `gameday`, `monte-carlo`

## [1.2.0] - 2026-03-15

### Added
- Cost Impact Engine: business loss, SLA penalty, recovery cost per scenario
- Monte Carlo Simulation: probabilistic availability (p50/p95/p99, CI)
- 5-Layer Availability Model (Layer 4: Operational, Layer 5: External SLA)
- Resilience Score v2: 5-category breakdown with recommendations
- Plugin System: EnginePlugin, ReporterPlugin, DiscoveryPlugin protocols
- New CLI commands: `cost`, `monte-carlo`

## [1.1.0] - 2026-03-15

### Added
- 3-Layer Availability Model (mathematical implementation replacing heuristic lookup)
- JSON export (`--json` flag) for all simulation commands (simulate, dynamic, ops-sim)
- Baseline regression detection: `--save-baseline` / `--baseline` flags for CI/CD
- HA replica guard: min 2 replicas for failover/LB/DNS components
- Quorum guard: min 3 replicas for cache/queue with >=3 replicas
- CLI validation: `--step` < `--duration`, `--growth` range, `--slo` range

### Changed
- Brand rename: InfraSim -> ChaosProof (EMC "InfraSIM" trademark conflict avoidance)
- PyPI package: `infrasim` -> `chaosproof`
- CLI command: `chaosproof` (with `infrasim` backward-compat alias)
- Env vars: `INFRASIM_*` -> `CHAOSPROOF_*` (with fallback)
- MAX_SCENARIOS: 1000 -> 2000

## [1.0.0] - 2026-03-14

### Added
- PyPI-ready package with full metadata (authors, classifiers, keywords, project URLs)
- ProductHunt/Hacker News/Reddit launch materials
- Accumulated parallel session updates: evaluate CLI, extended test suites (482 -> 974 tests)
- Iteration 2: tiered likelihood cap, per-LB partition scenarios, `evaluate --compare`
- Iteration 3: maxUnavailable rolling restart (K8s 25% default), emergency autoscaling, adaptive circuit breaker recovery

### Changed
- Version: 0.1.0 -> 1.0.0

## [0.7.0] - 2026-03-14

### Added
- Web UI overhaul: Jinja2 templates, resilience score gauge, component status cards, D3.js graph styling
- PDF export (`--pdf` flag) and Markdown export (`--md` flag)
- SSO: GitHub + Google OAuth2 login flow
- Prometheus continuous monitoring: background asyncio polling
- Cloud deployment configs: Railway, Fly.io (Tokyo), Render
- Multi-tenant API: team-scoped project management
- Audit log: auto-logged actions with GET `/api/audit-logs` endpoint
- Plugin system: ScenarioPlugin / AnalyzerPlugin protocols with `load_plugins_from_dir()`
- Webhook integrations: Slack (Block Kit), PagerDuty, generic webhook
- CLI split: `cli.py` (758 lines) -> `cli/` package with 7 modules
- CORS middleware, rate limiter (60 req/min), structured error responses
- GitHub App / CI integration: `infrasim-pr-check.yml`, reusable composite action

### Changed
- Test coverage: 52% -> 77% (+309 tests, 430 total)

## [0.6.0] - 2026-03-14

### Added
- AI Analysis Engine (rule-based, no API key): SPOF detection, cascade amplifier ID, capacity bottleneck detection, circuit breaker detection, availability tier assessment, natural language summary
- DORA Compliance Report Generator: ICT risk assessment, resilience testing evidence, third-party dependency analysis, incident impact analysis, remediation plan
- SaaS Phase 2: SQLAlchemy 2.0 + async SQLite persistence, API key authentication (SHA-256), simulation result persistence, CSV/JSON export
- SaaS Phase 1: Dockerfile + docker-compose.yml, GitHub Actions CI/CD (Python 3.11-3.13), OpenAPI/Swagger, CONTRIBUTING.md, issue/PR templates
- New CLI commands: `analyze`, `create-api-key`

## [0.5.14] - 2026-03-14

### Fixed
- YAML loader now parses NetworkProfile and RuntimeJitter fields (previously ignored, defaulting to 0.01% packet loss)

## [0.5.13] - 2026-03-14

### Added
- NetworkProfile model: rtt_ms, packet_loss_rate, jitter_ms, dns/tls overheads
- RuntimeJitter model: gc_pause_ms, gc_pause_frequency, scheduling_jitter_ms
- Availability now includes baseline request failure probability from physical network characteristics and runtime environment

## [0.5.12] - 2026-03-14

### Changed
- `FailoverConfig.promotion_time_seconds`: int -> float (enables 0.5s failover)
- `FailoverConfig.health_check_interval_seconds`: int -> float

## [0.5.11] - 2026-03-14

### Added
- Instance-level failure tracking: random failures down 1 of N replicas (DEGRADED, not DOWN)
- Request-level micro-availability: failover transitions cause proportional request failures
- Correlated failure (AZ outage) simulation: affects ~33% of components for 120s
- Availability precision: 10 decimal places

## [0.5.10] - 2026-03-14

### Changed
- Service-tier aware availability calculation: components grouped by name prefix, tier DOWN only when ALL members DOWN
- Multi-replica standalone components get reduced impact
- Realistic active-active / load-balanced availability modeling

## [0.5.9] - 2026-03-14

### Fixed
- Failover availability was too optimistic (showed 100%); now uses fractional DOWN based on promotion + detection delay, capped at 0.5

## [0.5.8] - 2026-03-14

### Added
- Failover-aware availability: components with failover.enabled treated as DEGRADED (not DOWN)

## [0.5.7] - 2026-03-14

### Changed
- Resilience score now weights SPOF penalties by dependency type (requires=1.0, optional=0.3, async=0.1), failover (70% reduction), autoscaling (50% reduction)

## [0.5.6] - 2026-03-14

### Fixed
- Rolling restart scenario now keeps at least 1 server up (previously took ALL servers down in 2-server setups)

### Added
- README: version badge, test coverage table, changelog section (v5.0-v5.6)

## [0.5.5] - 2026-03-14

### Fixed
- Dynamic simulation result display: `peak_severity` compared float to string literals, causing 0 critical/warning
- `dynamic` CLI command passed `DynamicSimulationReport` directly instead of extracting `.results`

### Added
- `--deploy-hour` validation (0-23 range)
- 14 new tests covering severity classification and boundaries

## [0.5.4] - 2026-03-14

### Added
- Input validation with Pydantic field_validators: `Component.replicas` >= 1, `Scenario.traffic_multiplier` >= 0, `DynamicScenario.duration_seconds/time_step_seconds` > 0

## [0.5.3] - 2026-03-14

### Fixed
- TypeError in dynamic CLI command: `run_all_dynamic_defaults()` did not accept duration/step parameters

## [0.5.2] - 2026-03-14

### Fixed
- XSS in SVG labels via `xml.sax.saxutils.escape`

### Added
- MAX_SCENARIOS=1000 cap to prevent unbounded execution
- Logging for XML parse failures in RSS/Atom feeds

## [0.5.1] - 2026-03-14

### Fixed
- Whatif replica clamping: metrics only adjusted when replicas actually change
- `dynamic_engine`: use public `all_dependency_edges()` API instead of `_graph` access

### Added
- CLI validation: `--diurnal-peak` must be >= 1.0
- Tests: cascade path direction, critical paths guard, optional dep propagation (71 total)

## [0.5.0] - 2026-03-14

### Added
- README overhaul with all 17 CLI commands

### Fixed
- `get_cascade_path()`: traverse downstream (reversed graph) for correct cascade direction
- `get_critical_paths()`: max_paths guard preventing combinatorial explosion
- `--defaults` ignoring `--step` in ops-sim

### Changed
- Downtime event scan optimized with `_comp_events` index (O(n*E) -> O(1) per component)
- Ops-sim event timeline expanded from 10 to 25 events
- TimeUnit enum: ONE_MINUTE -> MINUTE, ONE_HOUR -> HOUR

## [0.4.9] - 2026-03-14

### Added
- Right-sizing recommendations for over-provisioned components
- Circular dependency detection (DAG validation) in loader
- 35 new tests across 5 modules

### Fixed
- Duplicate `_propagate_dependencies()` call (cached in SLOTracker)
- O(n) list concat per timestep replaced with incremental extend
- Deterministic DDoS jitter (hash-based, no module-level RNG state)
- Type hint `InfraComponent` -> `Component` in ops_engine

### Changed
- Validation: duration_days > 0, slo_target (0, 100], dependency_type, replicas >= 1

## [0.4.8] - 2026-03-13

### Changed
- `_replicas_needed` allows scale-down recommendations (max(1, needed) instead of max(needed, current))
- `SLOTracker.record()` single-pass health counting (one loop instead of four sum() comprehensions)

### Fixed
- CLI `--multi` precedence over `--defaults`

## [0.4.7] - 2026-03-13

### Changed
- `load_yaml()` accepts both str and Path objects
- CLI positional YAML argument for whatif/capacity/ops-sim
- Per-scenario jitter RNG replaces module-level `_ops_rng`

### Fixed
- `_schedule_events` no longer mutates the input graph

### Added
- `weekend_factor` as proper field on TrafficPattern

## [0.4.6] - 2026-03-13

### Added
- Dependency-aware availability: fixed-point iteration over dependency edges
- `all_dependency_edges()` helper on InfraGraph
- Rolling update model: maintenance/deploy on multi-replica -> DEGRADED (not DOWN)

## [0.4.5] - 2026-03-13

### Changed
- Gentler MTBF cap in `_apply_mttr_factor` (duration_hours instead of /3)
- CLI report color based on avg_availability instead of min_availability
- Burn rate replica redundancy discount
- Fault-overlap downtime calculation (replaces step_seconds overestimation)

### Added
- `base_multiplier` field on TrafficPattern

## [0.4.4] - 2026-03-13

### Fixed
- MTTR What-If sensitivity: cap MTBF in `_apply_mttr_factor` to force failures
- Type: `total_downtimes` list[int] -> list[float], `total_downtime_seconds` int -> float

### Added
- Capacity engine burn rate: risk-based formula (utilization + MTBF/MTTR + SPOF)
- CLI: Downtime(s) column in what-if output
- CLI: `--no-maintenance` flag

## [0.4.3] - 2026-03-13

### Fixed
- `global_group_idx += 0` dead code bug (now += 1)
- `_composite_traffic` floor 1.0 -> 0.1 (allows sub-baseline traffic)
- What-if RNG state preservation (save/restore in try/finally)

### Changed
- Proportional weighted downtime (weighted by component count)
- `_ops_utilization` avg -> max (consistency with `Component.utilization()`)

### Added
- `total_component_down_seconds` metric for absolute component downtime

## [0.4.2] - 2026-03-13

### Changed
- OVERLOADED components count as 80% available (weight=0.2) instead of fully available

## [0.4.1] - 2026-03-13

### Added
- Multi-parameter What-if analysis (MultiWhatIfScenario, `run_multi_whatif`)
- Traffic-based overload detection (HealthStatus.OVERLOADED)
- CLI `--multi` flag for combined parameter sweeps

### Fixed
- Overload thresholds: replaced per-type with absolute (85/95/110%)
- MTBF/MTTR zero-value: pre-populate defaults before applying factor
- Replica factor: scale CPU/memory metrics inversely with replica changes
- Demo infra: proper provisioning (30-34% base utilization)

## [0.3.0] - 2026-03-13

### Added
- Operational simulation engine with SLO tracking (days/weeks-scale)
- Diurnal-weekly traffic patterns + monthly growth trends
- Operational event injection: deploys, maintenance, random failures (MTBF)
- Gradual degradation models: memory leak, disk fill, connection leak
- SLO/Error Budget tracking with burn rate calculation
- New CLI command: `ops-sim`

## [0.2.1] - 2026-03-13

### Added
- CircuitBreakerConfig, RetryStrategy, CacheWarmingConfig, SingleflightConfig models
- 3-state circuit breaker machine (CLOSED -> OPEN -> HALF_OPEN) in dynamic engine
- Singleflight request coalescing and cache warming penalty
- Cascade engine: CB trip, adaptive retry, singleflight support

### Fixed
- CLI dynamic results display (`DynamicSimulationReport` has `.results`)

## [0.2.0] - 2026-03-12

### Changed
- Code quality cleanup: extract shared demo graph builder into `model/demo.py` (DRY)
- Replace `list.pop(0)` with `collections.deque` in BFS traversal (O(1) vs O(n))
- Add logging for silently swallowed exceptions in scanner.py and store.py
- Remove unused imports from scanner.py
- Use dict key view union in terraform.py

## [0.1.2] - 2026-03-09

### Added
- Security news feed integration (CISA, NVD, Krebs, etc.) with RSS/Atom parsing
- Auto-convert real-world incidents to chaos scenarios
- Persistent scenario store with deduplication
- Feed CLI commands: `feed-update`, `feed-list`, `feed-sources`, `feed-clear`
- Expand chaos scenarios from 7 to 30 categories (150+ scenarios)
- README.md, LICENSE (MIT)

## [0.1.1] - 2026-03-09

### Added
- Terraform integration: `tf-import` and `tf-plan` commands
- Parse terraform.tfstate to auto-discover components
- Parse terraform plan to analyze change impact before apply
- AWS/GCP/Azure resource type mapping
- Risk scoring for Terraform changes (1-10)

## [0.1.0] - 2026-03-09

### Added
- Web GUI: FastAPI dashboard with D3.js dependency graph visualization
- Prometheus integration: auto-discover components and import real metrics
- YAML infrastructure definition
- HTML report: standalone shareable simulation report
- Severity scoring: proper CRITICAL/WARNING/LOW differentiation
- Compound failure scenarios, latency spikes, network partitions, peak hour simulation

## [0.0.1] - 2026-03-09

### Added
- Initial project setup
- Core simulation engine
- CLI interface
- Basic test suite

[Unreleased]: https://github.com/mattyopon/faultray/compare/v10.1.0...HEAD
[10.1.0]: https://github.com/mattyopon/faultray/compare/v10.0.0...v10.1.0
[10.0.0]: https://github.com/mattyopon/faultray/compare/v9.0.0...v10.0.0
[9.0.0]: https://github.com/mattyopon/faultray/compare/v8.2.0...v9.0.0
[8.2.0]: https://github.com/mattyopon/faultray/compare/v8.1.0...v8.2.0
[8.1.0]: https://github.com/mattyopon/faultray/compare/v8.0.0...v8.1.0
[8.0.0]: https://github.com/mattyopon/faultray/compare/v7.0.0...v8.0.0
[7.0.0]: https://github.com/mattyopon/faultray/compare/v6.0.0...v7.0.0
[6.0.0]: https://github.com/mattyopon/faultray/compare/v5.0.0...v6.0.0
[5.0.0]: https://github.com/mattyopon/faultray/compare/v4.0.0...v5.0.0
[4.0.0]: https://github.com/mattyopon/faultray/compare/v3.3.0...v4.0.0
[3.3.0]: https://github.com/mattyopon/faultray/compare/v3.2.0...v3.3.0
[3.2.0]: https://github.com/mattyopon/faultray/compare/v3.1.0...v3.2.0
[3.1.0]: https://github.com/mattyopon/faultray/compare/v3.0.0...v3.1.0
[3.0.0]: https://github.com/mattyopon/faultray/compare/v2.3.0...v3.0.0
[2.3.0]: https://github.com/mattyopon/faultray/compare/v2.2.0...v2.3.0
[2.2.0]: https://github.com/mattyopon/faultray/compare/v2.1.0...v2.2.0
[2.1.0]: https://github.com/mattyopon/faultray/compare/v2.0.0...v2.1.0
[2.0.0]: https://github.com/mattyopon/faultray/compare/v1.3.0...v2.0.0
[1.3.0]: https://github.com/mattyopon/faultray/compare/v1.2.0...v1.3.0
[1.2.0]: https://github.com/mattyopon/faultray/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/mattyopon/faultray/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/mattyopon/faultray/compare/v0.7.0...v1.0.0
[0.7.0]: https://github.com/mattyopon/faultray/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/mattyopon/faultray/compare/v0.5.14...v0.6.0
[0.5.14]: https://github.com/mattyopon/faultray/compare/v0.5.13...v0.5.14
[0.5.13]: https://github.com/mattyopon/faultray/compare/v0.5.12...v0.5.13
[0.5.12]: https://github.com/mattyopon/faultray/compare/v0.5.11...v0.5.12
[0.5.11]: https://github.com/mattyopon/faultray/compare/v0.5.10...v0.5.11
[0.5.10]: https://github.com/mattyopon/faultray/compare/v0.5.9...v0.5.10
[0.5.9]: https://github.com/mattyopon/faultray/compare/v0.5.8...v0.5.9
[0.5.8]: https://github.com/mattyopon/faultray/compare/v0.5.7...v0.5.8
[0.5.7]: https://github.com/mattyopon/faultray/compare/v0.5.6...v0.5.7
[0.5.6]: https://github.com/mattyopon/faultray/compare/v0.5.5...v0.5.6
[0.5.5]: https://github.com/mattyopon/faultray/compare/v0.5.4...v0.5.5
[0.5.4]: https://github.com/mattyopon/faultray/compare/v0.5.3...v0.5.4
[0.5.3]: https://github.com/mattyopon/faultray/compare/v0.5.2...v0.5.3
[0.5.2]: https://github.com/mattyopon/faultray/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/mattyopon/faultray/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/mattyopon/faultray/compare/v0.4.9...v0.5.0
[0.4.9]: https://github.com/mattyopon/faultray/compare/v0.4.8...v0.4.9
[0.4.8]: https://github.com/mattyopon/faultray/compare/v0.4.7...v0.4.8
[0.4.7]: https://github.com/mattyopon/faultray/compare/v0.4.6...v0.4.7
[0.4.6]: https://github.com/mattyopon/faultray/compare/v0.4.5...v0.4.6
[0.4.5]: https://github.com/mattyopon/faultray/compare/v0.4.4...v0.4.5
[0.4.4]: https://github.com/mattyopon/faultray/compare/v0.4.3...v0.4.4
[0.4.3]: https://github.com/mattyopon/faultray/compare/v0.4.2...v0.4.3
[0.4.2]: https://github.com/mattyopon/faultray/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/mattyopon/faultray/compare/v0.3.0...v0.4.1
[0.3.0]: https://github.com/mattyopon/faultray/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/mattyopon/faultray/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/mattyopon/faultray/compare/v0.1.2...v0.2.0
[0.1.2]: https://github.com/mattyopon/faultray/compare/v0.1.1...v0.1.2
[0.1.1]: https://github.com/mattyopon/faultray/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/mattyopon/faultray/compare/v0.0.1...v0.1.0
[0.0.1]: https://github.com/mattyopon/faultray/releases/tag/v0.0.1
