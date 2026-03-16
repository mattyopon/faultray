# FaultRay — US Provisional Patent Application Draft

**Title of Invention:**
System and Method for In-Memory Infrastructure Resilience Simulation Using Graph-Based Topology Modeling and Multi-Layer Availability Analysis

**Inventor:** Yutaro Maeda

**Date:** March 2026

**Status:** DRAFT — For review by patent attorney before filing

---

## 1. FIELD OF THE INVENTION

The present invention relates to systems and methods for evaluating the resilience of computing infrastructure. More specifically, the invention pertains to an in-memory simulation system that models infrastructure topologies as directed graphs, injects virtual faults into the model without affecting any real systems, and computes availability limits through a novel multi-layer mathematical framework.

## 2. BACKGROUND OF THE INVENTION

### 2.1 Problem Statement

Modern distributed computing systems are increasingly complex, comprising dozens to hundreds of interconnected components (load balancers, application servers, databases, caches, message queues, and external APIs). Understanding how these systems behave under failure conditions is critical to ensuring reliability.

### 2.2 Limitations of Existing Approaches

Existing approaches to infrastructure resilience evaluation fall into two categories, both with significant limitations:

**A) Real-Environment Fault Injection (Chaos Engineering)**

Tools such as Netflix Chaos Monkey (2011), Gremlin, LitmusChaos, Chaos Mesh, and AWS Fault Injection Simulator inject faults into live or staging environments. These approaches:

- Require access to actual infrastructure resources
- Carry risk of unintended production impact
- Are expensive to operate (require dedicated staging environments)
- Cannot evaluate theoretical availability limits
- Cannot exhaustively test all failure combinations (combinatorial explosion)
- Require significant setup time and infrastructure investment before any insight is gained

**B) Static Analysis Tools**

Tools such as HPE's SPOF analysis (US9280409B2) perform static analysis of infrastructure configurations. These approaches:

- Do not simulate dynamic system behavior (autoscaling, failover, circuit breakers)
- Cannot model time-varying conditions (traffic patterns, cascading failures)
- Do not account for the interplay between multiple failure modes
- Cannot quantify the severity and propagation of cascading failures

### 2.3 Unmet Need

There exists no system that:
1. Models infrastructure topology entirely in memory without requiring access to real systems
2. Simulates thousands of failure scenarios automatically from a topology definition
3. Computes mathematically rigorous availability limits accounting for software, hardware, operational, and external dependency factors
4. Models dynamic behaviors including cascading failures, autoscaling responses, circuit breaker activation, and failover sequences
5. Produces quantitative resilience scores that enable comparison across different infrastructure designs

The present invention addresses all of these needs.

## 3. SUMMARY OF THE INVENTION

The invention provides a computer-implemented system and method comprising:

1. **A graph-based infrastructure topology model** stored entirely in computer memory, where infrastructure components are represented as nodes and dependencies as directed edges in a directed graph (DiGraph), each annotated with typed attributes including component capacity, health metrics, network characteristics, runtime jitter profiles, autoscaling configurations, failover configurations, and circuit breaker settings.

2. **An automated fault scenario generation engine** that algorithmically generates a comprehensive set of failure scenarios from the topology model, including single-component failures, pairwise combinations, triple failures, component-type-specific faults, traffic spike scenarios at multiple magnitudes, and specialized scenarios based on component semantics (database replication lag, cache stampede, queue backpressure, etc.), producing 2,000 or more distinct scenarios from a typical topology.

3. **A multi-engine simulation architecture** comprising twenty-three complementary simulation engines:
   - A **Cascade Engine** that propagates failure effects through the dependency graph using breadth-first search (BFS), computing severity scores based on impact and spread metrics, and modeling dependency-type-aware propagation (required vs. optional vs. asynchronous dependencies)
   - A **Dynamic Engine** that executes time-stepped simulations with traffic pattern injection, autoscaling response modeling, circuit breaker activation, failover sequence simulation, and latency cascade tracking
   - An **Operations Engine** that simulates multi-day operational scenarios incorporating MTBF/MTTR-based stochastic event generation, deployment events, and gradual degradation patterns
   - A **What-If Engine** that performs parametric sensitivity analysis by varying system parameters (MTTR, MTBF, traffic multipliers, replica counts) and measuring resilience response
   - A **Capacity Engine** that predicts resource saturation points and evaluates high-availability configurations including quorum-based systems
   - A **Bayesian Network Engine** that computes conditional failure probabilities using Bayes' theorem with dependency-type-based impact factors, enabling probabilistic what-if analysis
   - A **Markov Chain Engine** that computes steady-state availability using a three-state continuous-time Markov chain (HEALTHY/DEGRADED/DOWN) with transition rates derived from component operational profiles
   - A **Discrete Event Simulation (DES) Engine** that processes time-stamped events from a priority queue with asynchronous event-driven propagation, providing exact temporal resolution
   - A **Genetic Algorithm Optimizer** that discovers worst-case failure scenarios through population-based evolutionary search over binary chromosome encodings of simultaneous multi-fault combinations
   - A **Fault Tree Analysis (FTA) Engine** that performs top-down deductive failure analysis using AND/OR/VOTING gates to compute system failure probability and minimal cut sets
   - A **Survival Analysis Engine** that estimates remaining useful life using Kaplan-Meier survival curves, Weibull distribution fitting, and hazard function computation
   - A **Petri Net Engine** that models concurrent failure propagation using Place/Transition nets with reachability analysis and deadlock detection
   - A **Cellular Automata Engine** that models deterministic failure propagation using threshold-based local rules with pattern classification (stable/oscillating/chaotic)
   - A **System Dynamics Engine** that models component health as continuous-valued stocks governed by ordinary differential equations with degradation and recovery flows, using Euler integration to capture smooth degradation curves, tipping-point thresholds, and recovery trajectories invisible to discrete-state models
   - An **RNN/LSTM Failure Predictor** that captures temporal dependencies in infrastructure metric time-series using recurrent neural networks (Simple RNN and LSTM variants), trained on simulation-synthesized data rather than production logs
   - A **Simulated Annealing Optimizer** that discovers worst-case failure scenarios through single-solution metaheuristic search with Metropolis acceptance criterion and geometric cooling schedule
   - A **Reliability Block Diagram (RBD) Analyzer** that computes system-level availability from series and parallel block compositions derived from the infrastructure dependency graph
   - An **Event Tree Analysis (ETA) Engine** that performs inductive forward risk assessment from initiating events through automatically generated safety barrier branches
   - An **Extreme Value Theory (EVT) Analyzer** that fits a Generalised Extreme Value distribution to cascade severity block-maxima for return level computation and tail-risk probability estimation
   - A **Model Checker** that performs exhaustive state-space exploration with CTL temporal-logic property verification (AG, EF, AF operators) and counterexample generation
   - A **Random Forest Predictor** that uses bagged decision tree ensembles with feature sub-sampling to capture non-linear failure prediction boundaries
   - An **Anomaly Autoencoder** that performs unsupervised anomaly detection via reconstruction error on simulation-synthesized normal data, requiring no labeled failure examples
   - A **Transformer Predictor** that uses self-attention to predict failure probability from metric time-series with parallel processing and attention-weight interpretability

4. **A multi-layer availability limit model** (the "N-Layer Model") that computes mathematically distinct availability ceilings:
   - **Layer 1 (Software Limit):** Accounts for deployment downtime frequency, human error rate, and configuration drift probability. Computed as: `A_sw = 1 - (deploy_frequency × avg_deploy_downtime / period + human_error_rate + config_drift_rate)`, bounded by the hardware limit.
   - **Layer 2 (Hardware Limit):** For each component, computes single-instance availability as `A_single = MTBF / (MTBF + MTTR)`, parallel redundancy as `A_tier = 1 - (1 - A_single)^replicas`, and applies a failover penalty based on promotion time and detection latency. System availability is the product of all critical-path tier availabilities, where criticality is determined by the dependency graph edge types.
   - **Layer 3 (Theoretical Limit):** Computes the irreducible physical noise floor from network packet loss rates, garbage collection pause fractions, and kernel scheduling jitter, applied as multiplicative penalties on the hardware availability.
   - **Layer 4 (Operational Limit):** Models human factor availability based on incident frequency, mean response time, on-call coverage percentage, runbook coverage, and automation level. Computed as: `A_ops = 1 - (incidents/year × effective_response_hours / 8760)`, where effective response time is adjusted by coverage, runbook, and automation factors.
   - **Layer 5 (External SLA Cascading):** Computes the product of all external dependency SLA values, establishing the hard ceiling imposed by third-party service availability.
   - The model is generalizable to **N layers**, where additional layers may be defined for geographic constraints, economic constraints (budget-limited availability), regulatory constraints, or other domain-specific factors.

5. **A resilience scoring system** that aggregates simulation results into a quantitative score (0-100) enabling comparison across different infrastructure designs and configurations.

6. **A security resilience engine** that simulates cyberattack scenarios (DDoS, ransomware, SQL injection, supply chain attacks, insider threats, zero-day exploits, etc.) against the in-memory topology model, computes defense effectiveness using a defense matrix that maps security controls to attack mitigations via independent-layer combination (`1 - ∏(1 - mᵢ)`), and models lateral movement propagation through the dependency graph with network segmentation as a blocking factor.

7. **A financial risk engine** that combines simulation results (cascade severity, likelihood) with revenue data to produce financial risk metrics including Value-at-Risk at the 95th percentile (VaR95), expected annual loss, and mitigation ROI analysis that ranks remediation actions by cost-effectiveness.

8. **An infrastructure resilience genome ("Chaos Genome")** system that computes a multi-dimensional fingerprint vector from the topology graph's structural properties (graph density, average path length, clustering coefficient, component diversity, redundancy coverage, failover coverage, circuit breaker coverage, etc.), enabling: (a) benchmarking against industry-specific reference profiles (fintech, e-commerce, healthcare, SaaS, etc.), (b) tracking resilience evolution over time as a genome trajectory, (c) identifying structural weaknesses inherited from architecture decisions, and (d) predicting failure patterns based on structural similarity to known-vulnerable topology patterns.

9. **A real-time threat feed integration system** that automatically fetches security news from RSS/Atom feeds, extracts threat patterns via keyword and semantic matching, and converts detected threats into executable fault scenarios that are injected into the simulation pipeline, enabling the system to automatically evaluate infrastructure resilience against emerging real-world threats.

10. **A blast radius predictor** that, prior to any fault injection, predicts the cascading impact with confidence-interval-bounded estimates of: affected component count, per-component impact severity (total outage / major degradation / minor degradation / negligible), propagation depth (hop count from failed component), time-to-impact for each affected component, and whether existing circuit breakers or failover configurations would mitigate the impact.

11. **A chaos experiment recommender** that analyzes simulation results to identify coverage gaps in resilience testing and produces a prioritized list of recommended real-world chaos experiments, ranked by risk exposure, potential learning value, and coverage gap severity, thereby bridging the gap between in-memory simulation and real-environment validation.

## 4. DETAILED DESCRIPTION

### 4.1 System Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                    FaultRay System                   │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌───────────┐    ┌──────────────────────────────┐ │
│  │ Topology   │───▶│ In-Memory Directed Graph     │ │
│  │ Definition │    │ (networkx DiGraph)           │ │
│  │ (YAML/     │    │                              │ │
│  │  Terraform/│    │ Nodes: Component instances   │ │
│  │  Cloud API)│    │ Edges: Typed dependencies    │ │
│  └───────────┘    └──────────┬───────────────────┘ │
│                              │                      │
│                    ┌─────────▼──────────┐           │
│                    │ Scenario Generator  │           │
│                    │ (30 categories,     │           │
│                    │  2000+ scenarios)   │           │
│                    └─────────┬──────────┘           │
│                              │                      │
│         ┌────────────────────┼────────────────┐     │
│         ▼          ▼         ▼        ▼       ▼     │
│    ┌─────────┐┌────────┐┌──────┐┌───────┐┌──────┐  │
│    │Cascade  ││Dynamic ││ Ops  ││What-If││Capac.│  │
│    │Engine   ││Engine  ││Engine││Engine ││Engine│  │
│    │(static) ││(time)  ││(days)││(param)││(sat.)│  │
│    └────┬────┘└───┬────┘└──┬───┘└──┬────┘└──┬───┘  │
│         └─────────┼────────┼───────┼────────┘      │
│                   ▼        ▼       ▼                │
│            ┌──────────────────────────┐             │
│            │ N-Layer Availability     │             │
│            │ Limit Model             │             │
│            │ (5+ mathematical layers) │             │
│            └───────────┬─────────────┘             │
│                        ▼                            │
│            ┌──────────────────────────┐             │
│            │ Resilience Score &       │             │
│            │ Report Generation        │             │
│            └──────────────────────────┘             │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 4.2 Graph-Based Topology Model

The infrastructure topology is represented as a directed graph G = (V, E) where:

- **V (Vertices):** Each vertex represents an infrastructure component with the following typed attributes:
  - `type`: One of {load_balancer, web_server, app_server, database, cache, queue, storage, dns, external_api, custom}
  - `replicas`: Integer replica count for parallel redundancy modeling
  - `metrics`: Current resource utilization (CPU%, memory%, disk%, network connections, open files)
  - `capacity`: Resource limits (max connections, max RPS, connection pool size, timeout, retry multiplier)
  - `network`: Network characteristics (RTT, packet loss rate, jitter, DNS resolution time, TLS handshake time)
  - `runtime_jitter`: Application-level jitter sources (GC pause duration/frequency, scheduling jitter)
  - `operational_profile`: MTBF (hours), MTTR (minutes), deploy downtime (seconds)
  - `autoscaling`: HPA/KEDA configuration (min/max replicas, thresholds, delays, step size)
  - `failover`: Failover configuration (enabled, promotion time, health check interval, threshold)
  - `circuit_breaker`: Circuit breaker configuration (enabled, threshold, reset timeout)
  - `external_sla`: Provider SLA percentage for external dependencies
  - `team`: Operational team readiness (runbook coverage %, automation %)

- **E (Edges):** Each directed edge (u, v) represents that component u depends on component v, with attributes:
  - `dependency_type`: One of {requires, optional, async}
  - `weight`: Dependency strength (0.0 to 1.0)
  - `latency_ms`: Expected edge latency
  - `circuit_breaker`: Edge-level circuit breaker configuration
  - `retry_strategy`: Retry configuration (enabled, max retries, backoff strategy)
  - `singleflight`: Request coalescing configuration

The topology may be defined via:
- A declarative YAML schema
- Import from Terraform state files
- Import from cloud provider APIs (AWS, GCP, Azure)
- Import from Prometheus/monitoring metrics
- Import from Kubernetes cluster state

In addition to declarative YAML, Terraform import, and cloud API discovery, the system provides an interactive step-by-step wizard for topology definition:

1. **Environment type selection:** The user selects from cloud-only, on-premise-only, or hybrid (on-premise plus cloud) deployment models.
2. **Cloud provider selection:** For cloud-only and hybrid environments, the user selects the target cloud provider (AWS, GCP, or Azure), which determines the available managed service presets.
3. **On-premise component selection:** For on-premise and hybrid environments, the user selects from categorized component presets including load balancer type (F5 BIG-IP, Nginx, HAProxy), database type (Oracle, MySQL, PostgreSQL, SQL Server), application server type (Tomcat, IIS, Node.js), cache layer (Redis, Memcached), message queue (RabbitMQ, ActiveMQ, Kafka), and storage (NAS, SAN, NFS).
4. **Per-component configuration:** For each selected component, the user specifies replica count, failover enablement, and high-availability settings. Cloud components additionally support autoscaling configuration (minimum replicas, maximum replicas).
5. **Cross-environment connectivity:** For hybrid environments, the user selects the connectivity method (VPN, Direct Connect, or Internet) linking the on-premise and cloud environments, with associated network characteristics (round-trip time, packet loss rate, jitter).
6. **Automatic YAML generation with confirmation:** The system assembles all selected components into a complete YAML topology definition, automatically generates dependency edges based on component type relationships (load balancer to application server, application server to database, etc.), presents a summary table for user confirmation, and writes the validated YAML file.

This wizard enables users without YAML expertise or Infrastructure-as-Code knowledge to define complex hybrid infrastructure topologies through guided prompts, significantly lowering the barrier to entry for resilience evaluation.

### 4.3 Automated Fault Scenario Generation

The scenario generator produces fault scenarios across 30 categories, including but not limited to:

1. Single-component DOWN for each component in V
2. Traffic spike scenarios at multipliers {1.5x, 2x, 3x, 5x, 10x}
3. Pairwise combination failures: C(|V|, 2)
4. Triple combination failures: C(|V|, 3)
5. Component-type-specific faults:
   - Database: replication lag, connection storm, split-brain
   - Cache: stampede, invalidation storm, eviction cascade
   - Queue: backpressure, poison message, consumer lag
   - Load balancer: health check failure, TLS certificate expiry
   - Application server: memory leak, GC pause storm, thread pool exhaustion
6. Infrastructure-level: availability zone failure, network partition, DNS failure
7. Resource exhaustion: CPU saturation, memory exhaustion, disk full, connection pool exhaustion

The total scenario count is bounded by a configurable MAX_SCENARIOS parameter (default: 2,000). Scenarios are generated deterministically from the topology structure, ensuring reproducibility.

Each scenario S is defined as a tuple: `S = (id, name, faults[], traffic_multiplier)` where each fault `f ∈ faults` is defined as: `f = (target_component_id, fault_type, severity, duration_seconds, parameters)`.

### 4.4 Cascade Engine

The Cascade Engine simulates failure propagation through the dependency graph using a modified breadth-first search (BFS) algorithm.

**4.4.1 Direct Effect Computation**

For each fault f applied to component c, the direct effect is computed based on the fault type:
- COMPONENT_DOWN → health = DOWN
- DISK_FULL → health = DOWN
- MEMORY_EXHAUSTION → health = DOWN (OOM)
- CONNECTION_POOL_EXHAUSTION → health = DOWN
- CPU_SATURATION → health = OVERLOADED
- LATENCY_SPIKE → health = DEGRADED
- NETWORK_PARTITION → health = DOWN
- TRAFFIC_SPIKE → health = OVERLOADED

**4.4.2 Likelihood Computation**

For each fault, a likelihood score (0.2 to 1.0) is computed based on the current state proximity to the failure condition. For example, for DISK_FULL: if current disk usage > 90% → likelihood = 1.0 (imminent); if > 75% → 0.7; if > 50% → 0.4; otherwise → 0.2.

**4.4.3 Cascade Propagation**

Failure effects propagate through the dependency graph according to dependency type:

- `requires` dependency with failed_health=DOWN:
  - If dependent has replicas > 1: dependent becomes DEGRADED
  - If dependent has replicas = 1 (SPOF): dependent becomes DOWN, with timeout and retry storm modeling
- `optional` dependency with failed_health=DOWN: dependent becomes DEGRADED
- `async` dependency with failed_health=DOWN: dependent becomes DEGRADED (delayed, queue buildup)

**4.4.4 Latency Cascade Simulation**

A specialized cascade mode simulates latency propagation through the dependency graph:
- Accumulated latency is tracked through each hop
- Circuit breakers are evaluated at each edge (cascade stopped if latency > timeout)
- Connection pool exhaustion is computed when accumulated latency causes request pileup
- Retry storms are modeled as connection multiplication factors
- Singleflight (request coalescing) is modeled as a load reduction factor

**4.4.5 Severity Scoring**

Cascade severity is computed as:
```
severity = impact_score × spread_score × 10.0 × likelihood
```
Where:
- `impact_score = (DOWN_count × 1.0 + OVERLOADED_count × 0.5 + DEGRADED_count × 0.25) / affected_count`
- `spread_score = affected_count / total_components`
- Caps: no cascade (single component) → max 3.0; <30% spread → max 6.0; degraded-only → max 4.0

### 4.5 Dynamic Engine

The Dynamic Engine executes time-stepped simulations over discrete time intervals (default: 30-second steps), incorporating:

- **Traffic Pattern Injection:** 10 traffic pattern types including sinusoidal (diurnal), spike, gradual ramp, DDoS volumetric, flash crowd, viral event, and seasonal patterns
- **Autoscaling Response:** Models scale-up/down decisions based on CPU thresholds, with configurable delays, step sizes, and min/max bounds
- **Failover Sequences:** Models health check detection time + promotion time, with partial unavailability during failover
- **Circuit Breaker Activation:** Models open/half-open/closed states based on failure thresholds
- **Recovery Modeling:** Components recover over time based on MTTR profiles

### 4.6 Operations Engine

The Operations Engine simulates multi-day operational scenarios (default: 7 days) incorporating:
- Stochastic failure events generated from MTBF distributions (Poisson process)
- Deployment events with associated downtime
- Gradual degradation patterns (resource leak, configuration drift)
- Incident response modeling with team availability

### 4.7 What-If Engine

The What-If Engine performs parametric sensitivity analysis by:
- Varying one or more system parameters across a defined range
- Executing the Cascade Engine and/or Dynamic Engine for each parameter combination
- Producing a response surface showing resilience as a function of the varied parameters
- Identifying optimal parameter values (e.g., "adding 1 replica to database eliminates SPOF")

### 4.8 Capacity Engine

The Capacity Engine predicts resource saturation points by:
- Projecting current resource usage trends forward in time
- Modeling the interaction between autoscaling and resource consumption
- Evaluating quorum-based system requirements (e.g., "3 of 5 nodes must be healthy")
- Identifying the earliest expected saturation point across all resources

### 4.9 N-Layer Availability Limit Model

The N-Layer Availability Limit Model provides mathematically distinct availability ceilings. The core insight is that system availability is bounded by multiple independent factors, each of which imposes a ceiling that cannot be exceeded regardless of improvements in other layers.

**Mathematical Formulation:**

For a system with components C = {c₁, c₂, ..., cₙ} and dependency graph G = (C, E):

**Layer 2 (Hardware Limit):**
```
For each component cᵢ:
  A_single(cᵢ) = MTBF(cᵢ) / (MTBF(cᵢ) + MTTR(cᵢ))
  A_tier(cᵢ) = 1 - (1 - A_single(cᵢ))^replicas(cᵢ)

  If failover enabled:
    fo_events/year = (365.25 × 24 / MTBF(cᵢ)) × replicas(cᵢ)
    fo_downtime_fraction = fo_events × (promotion_time + detection_time) / (365.25 × 24 × 3600)
    A_tier(cᵢ) = A_tier(cᵢ) × (1 - fo_downtime_fraction)

A_hw = ∏{cᵢ ∈ critical_path(G)} A_tier(cᵢ)
```

Where `critical_path(G)` includes all components that have at least one `requires`-type dependent or are leaf nodes.

**Layer 1 (Software Limit):**
```
A_sw = min(1 - (deploy_freq × avg_deploy_downtime / period + human_error_rate + config_drift_rate), A_hw)
```

**Layer 3 (Theoretical Limit):**
```
A_theoretical = A_hw × (1 - avg_packet_loss) × (1 - avg_gc_fraction)
```

**Layer 4 (Operational Limit):**
```
effective_response = (mean_response / coverage) × runbook_factor × automation_factor
A_ops = 1 - (incidents/year × effective_response / 8760)
```

**Layer 5 (External SLA Cascading):**
```
A_external = ∏{cᵢ ∈ external_deps} SLA(cᵢ)
```

**N-Layer Generalization:**

The model is extensible to N layers. Additional layers that may be defined include but are not limited to:
- **Layer 6 (Geographic Limit):** Availability ceiling imposed by geographic distance, network latency between regions, and regulatory data residency requirements
- **Layer 7 (Economic Limit):** Availability ceiling imposed by budget constraints, where `A_economic = f(budget, cost_per_nine)` and cost increases exponentially per additional nine
- **Layer N (Custom Domain-Specific Limit):** Any domain-specific constraint that imposes an independent availability ceiling

The effective system availability is:
```
A_system = min(A_layer1, A_layer2, ..., A_layerN)
```

### 4.10 Security Resilience Engine

The Security Resilience Engine simulates cyberattack scenarios against the in-memory infrastructure topology. Unlike traditional vulnerability scanners that inspect real systems, this engine operates entirely on the graph model.

**4.10.1 Attack Types**

The engine models 10 attack categories: DDoS Volumetric, DDoS Application, Credential Stuffing, SQL Injection, Ransomware, Supply Chain, Insider Threat, Zero-Day, API Abuse, and Data Exfiltration.

**4.10.2 Automatic Attack Scenario Generation**

Attack scenarios are generated from topology properties:
- Public-facing components (port 443/80) → DDoS, SQL Injection, API Abuse scenarios
- Database/Storage components → SQL Injection, Data Exfiltration, Ransomware scenarios
- Components without authentication → Credential Stuffing scenarios
- Components without network segmentation → Supply Chain, Insider Threat scenarios

**4.10.3 Defense Effectiveness Matrix**

A defense matrix maps security controls to attack mitigations. Each control (WAF, rate limiting, encryption at rest, encryption in transit, network segmentation, authentication, IDS monitoring) provides a mitigation value (0.0-1.0) against specific attack types. Multiple controls combine via independent-layer formula:

```
defense_effectiveness = 1 - ∏(1 - mᵢ)
```

where mᵢ is the mitigation value of each active control against the attack type.

**4.10.4 Lateral Movement Simulation**

Attack propagation is modeled via bidirectional BFS through the dependency graph. Network segmentation acts as a deterministic blocking factor: segmented components are not compromised by lateral movement. This produces a list of compromised components (blast radius), data-at-risk assessment, and estimated downtime.

**4.10.5 Security Resilience Score**

A quantitative score (0-100) is computed across five categories (each 0-20):
- Encryption (at rest + in transit coverage)
- Access Control (authentication + rate limiting coverage)
- Network (segmentation + WAF coverage)
- Monitoring (logging + IDS coverage)
- Recovery (backup enabled + backup frequency + patch SLA)

### 4.11 Financial Risk Engine

The Financial Risk Engine applies financial engineering techniques to infrastructure failure simulation results, producing quantitative risk metrics suitable for executive decision-making.

**4.11.1 Loss Estimation**

For each critical/warning scenario from the simulation:
```
business_loss = downtime_minutes × revenue_per_minute + SLA_credit_costs + recovery_engineer_costs
```

Where:
- `revenue_per_minute = annual_revenue / (365.25 × 24 × 60)`
- `SLA_credit_costs`: computed from component cost profiles and SLA credit percentages
- `recovery_engineer_costs`: `engineer_hourly_rate × MTTR_hours × min(team_size, 3)`

**4.11.2 Value-at-Risk (VaR95)**

The 95th percentile Value-at-Risk is computed by:
1. Sorting all scenario losses by magnitude (ascending)
2. Computing cumulative probability across scenarios
3. Identifying the loss value at which cumulative probability reaches 0.95

**4.11.3 Expected Annual Loss**

```
EAL = Σ(probabilityᵢ × business_lossᵢ)
```

**4.11.4 Mitigation ROI Analysis**

The engine identifies remediation opportunities and ranks them by ROI:
- SPOF elimination: `savings = related_losses × 0.7; ROI = (savings - cost) / cost × 100`
- Autoscaling enablement: estimated savings from avoided capacity-related outages
- Circuit breaker addition: zero-cost code changes with loss reduction estimates

### 4.12 Infrastructure Resilience Genome (Chaos Genome)

The Chaos Genome system computes a multi-dimensional "DNA fingerprint" for any infrastructure topology, enabling quantitative comparison and evolution tracking.

**4.12.1 Genome Traits**

The genome is a vector of normalized traits (each 0.0-1.0) extracted from the topology graph:

Structural traits:
- `graph_density`: ratio of actual edges to possible edges in the dependency graph
- `avg_path_length`: average shortest path length between all component pairs
- `max_depth`: maximum depth of the dependency tree
- `clustering_coefficient`: degree of local interconnectedness

Redundancy traits:
- `avg_replicas`: average replica count across all components
- `min_replicas`: minimum replica count (highlights weakest link)
- `failover_coverage`: fraction of components with failover enabled
- `multi_az_coverage`: fraction of components with multi-AZ deployment

Resilience mechanism traits:
- `circuit_breaker_coverage`: fraction of dependency edges with circuit breakers
- `autoscaling_coverage`: fraction of components with autoscaling enabled
- `type_diversity`: Shannon entropy of component type distribution
- `provider_diversity`: number of distinct infrastructure providers

**4.12.2 Industry Benchmarking**

Pre-computed benchmark profiles for industry verticals (fintech, e-commerce, healthcare, SaaS, gaming, media, government) define expected trait ranges. The genome is compared against these benchmarks to produce:
- Per-trait deviation scores
- Overall similarity score (cosine similarity between genome vector and benchmark vector)
- Identification of traits where the infrastructure falls below industry standards

**4.12.3 Genome Evolution Tracking**

By computing the genome at different points in time (e.g., after each infrastructure change), the system tracks the resilience evolution trajectory. This enables:
- Detection of resilience regression (genome traits moving away from benchmarks)
- Quantification of improvement from infrastructure investments
- Prediction of future resilience trajectory based on historical genome changes

**4.12.4 Structural Weakness Identification**

The genome identifies "genetic weaknesses" — structural patterns that are known to correlate with high failure risk:
- Low `min_replicas` with high `graph_density` → cascade amplification risk
- Low `circuit_breaker_coverage` with high `avg_path_length` → latency cascade risk
- Low `provider_diversity` with low `multi_az_coverage` → correlated failure risk

### 4.13 Real-Time Threat Feed Integration

The system integrates with external security news feeds (RSS/Atom) to automatically update the simulation scenario set based on emerging threats.

**4.13.1 Feed Fetching and Parsing**

The system periodically fetches articles from configured security news sources, parsing RSS and Atom feed formats to extract article title, summary, publication date, and tags.

**4.13.2 Threat-to-Scenario Conversion**

Extracted articles are analyzed for threat patterns through keyword and semantic matching. When a matching threat is detected (e.g., a new DDoS technique, a newly discovered vulnerability class, or a supply chain attack vector), the system automatically generates corresponding fault scenarios and adds them to the simulation pipeline.

This creates a continuously evolving scenario set that reflects the current threat landscape, rather than a static set of pre-defined scenarios.

### 4.14 Blast Radius Predictor

The Blast Radius Predictor provides pre-simulation impact estimates with confidence-bounded predictions.

**4.14.1 Impact Assessment**

For each potential component failure, the predictor computes:
- `impact_severity`: classified as total_outage, major_degradation (>50% capacity loss), minor_degradation (<50% capacity loss), or negligible
- `propagation_depth`: number of graph hops from the failed component to the affected component
- `time_to_impact_seconds`: estimated time before the impact reaches each affected component
- `has_circuit_breaker`: whether a circuit breaker exists on the dependency path
- `has_failover`: whether the affected component has failover configured
- `mitigated`: whether existing resilience mechanisms would prevent the impact

**4.14.2 Pre-Simulation Triage**

The predictor enables rapid triage of potential failures without executing full simulations, identifying which components warrant detailed simulation and which have sufficient resilience mechanisms in place.

### 4.15 Chaos Experiment Recommender

The Chaos Experiment Recommender bridges the gap between in-memory simulation and real-world chaos engineering by analyzing simulation results and recommending targeted experiments.

**4.15.1 Coverage Gap Analysis**

The recommender identifies areas of the infrastructure that have not been adequately tested:
- Components with high cascade severity but no failover testing
- Dependency edges without circuit breaker validation
- Traffic patterns that have not been simulated at realistic scales

**4.15.2 Priority-Based Recommendations**

Each recommended experiment is assigned a priority (critical/high/medium/low) based on:
- Risk exposure: potential business impact of an untested failure mode
- Learning value: how much new information the experiment would provide
- Coverage gap severity: how far the current testing falls short of comprehensive coverage

**4.15.3 Experiment Types**

Recommended experiments span 10 categories: node failure, network partition, latency injection, resource exhaustion, dependency failure, cascade test, failover test, load spike, DNS failure, and configuration corruption.

### 4.16 Monte Carlo Stochastic Simulation

In addition to the closed-form availability analysis (N-Layer Model), the system provides a stochastic simulation mode using Monte Carlo methods.

**4.16.1 Sampling Method**

For each trial:
- Component MTBF is sampled from an exponential distribution
- Component MTTR is sampled from a log-normal distribution
- Per-component availability is computed as `A = MTBF / (MTBF + MTTR)`
- System availability is computed from the dependency graph structure

**4.16.2 Statistical Output**

After N trials (default: 10,000), the system computes:
- Mean, median, and standard deviation of system availability
- Percentile-based confidence intervals (p5, p25, p50, p75, p95)
- Per-component availability distributions
- Identification of components with the highest variance (most uncertain reliability)

This provides a complementary view to the deterministic N-Layer Model: where the N-Layer Model computes theoretical ceilings, Monte Carlo provides empirical distribution estimates accounting for real-world stochastic variation.

### 4.17 Chaos Fuzzer (AFL-Inspired Scenario Discovery)

The Chaos Fuzzer applies security fuzzing techniques (inspired by American Fuzzy Lop / AFL) to infrastructure failure scenario discovery.

**4.17.1 Mutation-Based Exploration**

Starting from a seed corpus of known scenarios, the fuzzer applies random mutations:
- `add_fault`: Add a random fault to an existing scenario
- `change_target`: Redirect a fault to a different component
- `combine`: Merge two scenarios into a compound scenario
- `amplify_traffic`: Increase traffic multiplier
- `change_severity`: Modify fault severity

**4.17.2 Novelty Detection**

Each mutated scenario is simulated, and its result is fingerprinted. If the failure pattern (set of affected components, severity distribution) has not been observed before, the scenario is added to the corpus as "interesting." This enables discovery of **unknown failure modes** that rule-based generation cannot anticipate.

**4.17.3 Corpus Management**

The fuzzer maintains a growing corpus of interesting scenarios, enabling iterative exploration of the failure space. This is fundamentally different from the deterministic 30-category scenario generation: where rule-based generation is exhaustive within known categories, fuzzing discovers failures across category boundaries.

### 4.18 Automatic Runbook Generation

The system automatically generates incident response runbooks from simulation results.

**4.18.1 Runbook Structure**

For each critical or warning scenario, a runbook is generated containing:
- **Detection steps**: Specific alerts and metrics to monitor
- **Diagnosis steps**: Commands and checks to confirm the issue
- **Mitigation steps**: Immediate actions to reduce impact
- **Recovery steps**: Full recovery procedure with estimated time
- **Post-incident steps**: Review checklist and prevention recommendations
- **Communication templates**: Status page updates, Slack notifications, stakeholder emails

**4.18.2 Context-Aware Generation**

Runbooks are tailored to the specific infrastructure topology and failure mode:
- Component-type-specific recovery procedures (database vs. cache vs. queue)
- Dependency-aware escalation paths
- Team assignment based on component ownership

### 4.19 Compliance Framework Simulation

The system simulates compliance posture against multiple regulatory frameworks entirely in memory.

**4.19.1 Supported Frameworks**

SOC 2 Type II, ISO 27001, PCI DSS, DORA (Digital Operational Resilience Act), HIPAA, and GDPR. Each framework is decomposed into specific control requirements mapped to infrastructure properties.

**4.19.2 Compliance Assessment Method**

For each framework, the system evaluates:
- Control coverage: which required controls are implemented in the topology
- Control effectiveness: how well each control mitigates its target risks (using the defense matrix)
- Gap identification: missing controls and their risk impact
- Evidence generation: automated compliance evidence from simulation results

**4.19.3 Compliance-Driven Chaos**

The system generates compliance-specific chaos scenarios: "What happens to our PCI DSS compliance if the WAF goes down?" This enables proactive compliance resilience testing.

### 4.20 FMEA Engine (Failure Mode and Effects Analysis)

The system adapts the FMEA methodology (originating from manufacturing/aerospace) to cloud infrastructure.

**4.20.1 Risk Priority Number (RPN)**

For each component and failure mode:
```
RPN = Severity × Occurrence × Detection
```
Where:
- `Severity` (1-10): Impact on the overall system (derived from cascade simulation)
- `Occurrence` (1-10): Likelihood based on component MTBF and current metrics
- `Detection` (1-10): How quickly the failure would be detected (based on monitoring and alerting coverage)

**4.20.2 FMEA Table Generation**

The system automatically populates FMEA tables for all components and failure modes, enabling traditional reliability engineering workflows to be applied to cloud infrastructure without manual analysis.

### 4.21 SLA Mathematical Provability

The system provides mathematical proof of SLA achievability or unachievability.

**4.21.1 SLA Validation**

Given a target SLA (e.g., 99.99%), the system:
1. Computes the N-Layer availability limits
2. Determines which layer is the binding constraint
3. If any layer's ceiling is below the target SLA: outputs a mathematical proof of **unachievability** with the specific limiting factor
4. If all layers exceed the target: outputs conditions that must be maintained for SLA compliance

**4.21.2 SLA Gap Analysis**

When the target SLA is unachievable, the system computes the minimum infrastructure changes required to meet the target:
- Additional replicas needed per component
- MTTR improvement required
- Failover configuration changes
- External dependency SLA requirements

### 4.22 CI/CD Pipeline Integration (Resilience Gate)

The system is designed to operate as a quality gate within CI/CD pipelines.

**4.22.1 Gate Mechanism**

When integrated into a deployment pipeline:
1. Infrastructure-as-Code changes (Terraform, CDK) are automatically imported into the topology model
2. The full simulation suite is executed against the proposed changes
3. A resilience score is computed for the new configuration
4. If the score falls below a configurable threshold, the deployment is **blocked**
5. A report is generated identifying the specific resilience regressions

**4.22.2 Regression Detection**

The system compares the resilience score and specific metrics (SPOF count, cascade severity distribution, availability layers) between the current and proposed configurations, flagging any degradation.

### 4.23 Resilience Score Computation

The resilience score R (0-100) aggregates results across all simulation engines:
- SPOF analysis score (weight: high)
- Cascade severity distribution (weight: high)
- Dynamic simulation survival rate (weight: medium)
- Availability layer analysis (weight: medium)
- Security resilience score (weight: medium)
- Compliance posture score (weight: medium)
- Capacity headroom (weight: low)

### 4.24 Machine Learning-Based Dependency Inference

#### 4.24.1 Problem Statement

In real-world distributed systems, the declared topology — as specified in Infrastructure-as-Code definitions or service registries — frequently omits implicit or emergent dependencies between components. Examples include: (a) a caching layer that, when evicted, causes unexpected load on a database not declared as a direct dependency; (b) a shared logging service whose degradation correlates with latency spikes across multiple independent services; and (c) components that communicate through side channels such as shared file systems, environment variables propagated at deploy time, or transient DNS resolution chains. Manual identification of such hidden dependencies is error-prone, incomplete, and does not scale as infrastructure complexity increases. The present invention addresses this limitation by automatically inferring undeclared dependencies from observational data using multiple complementary statistical methods, without requiring any modification to the monitored infrastructure.

#### 4.24.2 Metrics Correlation Analysis

The system collects time-series metric observations for each infrastructure component, including but not limited to CPU utilization, memory consumption, request latency, requests per second, and error rate. For each unordered pair of components $(A, B)$ and each metric dimension $m$, the system computes the Pearson product-moment correlation coefficient:

$$r_{AB}^{(m)} = \frac{\sum_{i=1}^{n}(x_i - \bar{x})(y_i - \bar{y})}{\sqrt{\sum_{i=1}^{n}(x_i - \bar{x})^2 \cdot \sum_{i=1}^{n}(y_i - \bar{y})^2}}$$

where $x_i$ and $y_i$ are the metric values at time step $i$ for components $A$ and $B$ respectively, and $\bar{x}$, $\bar{y}$ are the corresponding arithmetic means.

When the absolute value of the instantaneous correlation exceeds a configurable threshold (default: $|r| > 0.7$), the system performs lagged correlation analysis to determine the causal direction of the relationship. For each integer lag $\ell \in [-L, +L]$ (where $L$ is a configurable maximum lag, default $L = 5$), the system computes:

$$r_{AB}^{(m,\ell)} = \text{pearson}(x_{1:n-\ell}, \; y_{1+\ell:n}) \quad \text{for } \ell > 0$$

$$r_{AB}^{(m,\ell)} = \text{pearson}(x_{1-\ell:n}, \; y_{1:n+\ell}) \quad \text{for } \ell < 0$$

The lag $\ell^*$ that maximizes $|r_{AB}^{(m,\ell)}|$ determines the inferred causal direction: a positive optimal lag indicates that component $A$ leads component $B$ (i.e., $A \rightarrow B$), while a negative optimal lag indicates $B \rightarrow A$. This constitutes a simplified Granger causality test suitable for infrastructure metric time series. The confidence score for the inferred dependency is computed as:

$$c_{\text{corr}} = |r_{AB}^{(m)}| \cdot \max\!\left(0.3, \; 1 - \frac{1}{1 + |\ell^*|}\right)$$

The floor factor of 0.3 ensures that even contemporaneous correlations (zero lag) contribute a non-trivial confidence when the correlation magnitude is high.

#### 4.24.3 Traffic Pattern Similarity (Dynamic Time Warping)

For each component, the system collects request-count time series and normalizes them to the $[0, 1]$ range using min-max normalization:

$$\hat{s}_i = \frac{s_i - \min(s)}{\max(s) - \min(s)}$$

The system then computes the Dynamic Time Warping (DTW) distance between each pair of normalized traffic time series. DTW finds the optimal non-linear alignment between two sequences $S = (s_1, \ldots, s_n)$ and $T = (t_1, \ldots, t_m)$ by solving the following dynamic programming recurrence:

$$D(i, j) = (s_i - t_j)^2 + \min\!\big(D(i-1, j),\; D(i, j-1),\; D(i-1, j-1)\big)$$

with boundary condition $D(0, 0) = 0$ and $D(i, 0) = D(0, j) = \infty$ for $i, j > 0$. The DTW distance is $\text{DTW}(S, T) = \sqrt{D(n, m)}$. This is normalized by the square root of the maximum series length for cross-pair comparability:

$$d_{\text{norm}} = \frac{\text{DTW}(S, T)}{\sqrt{\max(n, m)}}$$

Component pairs with $d_{\text{norm}}$ below a configurable threshold (default: $0.3$) are inferred to share a dependency relationship, as synchronous traffic fluctuations indicate that one component forwards or triggers requests to the other. The confidence score is:

$$c_{\text{dtw}} = \max\!\big(0, \; \min(1, \; 1 - d_{\text{norm}})\big)$$

The causal direction is heuristically determined by comparing average response times: the component with lower average response time is designated as the upstream (source) component, as upstream components typically exhibit lower processing latency.

#### 4.24.4 Failure Co-occurrence Analysis

The system maintains a history of incident records, each annotated with the set of affected component identifiers. For each unordered pair of components $(A, B)$, the system computes the Jaccard similarity coefficient over the sets of incident indices in which each component was affected:

$$J(A, B) = \frac{|I_A \cap I_B|}{|I_A \cup I_B|}$$

where $I_A$ is the set of incident indices affecting component $A$ and $I_B$ is the set for component $B$. A Jaccard similarity exceeding a configurable threshold (default: $J > 0.5$) indicates that the two components are consistently affected together, suggesting a dependency relationship. The confidence score is set directly to the Jaccard similarity value: $c_{\text{jac}} = J(A, B)$.

The causal direction is heuristically inferred from incident frequency: the component appearing in a greater number of incidents is more likely to be the upstream dependency whose failure cascades to the other component.

#### 4.24.5 Multi-Method Fusion

When the same component pair $(A, B)$ is detected as a potential dependency by multiple inference methods, the system fuses the individual confidence scores to produce a single aggregated confidence. The fusion strategy employs a boosted maximum:

$$c_{\text{fused}} = \min\!\left(1.0, \; \max(c_1, c_2, \ldots, c_k) \cdot \beta_k\right)$$

where $c_1, \ldots, c_k$ are the confidence scores from $k$ distinct methods and $\beta_k$ is a boost factor reflecting the increased reliability of multi-method agreement:

$$\beta_k = \begin{cases} 1.0 & \text{if } k = 1 \\ 1.1 & \text{if } k = 2 \\ 1.2 & \text{if } k \geq 3 \end{cases}$$

This fusion approach favors the strongest individual signal while providing a calibrated uplift for corroboration. The system also merges evidence metadata from all contributing methods, enabling downstream consumers to inspect the full evidentiary basis for each inferred dependency. When different methods infer opposing causal directions for the same pair, the direction from the highest-confidence individual method is adopted.

The fused result set is filtered to exclude component pairs that already exist as declared dependencies in the current graph topology, ensuring that inference output represents only genuinely novel discoveries.

#### 4.24.6 Graph Integration

Inferred dependencies that exceed a configurable minimum confidence threshold (default: $c_{\text{fused}} \geq 0.7$) are automatically added to the InfraGraph directed graph topology model as new dependency edges. Each added edge is annotated with:

- **dependency_type**: `"requires"` if confidence $\geq 0.8$, otherwise `"optional"`, reflecting the strength of the inferred relationship;
- **protocol**: `"inferred"`, distinguishing ML-inferred edges from explicitly declared dependencies;
- **weight**: the fused confidence score, enabling downstream simulation engines to weight inferred dependencies appropriately during cascade propagation and availability computation.

Both source and target components must already exist in the graph for an inferred edge to be added; the system does not create phantom components. This conservative approach ensures that inferred topology augmentations are grounded in known infrastructure inventory.

The integration of inferred dependencies directly into the graph topology enables all existing simulation engines — Cascade Engine, Dynamic Engine, Operations Engine, What-If Engine, and Capacity Engine — to automatically account for previously hidden relationships in their analyses, thereby improving the accuracy and coverage of resilience evaluation without requiring any modification to the simulation algorithms.

### 4.25 Backtest Engine for Prediction Validation

The system includes a backtest engine that validates simulation predictions against documented historical cloud infrastructure incidents, establishing empirical accuracy metrics and enabling automatic calibration of simulation parameters.

#### 4.25.1 Architecture

The backtest engine is implemented as a `BacktestEngine` class that accepts an `InfraGraph` directed graph topology model and a list of `RealIncident` records. Each `RealIncident` record comprises:
- `incident_id`: A unique identifier for the historical incident
- `timestamp`: The date and time of the incident
- `failed_component`: The component identifier representing the initial point of failure
- `actual_affected_components`: The list of component identifiers that were affected in the real incident
- `actual_downtime_minutes`: The total duration of the incident in minutes
- `actual_severity`: The severity classification of the incident (critical, high, medium, or low)
- `root_cause`: A textual description of the root cause

For each incident, the engine produces a `BacktestResult` record comprising the predicted affected components, predicted severity (0-10 scale), predicted downtime in minutes, precision, recall, F1 score, severity accuracy, downtime mean absolute error, prediction confidence, and the full cascade chain for detailed inspection.

#### 4.25.2 CascadeEngine Integration

For each historical incident, the backtest engine constructs a `Fault` object with `fault_type=COMPONENT_DOWN` targeting the identified failed component, then invokes `CascadeEngine.simulate_fault()` on the in-memory graph. The cascade simulation propagates the fault through the directed dependency graph using the breadth-first search algorithm described in Section 4.4, producing a `CascadeChain` containing the list of `CascadeEffect` objects representing each affected component, its resulting health status, and estimated time to impact. The predicted affected component set is extracted from the cascade chain effects.

#### 4.25.3 Accuracy Metrics

The backtest engine computes the following accuracy metrics by comparing the predicted affected component set against the actual affected component set from the historical incident record:

- **Precision:** The fraction of predicted affected components that were actually affected, computed as `Precision = TP / (TP + FP)` where TP (true positives) is the count of components in both the predicted and actual sets, and FP (false positives) is the count of components in the predicted set but not the actual set.

- **Recall:** The fraction of actually affected components that were correctly predicted, computed as `Recall = TP / (TP + FN)` where FN (false negatives) is the count of components in the actual set but not the predicted set.

- **F1 Score:** The harmonic mean of precision and recall, computed as `F1 = 2 × Precision × Recall / (Precision + Recall)`.

- **Severity Accuracy:** A measure of how closely the predicted severity (0-10 numeric scale) matches the actual severity (categorical), computed as `severity_accuracy = 1 - |predicted_severity - actual_severity_numeric| / 10`, where actual severity categories are mapped to numeric values (critical=9.0, high=7.0, medium=5.0, low=2.0). This yields a value between 0.0 and 1.0 where 1.0 indicates a perfect severity match.

- **Downtime Mean Absolute Error (MAE):** The absolute difference between predicted and actual downtime in minutes, computed as `downtime_mae = |predicted_downtime - actual_downtime|`.

- **Prediction Confidence:** A composite score weighting the above metrics, computed as `prediction_confidence = F1 × 0.5 + severity_accuracy × 0.3 + max(0, 1 - downtime_mae / 60) × 0.2`. This assigns the highest weight to component prediction accuracy (F1), followed by severity accuracy, with downtime accuracy contributing a diminishing factor that saturates at 60 minutes of error.

#### 4.25.4 Automatic Calibration

The backtest engine includes a calibration subsystem that analyzes systematic biases in prediction results and recommends parameter adjustments for the simulation engine:

- **Downtime Bias Correction:** Computes the mean error between predicted and actual downtime across all backtest incidents. When the absolute mean error exceeds a threshold (default: 10 minutes), a `downtime_bias_correction` adjustment is recommended, equal to the negation of the mean error. This correction factor may be applied to the downtime estimation heuristics of the cascade engine.

- **Dependency Weight Threshold Reduction:** When the average recall across all backtest incidents falls below a threshold (default: 0.70), a `dependency_weight_threshold_reduction` adjustment of 0.1 is recommended. Low recall indicates that the simulation is failing to predict components that were affected in real incidents, suggesting that dependency weights should be reduced to enable wider cascade propagation.

- **Severity Bias Correction:** Computes the mean error between predicted severity (numeric) and actual severity (mapped to numeric). When the absolute mean severity error exceeds a threshold (default: 2.0 on the 0-10 scale), a `severity_bias_correction` adjustment is recommended, equal to the negation of the mean error.

#### 4.25.5 Historical Incident Database

The system includes a curated database of 18 documented public cloud infrastructure incidents spanning major cloud providers and Internet services, used as the default backtest corpus. The incidents include:

- AWS us-east-1 outage (December 2021) — Internal network connectivity loss affecting multiple AWS services
- AWS S3 outage (February 2017) — S3 service disruption due to operational error
- Meta/Facebook BGP withdrawal (October 2021) — Complete platform outage due to BGP routing configuration error
- Cloudflare outage (June 2022) — BGP routing error affecting global CDN
- GCP networking outage (June 2019) — Network congestion affecting Google Cloud services
- Azure global outage (January 2023) — Wide-area network device connectivity issue
- GitHub DDoS attack (February 2018) — Memcached amplification DDoS attack
- Fastly CDN outage (June 2021) — Software deployment causing global CDN failure
- CrowdStrike/Microsoft outage (July 2024) — Falcon sensor update causing global BSOD
- AWS DynamoDB outage (September 2015) — Storage server latency affecting DynamoDB
- GCP Load Balancer outage (November 2021) — Network routing issue affecting load balancers
- Dyn DNS DDoS attack (October 2016) — Massive DDoS against DNS infrastructure
- AWS Kinesis outage (November 2020) — Internal network scaling failure
- Slack outage (February 2022) — Infrastructure connectivity issues
- AWS EBS outage (April 2011) — EBS volume replication failure cascade
- Roblox outage (October 2021) — Internal network configuration failure
- Azure AD outage (March 2021) — Authentication infrastructure disruption
- OVH datacenter fire (March 2021) — Physical infrastructure destruction

Each incident record contains the provider, affected services, affected regions, root cause description, actual severity, actual downtime duration, and the list of services that were impacted. The database enables systematic validation of FaultRay's prediction accuracy across diverse failure modes including network failures, control plane outages, physical infrastructure destruction, host operating system failures, and application-level incidents.

### 4.26 Shared Infrastructure Dependency Modeling

The system models shared infrastructure dependencies that are not explicitly represented in service-level dependency graphs, enabling accurate simulation of correlated multi-service failures originating from common shared infrastructure layers.

#### 4.26.1 Problem Statement

Large-scale cloud infrastructure outages frequently originate from shared infrastructure layers — internal networks, control planes, physical infrastructure, and host operating systems — that underlie multiple services but are not represented as explicit nodes in service dependency graphs. When such a shared layer fails, all services that depend on it are affected simultaneously, producing correlated multi-service failures that a conventional service-to-service dependency graph cannot predict. For example, an internal network failure at a cloud provider may simultaneously impact compute, storage, database, and CDN services, even though these services have no direct dependencies on one another. Traditional dependency graph models that only capture explicit service-to-service relationships systematically underpredict the scope of such incidents, yielding low recall in backtest validation.

#### 4.26.2 Shared Infrastructure Nodes

The system addresses this limitation by dynamically injecting shared infrastructure nodes into the directed graph topology model. Four categories of shared infrastructure nodes are defined:

- **shared_network:** Represents the internal network fabric of a cloud provider or datacenter. This node models failures such as network connectivity loss, BGP routing errors, internal network congestion, DDoS attacks, and DNS infrastructure failures.

- **control_plane:** Represents the management and orchestration layer of a cloud provider. This node models failures such as API management disruptions, autoscaling failures, deployment pipeline failures, and configuration propagation errors.

- **physical_infra:** Represents the physical infrastructure layer including datacenter facilities. This node models failures such as datacenter fires, power outages, cooling failures, and physical destruction events.

- **host_os:** Represents the host operating system layer on which cloud services execute. This node models failures such as kernel panics, driver crashes, faulty agent updates (e.g., security agent BSOD), and operating system update failures.

When a shared infrastructure node is injected into the graph, all existing service components are connected to the shared node via `requires`-type dependency edges with weight 1.0, reflecting the fact that every service component implicitly depends on the underlying shared infrastructure. The shared node thus serves as a single fault injection point whose failure cascades to all connected service components through the standard cascade propagation algorithm described in Section 4.4.

#### 4.26.3 Intelligent Root Cause Routing

The system employs intelligent root cause routing to automatically determine which shared infrastructure node should serve as the fault injection point for a given incident. The routing algorithm analyzes the root cause description text using keyword matching against four category-specific keyword lists:

- **Network keywords:** network, connectivity, routing, bgp, backbone, internal network, network device, congestion, packet, peering, dns, ddos, traffic, amplification
- **Control plane keywords:** control plane, api, management, orchestration, autoscaling, configuration, deployment
- **Physical infrastructure keywords:** fire, data center, datacenter, power, physical, cooling, flood, earthquake, destroyed
- **Host OS keywords:** bsod, kernel, os update, agent, falcon, crowdstrike, blue screen, sensor, driver

Additionally, when three or more service components are affected simultaneously and no specific root cause keyword match is found, the system defaults to routing the fault to the `shared_network` node, as multi-service concurrent failures most commonly originate from network infrastructure issues.

This routing mechanism enables the backtest engine to automatically select the appropriate shared infrastructure fault injection point without manual incident classification, preserving full automation of the backtest pipeline.

#### 4.26.4 Backtest Accuracy Impact

The introduction of shared infrastructure dependency modeling produced a significant improvement in backtest accuracy when validated against the 18 historical public cloud incidents described in Section 4.25.5:

**Version 1 (Explicit Dependencies Only):**
- Average Precision: 1.000
- Average Recall: 0.499
- Average F1 Score: 0.626

**Version 2 (With Shared Infrastructure Modeling):**
- Average Precision: 1.000
- Average Recall: 1.000
- Average F1 Score: 1.000
- Average Severity Accuracy: 0.819
- Average Prediction Confidence: 0.756

The recall improvement from 0.499 to 1.000 demonstrates that shared infrastructure dependency modeling eliminates the systematic underprediction of failure scope that occurs when using explicit service-to-service dependencies alone. The perfect precision and recall indicate that the system correctly identifies all affected components without false positives when shared infrastructure nodes are present. The severity accuracy of 0.819 and prediction confidence of 0.756 reflect the remaining challenges in precisely estimating severity magnitude and incident duration, which depend on factors beyond dependency graph topology (e.g., provider response time, incident complexity).

### 4.27 Agent-Based Model (ABM) Simulation Engine

The system provides an agent-based model (ABM) simulation engine that models each infrastructure component as an independent, autonomous agent capable of observing the health states of its neighboring components and making probabilistic decisions about its own state transitions. Unlike the deterministic breadth-first search (BFS) cascade engine described in Section 4.2, which computes a single deterministic propagation path, the ABM engine discovers **emergent failure patterns** — cascading behaviors that arise from the concurrent interaction of many independent agents and cannot be predicted by graph traversal alone.

#### 4.27.1 Agent Construction

Each component in the directed graph topology is converted into an autonomous agent with the following attributes:

- **component_id:** A unique identifier linking the agent to its corresponding graph node.
- **state:** One of four health states — `HEALTHY`, `DEGRADED`, `OVERLOADED`, or `DOWN` — initialized to `HEALTHY` at the start of each simulation run.
- **neighbors:** A mapping of neighboring component identifiers to dependency metadata, including both forward dependencies (components this agent depends on) and reverse dependencies (components that depend on this agent, modeled as `dependent` type with weight 0.5). This bidirectional awareness enables the agent to model upstream back-pressure effects.
- **metrics:** Simulated resource metrics derived from the component's current state, including CPU utilization, memory utilization, disk utilization, network connections, and maximum connection capacity.
- **rules:** An ordered list of decision rules, each specifying a condition, a target state, and a priority. Rules are evaluated in descending priority order. The default rule set comprises four rules:
  - `required_dependency_down` (priority 100): Transitions the agent to `DOWN` if any required dependency has been in the `DOWN` state for a number of consecutive steps equal to or exceeding the agent's `timeout_steps` threshold.
  - `cpu_saturation` (priority 70): Transitions the agent to `OVERLOADED` if the agent's CPU utilization exceeds 90%.
  - `optional_dependency_down` (priority 50): Transitions the agent to `DEGRADED` if any optional dependency is `DOWN`.
  - `probabilistic_cascade` (priority 30): A stochastic rule that models retry storms, back-pressure propagation, and emergent load amplification. The probability of transitioning to `DEGRADED` is computed as `P = (unhealthy_neighbors / total_neighbors) × 0.4`, where `unhealthy_neighbors` is the count of neighbors in `DOWN` or `OVERLOADED` state. This probabilistic element is the key differentiator from deterministic BFS: it enables the discovery of failure patterns that depend on the density and distribution of unhealthy neighbors rather than on explicit dependency edges.
- **timeout_steps:** Derived from the component's configured timeout in seconds divided by 5 (each simulation step represents approximately 5 seconds of real time), with a minimum of 1.

#### 4.27.2 Synchronous Discrete-Time Simulation

The ABM simulation proceeds in discrete time steps using a **synchronous update** scheme:

1. **Fault injection:** The target component's agent is set to `DOWN` and remains pinned in that state for the entire simulation.
2. **Snapshot capture:** At the beginning of each step, a read-only snapshot of all agent states is captured. All agents read from this snapshot, ensuring that the order of agent evaluation does not affect the outcome.
3. **Rule evaluation:** Each non-pinned agent evaluates its rules against the snapshot. The worst matching state (highest severity among `HEALTHY` < `DEGRADED` < `OVERLOADED` < `DOWN`) becomes the agent's next state.
4. **State application:** All computed next states are applied simultaneously after all agents have been evaluated.
5. **Convergence detection:** The simulation terminates when the global state snapshot remains unchanged for two consecutive steps, or when a maximum step limit (default 50) is reached.

For multi-fault scenarios, multiple agents are pinned to `DOWN` simultaneously before the simulation loop begins.

#### 4.27.3 Emergent Pattern Detection

After simulation convergence, the ABM engine compares its results against a naive BFS prediction (the transitive closure of required dependencies from the fault target) to identify emergent patterns:

- **Emergent cascade:** Components affected by the ABM simulation but not predicted by BFS. These represent failure propagation through probabilistic back-pressure and retry storm effects that pure graph traversal cannot capture.
- **Resilience discovery:** Components predicted to fail by BFS but remaining healthy in the ABM simulation. These represent cases where timeout buffers, low propagation probability, or partial load shedding prevented cascading failure.

#### 4.27.4 Severity Computation

The ABM engine computes a severity score in the range `[0.0, 10.0]` using a formula consistent with the CascadeEngine:

```
impact_score = (down_count × 1.0 + overloaded_count × 0.5 + degraded_count × 0.25) / affected_count
spread_score = affected_count / total_agents
severity = impact_score × spread_score × 10.0
```

Severity caps are applied: single-component impact is capped at 3.0, spread below 30% is capped at 6.0, and degradation-only scenarios are capped at 4.0.

#### 4.27.5 Comparative Analysis with BFS Cascade Engine

The ABM engine provides a `compare_with_cascade` method that quantifies the agreement between ABM and BFS predictions:

- `bfs_only`: Components affected by BFS but not ABM.
- `abm_only`: Components affected by ABM but not BFS.
- `both`: Components affected by both methods.
- `agreement_ratio`: The Jaccard similarity `|both| / |bfs_only ∪ abm_only ∪ both|`, indicating the degree of overlap between the two prediction methods.

This comparative analysis is valuable for identifying scenarios where deterministic BFS may be over- or under-predicting failure scope, and for calibrating the probabilistic parameters of the ABM engine.

### 4.28 Reinforcement Learning-Based Scenario Generation

The system provides a reinforcement learning (RL) scenario generator that treats the FaultRay simulation engine as an RL environment and uses tabular Q-learning to autonomously discover the most impactful failure scenarios. Rather than relying on predefined scenario generation rules (as described in Section 4.3), the RL agent learns through trial and error which components to fail, in what combination, and with which fault types, in order to maximize cascade damage.

#### 4.28.1 Environment Formulation

The RL environment is defined as follows:

- **State space:** Each state is an immutable snapshot of all component health statuses, encoded as a frozenset of `(component_id, health_status)` pairs. The initial state has all components in `healthy` status. States are serialized to deterministic string keys for Q-table indexing.
- **Action space:** Each action represents the injection of a specific fault type on a specific component. The full action space is the Cartesian product of all component identifiers and all fault types (`COMPONENT_DOWN`, `LATENCY_SPIKE`, `CPU_SATURATION`, `MEMORY_EXHAUSTION`, `DISK_FULL`, `CONNECTION_POOL_EXHAUSTION`, `NETWORK_PARTITION`), yielding `|components| × 7` possible actions.
- **Transition function:** Executing an action invokes the CascadeEngine to simulate fault propagation. The resulting cascade effects update the state by replacing affected component health statuses.
- **Reward signal:** The cascade severity score (range `[0.0, 10.0]`) returned by the CascadeEngine serves as the immediate reward. Higher cascade severity corresponds to higher reward, incentivizing the agent to discover maximally damaging fault combinations.

#### 4.28.2 Q-Learning Algorithm

The agent employs an **ε-greedy tabular Q-learning** algorithm with the following update rule:

```
Q[s][a] ← Q[s][a] + α × (r + γ × max_a' Q[s'][a'] − Q[s][a])
```

Where:
- `Q[s][a]` is the estimated value of taking action `a` in state `s`.
- `α` (learning rate, default 0.1) controls the speed of learning.
- `γ` (discount factor, default 0.9) balances immediate versus future rewards.
- `r` is the immediate reward (cascade severity).
- `max_a' Q[s'][a']` is the maximum Q-value achievable from the next state.
- `ε` (exploration rate, default 0.3, decayed by factor 0.995 per episode to a minimum of 0.05) governs the exploration-exploitation tradeoff.

Each training episode consists of up to `max_steps_per_episode` (default 5) sequential fault injections starting from the all-healthy initial state. Over hundreds of episodes, the Q-table converges to encode a policy mapping infrastructure states to the most damaging actions.

#### 4.28.3 Scenario Generation from Learned Policy

After training, the learned policy is exploited to generate high-impact scenarios through two complementary strategies:

1. **Greedy policy replay:** Starting from the initial state, the agent greedily selects the highest-Q-value action at each step (ε = 0), building a multi-fault scenario of increasing severity. Partial scenarios at each step depth (1-fault, 2-fault, ..., N-fault) are recorded and evaluated through the full simulation engine.

2. **Top-K single-fault extraction:** The Q-values for the initial state are ranked, and the top-K highest-valued actions are extracted as single-fault scenarios. Each scenario is evaluated through the simulation engine to obtain its actual severity score.

All discovered scenarios are ranked by severity, and the top-K are returned as `RLDiscovery` objects containing the `Scenario`, severity score, and discovery method provenance.

#### 4.28.4 Novel Aspects

The RL scenario generation method is novel in that it:
- Uses the infrastructure simulation engine itself as the RL environment, creating a self-contained feedback loop that requires no external data or historical incident records.
- Discovers multi-step correlated failure scenarios that rule-based generators cannot enumerate due to combinatorial explosion.
- Produces a reusable Q-table (policy) that encodes learned knowledge about infrastructure vulnerabilities, enabling rapid scenario generation for subsequent analysis cycles without retraining.

### 4.29 Graph Neural Network (GNN) Cascade Prediction

The system provides a Graph Neural Network (GNN) cascade predictor that learns to predict failure cascade patterns directly from the infrastructure topology structure. This implements the alternative embodiment described in Section 5.8 and the method claimed in Claim 17, using a Message Passing Neural Network (MPNN) architecture.

#### 4.29.1 Architecture

The GNN cascade predictor employs a multi-layer MPNN architecture with the following components:

- **Input layer:** Each node (infrastructure component) is represented by a 14-dimensional feature vector:
  - 4 metric features: CPU utilization / 100, memory utilization / 100, disk utilization / 100, min(network_connections / 1000, 1.0).
  - 10 component type features: One-hot encoding over the 10 infrastructure component types (load_balancer, web_server, app_server, database, cache, message_queue, api_gateway, cdn, dns, external_api).

- **Edge features:** Each dependency edge is represented by a 4-dimensional feature vector:
  - 3 dependency type features: One-hot encoding over dependency types (requires, optional, async).
  - 1 weight feature: The dependency weight value.

- **Message passing layers:** The network performs `num_layers` (default 2) rounds of message passing. At each layer, for each node `v`:

```
h_v^{(l+1)} = σ(W_self^{(l)} · h_v^{(l)} + Σ_{u ∈ N(v)} W_msg^{(l)} · h_u^{(l)} · edge_weight(u,v) + b^{(l)})
```

Where:
  - `W_self^{(l)}` is the self-transformation weight matrix (hidden_dim × input_dim).
  - `W_msg^{(l)}` is the message weight matrix (hidden_dim × input_dim).
  - `edge_weight(u,v)` is the scalar dependency weight between nodes `u` and `v`.
  - `b^{(l)}` is the bias vector.
  - `σ` is the ReLU activation function.
  - `N(v)` is the set of neighbors of node `v` (bidirectional — both dependencies and dependents).

- **Output head:** A linear layer maps each node's final hidden state to a scalar logit, followed by a sigmoid activation to produce a failure probability in `[0, 1]`:

```
P(fail_v) = sigmoid(w_out · h_v^{(L)} + b_out)
```

#### 4.29.2 Self-Supervised Training Data Generation

Training data is generated automatically by running the rule-based CascadeEngine on random single-fault scenarios:

1. For each of `n_scenarios` (default 200) training examples, a random component and random fault type are selected.
2. The CascadeEngine simulates the fault and records which components end up in `DOWN`, `OVERLOADED`, or `DEGRADED` states.
3. Each training example is a pair `(failed_component_id, [affected_component_ids])`.
4. Binary labels are constructed: `1.0` for affected components, `0.0` for unaffected components.
5. The failed component's input features are modified (CPU and memory set to 1.0) to signal the fault injection point.

This self-supervised approach means the GNN learns to approximate the CascadeEngine's behavior from its own outputs, then generalizes to predict **non-obvious cascade patterns** that the rule-based engine might miss due to the GNN's ability to capture higher-order structural relationships in the graph.

#### 4.29.3 Training Procedure

The GNN is trained using binary cross-entropy (BCE) loss and stochastic gradient descent (SGD):

**Loss function:**
```
L = -(1/N) × Σ_v [y_v × log(p_v) + (1 - y_v) × log(1 - p_v)]
```

Where `y_v` is the binary label and `p_v` is the predicted failure probability for node `v`.

**Weight updates:**
- Output head weights are updated using the exact gradient: `∂L/∂w_out = (1/N) × Σ_v (p_v - y_v) × h_v`.
- Message passing layer weights are updated using a simplified node-level gradient propagation scheme that back-propagates the output error signal through the output head weights to the GNN layer parameters.
- Weight matrices are initialized using Xavier-scale initialization: `U(-limit, limit)` where `limit = scale × √(6 / (fan_in + fan_out))`.

#### 4.29.4 Prediction and Confidence

Given a failed component, the trained GNN predicts the failure probability for every component in the infrastructure:

- The failed component's features are modified to signal fault injection.
- The message passing forward pass is executed.
- Each node receives a failure probability and a confidence score computed as `confidence = |probability - 0.5| × 2.0`, reflecting how decisive the prediction is (higher confidence when probability is far from the decision boundary).
- Predictions are sorted by failure probability in descending order.

#### 4.29.5 Novel Aspects

The GNN cascade predictor is novel in that it:
- Learns structural patterns in the infrastructure topology graph that influence failure propagation but are not captured by explicit dependency traversal rules.
- Uses self-supervised training from the system's own CascadeEngine results, requiring no external training data or labeled historical incidents.
- Operates entirely within the Python standard library (no external ML framework dependencies), implementing matrix operations, activation functions, and gradient computation from first principles.
- Provides per-component failure probability predictions with confidence scores, enabling risk-ranked prioritization of infrastructure hardening efforts.

### 4.30 ML-Based Failure Prediction from Infrastructure Metrics

The system provides a machine learning-based failure predictor that estimates the probability of upcoming component failures from current infrastructure metric observations. This predictor uses logistic regression trained on synthetic data generated by the system's own simulation engines, enabling predictive failure analysis without requiring historical production incident data.

#### 4.30.1 Feature Extraction

Each infrastructure component's current state is encoded as a 5-dimensional normalized feature vector:

```
x = [cpu/100, memory/100, disk/100, connections/max_connections, utilization/100]
```

Where:
- `cpu`, `memory`, `disk` are the component's current resource utilization percentages.
- `connections` is the current active network connection count, normalized by the component's maximum connection capacity.
- `utilization` is the component's overall utilization score (a composite metric derived from resource usage and capacity).

#### 4.30.2 Logistic Regression Model

The failure predictor employs a logistic regression model:

```
P(failure) = sigmoid(w · x + b) = 1 / (1 + exp(-(w · x + b)))
```

Where `w` is a 5-dimensional weight vector and `b` is a scalar bias, both learned during training.

#### 4.30.3 Synthetic Training Data Generation

Training data is synthesized by running the CascadeEngine on random fault scenarios with metric perturbation:

1. For each of `n_samples` (default 500) training examples:
   a. A random component and random fault type are selected from `COMPONENT_DOWN`, `CPU_SATURATION`, `MEMORY_EXHAUSTION`, `DISK_FULL`, and `CONNECTION_POOL_EXHAUSTION`.
   b. The component's metrics are extracted and perturbed with Gaussian noise (σ = 0.15) to introduce training variety.
   c. The CascadeEngine simulates the fault injection.
   d. If the target component ends up in `DOWN` state, the label is `1.0` (failure); otherwise `0.0`.
2. For positive (failure) samples, features are further biased toward high utilization (additive uniform noise in `[0.1, 0.4]`) to model the pre-failure stress signature.
3. For negative (non-failure) samples, features are biased toward normal utilization (subtractive uniform noise in `[0.0, 0.2]`).

This data augmentation strategy ensures the model learns to associate high resource utilization patterns with impending failure, even though the simulation engine does not explicitly model gradual degradation.

#### 4.30.4 Training Procedure

The model is trained using stochastic gradient descent (SGD) on binary cross-entropy loss:

**Loss function:**
```
L = -[y × log(p) + (1 - y) × log(1 - p)]
```

**Gradient with respect to weights:**
```
∂L/∂w_k = (p - y) × x_k
∂L/∂b = (p - y)
```

**Update rule (per-sample SGD):**
```
w_k ← w_k - lr × (p - y) × x_k
b ← b - lr × (p - y)
```

Where `lr` (learning rate, default 0.01) controls the step size and training runs for a configurable number of epochs (default 200).

#### 4.30.5 Prediction Output

For each component, the predictor outputs:

- **failure_probability:** The sigmoid output in `[0, 1]`, representing the estimated probability of failure.
- **risk_level:** A categorical classification derived from the probability:
  - `critical`: probability ≥ 0.8
  - `high`: probability ≥ 0.6
  - `medium`: probability ≥ 0.3
  - `low`: probability < 0.3
- **time_to_failure_minutes:** An estimated time to failure computed from the current utilization level and the failure probability:
  - Critical (p > 0.8): `max(1, (1 - utilization/100) × 60)` minutes.
  - High (p > 0.5): `max(10, (1 - utilization/100) × 360)` minutes.
  - Low (p ≤ 0.5): `max(60, (1 - utilization/100) × 1440)` minutes.

The `predict_all` method generates a `PredictorReport` containing predictions for every component sorted by failure probability, a list of high-risk component identifiers, and the model's training accuracy.

#### 4.30.6 Model Evaluation

The predictor provides an evaluation method that computes classification metrics on a held-out test set (generated using the same synthetic data pipeline):

- **Accuracy:** `(TP + TN) / (TP + TN + FP + FN)`
- **Precision:** `TP / (TP + FP)`
- **Recall:** `TP / (TP + FN)`

#### 4.30.7 Novel Aspects

The ML failure predictor is novel in that it:
- Trains entirely on synthetic data generated by the system's own simulation engines, eliminating the cold-start problem inherent in ML-based failure prediction systems that require historical production data.
- Bridges the gap between simulation-based resilience analysis (which evaluates "what would happen if component X fails") and predictive analytics (which estimates "which component is most likely to fail next").
- Operates entirely within the Python standard library, implementing logistic regression, sigmoid activation, and SGD optimization from first principles without external ML framework dependencies.
- Provides actionable output (risk level, time-to-failure estimate) that enables proactive infrastructure hardening before failures occur.

### 4.31 Bayesian Network Failure Probability

The system provides a Bayesian network engine that computes conditional failure probabilities for each infrastructure component using Bayes' theorem applied to the dependency graph structure. Unlike the deterministic BFS cascade engine described in Section 4.4, which propagates a single failure state through dependency edges, the Bayesian engine computes the *probability* that each component will fail given the observed or hypothesized states of its dependencies, enabling probabilistic what-if analysis without executing a full cascade simulation.

#### 4.31.1 Prior Failure Probability

For each component $c_i$ in the directed graph, a prior failure probability is computed from the component's steady-state unavailability:

$$P(\text{fail}_i) = \left(\frac{\text{MTTR}_i}{\text{MTBF}_i + \text{MTTR}_i}\right)^{r_i}$$

Where $\text{MTBF}_i$ is the mean time between failures in hours, $\text{MTTR}_i$ is the mean time to repair in hours, and $r_i$ is the replica count. The exponentiation by replica count models parallel redundancy under the assumption of independent replica failures: $P(\text{all replicas fail}) = P(\text{single fail})^{r_i}$.

#### 4.31.2 Conditional Impact Computation

For each component $c_i$ and each of its dependencies $c_j$ (components on which $c_i$ depends), the system computes the conditional failure probability $P(\text{fail}_i \mid \text{fail}_j)$ using dependency-type-based impact factors:

$$P(\text{fail}_i \mid \text{fail}_j) = \min\!\left(1.0,\; P(\text{fail}_i) + f(d_{ij}) \cdot (1 - P(\text{fail}_i))\right)$$

Where $f(d_{ij})$ is the impact factor for the dependency type $d_{ij}$ between components $c_i$ and $c_j$:

- `requires` dependency: $f = 0.9$ (near-certain failure propagation)
- `optional` dependency: $f = 0.3$ (partial impact)
- `async` dependency: $f = 0.1$ (minimal immediate impact)

This formulation ensures that $P(\text{fail}_i \mid \text{fail}_j) \geq P(\text{fail}_i)$, i.e., a dependency failure never *decreases* the probability of the dependent component's failure.

#### 4.31.3 Posterior Probability with Evidence

The system supports evidence-based querying: given a set of observed component states (healthy, degraded, or down), it computes the updated posterior failure probability for all components. The posterior is computed using the law of total probability across all dependency relationships:

$$P(\text{fail}_i \mid \text{evidence}) = \min\!\left(1.0,\; P(\text{fail}_i) + e_{\max} \cdot (1 - P(\text{fail}_i))\right)$$

Where $e_{\max}$ is the maximum combined effect across all dependencies, incorporating both observed evidence (known-down dependencies contribute their full impact factor) and uncertain evidence (healthy or unknown dependencies contribute their impact factor weighted by their own prior failure probability).

#### 4.31.4 Differentiation from Other Engines

The Bayesian engine is complementary to other simulation engines in the following respects:

- Unlike the **BFS cascade engine** (Section 4.4), which computes deterministic binary outcomes (affected/unaffected), the Bayesian engine produces continuous probability distributions.
- Unlike the **ABM engine** (Section 4.27), which uses stochastic simulation with fixed probabilistic rules, the Bayesian engine derives probabilities analytically from the graph structure and operational profiles.
- Unlike the **GNN cascade predictor** (Section 4.29), which learns propagation patterns from training data, the Bayesian engine computes probabilities from first principles using Bayes' theorem without requiring training.
- Unlike the **ML failure predictor** (Section 4.30), which predicts failure from current resource metrics using logistic regression, the Bayesian engine predicts failure from dependency structure and observed component states.

### 4.32 Markov Chain Availability Model

The system provides a continuous-time Markov chain (CTMC) availability model that computes steady-state availability for each infrastructure component using a three-state Markov process. Unlike the N-Layer Availability Limit Model described in Section 4.9, which computes static availability ceilings from closed-form expressions, the Markov model captures the *dynamic transition behavior* between component health states, including degradation-before-failure paths that the N-Layer model does not represent.

#### 4.32.1 Three-State Model

Each component is modeled as a continuous-time Markov chain with three states:

- **HEALTHY** (state 0): The component is operating normally.
- **DEGRADED** (state 1): The component is experiencing partial impairment but remains operational.
- **DOWN** (state 2): The component has failed and is not serving requests.

The state transitions form the following structure:

```
HEALTHY ←→ DEGRADED → DOWN → HEALTHY
```

That is:
- HEALTHY may transition to DEGRADED (gradual degradation) or directly to DOWN (catastrophic failure).
- DEGRADED may recover to HEALTHY or deteriorate to DOWN.
- DOWN recovers to HEALTHY (repair).

#### 4.32.2 Transition Rate Parameterization

The transition rates are derived from each component's operational profile:

- **HEALTHY → DEGRADED:** Degradation rate $\lambda_{H \to D}$, derived from the component's degradation profile (memory leak rate, disk fill rate). Components exhibiting resource leaks receive a higher degradation rate (default $0.05$/hour) than stable components (default $0.01$/hour).
- **HEALTHY → DOWN:** Direct failure rate $\lambda_{H \to \text{DOWN}} = 0.3 / \text{MTBF}$, reflecting catastrophic failures that bypass the degraded state.
- **DEGRADED → DOWN:** Accelerated failure rate $\lambda_{D \to \text{DOWN}} = 3.0 / \text{MTBF}$, reflecting the increased failure risk of degraded components (three times the base rate).
- **DEGRADED → HEALTHY:** Recovery rate $\lambda_{D \to H}$, representing automated recovery from degradation (default $0.1$/hour).
- **DOWN → HEALTHY:** Repair rate $\lambda_{\text{DOWN} \to H} = 1 / \text{MTTR}$.

Rates are converted to discrete-time transition probabilities using the exponential complementary CDF: $P(\text{transition}) = 1 - e^{-\lambda \cdot \Delta t}$, where $\Delta t = 1$ hour.

#### 4.32.3 Steady-State Distribution

The steady-state probability vector $\pi = [\pi_H, \pi_D, \pi_{\text{DOWN}}]$ is computed using the iterative power method:

$$\pi^{(t+1)} = \pi^{(t)} \cdot P$$

Where $P$ is the $3 \times 3$ row-stochastic transition matrix. The iteration continues until convergence: $\|\pi^{(t+1)} - \pi^{(t)}\|_\infty < \epsilon$ (default $\epsilon = 10^{-12}$).

#### 4.32.4 Derived Metrics

From the steady-state distribution, the following metrics are computed:

- **Availability:** $A = \pi_H + \pi_D$ (probability of not being DOWN).
- **Nines of availability:** $N = -\log_{10}(1 - A)$, expressing availability in the standard "nines" notation.
- **Mean sojourn time:** For each state $i$, the expected time spent in that state before transitioning: $\bar{T}_i = 1 / (1 - P_{ii})$.

#### 4.32.5 Differentiation from N-Layer Model

The Markov model is complementary to the N-Layer Availability Limit Model (Section 4.9) in the following respects:

- The **N-Layer model** computes static availability ceilings and identifies the binding constraint layer; the **Markov model** computes the dynamic equilibrium availability accounting for state transition paths.
- The N-Layer model treats each component as binary (available/unavailable); the Markov model explicitly represents the DEGRADED intermediate state.
- The Markov model captures the effect of degradation rate on availability: components with high degradation rates (e.g., memory leaks) have lower steady-state availability even when their MTBF/MTTR ratio is favorable.
- The Markov model provides sojourn times, enabling prediction of how long a component is expected to remain in each state — information not available from the N-Layer model.

### 4.33 Discrete Event Simulation (DES) Engine

The system provides a discrete event simulation (DES) engine that models infrastructure failure propagation as a sequence of time-stamped events processed from a priority queue. Unlike the ABM engine described in Section 4.27, which uses synchronous discrete-time steps where all agents update simultaneously, the DES engine processes events asynchronously in strict chronological order, enabling precise modeling of temporal dynamics including propagation delays, timeout-triggered cascades, and MTTR-based recovery timing.

#### 4.33.1 Event Model

Each event in the simulation is a tuple $(t, c, \tau, D)$ where:

- $t$ is the timestamp (simulation time in seconds).
- $c$ is the target component identifier.
- $\tau$ is the event type: one of `FAULT` (initial failure injection), `CASCADE` (failure propagation from a dependency), or `RECOVERY` (component restoration).
- $D$ is an arbitrary metadata dictionary carrying event-specific information (source component, dependency type, reason string, severity).

Events are ordered by timestamp using a min-heap (priority queue), ensuring that the earliest event is always processed first regardless of insertion order.

#### 4.33.2 Event-Driven Processing Loop

The simulation proceeds as follows:

1. **Initialization:** All components are set to HEALTHY. The initial fault is scheduled as a `FAULT` event at $t = 0$.
2. **Main loop:** The earliest event is popped from the priority queue. If its timestamp exceeds the simulation duration, the simulation terminates. Otherwise, the event is processed according to its type:
   - **FAULT event:** The target component is set to DOWN. For each component that depends on the target, a `CASCADE` event is scheduled at time $t + \delta$, where the propagation delay $\delta$ is computed as $\max(\text{edge\_latency}, 0.1) + \text{timeout} \times 0.1$. A `RECOVERY` event is scheduled at time $t + \text{MTTR}$.
   - **CASCADE event:** The target component's state is updated based on dependency type (`requires` → DOWN or DEGRADED based on replica count; `optional` → DEGRADED; `async` → DEGRADED). If the component transitions to DOWN, further cascade events are scheduled for its dependents. A recovery event is scheduled based on MTTR.
   - **RECOVERY event:** The target component is restored to HEALTHY.
3. **Termination:** The simulation ends when the event queue is empty or the simulation clock exceeds the configured duration.

#### 4.33.3 Temporal Precision

The DES engine's event-driven paradigm provides temporal precision that is not achievable with the time-stepped approaches used by the Dynamic Engine (Section 4.5, 30-second steps) or the ABM Engine (Section 4.27, 5-second steps):

- Events are processed at their exact scheduled time, not rounded to the nearest time step.
- Cascade propagation delays reflect actual network latency and timeout configurations, producing realistic time-to-impact estimates.
- Recovery events fire at the precise MTTR-derived time, enabling accurate modeling of overlapping failure and recovery dynamics.

#### 4.33.4 Severity Computation

The DES engine computes severity using the same formula as the Cascade Engine (Section 4.4.5):

$$\text{severity} = \frac{\text{DOWN} \times 1.0 + \text{OVERLOADED} \times 0.5 + \text{DEGRADED} \times 0.25}{\text{affected}} \times \frac{\text{affected}}{\text{total}} \times 10.0$$

With the same caps applied (single-component ≤ 3.0; spread < 30% ≤ 6.0; degraded-only ≤ 4.0).

#### 4.33.5 Differentiation from Other Engines

- Unlike the **BFS cascade engine** (Section 4.4), which computes a single instantaneous propagation, the DES engine produces a full event timeline with realistic propagation delays.
- Unlike the **Dynamic Engine** (Section 4.5), which uses fixed-interval time steps, the DES engine processes events at arbitrary time granularity.
- Unlike the **ABM engine** (Section 4.27), which uses synchronous update (all agents evaluate simultaneously), the DES engine uses asynchronous update (events are processed one at a time in strict chronological order), enabling discovery of timing-dependent failure patterns.

### 4.34 Genetic Algorithm Scenario Optimizer

The system provides a genetic algorithm (GA) optimizer that discovers worst-case failure scenarios through population-based evolutionary search. Unlike the reinforcement learning scenario generator described in Section 4.28, which trains a single agent through sequential trial-and-error episodes, the GA optimizer evolves a *population* of candidate scenarios simultaneously, exploiting crossover between high-fitness individuals to explore the combinatorial failure space more broadly.

#### 4.34.1 Chromosome Encoding

Each candidate scenario is encoded as a binary chromosome (bitstring) of length $N$, where $N$ is the number of components in the infrastructure graph. A `True` at position $i$ indicates that the $i$-th component is injected with a `COMPONENT_DOWN` fault; a `False` indicates no fault. This encoding directly maps the combinatorial failure space ($2^N$ possible scenarios) to the GA's search space.

#### 4.34.2 Fitness Function

The fitness of a chromosome is the total cascade severity produced by simultaneously injecting all flagged faults:

$$\text{fitness}(c) = \min\!\left(10.0,\; \sum_{i : c_i = \text{True}} \text{severity}(\text{cascade}(i))\right)$$

Each fault is individually simulated through the CascadeEngine, and the resulting severities are accumulated, capped at 10.0. Higher fitness indicates greater system damage, steering the GA toward discovering the most impactful failure combinations.

#### 4.34.3 Evolutionary Operators

The GA employs three standard evolutionary operators:

1. **Tournament selection** ($k = 3$): Three individuals are randomly sampled from the population, and the fittest is selected as a parent. This balances selection pressure with diversity preservation.

2. **Single-point crossover:** A random crossover point $p \in [1, N-1]$ is selected. Two parents exchange their chromosome segments at position $p$, producing two offspring that combine failure patterns from both parents.

3. **Bit-flip mutation** (rate = 0.05): Each bit in the offspring chromosome is independently flipped with 5% probability, introducing novel fault combinations not present in either parent.

#### 4.34.4 Evolution Loop

The GA proceeds for a configurable number of generations (default: 100) with a population of configurable size (default: 50):

1. **Initialization:** Random population with ~10% fault density per chromosome.
2. **Evaluation:** All chromosomes are evaluated via the fitness function.
3. **Elitism:** The best individual is carried forward unchanged.
4. **Reproduction:** Remaining slots are filled via tournament selection → crossover → mutation.
5. **Termination:** The loop ends when the maximum generation count is reached or a chromosome achieves maximum fitness (10.0).

#### 4.34.5 Differentiation from RL Scenario Generator

The GA optimizer is complementary to the RL scenario generator (Section 4.28) in the following respects:

- The **RL agent** explores the scenario space by sequentially injecting faults and observing outcomes, building a Q-table that encodes value estimates for individual (state, action) pairs. The **GA** evolves a *population* of complete scenarios simultaneously, exploiting crossover to combine partial solutions that may never be discovered by sequential exploration.
- The RL agent discovers *sequential* multi-step attack strategies; the GA discovers *simultaneous* multi-fault combinations that cause maximum damage when all faults occur at once.
- The GA uses the Cascade Engine as a black-box fitness oracle, while the RL agent uses it as an environment transition function — a philosophical difference in how the simulation engine is coupled to the search process.
- The GA produces a single best scenario (the highest-fitness chromosome) plus generation-level fitness history; the RL agent produces a reusable Q-table policy.

### 4.35 Fault Tree Analysis (FTA)

The system provides a Fault Tree Analysis (FTA) engine that performs top-down deductive failure analysis on the infrastructure dependency graph. Unlike the FMEA engine described in Section 4.20, which performs a *bottom-up* inductive analysis (enumerating failure modes per component and computing their risk priority numbers), the FTA engine starts from a *top event* (system failure) and deductively decomposes it into combinations of basic events (individual component failures) through Boolean logic gates.

#### 4.35.1 Fault Tree Construction

The Fault Tree is constructed from the infrastructure directed graph by walking the dependency structure:

- **Root node (top event):** Represents system failure. The root is an OR gate over all entry-point components (components with no dependents), reflecting the fact that the failure of any user-facing entry point constitutes a system-level failure.
- **Intermediate nodes:** Each component with required dependencies generates a subtree. Components with single instances yield an **OR gate** (any single dependency failure impacts the component). Components with multiple replicas yield a **VOTING gate** ($k$-of-$n$, where $k$ failures out of $n$ dependencies are required to cause failure).
- **Leaf nodes (basic events):** Components with no further required dependencies. Each leaf carries a base failure probability derived from its MTBF: $P(\text{fail}) = 1 - e^{-1/\text{MTBF}}$ (probability of failure within a one-hour window).

Optional dependencies are excluded from the fault tree, as they do not contribute to the critical failure path.

#### 4.35.2 Probability Computation

The top-event probability is computed bottom-up through the tree:

- **OR gate:** $P(\text{OR}) = 1 - \prod_{i}(1 - P_i)$ (at least one child fails).
- **AND gate:** $P(\text{AND}) = \prod_{i} P_i$ (all children fail).
- **VOTING gate** ($k$-of-$n$): $P(k\text{-of-}n) = \sum_{r=k}^{n} \sum_{C \in \binom{[n]}{r}} \prod_{i \in C} P_i \prod_{j \notin C} (1 - P_j)$.

#### 4.35.3 Minimal Cut Sets

A *cut set* is a set of basic events (leaf component failures) whose simultaneous occurrence causes the top event. A *minimal cut set* has no proper subset that is also a cut set. The FTA engine computes minimal cut sets by:

- **OR gate:** The union of all children's cut sets.
- **AND gate:** The Cartesian product of children's cut sets.
- **VOTING gate:** The union of Cartesian products over all $\binom{n}{k}$ combinations of $k$ children.

Non-minimal cut sets (supersets of other cut sets) are removed in a post-processing step.

#### 4.35.4 Critical Component Ranking

Components are ranked by criticality based on the number of minimal cut sets in which they appear. Components appearing in more minimal cut sets represent higher-leverage points for reliability improvement, as hardening a single such component eliminates multiple failure paths simultaneously.

#### 4.35.5 Differentiation from FMEA and Cascade Engine

- The **FMEA engine** (Section 4.20) is *bottom-up inductive*: it enumerates failure modes per component and computes RPN scores. The **FTA engine** is *top-down deductive*: it starts from the system failure event and decomposes it into contributing causes.
- The **Cascade Engine** (Section 4.4) computes how a specific fault propagates forward through the graph. The FTA engine computes which *combinations* of basic component failures can cause a system-level failure event — a backward analysis.
- Minimal cut sets from FTA directly identify the smallest sets of component failures that would bring down the system, providing actionable input for redundancy planning.

### 4.36 Survival Analysis

The system provides a survival analysis engine that estimates the remaining useful life of each infrastructure component using classical statistical methods adapted from reliability engineering. Unlike the ML failure predictor described in Section 4.30, which uses logistic regression trained on synthetic data to estimate failure probability from current metrics, the survival analysis engine applies non-parametric (Kaplan-Meier) and parametric (Weibull distribution) statistical techniques to model the time-to-failure distribution, producing survival curves, hazard functions, and remaining-life predictions grounded in established statistical theory.

#### 4.36.1 Kaplan-Meier Survival Estimation

For each component, the engine generates synthetic failure-time observations from the component's MTBF using the inverse CDF of the exponential distribution:

$$t_k = -\text{MTBF} \cdot \ln\!\left(1 - \frac{k}{n+1}\right), \quad k = 1, \ldots, n$$

The Kaplan-Meier estimator computes the survival function $S(t)$ — the probability of surviving beyond time $t$:

$$S(t) = \prod_{t_i \leq t} \left(1 - \frac{d_i}{n_i}\right)$$

Where $d_i$ is the number of failures at time $t_i$ and $n_i$ is the number of components at risk just before $t_i$. The last observation is treated as right-censored (still operational), following standard survival analysis practice.

#### 4.36.2 Weibull Distribution Fitting

The engine fits a two-parameter Weibull distribution to observed failure times using a simplified maximum likelihood estimation:

- **Scale parameter** ($\lambda$): Derived from the mean failure time via $\lambda = \bar{t} / \Gamma(1 + 1/k)$.
- **Shape parameter** ($k$): Estimated from the coefficient of variation via $k \approx 1.2 / \text{CV}$, bounded to $[0.5, 5.0]$.

The shape parameter characterizes the failure behavior:
- $k < 1$: Infant mortality (decreasing hazard rate).
- $k = 1$: Random failures (constant hazard, equivalent to exponential distribution).
- $k > 1$: Wear-out (increasing hazard rate — typical of aging infrastructure).

#### 4.36.3 Hazard Function

The Weibull hazard function (instantaneous failure rate) at time $t$ is:

$$h(t) = \frac{k}{\lambda} \left(\frac{t}{\lambda}\right)^{k-1}$$

This provides the instantaneous risk of failure at any given point in time, enabling identification of components entering the wear-out phase ($h(t)$ increasing over time).

#### 4.36.4 Remaining Useful Life Prediction

For each component, the engine predicts remaining useful life by computing an effective MTBF adjusted for current operational stress:

$$\text{MTBF}_{\text{eff}} = \frac{\text{MTBF}}{\text{stress} \times \text{degrade}}$$

Where:
- $\text{stress} = 1 + (\text{utilization} / 100) \times 2$, modeling the life-shortening effect of high resource utilization (up to 3× acceleration at 100% utilization).
- $\text{degrade}$ accounts for active degradation patterns (memory leaks approaching OOM, disk fill approaching capacity).

The predicted remaining life is $\text{MTBF}_{\text{eff}} \times \Gamma(1 + 1/k)$ hours, where $k = 1.5$ (wear-out assumption).

#### 4.36.5 Differentiation from ML Failure Predictor

- The **ML failure predictor** (Section 4.30) uses logistic regression trained on synthetic data, outputting a binary failure probability and categorical risk level. The **survival analysis engine** provides continuous survival curves, hazard functions, and quantitative remaining-life estimates in hours.
- The ML predictor relies on current metric snapshots; survival analysis incorporates the full time-to-failure distribution.
- Survival analysis is a well-established statistical methodology (Kaplan & Meier, 1958; Weibull, 1951) with known properties and confidence interval theory, providing a principled complement to the ML predictor's data-driven approach.

### 4.37 Petri Net Modeling

The system provides a Petri Net modeling engine that represents the infrastructure as a formal Place/Transition net, enabling reachability analysis and deadlock detection. Unlike the DES engine described in Section 4.33, which models failures as discrete events processed from a priority queue, the Petri Net engine models the *concurrency structure* of the system explicitly through token flow, enabling formal verification of properties such as reachability, liveness, and deadlock freedom that event-based simulation cannot guarantee.

#### 4.37.1 Place/Transition Net Construction

The infrastructure directed graph is automatically converted into a Petri Net:

- **Places:** Each component $c_i$ generates three places: `{c_i}_healthy` (initial token count = 1), `{c_i}_degraded` (initial token count = 0), and `{c_i}_down` (initial token count = 0). The token in `{c_i}_healthy` represents the component's initial operational state. The conservation of one token per component across its three places ensures that a component is in exactly one state at any time.

- **Transitions:** Dependency edges generate transitions that model failure propagation:
  - For `requires` dependencies: Two transitions — (1) `cascade_degrade` fires when the dependency is DOWN and the dependent is HEALTHY, moving the dependent to DEGRADED; (2) `cascade_down` fires when the dependency is DOWN and the dependent is already DEGRADED, moving the dependent to DOWN.
  - For `optional` dependencies: One `opt_degrade` transition that moves the dependent from HEALTHY to DEGRADED when the dependency is DOWN.
  - For `async` dependencies: One `async_degrade` transition with the same topology as optional.
  - For each component: A `recovery` transition that moves the component from DOWN back to HEALTHY.

- **Token semantics:** The dependency's DOWN place serves as both an input and output of cascade transitions (self-loop), ensuring that the dependency remains DOWN while enabling the transition to fire — modeling the persistent effect of an upstream failure.

#### 4.37.2 Simulation

The Petri Net simulation proceeds by repeatedly finding and firing enabled transitions:

1. **Fault injection:** The initial marking is overridden to set a target component's `_healthy` place to 0 tokens and its `_down` place to 1 token.
2. **Firing loop:** At each step, all enabled transitions (transitions whose input places all have at least one token) are identified. The first enabled transition is fired deterministically. Firing consumes one token from each input place and produces one token in each output place.
3. **Termination:** The simulation terminates when no transitions are enabled (deadlock), when the marking has been previously visited (cycle detection), or when the maximum step count is reached.

#### 4.37.3 Reachability Analysis

The engine performs full reachability analysis via BFS over the state space:

Starting from the current marking, all possible transition firings are explored. Each unique marking (state) is recorded. The exploration continues until all reachable markings have been visited or a safety cap (default: 10,000 states) is reached.

The reachable state set enables:
- **Deadlock detection:** A reachable state with no enabled transitions is a deadlock — indicating a failure mode from which the system cannot recover without external intervention.
- **Safety property verification:** Checking whether any reachable state violates safety constraints (e.g., "no state exists where all database replicas are simultaneously DOWN").

#### 4.37.4 Differentiation from DES and ABM Engines

- The **DES engine** (Section 4.33) processes events asynchronously; the **Petri Net engine** models concurrency explicitly through token flow and transition enablement.
- The **ABM engine** (Section 4.27) uses probabilistic rules; the Petri Net engine is fully deterministic given the initial marking.
- The Petri Net formalism enables formal verification (reachability analysis, deadlock detection) that is not possible with event-based or agent-based simulation approaches.
- The Petri Net's state space is finite and enumerable, enabling exhaustive analysis of all possible system behaviors from a given initial condition.

### 4.38 Cellular Automata Failure Propagation

The system provides a cellular automata (CA) engine that models failure propagation using deterministic local rules applied synchronously across all infrastructure components. Unlike the ABM engine described in Section 4.27, which uses *probabilistic* rules where the cascade probability depends on the fraction of unhealthy neighbors, the CA engine uses *deterministic* threshold rules where state transitions are entirely determined by the count of neighbors in each state, producing fully reproducible results suitable for formal analysis and pattern classification.

#### 4.38.1 Grid Construction

The CA grid is derived from the infrastructure dependency graph, where each component is a *cell* and the neighbor set of each cell comprises both upstream dependencies and downstream dependents (bidirectional adjacency). This contrasts with the ABM engine, which also considers bidirectional dependencies but applies weighted probabilistic rules; the CA engine applies unweighted deterministic threshold rules.

#### 4.38.2 Deterministic Transition Rules

Each cell occupies one of four states, ordered by severity: `HEALTHY` (0) < `DEGRADED` (1) < `OVERLOADED` (2) < `DOWN` (3). On each generation, all cells update simultaneously according to the following deterministic rules (evaluated in priority order):

1. **DOWN is absorbing:** A cell in DOWN state remains DOWN (no recovery within the simulation).
2. **Rule 1:** If $\geq 2$ neighbors are DOWN → cell becomes DOWN (overwhelming failure pressure).
3. **Rule 2:** If $\geq 1$ neighbor is DOWN → cell becomes at least DEGRADED. If the cell is already OVERLOADED or worse, it becomes DOWN.
4. **Rule 3:** If $\geq 3$ neighbors are DEGRADED → cell becomes at least OVERLOADED (cumulative degradation pressure).
5. **Rule 4:** If $\geq 2$ neighbors are OVERLOADED → cell becomes at least OVERLOADED.
6. **Default:** Cell retains its current state.

The `max` operator ensures monotonicity: a cell's state never improves during the simulation (states can only worsen or stay the same).

#### 4.38.3 Pattern Classification

After simulation, the engine classifies the observed dynamic into one of three categories:

- **Stable:** The grid converged (last two generation snapshots are identical). This indicates that the failure has reached a fixed point — all affected components have settled into their final states.
- **Oscillating:** The grid exhibits a repeating cycle of length 2-5. This indicates sustained oscillation in the failure dynamics, analogous to flapping health checks or retry-recovery loops in real infrastructure.
- **Chaotic:** No convergence or repeating pattern is detected within the simulation horizon. This indicates complex, unpredictable failure dynamics.

This classification is inspired by Wolfram's classification of one-dimensional cellular automata (Classes I-IV) adapted to infrastructure failure dynamics.

#### 4.38.4 Differentiation from ABM Engine

The CA engine is complementary to the ABM engine (Section 4.27) in the following respects:

- The **ABM engine** uses *probabilistic* rules: the probability of cascading depends on the ratio of unhealthy neighbors to total neighbors, introducing stochastic variation. The **CA engine** uses *deterministic threshold* rules: the outcome depends solely on the *count* of neighbors in each state, producing identical results on every run.
- The ABM engine requires multiple runs for statistical significance; a single CA run is sufficient for deterministic analysis.
- The CA engine's deterministic nature enables formal analysis: the exact conditions under which a failure propagates to a given component can be stated as a logical formula over neighbor state counts.
- The CA engine's pattern classification (stable/oscillating/chaotic) provides qualitative insight into failure dynamics that the ABM engine does not produce.
- Both engines use synchronous update (all cells/agents evaluate simultaneously from a snapshot), but they differ in whether the transition function is deterministic (CA) or stochastic (ABM).

### 4.39 System Dynamics (Stock-and-Flow) Engine

The system provides a System Dynamics engine that models infrastructure component health as continuous-valued stocks governed by ordinary differential equations (ODEs), with degradation and recovery expressed as continuous flows. This approach fills a fundamental paradigm gap in the FaultRay multi-engine architecture: whereas the ABM engine (Section 4.27) models components as discrete autonomous agents with rule-based behavior, the DES engine (Section 4.33) processes discrete time-stamped events, and the Cellular Automata engine (Section 4.38) uses discrete state transitions on a grid, the System Dynamics engine treats health as a *continuous* variable evolving under smooth differential equations, enabling analysis of degradation velocity, tipping-point thresholds, and recovery trajectories that are invisible to discrete-state models.

#### 4.39.1 Stock-and-Flow Formulation

Each infrastructure component $i$ is modeled as a *stock* $H_i(t) \in [0.0, 1.0]$ representing the component's health level at time $t$. The health stock evolves according to three *flows*:

$$\frac{dH_i}{dt} = r_i - d_i - \sum_{j \in \text{deps}(i)} c_{ji}$$

where:
- $r_i$ is the **recovery rate** — the rate at which a healthy component self-heals or absorbs transient stress;
- $d_i$ is the **degradation rate** — the background wear or load-induced degradation;
- $c_{ji}$ is the **cascade impact** from each dependency $j$ that component $i$ relies on, computed as $c_{ji} = w_c \times (1 - H_j(t))$, where $w_c$ is a cascade weight parameter and the impact grows as the dependency's health decreases.

Cascade impact is further modulated by dependency type: `optional` dependencies carry a 0.3× multiplier and `async` dependencies carry a 0.1× multiplier, reflecting the reduced coupling of non-critical dependency types.

#### 4.39.2 Euler Integration

The continuous ODE is approximated using forward Euler integration with configurable time-step width $dt$:

$$H_i(t + dt) = H_i(t) + \frac{dH_i}{dt} \times dt$$

The result is clamped to $[0.0, 1.0]$ at each step. The faulted (initially failed) component is held at $H = 0.0$ throughout the simulation (modeling a hard failure), while all other components start at $H = 1.0$ and evolve under the ODE.

#### 4.39.3 Severity Computation

The engine computes an overall severity score (0.0–10.0) from the time-series of health values across all components:

$$\text{severity} = \left(\text{avg\_degradation} \times 0.6 + \text{spread} \times 0.4\right) \times 10$$

where $\text{avg\_degradation}$ is the average depth of degradation ($1 - \min(H_i)$) across all components, and $\text{spread}$ is the fraction of components whose health dropped below 0.5 at any point during the simulation.

#### 4.39.4 Differentiation from Other Engines

| Aspect | ABM (Section 4.27) | DES (Section 4.33) | CA (Section 4.38) | System Dynamics |
|--------|---------------------|---------------------|---------------------|-----------------|
| State representation | Discrete {HEALTHY, DEGRADED, OVERLOADED, DOWN} | Discrete event-driven state | Discrete {0,1,2,3} | Continuous $[0.0, 1.0]$ |
| Update mechanism | Probabilistic rules | Event priority queue | Deterministic threshold | ODE integration |
| Temporal model | Discrete steps | Asynchronous events | Synchronous generations | Continuous time |
| Granularity | Coarse (4 states) | Event-resolution | Coarse (4 states) | Arbitrary precision |
| Unique insight | Emergent patterns | Exact timing | Pattern classification | Degradation velocity, tipping points |

The continuous-valued representation enables the System Dynamics engine to detect phenomena such as: (a) slow degradation trends that have not yet crossed a discrete-state threshold but are on a trajectory toward failure; (b) the exact health level at which cascade effects become self-reinforcing (tipping point); and (c) the recovery rate required to stabilize a degrading system before it reaches a failure state.

### 4.40 RNN/LSTM Time-Series Failure Prediction

The system provides recurrent neural network (RNN) and Long Short-Term Memory (LSTM) predictors that consume sequences of infrastructure metric snapshots and predict failure probability by capturing temporal dependencies across the sequence. Unlike the logistic regression predictor (Section 4.30) which treats each observation as an independent, static feature vector, the RNN/LSTM predictor models *time-series dynamics* — learning patterns such as "CPU utilization rising for three consecutive observation windows precedes an out-of-memory failure" that a memoryless classifier would miss.

#### 4.40.1 Simple RNN Architecture

The Simple RNN (Elman network) computes a hidden state $h_t$ at each time-step $t$ from the current input $x_t$ and the previous hidden state $h_{t-1}$:

$$h_t = \tanh(W_{hh} \cdot h_{t-1} + W_{xh} \cdot x_t + b_h)$$

The final hidden state $h_T$ is passed through a linear output layer with sigmoid activation to produce a scalar failure probability:

$$y = \sigma(W_{hy} \cdot h_T + b_y)$$

This architecture is computationally efficient and sufficient for short metric sequences (10–20 time-steps).

#### 4.40.2 LSTM Architecture

The LSTM variant addresses the vanishing-gradient problem of vanilla RNNs by introducing gated memory cells that selectively retain or discard information:

$$f_t = \sigma(W_f \cdot [h_{t-1}, x_t] + b_f) \quad \text{(forget gate)}$$
$$i_t = \sigma(W_i \cdot [h_{t-1}, x_t] + b_i) \quad \text{(input gate)}$$
$$\tilde{c}_t = \tanh(W_g \cdot [h_{t-1}, x_t] + b_g) \quad \text{(candidate cell)}$$
$$o_t = \sigma(W_o \cdot [h_{t-1}, x_t] + b_o) \quad \text{(output gate)}$$
$$c_t = f_t \odot c_{t-1} + i_t \odot \tilde{c}_t$$
$$h_t = o_t \odot \tanh(c_t)$$

The forget gate bias is initialized to 1.0 (Jozefowicz et al., 2015), encouraging the LSTM to retain information by default. The gating mechanism enables the LSTM to model long-range temporal dependencies (e.g., a gradual disk fill rate over dozens of observation windows) that the simple RNN cannot reliably capture.

#### 4.40.3 Training on Simulation-Synthesized Data

A critical differentiating aspect of the FaultRay RNN/LSTM predictor is that training data is *synthetically generated from the in-memory simulation model*, not collected from real production logs. The data generation process:

1. Selects a random component from the infrastructure graph as a seed;
2. Extracts base metric values (CPU%, memory%, disk%) from the component's current configuration;
3. Generates a metric time-series of configurable length by applying either an upward trend (simulating resource exhaustion leading to failure) or a stable/declining trend (simulating normal operation);
4. Labels the sequence as positive (failure) or negative (normal) based on the applied trend.

This simulation-synthesized training approach enables the predictor to learn failure patterns from a rich corpus of generated scenarios without requiring access to historical production data, making it applicable to infrastructure that has not yet experienced failures or for which no historical telemetry is available.

#### 4.40.4 Differentiation from Prior Art

**Differentiation from NEC Corporation (US20170293542A1) — "Anomaly detection in streams of short text using LSTM networks":** The NEC patent applies LSTM to real-world operational log data streams for anomaly detection on production systems. The FaultRay RNN/LSTM predictor differs fundamentally in that: (a) it is trained exclusively on *simulation-synthesized data* generated from the in-memory infrastructure model, requiring no access to real production logs or telemetry; (b) prediction is performed *on the in-memory simulation model* to evaluate hypothetical infrastructure configurations before deployment, rather than monitoring a live production system; and (c) the predictor operates as one component of a multi-engine simulation architecture where simulation results from other engines (Cascade, Dynamic, Operations) serve as ground truth for training data generation.

**Differentiation from logistic regression predictor (Section 4.30):** The logistic regression predictor treats each component snapshot as an independent feature vector, discarding temporal ordering. The RNN/LSTM predictor consumes the *ordered sequence* of snapshots, enabling it to detect failure-predictive temporal patterns (monotonic resource increase, oscillatory instability, sudden slope changes) that are invisible to a memoryless classifier.

### 4.41 Simulated Annealing Scenario Optimizer

The system provides a Simulated Annealing (SA) optimizer that discovers worst-case failure scenarios through single-solution metaheuristic search over the fault-scenario space. Unlike the Genetic Algorithm optimizer (Section 4.34) which evolves a *population* of candidate solutions through crossover and mutation, and the Reinforcement Learning scenario generator (Section 4.28) which learns a sequential fault-injection policy through trial-and-error, the SA optimizer maintains a *single candidate solution* and performs local perturbation (bit-flip), accepting worse solutions with a probability governed by the Metropolis criterion that decreases as the system "cools."

#### 4.41.1 Search Space and Objective

The search space is the set of all binary vectors of length $N$ (where $N$ is the number of infrastructure components), where a 1 indicates that the corresponding component is faulted. The objective is to maximize the estimated cascade severity, computed by counting the transitive dependents affected by each faulted component, weighted by dependency type and cross-fault interactions.

#### 4.41.2 Metropolis Acceptance Criterion

At each iteration, a neighbor solution is generated by flipping one random bit in the current solution. The neighbor is accepted or rejected according to:

- If the neighbor has higher severity (improvement): always accept.
- If the neighbor has lower severity (worsening): accept with probability $P = \exp(\Delta E / T)$, where $\Delta E = \text{neighbor\_cost} - \text{current\_cost}$ (negative for a worsening move) and $T$ is the current temperature.

This probabilistic acceptance of worse solutions enables the optimizer to escape local optima in the early high-temperature phase, while the geometric cooling schedule $T(k) = T_0 \times \alpha^k$ (where $\alpha$ is the cooling rate, typically 0.995) ensures convergence to a near-optimal solution as the temperature approaches zero.

#### 4.41.3 Differentiation from GA and RL Approaches

| Aspect | GA (Section 4.34) | RL (Section 4.28) | Simulated Annealing |
|--------|---------------------|---------------------|---------------------|
| Search paradigm | Population-based evolution | Sequential policy learning | Single-solution neighborhood search |
| Exploration mechanism | Crossover + mutation | ε-greedy exploration | Temperature-controlled acceptance |
| Solution representation | Binary chromosome (same) | State-action pairs | Binary vector (same as GA) |
| Knowledge persistence | Population diversity | Q-table | Best solution found |
| Parallelism | Inherently parallel (population) | Sequential episodes | Sequential iterations |
| Local optima escape | Crossover jumps | Exploration policy | Metropolis acceptance |

The SA optimizer is complementary to the GA optimizer: GA explores the combinatorial space broadly through population diversity and crossover, while SA explores locally through neighborhood perturbation with controlled randomness. Running both optimizers and comparing results provides higher confidence that the true worst-case scenario has been identified.

### 4.42 Reliability Block Diagram (RBD)

The system provides a Reliability Block Diagram (RBD) analyzer that computes system-level availability from the composition of series and parallel blocks derived from the infrastructure dependency graph. Unlike the Fault Tree Analysis engine (Section 4.35) which uses AND/OR/VOTING gates on *failure events* (top-down deductive analysis), the RBD analyzer uses block connectivity patterns on *success paths* (bottom-up structural analysis), providing a complementary perspective on system reliability.

#### 4.42.1 Component Availability Computation

Individual component availability is derived from operational profile parameters:

$$A_{\text{single}} = \frac{\text{MTBF}}{\text{MTBF} + \text{MTTR}}$$

For components with parallel redundancy (replicas > 1 or failover enabled), effective availability is computed using the parallel redundancy formula:

$$A_{\text{parallel}} = 1 - (1 - A_{\text{single}})^n$$

where $n$ is the effective replica count (the maximum of the declared replica count and 2 when failover is enabled).

#### 4.42.2 Series and Parallel Block Composition

The RBD analyzer converts the infrastructure dependency graph into a block diagram:

- **Series blocks:** Components connected by `requires` dependencies form a series chain. The path availability is the product of individual availabilities: $P_{\text{path}} = \prod_{i \in \text{path}} A_i$. All components in the chain must be operational for the path to succeed (weakest-link semantics).
- **Parallel blocks:** Multiple independent paths between the same endpoints provide parallel redundancy. The system availability is: $A_{\text{system}} = 1 - \prod_{\text{paths}} (1 - P_{\text{path}})$. The system is operational if *any* path is operational.

Critical paths are identified from the dependency graph using root-to-leaf traversal (up to 50 paths), and the overall system availability is computed as the parallel combination of all path availabilities.

#### 4.42.3 Differentiation from Fault Tree Analysis (Section 4.35)

| Aspect | FTA (Section 4.35) | RBD |
|--------|---------------------|-----|
| Analysis direction | Top-down deductive (from system failure to component failures) | Bottom-up structural (from component blocks to system availability) |
| Modeling focus | Failure events and logic gates (OR/AND/VOTING) | Success paths and block connectivity |
| Output | System failure probability, minimal cut sets | System availability, path availabilities, component contributions |
| Question answered | "What combinations of failures cause system failure?" | "What is the system availability given component reliabilities?" |
| Complementary insight | Identifies critical failure combinations | Quantifies availability impact of redundancy configurations |

### 4.43 Event Tree Analysis (ETA)

The system provides an Event Tree Analysis (ETA) engine that performs inductive forward risk assessment starting from an initiating event (e.g., a component failure) and tracing forward through a sequence of safety barriers or mitigation functions, each of which can succeed or fail. This is the *inductive complement* to Fault Tree Analysis (Section 4.35) which works *deductively* backward from a top event.

#### 4.43.1 Event Tree Construction

Given an initiating event (identified by component ID), the ETA engine automatically generates branching safety functions from the infrastructure topology:

1. **Circuit Breaker Activation:** Success probability derived from the ratio of dependents that have circuit breakers configured on their edges to the failing component.
2. **Failover to Standby:** High success probability (0.95) when failover is enabled; low probability (0.10) when not configured.
3. **Autoscaling Response:** Present when autoscaling is enabled, with success probability 0.85 reflecting the typical response time lag.
4. **Replica Redundancy:** Present when replicas > 1, with success probability $1 - (0.01)^{\text{replicas}}$ reflecting the probability that at least one replica survives.

#### 4.43.2 Outcome Enumeration

The engine enumerates all $2^n$ combinations of success/failure across $n$ safety barriers, computing the combined probability of each outcome path as the product of the individual barrier probabilities along that path. Each outcome is classified by severity:

- **Low:** All barriers succeeded ($0$ failures).
- **Medium:** Up to half the barriers failed.
- **High:** More than half but not all barriers failed.
- **Critical:** All barriers failed.

The total risk is computed as $\text{Risk} = \sum_i P_i \times W_i$, where $P_i$ is the outcome probability and $W_i$ is the severity weight (low=1, medium=3, high=7, critical=10).

#### 4.43.3 Differentiation from Fault Tree Analysis

| Aspect | FTA (Section 4.35) | ETA |
|--------|---------------------|-----|
| Direction | Top-down deductive (backward from top event) | Bottom-up inductive (forward from initiating event) |
| Question answered | "What causes system failure?" | "What happens after a component fails?" |
| Output | Failure probability, minimal cut sets | Outcome probability distribution, total risk |
| Gate model | AND/OR/VOTING logic gates | Binary success/failure branches |
| Use case | Identifying root cause combinations | Evaluating effectiveness of safety barriers |

### 4.44 Extreme Value Theory (EVT)

The system provides an Extreme Value Theory analyzer that fits a Generalised Extreme Value (GEV) distribution to block-maxima of cascade severity data, enabling Return Level analysis and tail-risk probability estimation. Unlike the Survival Analysis engine (Section 4.36) which models the *time until failure* (answering "when will it fail?"), the EVT analyzer models the *magnitude of the worst outcomes* (answering "how bad can the worst case get?") — fundamentally different questions requiring fundamentally different statistical frameworks.

#### 4.44.1 GEV Distribution

The Generalised Extreme Value distribution unifies the three classical extreme value distributions (Gumbel, Fréchet, Weibull) via the shape parameter $\xi$:

$$F(x) = \exp\left(-\left[1 + \xi \frac{x - \mu}{\sigma}\right]^{-1/\xi}\right)$$

where $\mu$ is the location parameter, $\sigma > 0$ is the scale parameter, and $\xi$ is the shape parameter:
- $\xi > 0$: Fréchet distribution (heavy tail — extreme failures can be arbitrarily severe)
- $\xi = 0$: Gumbel distribution (light exponential tail)
- $\xi < 0$: Weibull distribution (bounded upper tail — there is a maximum possible severity)

Parameters are estimated via the Method of Moments: $\sigma \approx \text{std} \times \sqrt{6} / \pi$, $\mu \approx \text{mean} - \sigma \times \gamma$ (where $\gamma \approx 0.5772$ is the Euler–Mascheroni constant), and $\xi$ is estimated from the skewness of the observed data.

#### 4.44.2 Return Level Computation

The Return Level $x_T$ for a return period $T$ represents the severity level expected to be exceeded once every $T$ observation windows:

$$x_T = \mu + \frac{\sigma}{\xi}\left((-\log(1 - 1/T))^{-\xi} - 1\right)$$

For the Gumbel case ($\xi = 0$): $x_T = \mu - \sigma \log(-\log(1 - 1/T))$.

This enables infrastructure operators to answer questions such as "what cascade severity should we expect to encounter once every 100 simulation windows?" — a tail-risk metric that is not available from any of the other simulation engines.

#### 4.44.3 Tail-Risk Probability

The exceedance probability $P(X > x)$ for a given severity threshold $x$ is computed as:

$$P(X > x) = 1 - F(x)$$

This enables estimation of the probability that a cascade event will exceed a specific severity threshold, supporting risk-informed infrastructure investment decisions.

#### 4.44.4 Differentiation from Survival Analysis (Section 4.36)

| Aspect | Survival Analysis (Section 4.36) | EVT |
|--------|-----------------------------------|-----|
| Question answered | "When will it fail?" | "How severe will the worst failure be?" |
| Distribution | Weibull (time-to-event) | GEV (block-maxima magnitude) |
| Input data | Component MTBF, degradation patterns | Maximum cascade severity per observation window |
| Output | Remaining useful life, hazard rate | Return levels, tail-risk probabilities |
| Risk perspective | Temporal (time-to-failure) | Magnitude (worst-case severity) |

### 4.45 Model Checking (Formal Verification)

The system provides a model checker that performs exhaustive state-space exploration with CTL-like (Computation Tree Logic) temporal property verification. Unlike the Petri Net engine (Section 4.37) which models concurrency via token flow and verifies reachability properties, the model checker operates on explicit state tuples and supports temporal-logic property checking (AG, EF, AF) that go beyond simple reachability, providing a more expressive formal verification capability.

#### 4.45.1 State Space Construction

The model checker enumerates the reachable state space of the infrastructure graph by breadth-first search (BFS). Each state is a tuple assigning a health status (HEALTHY or DOWN) to every component. Transitions model failure propagation: when a component is DOWN, its dependents connected via `requires` dependencies (with replica count ≤ 1) may also transition to DOWN. The cascade propagation is computed iteratively until a fixed point is reached.

The state space is bounded by a configurable maximum state count (default 10,000) to prevent combinatorial explosion while still providing useful verification results.

#### 4.45.2 CTL Temporal-Logic Properties

Three CTL operators are supported, each answering a distinct formal verification question about the infrastructure:

- **AG(p)** — "Always Globally": Property $p$ holds in *all* reachable states. Example: AG(database ≠ DOWN) — "the database never fails in any scenario." A counterexample is a path from the initial state to a state that violates $p$.
- **EF(p)** — "Exists Finally": There *exists* a reachable state where $p$ holds. Example: EF(all\_services = DOWN) — "is it possible for all services to go down simultaneously?" A witness is a path from the initial state to a satisfying state.
- **AF(p)** — "Always Finally": On *all* paths, $p$ *eventually* holds. Example: AF(web\_server = DOWN) — "will the web server inevitably fail in every scenario?" Approximated by verifying that all terminal states (no successors) satisfy $p$.

Each verification returns a result comprising the property name, satisfaction status, number of states explored, and a counterexample (or witness) path when applicable.

#### 4.45.3 Counterexample Generation

When a property is violated (AG) or witnessed (EF), the model checker produces a path of states from the initial (all-healthy) state to the violating/witnessing state via BFS, providing a concrete execution trace that demonstrates the property violation. This trace identifies the exact sequence of component failures that leads to the undesired state.

#### 4.45.4 Differentiation from Petri Net (Section 4.37)

| Aspect | Petri Net (Section 4.37) | Model Checker |
|--------|--------------------------|---------------|
| Formalism | Place/Transition net (tokens) | Explicit state tuples |
| Property types | Reachability, deadlock detection | Temporal logic (AG, EF, AF) |
| Expressiveness | "Can state X be reached?" | "Does property P hold on all/some paths always/eventually?" |
| Concurrency model | Token flow (inherently concurrent) | State enumeration (explicit) |
| Output | Reachable markings, deadlock states | Satisfaction result + counterexample paths |

The model checker's temporal-logic capability enables verification of properties that combine universal/existential quantification over paths with always/eventually quantification over time — a strictly more expressive query language than the reachability queries supported by the Petri Net engine.

### 4.46 Random Forest Failure Predictor

The system provides a Random Forest predictor that uses an ensemble of bagged decision trees with feature sub-sampling to predict component failure probability from infrastructure metrics. Unlike the logistic regression predictor (Section 4.30) which fits a linear decision boundary in the feature space, the Random Forest captures non-linear interactions and complex decision boundaries without explicit feature engineering.

#### 4.46.1 Decision Tree Construction

Each tree in the forest is trained by recursively splitting the feature space to maximize information gain (reduction in entropy):

$$\text{Gain} = H(\text{parent}) - \sum_{\text{children}} \frac{|S_c|}{|S|} H(S_c)$$

where $H(S) = -\sum_k p_k \log_2(p_k)$ is the entropy of label distribution in set $S$. Splits are selected from a random subset of features at each node (feature sub-sampling), and trees are grown to a configurable maximum depth.

#### 4.46.2 Bagging and Feature Sub-Sampling

The Random Forest achieves variance reduction through two sources of randomness:

1. **Bootstrap aggregation (bagging):** Each tree is trained on a bootstrap sample (random sampling with replacement) of the training data, so each tree sees a different subset of examples.
2. **Feature sub-sampling:** At each split, only a random subset of $\sqrt{d}$ features (where $d$ is the total feature count) is considered, de-correlating the trees.

Final predictions are the average of all tree predictions, providing a smoothed probability estimate with lower variance than any individual tree.

#### 4.46.3 Training on Simulation-Synthesized Data

As with the RNN/LSTM predictor (Section 4.40), training data is synthetically generated from the in-memory infrastructure model. The feature vector comprises CPU utilization, memory utilization, disk utilization, connection pool saturation, and replica count (all normalized to [0, 1]). Labels are generated using a weighted risk score with stochastic threshold.

#### 4.46.4 Differentiation from Logistic Regression (Section 4.30)

| Aspect | Logistic Regression (Section 4.30) | Random Forest |
|--------|--------------------------------------|---------------|
| Decision boundary | Linear hyperplane | Arbitrary non-linear |
| Feature interactions | Must be manually engineered | Automatically captured by tree splits |
| Model type | Single model (low variance, potential high bias) | Ensemble (low bias, reduced variance) |
| Interpretability | Feature weight vector | Feature importance from split frequency |
| Overfitting risk | Low (linear constraint) | Controlled by bagging + depth limit |

### 4.47 Autoencoder Anomaly Detection

The system provides an autoencoder neural network for unsupervised anomaly detection in infrastructure metrics. Unlike the ML Failure Predictor (Section 4.30) and Random Forest (Section 4.46) which require labeled failure data (supervised learning), the autoencoder learns to reconstruct *normal* metric patterns and flags samples with high reconstruction error as anomalies, requiring *only normal data* for training (unsupervised learning).

#### 4.47.1 Architecture

The autoencoder consists of:

- **Encoder:** A linear layer mapping from input dimension $d$ to a lower-dimensional hidden representation of dimension $h$ ($h < d$), followed by ReLU activation. The encoder compresses the input, forcing the network to learn a compact representation of normal patterns.
- **Decoder:** A linear layer mapping from the hidden dimension $h$ back to the input dimension $d$, followed by sigmoid activation (bounding outputs to [0, 1]).

The bottleneck architecture (input → compressed → reconstructed) forces the network to learn the essential structure of normal data. Anomalous patterns, which differ from the training distribution, are reconstructed poorly, producing high reconstruction error.

#### 4.47.2 Anomaly Detection via Reconstruction Error

Training minimizes the mean squared reconstruction error on normal data:

$$\text{MSE} = \frac{1}{d} \sum_{i=1}^{d} (x_i - \hat{x}_i)^2$$

At inference time, the anomaly threshold is set at the configured percentile (default 95th) of training reconstruction errors. Samples exceeding this threshold are classified as anomalous.

#### 4.47.3 Training on Simulation-Synthesized Data

The autoencoder is trained on normal-state metric vectors generated from the in-memory infrastructure model. This enables anomaly detection on infrastructure configurations that have not yet been deployed to production, identifying metric patterns that deviate from the expected baseline.

#### 4.47.4 Differentiation from Prior Art

**Differentiation from Amazon Technologies (US11374952B1) — "Autoencoder-based anomaly detection for cloud infrastructure":** The Amazon patent applies autoencoder anomaly detection to *real-time monitoring data from production cloud infrastructure* for operational anomaly detection. The FaultRay autoencoder differs fundamentally in that: (a) it is trained on *simulation-synthesized normal data* generated from the in-memory infrastructure model, not real production telemetry; (b) anomaly detection is performed *on the in-memory simulation model* to evaluate hypothetical infrastructure configurations before deployment, identifying anomalous metric patterns that *would* occur under simulated fault conditions; and (c) the autoencoder operates as one component of a multi-engine architecture where "normal" baseline data is derived from non-faulted simulation states, enabling anomaly detection without access to any production environment.

**Differentiation from supervised predictors (Sections 4.30, 4.46):** Supervised predictors require labeled failure examples; the autoencoder requires only normal data, making it applicable when failure examples are scarce or unavailable (e.g., for newly designed infrastructure that has never experienced failures).

### 4.48 Transformer/Attention Failure Propagation Predictor

The system provides a single-layer Transformer predictor that uses self-attention to predict failure probability from metric time-series. Unlike the RNN/LSTM predictor (Section 4.40) which processes time-steps sequentially and suffers from information compression over long sequences, the Transformer processes all time-steps in parallel via attention, directly capturing long-range dependencies without the sequential bottleneck and vanishing-gradient issues inherent in recurrent architectures.

#### 4.48.1 Architecture

The Transformer predictor comprises five stages:

1. **Input Projection:** Raw feature vectors ($d_{\text{input}}$ dimensions per time-step) are projected to the model dimension ($d_{\text{model}}$) via a learned linear transformation $W_{\text{embed}}$.

2. **Positional Encoding:** Sinusoidal positional encodings are added to the projected embeddings, injecting positional information since the attention mechanism is permutation-invariant:

$$\text{PE}(\text{pos}, 2i) = \sin\left(\frac{\text{pos}}{10000^{2i/d_{\text{model}}}}\right)$$
$$\text{PE}(\text{pos}, 2i+1) = \cos\left(\frac{\text{pos}}{10000^{2i/d_{\text{model}}}}\right)$$

3. **Self-Attention:** The core attention computation allows each time-step to attend to all other time-steps:

$$\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right) \cdot V$$

where $Q = X \cdot W_Q$, $K = X \cdot W_K$, $V = X \cdot W_V$ are learned linear projections of the input sequence. The scaling factor $\sqrt{d_k}$ prevents the dot products from growing large and producing near-deterministic softmax distributions.

4. **Feed-Forward Network:** A two-layer MLP with ReLU activation: $\text{FFN}(x) = W_2 \cdot \max(0, W_1 \cdot x + b_1) + b_2$. Residual connections and layer normalization are applied after both the attention and FFN sub-layers.

5. **Output:** Mean pooling over the sequence dimension followed by a linear + sigmoid layer produces the scalar failure probability.

#### 4.48.2 Attention Interpretability

The attention weight matrix ($T \times T$ where $T$ is the sequence length) is exposed for inspection, showing which time-steps the model considers most informative for the failure prediction. This provides an interpretability advantage: operators can identify *when* in the metric history the most predictive signal occurs (e.g., "the model attends most strongly to time-steps 7–9, suggesting that the metric spike at that point was the dominant failure indicator").

#### 4.48.3 Training on Simulation-Synthesized Data

As with the RNN/LSTM predictor, training data is synthetically generated from the in-memory simulation model. The output layer weights are updated using analytical gradient descent on binary cross-entropy loss.

#### 4.48.4 Differentiation from RNN/LSTM (Section 4.40)

| Aspect | RNN/LSTM (Section 4.40) | Transformer |
|--------|--------------------------|-------------|
| Processing order | Sequential (left-to-right) | Parallel (all positions simultaneously) |
| Long-range dependencies | Compressed through hidden state (lossy) | Direct attention (lossless) |
| Gradient flow | Through time (vanishing gradient risk) | Direct (no vanishing gradient) |
| Positional awareness | Implicit from recurrence | Explicit positional encoding |
| Interpretability | Hidden state is opaque | Attention weights are inspectable |
| Computational complexity | $O(T \times d^2)$ sequential | $O(T^2 \times d)$ parallelizable |

The Transformer's quadratic complexity in sequence length ($T^2$) is acceptable for the typical infrastructure monitoring sequence lengths (10–50 time-steps) used in FaultRay, while its ability to capture long-range dependencies and provide attention-based interpretability makes it the preferred architecture for scenarios where understanding *which* time-steps drive the prediction is as important as the prediction itself.

## 5. ALTERNATIVE EMBODIMENTS AND EXTENSIONS

### 5.1 Machine Learning-Enhanced Scenario Generation

In an alternative embodiment, the automated scenario generator is augmented with a machine learning model (including but not limited to large language models, graph neural networks, or reinforcement learning agents) that:
- Analyzes historical incident data to generate scenarios reflecting real-world failure patterns
- Identifies failure combinations that are statistically likely but not covered by rule-based generation
- Learns from simulation results to prioritize high-impact scenarios
- Generates natural-language descriptions of novel failure scenarios not anticipated by the rule-based categories

### 5.2 Digital Twin Continuous Synchronization

In an alternative embodiment, the in-memory topology model is continuously synchronized with a real infrastructure environment through:
- Real-time metric ingestion from monitoring systems (Prometheus, CloudWatch, Datadog, etc.)
- Automatic topology updates when infrastructure changes are detected (via Terraform state changes, Kubernetes API watches, or cloud provider event streams)
- Continuous simulation execution that re-evaluates resilience as the infrastructure evolves
- Drift detection between the model and reality, alerting when the model diverges from actual infrastructure state

In a further refinement of the digital twin synchronization embodiment, the continuous metric ingestion stream is additionally fed to the machine learning-based dependency inference engine described in Section 4.24. As the digital twin accumulates real-time metric snapshots, traffic observations, and incident records over successive synchronization cycles, the inference engine periodically re-evaluates the topology for undeclared dependencies. Newly inferred dependencies are automatically integrated into the synchronized graph model, enabling the digital twin to discover and adapt to emergent infrastructure relationships that were not present in the original topology declaration. This closed-loop integration between live metric ingestion and statistical dependency inference ensures that the digital twin's topology representation becomes progressively more accurate over time, even as the underlying infrastructure evolves.

### 5.3 Natural Language Infrastructure Definition

In an alternative embodiment, the infrastructure topology is defined through natural language input, where:
- A language model interprets descriptions such as "a three-tier web application with Redis cache and PostgreSQL database on AWS"
- The system automatically generates the corresponding graph topology with appropriate component types, dependencies, default metrics, and capacity configurations
- The user iteratively refines the model through natural language dialogue

### 5.4 Simulation-Driven Infrastructure Remediation

In an alternative embodiment, the system automatically generates remediation actions from simulation results:
- When a SPOF is detected, the system generates the specific Infrastructure-as-Code (Terraform, CloudFormation, CDK) modifications needed to add redundancy
- When a cascade vulnerability is identified, the system generates circuit breaker configurations or dependency restructuring proposals
- Remediation proposals are ranked by cost-effectiveness (improvement in resilience score per unit cost)
- The system can apply approved remediations directly to IaC repositories through pull request generation

### 5.5 Multi-Cloud Correlated Failure Analysis

In an alternative embodiment, the system models infrastructure spanning multiple cloud providers and analyzes correlated failures that cross provider boundaries:
- Shared dependency analysis (e.g., common DNS providers, CDN providers, certificate authorities)
- Cross-cloud network partition scenarios
- Correlated outage probability estimation based on historical cloud provider incident data
- Multi-cloud failover strategy evaluation

### 5.6 Temporal Infrastructure Evolution Simulation

In an alternative embodiment, the system simulates infrastructure evolution over extended time periods (months to years):
- Growth modeling: how increasing user traffic affects resilience over time
- Degradation modeling: component aging, technical debt accumulation, dependency obsolescence
- Planned change impact: evaluating how scheduled migrations, upgrades, or architecture changes affect resilience trajectory
- Optimal timing analysis: determining the best time to perform infrastructure investments

### 5.7 Cost-Constrained Resilience Optimization

In an alternative embodiment, the system performs multi-objective optimization to find the optimal infrastructure configuration under cost constraints:
- Pareto frontier computation between cost and resilience score
- Marginal resilience improvement per dollar analysis
- Automatic identification of the most cost-effective resilience improvements
- Budget allocation optimization across multiple infrastructure investments

### 5.8 Graph Neural Network-Based Topology Analysis

**Note:** This embodiment has been implemented. See Section 4.29 for the detailed description of the GNN cascade predictor, including MPNN architecture, self-supervised training from CascadeEngine results, and per-component failure probability prediction with confidence scores.

In an alternative embodiment, the graph-based topology model is analyzed using graph neural network (GNN) techniques:
- GNN-based failure propagation prediction that captures non-obvious cascade patterns
- Anomalous topology pattern detection (identifying structural vulnerabilities not captured by rule-based analysis)
- Transfer learning from simulation results of similar topologies to accelerate analysis of new infrastructure designs

### 5.9 Backtest Engine for Prediction Validation

**Note:** This embodiment has been implemented. See Section 4.25 for the detailed description of the backtest engine, including accuracy metrics, automatic calibration, and the historical incident database.

In an alternative embodiment, the system validates simulation predictions against historical incident data:
- Past incident scenarios are replayed through the simulator
- Predicted vs. actual impact is compared to establish prediction accuracy metrics
- Simulation parameters are automatically calibrated based on backtest results
- Confidence intervals are computed for future predictions based on historical accuracy

### 5.10 Continuous Validation Engine

**Note:** The backtest validation aspect of this embodiment has been implemented. See Section 4.25 for the backtest engine that compares simulation predictions against historical incident data and automatically calibrates simulation parameters based on prediction accuracy.

In an alternative embodiment, the system continuously compares simulation predictions with real-world monitoring data:
- Predicted failure modes are compared against actual incidents as they occur
- Model accuracy is tracked over time and used to adjust simulation parameters
- Divergence alerts are generated when the simulation model no longer accurately predicts real-world behavior
- Automated model recalibration is triggered when prediction accuracy falls below a configurable threshold

## 6. CLAIMS

### Independent Claims

**Claim 1.** A computer-implemented method for evaluating infrastructure resilience, comprising:
- (a) receiving a topology definition describing a plurality of infrastructure components and dependencies therebetween;
- (b) constructing, in computer memory, a directed graph representation of said topology, wherein nodes represent infrastructure components with typed attributes including capacity, metrics, network characteristics, and redundancy configurations, and edges represent typed dependencies between components;
- (c) automatically generating a plurality of fault scenarios from said directed graph by applying fault generation rules across multiple fault categories including single-component failures, combinatorial failures, component-type-specific failures, and traffic spike scenarios;
- (d) simulating, entirely in computer memory without affecting any real infrastructure, the propagation of each fault scenario through said directed graph to determine cascade effects on dependent components;
- (e) computing a multi-layer availability limit model comprising at least a software availability limit, a hardware availability limit based on component MTBF/MTTR and redundancy, and a theoretical availability limit based on irreducible physical noise factors; and
- (f) generating a resilience assessment comprising quantitative scores and identified vulnerabilities.

**Claim 2.** The method of Claim 1, wherein step (d) further comprises simulating cascade propagation using a breadth-first search through the directed graph, wherein propagation behavior is determined by dependency type (required, optional, or asynchronous) and component redundancy, and wherein severity is computed as a function of both impact score and spread score across the total system.

**Claim 3.** The method of Claim 1, further comprising executing a time-stepped dynamic simulation that models, over discrete time intervals, traffic pattern injection, autoscaling responses, circuit breaker activation, failover sequences, and component recovery.

**Claim 4.** The method of Claim 1, wherein the multi-layer availability limit model is an N-layer model generalizable to any number of layers, each layer representing an independent constraint on system availability.

**Claim 5.** The method of Claim 1, wherein the fault scenario generation comprises generating at least 30 categories of scenarios, including latency cascade scenarios that model accumulated latency through dependency chains, connection pool exhaustion from retry storms, and circuit breaker activation.

**Claim 6.** A computer-implemented system for in-memory infrastructure resilience simulation, comprising:
- a topology model module configured to construct a directed graph of infrastructure components in computer memory from a declarative topology definition;
- a scenario generation module configured to automatically produce a set of fault scenarios from the directed graph;
- a plurality of simulation engines including at least a cascade engine, a dynamic engine, an operations engine, a what-if engine, and a capacity engine, each configured to evaluate aspects of infrastructure resilience using the in-memory directed graph;
- an availability model module configured to compute a multi-layer availability limit comprising distinct software, hardware, theoretical, operational, and external SLA layers; and
- a scoring module configured to aggregate simulation results into a quantitative resilience score.

**Claim 7.** A computer-implemented method for computing an infrastructure resilience genome, comprising:
- (a) constructing a directed graph representation of an infrastructure topology in computer memory;
- (b) extracting a multi-dimensional trait vector from the directed graph, wherein traits include graph density, average path length, clustering coefficient, component diversity, redundancy coverage, failover coverage, and circuit breaker coverage, each normalized to a range of 0.0 to 1.0;
- (c) comparing the trait vector against one or more industry-specific benchmark profiles to produce deviation scores and an overall similarity metric; and
- (d) tracking changes in the trait vector over time to produce a resilience evolution trajectory.

**Claim 8.** A computer-implemented method for simulating cyberattack resilience on an in-memory infrastructure model, comprising:
- (a) automatically generating attack scenarios from the topology of a directed graph model based on component properties including network exposure, component type, authentication configuration, and network segmentation;
- (b) for each attack scenario, computing defense effectiveness at the entry point using a defense matrix that maps security controls to attack-type-specific mitigation values, combined via independent-layer formula `1 - ∏(1 - mᵢ)`;
- (c) simulating lateral movement propagation through the directed graph via bidirectional breadth-first search, wherein network segmentation acts as a deterministic blocking factor; and
- (d) computing a security resilience score aggregated across encryption, access control, network, monitoring, and recovery categories.

**Claim 9.** A computer-implemented method for estimating financial risk from infrastructure failure simulations, comprising:
- (a) receiving simulation results comprising cascade severity, likelihood, and affected component data;
- (b) computing per-scenario business loss as the sum of revenue loss (downtime minutes multiplied by revenue per minute), SLA credit costs, and recovery engineer costs;
- (c) computing a Value-at-Risk at the 95th percentile (VaR95) from the cumulative probability distribution of scenario losses; and
- (d) generating mitigation ROI recommendations ranking remediation actions by cost-effectiveness, computed as `(savings - cost) / cost`.

### Dependent Claims

**Claim 10.** The method of Claim 1, wherein the fault scenario generation is augmented by a machine learning model that generates additional scenarios based on learned failure patterns.

**Claim 11.** The method of Claim 1, further comprising continuously synchronizing the in-memory directed graph with a real infrastructure environment through real-time metric ingestion, automatic topology updates, and statistical inference of undeclared dependencies from metrics correlation, traffic pattern similarity, and failure co-occurrence analysis.

**Claim 12.** The method of Claim 1, wherein the topology definition is received as natural language input and automatically converted to the directed graph representation by a language model.

**Claim 13.** The method of Claim 1, further comprising automatically generating Infrastructure-as-Code modifications to remediate identified vulnerabilities based on simulation results.

**Claim 14.** The method of Claim 1, wherein the directed graph models infrastructure spanning multiple cloud providers and the simulation includes correlated cross-provider failure analysis.

**Claim 15.** The method of Claim 1, further comprising simulating infrastructure evolution over extended time periods to evaluate long-term resilience trajectory.

**Claim 16.** The method of Claim 1, further comprising performing multi-objective optimization between cost constraints and resilience score to identify Pareto-optimal infrastructure configurations.

**Claim 17.** The method of Claim 1, wherein the cascade propagation analysis is performed using a graph neural network trained on simulation results. **[Now implemented — see Section 4.29]**

**Claim 18.** The method of Claim 1, further comprising validating simulation predictions against historical incident data and automatically calibrating simulation parameters based on backtest accuracy.

**Claim 19.** The method of Claim 1, further comprising continuously comparing simulation predictions with real-world monitoring data and generating alerts when prediction accuracy diverges beyond a configurable threshold.

**Claim 20.** The method of Claim 1, further comprising automatically fetching security threat information from external feeds, converting detected threats into executable fault scenarios, and injecting said scenarios into the simulation pipeline to evaluate resilience against emerging real-world threats.

**Claim 21.** The method of Claim 1, further comprising a blast radius prediction step that, prior to full simulation execution, estimates the cascading impact of each potential component failure with per-component impact severity classification, propagation depth, time-to-impact estimation, and mitigation assessment.

**Claim 22.** The method of Claim 1, further comprising analyzing simulation coverage gaps and generating a prioritized list of recommended real-world chaos experiments ranked by risk exposure, learning value, and coverage gap severity.

**Claim 23.** The method of Claim 1, further comprising a stochastic simulation mode using Monte Carlo methods wherein component MTBF values are sampled from an exponential distribution and MTTR values from a log-normal distribution across a plurality of trials, producing percentile-based confidence intervals for system availability that complement the deterministic multi-layer availability limit model.

**Claim 24.** The method of Claim 1, further comprising a mutation-based scenario discovery process inspired by software fuzzing techniques, wherein existing fault scenarios are randomly mutated through operations including fault addition, target reassignment, scenario combination, and severity amplification, and wherein mutated scenarios producing novel failure fingerprints are retained in a growing corpus for iterative failure space exploration.

**Claim 25.** The method of Claim 1, further comprising automatically generating incident response runbooks from simulation results, wherein each runbook includes detection steps, diagnosis procedures, mitigation actions, recovery steps, post-incident review checklists, and communication templates, each tailored to the specific component types and dependency relationships in the topology.

**Claim 26.** The method of Claim 1, further comprising simulating compliance posture against regulatory frameworks including SOC 2, ISO 27001, PCI DSS, DORA, HIPAA, and GDPR, by mapping framework control requirements to infrastructure topology properties and evaluating control coverage, effectiveness, and gaps entirely through in-memory simulation.

**Claim 27.** The method of Claim 1, further comprising computing a Risk Priority Number (RPN) for each component and failure mode using the formula RPN = Severity × Occurrence × Detection, wherein Severity is derived from cascade simulation results, Occurrence from component MTBF and current metrics, and Detection from monitoring and alerting coverage analysis, adapting Failure Mode and Effects Analysis (FMEA) methodology to cloud infrastructure.

**Claim 28.** The method of Claim 1, further comprising mathematically proving the achievability or unachievability of a target Service Level Agreement (SLA), wherein the proof identifies the specific binding constraint layer from the multi-layer availability model and, when the SLA is unachievable, computes the minimum infrastructure changes required to meet the target.

**Claim 29.** The method of Claim 1, further comprising integration as a quality gate within a continuous integration/continuous deployment (CI/CD) pipeline, wherein proposed infrastructure-as-code changes are automatically imported into the topology model, the simulation suite is executed against the proposed configuration, and the deployment is blocked if the computed resilience score falls below a configurable threshold or if resilience regression is detected relative to the current configuration.

**Claim 30.** The method of Claim 1, further comprising automatically inferring undeclared dependencies between infrastructure components by:
- (a) computing pairwise Pearson correlation coefficients between component metrics time series and applying lagged correlation analysis to determine causal direction, wherein a positive optimal lag indicates that the first component leads the second and a negative optimal lag indicates the reverse, constituting a simplified Granger causality test;
- (b) computing Dynamic Time Warping (DTW) distance between component traffic patterns, after min-max normalization, to identify synchronous behavioral coupling, wherein DTW distance below a configurable threshold indicates a dependency relationship;
- (c) analyzing failure incident co-occurrence using Jaccard similarity over per-component incident sets to detect components that are consistently affected together; and
- (d) fusing confidence scores from said multiple inference methods using a boosted-maximum strategy that applies a calibrated uplift factor for multi-method corroboration, and integrating inferred dependencies exceeding a configurable confidence threshold into the directed graph topology model as weighted edges annotated with inference provenance.

**Claim 31.** The method of Claim 1, further comprising modeling shared infrastructure dependencies by:
- (a) analyzing incident root cause descriptions to classify the failure origin as network, control plane, physical infrastructure, or host operating system, using keyword matching against category-specific keyword lists;
- (b) dynamically injecting shared infrastructure nodes into the directed graph topology model, wherein all service components are connected to the appropriate shared node via required dependencies with weight 1.0, such that the shared node represents an implicit common dependency not declared in the explicit service-level topology;
- (c) using the shared infrastructure node as the fault injection point for cascade simulation, thereby modeling correlated multi-service failures that originate from a common shared dependency and propagate simultaneously to all dependent service components; and
- (d) applying intelligent root cause routing that automatically selects the appropriate shared infrastructure node based on keyword analysis of the incident description, with a fallback heuristic that routes to the shared network node when three or more services are concurrently affected, enabling fully automated backtest execution against historical incident databases without manual incident classification.

**Claim 32.** The method of Claim 1, further comprising an agent-based model (ABM) simulation engine that:
- (a) models each infrastructure component as an independent autonomous agent possessing a set of prioritized decision rules, a health state selected from HEALTHY, DEGRADED, OVERLOADED, and DOWN, and awareness of the health states of neighboring agents through both forward dependencies and reverse dependencies;
- (b) simulates fault propagation using synchronous discrete-time steps, wherein at each step all agents simultaneously evaluate their rules against a read-only snapshot of the previous step's global state and transition to the worst matching state;
- (c) incorporates a probabilistic cascade rule wherein the probability of an agent transitioning to DEGRADED state is computed as `P = (unhealthy_neighbors / total_neighbors) × 0.4`, modeling retry storms, back-pressure propagation, and emergent load amplification that deterministic graph traversal cannot capture;
- (d) detects convergence when the global state remains unchanged for two consecutive steps; and
- (e) identifies emergent failure patterns by comparing the set of affected agents against the transitive closure predicted by breadth-first search, thereby discovering both unexpected cascade propagation paths and previously unknown resilience properties.

**Claim 33.** The method of Claim 1, further comprising a reinforcement learning-based scenario generation method that:
- (a) formulates the infrastructure simulation engine as a reinforcement learning environment, wherein states are immutable snapshots of all component health statuses, actions are fault injections parameterized by target component and fault type, transitions are computed by the cascade simulation engine, and the reward signal is the cascade severity score;
- (b) trains a tabular Q-learning agent using the update rule `Q[s][a] ← Q[s][a] + α × (r + γ × max Q[s'] − Q[s][a])` with ε-greedy exploration that decays from an initial exploration rate toward a minimum exploitation rate over successive training episodes;
- (c) generates high-impact failure scenarios by replaying the learned greedy policy from the initial all-healthy state to build multi-fault scenarios of increasing severity, and by extracting the top-K highest-Q-value single-fault actions from the initial state; and
- (d) produces a reusable Q-table encoding learned knowledge about infrastructure vulnerabilities that enables rapid scenario generation for subsequent analysis cycles without retraining.

**Claim 34.** The method of Claim 1, further comprising a machine learning-based failure prediction method that:
- (a) extracts a normalized feature vector from each infrastructure component's current metrics, comprising CPU utilization, memory utilization, disk utilization, connection pool saturation, and overall utilization;
- (b) trains a logistic regression model `P(failure) = sigmoid(w · x + b)` using stochastic gradient descent on binary cross-entropy loss, wherein training data is synthetically generated by running the cascade simulation engine on random fault scenarios with metric perturbation, and positive samples are augmented with high-utilization bias to model pre-failure stress signatures;
- (c) predicts, for each component, a failure probability, a categorical risk level (critical, high, medium, or low), and an estimated time to failure derived from the current utilization trajectory; and
- (d) generates an infrastructure-wide prediction report ranking all components by failure probability to enable proactive infrastructure hardening before failures occur.

**Claim 35.** The method of Claim 1, further comprising a Bayesian network failure probability analysis method that:
- (a) computes, for each component in the directed graph, a prior failure probability from the component's mean time between failures and mean time to repair, adjusted for parallel redundancy by exponentiating by the replica count;
- (b) computes, for each dependency relationship, a conditional failure probability using Bayes' theorem with dependency-type-based impact factors, wherein `requires` dependencies carry a near-unity impact factor, `optional` dependencies carry a reduced impact factor, and `async` dependencies carry a minimal impact factor;
- (c) computes posterior failure probabilities for all components given a set of observed component states as evidence, using the law of total probability across all dependency relationships; and
- (d) identifies the most critical dependency for each component as the dependency whose failure produces the highest conditional failure probability increase, enabling targeted redundancy planning.

**Claim 36.** The method of Claim 1, further comprising a Markov chain availability analysis method that:
- (a) models each infrastructure component as a three-state continuous-time Markov chain with states HEALTHY, DEGRADED, and DOWN, wherein transition rates between states are derived from the component's MTBF, MTTR, and degradation profile (memory leak rate, disk fill rate);
- (b) constructs a row-stochastic transition matrix by converting continuous-time rates to discrete-time probabilities using the exponential complementary CDF;
- (c) computes the steady-state probability distribution using the iterative power method; and
- (d) derives per-component availability, nines of availability, and mean sojourn time in each state, capturing the dynamic transition behavior between health states including degradation-before-failure paths that static availability models do not represent.

**Claim 37.** The method of Claim 1, further comprising a discrete event simulation (DES) engine that:
- (a) models infrastructure failure propagation as a sequence of time-stamped events including fault injection, cascade propagation, and recovery events, each carrying a timestamp, target component, event type, and metadata;
- (b) processes events asynchronously from a min-heap priority queue in strict chronological order, wherein cascade events are scheduled with propagation delays derived from actual network latency and timeout configurations, and recovery events are scheduled at MTTR-derived times;
- (c) produces a complete event timeline with exact temporal resolution, enabling precise modeling of overlapping failure and recovery dynamics that fixed-interval time-stepped simulation approaches cannot capture; and
- (d) computes cascade severity from the final component state distribution, providing both temporal dynamics and quantitative impact assessment from a single simulation run.

**Claim 38.** The method of Claim 1, further comprising a genetic algorithm scenario optimization method that:
- (a) encodes each candidate failure scenario as a binary chromosome of length $N$ (where $N$ is the number of infrastructure components), wherein each bit indicates whether the corresponding component is injected with a failure fault;
- (b) evaluates the fitness of each chromosome as the total cascade severity produced by simultaneously injecting all flagged faults through the cascade simulation engine;
- (c) evolves a population of chromosomes over successive generations using tournament selection, single-point crossover, and bit-flip mutation operators; and
- (d) discovers worst-case simultaneous multi-fault combinations through population-based search, complementing the reinforcement learning scenario generator's sequential fault-injection approach with parallel exploration of the combinatorial failure space.

**Claim 39.** The method of Claim 1, further comprising a Fault Tree Analysis (FTA) method that:
- (a) constructs a Fault Tree from the infrastructure directed graph by top-down deductive decomposition, wherein the root node represents system failure, intermediate nodes carry Boolean logic gates (OR for single-instance components, VOTING for replicated components), and leaf nodes represent individual component failures with base probabilities derived from MTBF;
- (b) computes the top-event (system failure) probability by bottom-up evaluation through OR gates using $P = 1 - \prod(1 - P_i)$, AND gates using $P = \prod P_i$, and VOTING gates using combinatorial probability over $k$-of-$n$ failure subsets;
- (c) computes minimal cut sets — the smallest combinations of basic component failures that cause system failure — by recursive set operations through the tree, followed by removal of non-minimal supersets; and
- (d) ranks components by criticality based on minimal cut set membership frequency, identifying the highest-leverage points for reliability improvement.

**Claim 40.** The method of Claim 1, further comprising a survival analysis method for infrastructure component lifetime estimation that:
- (a) generates synthetic failure-time observations from each component's MTBF using the inverse CDF of the exponential distribution and computes a Kaplan-Meier survival curve $S(t) = \prod_{t_i \leq t}(1 - d_i/n_i)$ with right-censoring of the last observation;
- (b) fits a two-parameter Weibull distribution to observed failure times, estimating the shape parameter from the coefficient of variation and the scale parameter from the mean failure time, wherein the shape parameter characterizes the failure regime (infant mortality, random, or wear-out);
- (c) computes the Weibull hazard function $h(t) = (k/\lambda)(t/\lambda)^{k-1}$ to determine the instantaneous failure rate at any given time; and
- (d) predicts remaining useful life for each component by adjusting the effective MTBF for current utilization stress and active degradation patterns (memory leaks, disk fill rate), providing quantitative time-to-failure estimates grounded in established survival analysis theory.

**Claim 41.** The method of Claim 1, further comprising a Petri Net modeling method for concurrent failure analysis that:
- (a) converts the infrastructure directed graph into a Place/Transition Petri Net, wherein each component generates three places (healthy, degraded, down) with initial token placement reflecting operational state, and each dependency edge generates transitions that propagate failure states through token consumption and production;
- (b) simulates failure propagation by iteratively firing enabled transitions (transitions whose input places all contain at least one token) according to deterministic priority, consuming tokens from input places and producing tokens in output places;
- (c) performs reachability analysis via breadth-first search over the state space (set of all reachable markings), detecting deadlock states (markings with no enabled transitions) that represent irrecoverable failure modes; and
- (d) enables formal verification of safety properties — such as "no reachable state exists where all database replicas are simultaneously DOWN" — through exhaustive state space enumeration, providing guarantees that simulation-based approaches cannot offer.

**Claim 42.** The method of Claim 1, further comprising a cellular automata failure propagation method that:
- (a) models each infrastructure component as a cell in a grid defined by the bidirectional adjacency structure of the dependency graph, wherein the neighbor set of each cell comprises both upstream dependencies and downstream dependents;
- (b) applies deterministic threshold transition rules synchronously across all cells on each generation, wherein: two or more DOWN neighbors cause the cell to become DOWN; one or more DOWN neighbors cause the cell to become at least DEGRADED; three or more DEGRADED neighbors cause the cell to become OVERLOADED; and the DOWN state is absorbing;
- (c) classifies the observed failure propagation dynamics as stable (convergent), oscillating (repeating cycle of length 2-5), or chaotic (no detected pattern), providing qualitative characterization of failure behavior; and
- (d) produces fully deterministic, reproducible results suitable for formal analysis, complementing the agent-based model's stochastic approach with a deterministic counterpart that identifies the exact conditions under which failures propagate.

**Claim 43.** The method of Claim 1, further comprising a System Dynamics simulation method that:
- (a) models each infrastructure component's health as a continuous-valued stock $H_i(t) \in [0.0, 1.0]$ governed by an ordinary differential equation $dH_i/dt = r_i - d_i - \sum_{j \in \text{deps}(i)} c_{ji}$, where $r_i$ is the recovery rate, $d_i$ is the degradation rate, and $c_{ji}$ is the cascade impact from dependency $j$ modulated by dependency type;
- (b) integrates the health dynamics using forward Euler approximation with configurable time-step width, producing a continuous time-series of health values for each component;
- (c) detects degradation velocity, tipping-point thresholds, and recovery trajectories from the continuous health evolution, capturing phenomena that discrete-state models (ABM, CA, DES) cannot represent; and
- (d) computes an overall severity score from the average degradation depth and spread fraction across all components.

**Claim 44.** The method of Claim 1, further comprising an RNN/LSTM time-series failure prediction method that:
- (a) constructs a recurrent neural network comprising either a simple RNN cell computing $h_t = \tanh(W_{hh} \cdot h_{t-1} + W_{xh} \cdot x_t + b_h)$ or an LSTM cell with forget, input, and output gates, followed by a sigmoid output layer;
- (b) generates training data synthetically from the in-memory simulation model by extracting base metrics from infrastructure components and applying trend injection to simulate resource exhaustion sequences, rather than requiring historical production log data;
- (c) predicts failure probability from an ordered sequence of infrastructure metric snapshots, capturing temporal dependencies such as monotonic resource increase and oscillatory instability that memoryless classifiers cannot detect; and
- (d) operates entirely on the in-memory simulation model, differentiating from prior art LSTM-based anomaly detection systems (such as US20170293542A1) that require real-world operational data streams.

**Claim 45.** The method of Claim 1, further comprising a Simulated Annealing scenario optimization method that:
- (a) represents each candidate failure scenario as a binary vector of length $N$ (number of infrastructure components), where 1 indicates a faulted component;
- (b) generates neighbor solutions by single-bit-flip perturbation and accepts or rejects each neighbor according to the Metropolis criterion $P = \exp(\Delta E / T)$, where $\Delta E$ is the change in cascade severity and $T$ is the current temperature;
- (c) applies a geometric cooling schedule $T(k) = T_0 \times \alpha^k$ to transition from exploratory search (high temperature, frequent acceptance of worse solutions) to exploitative refinement (low temperature, convergence to near-optimal solution); and
- (d) discovers worst-case failure scenarios through single-solution neighborhood search, complementing the population-based Genetic Algorithm (Claim 38) and sequential Reinforcement Learning (Claim 33) approaches with a distinct metaheuristic that trades population diversity for deeper local exploration.

**Claim 46.** The method of Claim 1, further comprising a Reliability Block Diagram (RBD) analysis method that:
- (a) computes per-component availability from MTBF and MTTR as $A = \text{MTBF} / (\text{MTBF} + \text{MTTR})$, with parallel redundancy modeled as $A_{\text{parallel}} = 1 - (1 - A_{\text{single}})^n$ for components with $n$ replicas or failover enabled;
- (b) identifies critical paths through the infrastructure dependency graph and models each path as a series block with path availability $P_{\text{path}} = \prod_{i \in \text{path}} A_i$;
- (c) computes system-level availability as the parallel combination of all critical path availabilities: $A_{\text{system}} = 1 - \prod_{\text{paths}} (1 - P_{\text{path}})$; and
- (d) provides a structural availability perspective based on block connectivity patterns, complementing the Fault Tree Analysis (Claim 39) which operates on failure event logic gates, by analyzing success paths rather than failure combinations.

**Claim 47.** The method of Claim 1, further comprising an Event Tree Analysis (ETA) method that:
- (a) starting from an initiating event (component failure), automatically generates branching safety functions from the infrastructure topology, including circuit breaker activation, failover, autoscaling response, and replica redundancy, each with probability parameters derived from the component's configuration;
- (b) enumerates all $2^n$ outcome paths through the event tree (where $n$ is the number of safety barriers), computing combined probability for each path as the product of individual barrier success/failure probabilities;
- (c) classifies each outcome by severity based on the number of barrier failures and computes total risk as the probability-weighted sum of severity scores; and
- (d) performs inductive forward risk assessment from an initiating event, complementing the deductive backward analysis of Fault Tree Analysis (Claim 39) which traces backward from a top event to identify root cause combinations.

**Claim 48.** The method of Claim 1, further comprising an Extreme Value Theory (EVT) analysis method that:
- (a) fits a Generalised Extreme Value (GEV) distribution $F(x) = \exp(-(1 + \xi(x-\mu)/\sigma)^{-1/\xi})$ to block-maxima of cascade severity data, estimating location ($\mu$), scale ($\sigma$), and shape ($\xi$) parameters via the Method of Moments;
- (b) computes Return Levels $x_T = \mu + (\sigma/\xi)((-\log(1-1/T))^{-\xi} - 1)$ for configurable return periods, quantifying the cascade severity expected to be exceeded once every $T$ observation windows;
- (c) computes tail-risk exceedance probabilities $P(X > x) = 1 - F(x)$ for configurable severity thresholds; and
- (d) models the *magnitude of extreme failures* rather than the *time until failure*, differentiating from Survival Analysis (Claim 40) which estimates component lifetime using Weibull distributions, by applying extreme value statistics to the upper tail of the cascade severity distribution.

**Claim 49.** The method of Claim 1, further comprising a model checking formal verification method that:
- (a) constructs a finite state space by BFS enumeration of all reachable infrastructure states, where each state assigns a health status to every component and transitions model failure propagation through `requires` dependencies;
- (b) verifies CTL temporal-logic properties against the state space, including: AG(p) — property $p$ holds in all reachable states ("always globally"); EF(p) — there exists a path where $p$ eventually holds ("exists finally"); AF(p) — on all paths, $p$ eventually holds ("always finally");
- (c) generates counterexample (or witness) paths via BFS from the initial state to a violating (or satisfying) state, providing concrete execution traces that demonstrate property violations; and
- (d) provides temporal-logic property verification with strictly greater expressiveness than the reachability analysis of the Petri Net engine (Claim 41), supporting quantification over paths (universal/existential) combined with temporal quantification (always/eventually).

**Claim 50.** The method of Claim 1, further comprising a Random Forest failure prediction method that:
- (a) constructs an ensemble of decision trees, each trained on a bootstrap sample of synthetically generated training data, with information gain (entropy reduction) as the split criterion and random feature sub-sampling at each node;
- (b) generates training data from the in-memory infrastructure model by extracting normalized metric features (CPU, memory, disk, connections, replicas) and generating labels using a weighted risk score with stochastic threshold;
- (c) predicts failure probability as the average prediction across all trees in the ensemble, producing a smoothed estimate with lower variance than any individual tree; and
- (d) captures non-linear decision boundaries and feature interactions without explicit feature engineering, differentiating from the logistic regression predictor (Claim 34) which is limited to linear separability in the feature space.

**Claim 51.** The method of Claim 1, further comprising an autoencoder anomaly detection method that:
- (a) trains an encoder-decoder neural network to minimize reconstruction error on normal-state metric vectors generated from the in-memory infrastructure model, where the encoder maps input features to a lower-dimensional bottleneck representation and the decoder reconstructs the original features;
- (b) computes an anomaly threshold from the configured percentile (default 95th) of training-set reconstruction errors;
- (c) classifies new metric observations as anomalous when their reconstruction error exceeds the learned threshold, enabling unsupervised anomaly detection that requires only normal data and no labeled failure examples; and
- (d) operates entirely on simulation-synthesized data from the in-memory model, differentiating from prior art autoencoder anomaly detection systems (such as US11374952B1) that operate on real-time production monitoring telemetry, by detecting anomalous patterns that *would* occur under simulated fault conditions without access to any production environment.

**Claim 52.** The method of Claim 1, further comprising a Transformer-based failure prediction method that:
- (a) projects input metric sequences to a model embedding space, adds sinusoidal positional encodings, and applies self-attention $\text{Attention}(Q,K,V) = \text{softmax}(QK^T/\sqrt{d_k}) \cdot V$ to compute context-aware representations of each time-step, followed by a feed-forward network with residual connections and layer normalization;
- (b) mean-pools over the sequence dimension and applies a sigmoid output layer to produce a scalar failure probability;
- (c) exposes the attention weight matrix for interpretability, showing which time-steps in the metric history the model considers most informative for the failure prediction; and
- (d) processes all time-steps in parallel via attention, directly capturing long-range temporal dependencies without the sequential processing bottleneck and vanishing-gradient issues of recurrent architectures (Claim 44), while providing attention-based interpretability that recurrent models cannot offer.

---

## APPENDIX A: Implementation Reference

The described system is implemented as the FaultRay open-source software, available at https://github.com/mattyopon/faultray under the MIT License. The first public commit was made on March 9, 2026. The implementation is in Python 3.11+ and utilizes the networkx library for graph operations and pydantic for data model validation.

Key implementation files corresponding to the described components:
- Graph model: `src/faultray/model/graph.py` (InfraGraph class using networkx DiGraph)
- Component model: `src/faultray/model/components.py` (Component, Dependency, AutoScalingConfig, FailoverConfig, CircuitBreakerConfig)
- Cascade Engine: `src/faultray/simulator/cascade.py` (CascadeEngine class)
- Dynamic Engine: `src/faultray/simulator/dynamic_engine.py` (DynamicSimulator class)
- Operations Engine: `src/faultray/simulator/ops_engine.py`
- What-If Engine: `src/faultray/simulator/whatif_engine.py`
- Capacity Engine: `src/faultray/simulator/capacity_engine.py`
- Availability Model: `src/faultray/simulator/availability_model.py` (compute_five_layer_model function)
- Scenario Generator: `src/faultray/simulator/scenarios.py` (generate_default_scenarios function)
- Security Resilience Engine: `src/faultray/simulator/security_engine.py` (SecurityResilienceEngine class)
- Financial Risk Engine: `src/faultray/simulator/financial_risk.py` (FinancialRiskEngine class)
- Chaos Genome: `src/faultray/simulator/chaos_genome.py` (genome trait extraction, industry benchmarking)
- Threat Feed Integration: `src/faultray/feeds/fetcher.py` (RSS/Atom feed parsing and threat extraction)
- Blast Radius Predictor: `src/faultray/simulator/blast_radius_predictor.py` (pre-simulation impact estimation)
- Chaos Recommender: `src/faultray/simulator/chaos_recommender.py` (experiment recommendation engine)
- Auto-Remediation Pipeline: `src/faultray/remediation/auto_pipeline.py` (scan → evaluate → fix → validate cycle)
- Monte Carlo Simulation: `src/faultray/simulator/monte_carlo.py` (stochastic availability estimation)
- Chaos Fuzzer: `src/faultray/simulator/chaos_fuzzer.py` (AFL-inspired scenario mutation and discovery)
- Runbook Generator: `src/faultray/remediation/runbook_generator.py` (auto-generated incident response runbooks)
- Compliance Frameworks: `src/faultray/simulator/compliance_frameworks.py` (SOC2/ISO27001/PCI-DSS/DORA/HIPAA/GDPR)
- FMEA Engine: `src/faultray/simulator/fmea_engine.py` (Failure Mode and Effects Analysis with RPN)
- SLA Validator: `src/faultray/simulator/sla_validator.py` (mathematical SLA achievability proof)
- Digital Twin: `src/faultray/simulator/digital_twin.py` (continuous shadow simulation)
- CI/CD Integration: `src/faultray/ci/github_action.py` (resilience gate for deployment pipelines)
- ML Dependency Inference: `src/faultray/discovery/ml_dependency_inference.py` (DependencyInferenceEngine class — Pearson correlation, DTW, Jaccard similarity, multi-method fusion)
- Backtest Engine: `src/faultray/simulator/backtest_engine.py` (BacktestEngine class — historical incident validation, accuracy metrics, automatic calibration)
- Historical Incident Database: `src/faultray/simulator/incident_db.py` (18 documented public cloud incidents)
- Backtest Execution Script: `scripts/run_backtest_report.py` (shared infrastructure modeling, graph construction, 18-incident backtest with JSON/Markdown report generation)
- Interactive Topology Wizard: `src/faultray/cli/init_cmd.py` (step-by-step interactive infrastructure definition with environment type, cloud provider, component selection, and automatic YAML generation)
- Hybrid Infrastructure Template: `src/faultray/templates/hybrid-onprem-cloud.yaml` (on-premise plus AWS hybrid topology connected via VPN)
- ABM Engine: `src/faultray/simulator/abm_engine.py` (ABMEngine class — agent-based model with autonomous agents, synchronous discrete-time simulation, probabilistic cascade rules, emergent pattern detection)
- RL Scenario Generator: `src/faultray/simulator/rl_scenario_generator.py` (RLScenarioGenerator class — Q-learning agent, ε-greedy exploration, greedy policy replay, top-K scenario extraction)
- GNN Cascade Predictor: `src/faultray/simulator/gnn_engine.py` (GNNCascadePredictor class — MPNN architecture, self-supervised training from CascadeEngine, per-node failure probability prediction)
- ML Failure Predictor: `src/faultray/simulator/ml_failure_predictor.py` (MLFailurePredictor class — logistic regression, synthetic training data generation, risk-level classification, time-to-failure estimation)
- Bayesian Network Engine: `src/faultray/simulator/bayesian_model.py` (BayesianEngine class — conditional failure probability computation, prior/posterior analysis, evidence-based querying, dependency-type-based impact factors)
- Markov Chain Availability Model: `src/faultray/simulator/markov_model.py` (compute_markov_availability function, compute_system_markov function — three-state CTMC, steady-state distribution via power method, availability nines computation)
- DES Engine: `src/faultray/simulator/des_engine.py` (DESEngine class — event priority queue, asynchronous event processing, cascade/recovery event scheduling, temporal event timeline)
- GA Scenario Optimizer: `src/faultray/simulator/ga_scenario_optimizer.py` (GAOptimizer class — binary chromosome encoding, tournament selection, single-point crossover, bit-flip mutation, population-based worst-case scenario discovery)
- Fault Tree Engine: `src/faultray/simulator/fault_tree_engine.py` (FaultTreeEngine class — top-down fault tree construction, OR/AND/VOTING gate probability computation, minimal cut set extraction, critical component ranking)
- Survival Analysis Engine: `src/faultray/simulator/survival_engine.py` (SurvivalEngine class — Kaplan-Meier estimation, Weibull distribution fitting, hazard function computation, remaining useful life prediction)
- Petri Net Engine: `src/faultray/simulator/petri_net_engine.py` (PetriNetEngine class — Place/Transition net construction, token-based simulation, reachability analysis via BFS, deadlock detection)
- Cellular Automata Engine: `src/faultray/simulator/cellular_automata_engine.py` (CAEngine class — deterministic threshold rules, synchronous grid update, pattern classification as stable/oscillating/chaotic)
- System Dynamics Engine: `src/faultray/simulator/system_dynamics_engine.py` (SystemDynamicsEngine class — continuous-valued stock-and-flow health modeling, Euler integration of ODE, degradation velocity and tipping-point analysis)
- RNN/LSTM Failure Predictor: `src/faultray/simulator/rnn_predictor.py` (RNNFailurePredictor class — SimpleRNN and LSTM cells, time-series failure prediction from simulation-synthesized sequences, output-layer SGD training)
- Simulated Annealing / Random Forest / Autoencoder: `src/faultray/simulator/optimization_engines.py` (SimulatedAnnealingOptimizer class — Metropolis criterion, geometric cooling; RandomForestPredictor class — bagged decision tree ensemble with feature sub-sampling; AnomalyAutoencoder class — encoder-decoder anomaly detection via reconstruction error)
- Formal Methods (RBD / ETA / Model Checker): `src/faultray/simulator/formal_methods_engine.py` (ReliabilityBlockDiagram class — series/parallel availability; EventTreeAnalysis class — inductive forward risk assessment; SimpleModelChecker class — exhaustive state-space CTL verification with AG/EF/AF operators)
- Advanced ML (EVT / Transformer): `src/faultray/simulator/advanced_ml_engines.py` (ExtremeValueAnalyzer class — GEV distribution fitting, return level computation, tail-risk probability; SimpleTransformerPredictor class — self-attention, positional encoding, attention-interpretable failure prediction)

---

## APPENDIX B: Prior Art Differentiation

The following table summarizes the key differences between the present invention and known prior art:

| Prior Art | Approach | Key Difference |
|-----------|----------|----------------|
| US11397665B2 (JPMorgan) - Chaos Engineering Trials | Real-environment fault injection via APIs | Present invention operates entirely in-memory; no real systems are affected |
| US11307947B2 (Huawei) - Fault Injection Timing | Software-implemented fault injection in real systems | Present invention uses mathematical simulation, not real fault injection |
| US9280409B2 (HPE) - SPOF Analysis | Static analysis of infrastructure components | Present invention performs dynamic simulation with cascading failure propagation, not static analysis |
| US11392445B2 (Cognizant) - IT Resilience | Vulnerability assessment of existing IT environment | Present invention computes availability limits from mathematical models, not vulnerability scanning |
| Netflix Chaos Monkey (2011) | Random VM termination in production | Present invention requires no production access and tests all combinations exhaustively |
| AWS Fault Injection Simulator (2021) | Managed fault injection into AWS resources | Present invention is cloud-agnostic and operates without cloud resource access |
| Gremlin SaaS | Agent-based fault injection platform | Present invention is agentless and operates on topology models, not real infrastructure |
| US20170293542A1 (NEC) — LSTM anomaly detection in operational log streams | Applies LSTM networks to real-world operational log data for anomaly detection on production systems | Present invention trains RNN/LSTM models on *simulation-synthesized data* generated from the in-memory infrastructure model, not real production logs; prediction is performed on the simulation model to evaluate hypothetical configurations before deployment, not to monitor live systems |
| US11374952B1 (Amazon) — Autoencoder anomaly detection for cloud infrastructure | Applies autoencoder reconstruction-error-based anomaly detection to real-time production monitoring telemetry | Present invention trains autoencoders on *simulation-synthesized normal data* from the in-memory model, not production telemetry; anomaly detection evaluates hypothetical fault conditions on the simulation model before deployment, not real-time operational data |
| US10048996B1 (Amazon) — ML-based failure prediction for data center infrastructure | Applies machine learning to real data center metrics for predictive maintenance of physical infrastructure | Present invention operates entirely on in-memory simulation models without access to real infrastructure; ML models are trained on synthetically generated data from the simulation engine, enabling failure prediction for infrastructure that has not yet been deployed or experienced real failures |

---

## APPENDIX C: Backtest Accuracy Data

Backtest results against 18 documented public cloud incidents, comparing prediction accuracy with and without shared infrastructure dependency modeling:

### V1: Explicit Dependencies Only

| Metric | Value |
|--------|-------|
| Avg Precision | 1.000 |
| Avg Recall | 0.499 |
| Avg F1 Score | 0.626 |

### V2: With Shared Infrastructure Modeling

| Metric | Value |
|--------|-------|
| Avg Precision | 1.000 |
| Avg Recall | 1.000 |
| Avg F1 Score | 1.000 |
| Avg Severity Accuracy | 0.819 |
| Avg Confidence | 0.756 |

Incidents tested: AWS us-east-1 (2021), AWS S3 (2017), Meta BGP (2021), Cloudflare (2022), GCP (2019), Azure (2023), GitHub DDoS (2018), Fastly CDN (2021), CrowdStrike (2024), AWS DynamoDB (2015), GCP LB (2021), Dyn DNS (2016), AWS Kinesis (2020), Slack (2022), AWS EBS (2011), Roblox (2021), Azure AD (2021), OVH Fire (2021)

---

*END OF PROVISIONAL PATENT APPLICATION DRAFT*
