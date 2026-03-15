# Insurance Scoring

FaultZero provides insurance-grade risk scoring that quantifies infrastructure risk for cyber insurance underwriting and premium optimization.

## Overview

The insurance scoring module translates FaultZero resilience assessments into standardized risk metrics used by cyber insurance underwriters. Organizations can use these scores to negotiate lower premiums by demonstrating quantified resilience.

## Insurance Score

The insurance score extends the base resilience score with additional risk factors:

```bash
faultzero simulate -m model.json --insurance --output insurance-report.json
```

### Score Components

| Factor | Weight | Description |
|--------|--------|-------------|
| Infrastructure Resilience | 40% | Base FaultZero resilience score |
| Recovery Capability | 20% | RTO/RPO achievability |
| Blast Radius | 15% | Maximum impact of single failure |
| Compliance Posture | 15% | Regulatory framework coverage |
| Historical Incidents | 10% | Past incident frequency and severity |

## Risk Categories

| Score Range | Risk Category | Premium Impact |
|-------------|---------------|----------------|
| 90-100 | Excellent | Up to 30% discount |
| 75-89 | Good | Up to 15% discount |
| 60-74 | Moderate | Standard premium |
| 40-59 | Elevated | Up to 20% surcharge |
| 0-39 | High | Up to 50% surcharge or coverage denial |

## Generating Insurance Reports

```python
from infrasim import SimulationEngine
from infrasim.insurance import InsuranceScorer

engine = SimulationEngine(graph)
results = engine.simulate()

scorer = InsuranceScorer(results)
insurance_report = scorer.generate()

print(f"Insurance Score: {insurance_report.score}")
print(f"Risk Category: {insurance_report.risk_category}")
print(f"Estimated Premium Impact: {insurance_report.premium_impact}")
```

## Report Output

The insurance report includes:

1. **Risk Score Summary** — Overall score with category assignment
2. **Component Risk Analysis** — Per-component risk breakdown
3. **Scenario Coverage** — Which disaster scenarios are covered
4. **Recovery Assessment** — RTO/RPO analysis for critical systems
5. **Recommendations** — Actions to improve insurance scoring

## Integration with Insurance Platforms

FaultZero provides API endpoints for insurance platform integration:

```http
POST /api/v1/insurance/evaluate
Content-Type: application/json

{
  "model_id": "abc123",
  "include_historical": true
}
```
