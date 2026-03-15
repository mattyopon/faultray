# Risk Scoring

FaultZero calculates a resilience score from 0 to 100 based on multiple weighted factors. This page explains the scoring algorithm and how to interpret results.

## Score Breakdown

The overall resilience score is a weighted combination of four sub-scores:

| Factor | Weight | Description |
|--------|--------|-------------|
| SPOF Score | 30% | Penalty for single points of failure |
| Cascade Score | 25% | Risk of cascading failures |
| Redundancy Score | 25% | Coverage of redundant paths |
| Geographic Score | 20% | Distribution across regions/AZs |

## SPOF Score (30%)

Single Points of Failure receive the highest weight because they represent the most critical risk.

```
spof_score = 100 - (spof_count * spof_severity_weight)
```

Each SPOF is weighted by its position in the dependency graph:

- **Root-level SPOF** (e.g., single database): -30 points
- **Mid-tier SPOF** (e.g., single app server behind LB): -15 points
- **Edge SPOF** (e.g., single CDN origin): -10 points

## Cascade Score (25%)

Evaluates how far failures propagate through the dependency graph.

```
cascade_score = 100 - (max_cascade_depth / total_depth * 100)
```

A cascade depth of 1 (isolated failure) is ideal. A cascade that reaches all layers indicates severe architectural risk.

## Redundancy Score (25%)

Measures the percentage of components that have redundant alternatives.

```
redundancy_score = (redundant_components / total_components) * 100
```

Components are considered redundant if they have:

- Active-active or active-passive failover peers
- Auto-scaling groups with min instances > 1
- Cross-region replicas

## Geographic Score (20%)

Evaluates distribution across failure domains (regions and availability zones).

```
geo_score = (unique_azs / recommended_azs) * 100
```

Best practice is a minimum of 3 AZs for production workloads.

## Score Interpretation

| Score | Grade | Action Required |
|-------|-------|-----------------|
| 90-100 | A | Production-ready. Monitor and maintain. |
| 80-89 | B | Good. Address minor improvements. |
| 60-79 | C | Fair. Plan remediation for identified risks. |
| 40-59 | D | Poor. Immediate attention required. |
| 0-39 | F | Critical. Do not deploy without remediation. |

## Customizing Weights

Override default weights in your configuration:

```yaml
scoring:
  weights:
    spof: 0.35
    cascade: 0.25
    redundancy: 0.25
    geographic: 0.15
```

```bash
faultzero simulate -m model.json --scoring-config scoring.yaml
```
