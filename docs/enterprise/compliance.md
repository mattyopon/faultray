# Compliance

FaultZero provides compliance mapping and reporting for regulatory frameworks, helping organizations demonstrate infrastructure resilience to auditors.

## Supported Frameworks

| Framework | Coverage | Details |
|-----------|----------|---------|
| SOC 2 Type II | Availability criteria | A1.1, A1.2, A1.3 (system availability, recovery, backup) |
| ISO 27001 | Annex A controls | A.17 (business continuity), A.12 (operations security) |
| NIST CSF | Identify, Protect, Recover | ID.AM, PR.DS, RC.RP categories |
| PCI DSS | Requirement 12.10 | Incident response and business continuity |
| HIPAA | Technical safeguards | Contingency plan, data backup, disaster recovery |
| FedRAMP | Control families | CP (Contingency Planning), SC (System & Communications) |

## Generating Compliance Reports

```bash
faultzero simulate -m model.json --compliance soc2 --output compliance-report.html
```

### Multiple frameworks

```bash
faultzero simulate -m model.json --compliance soc2,iso27001,nist --output report.html
```

## Report Contents

Each compliance report includes:

1. **Control Mapping** — Maps resilience findings to specific compliance controls
2. **Evidence** — Simulation results as evidence of resilience testing
3. **Gap Analysis** — Identifies controls not satisfied by current architecture
4. **Recommendations** — Specific infrastructure changes to close compliance gaps
5. **Audit Trail** — Timestamped record of all simulation runs

## Example: SOC 2 Type II

```python
from infrasim import SimulationEngine
from infrasim.compliance import SOC2Reporter

engine = SimulationEngine(graph)
results = engine.simulate()

reporter = SOC2Reporter(results)
report = reporter.generate()

# Check specific criteria
assert report.a1_1_satisfied  # System availability commitments
assert report.a1_2_satisfied  # Recovery objectives
```

## Continuous Compliance

Integrate compliance checks into your CI/CD pipeline to maintain continuous compliance:

```bash
faultzero evaluate -m model.json --compliance soc2 --threshold 80
```

This ensures every infrastructure change meets compliance requirements before deployment.
