# CI/CD Integration

FaultZero integrates into your CI/CD pipeline to gate deployments on infrastructure resilience.

## GitHub Actions

```yaml
name: Resilience Check

on:
  pull_request:
    paths:
      - 'terraform/**'
      - 'k8s/**'

jobs:
  faultzero:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install FaultZero
        run: pip install faultzero

      - name: Import infrastructure model
        run: faultzero tf-import --dir ./terraform --output model.json

      - name: Run simulation
        run: faultzero simulate -m model.json --json > results.json

      - name: Check threshold
        run: faultzero evaluate -m model.json --threshold 70

      - name: Generate report
        if: always()
        run: faultzero report -m model.json -o report.html

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: resilience-report
          path: report.html
```

## GitLab CI

```yaml
resilience-check:
  image: python:3.12
  stage: test
  script:
    - pip install faultzero
    - faultzero tf-import --dir ./terraform --output model.json
    - faultzero simulate -m model.json --json > results.json
    - faultzero evaluate -m model.json --threshold 70
  artifacts:
    paths:
      - results.json
    when: always
```

## Jenkins

```groovy
pipeline {
    agent any
    stages {
        stage('Resilience Check') {
            steps {
                sh 'pip install faultzero'
                sh 'faultzero tf-import --dir ./terraform --output model.json'
                sh 'faultzero simulate -m model.json --json > results.json'
                sh 'faultzero evaluate -m model.json --threshold 70'
            }
            post {
                always {
                    archiveArtifacts artifacts: 'results.json'
                }
            }
        }
    }
}
```

## Exit Codes for CI/CD

FaultZero uses exit codes to signal pipeline outcomes:

| Exit Code | Meaning | CI/CD Action |
|-----------|---------|--------------|
| 0 | All checks passed | Continue pipeline |
| 2 | Critical issues found | Block deployment |
| 3 | Score below threshold | Block deployment |

## Best Practices

1. **Set a minimum threshold** — Use `--threshold 70` to enforce a minimum resilience score.
2. **Run on infrastructure changes** — Trigger only when Terraform, Kubernetes, or IaC files change.
3. **Archive reports** — Always save HTML reports as artifacts for post-merge review.
4. **Compare before/after** — Use `faultzero diff` to catch resilience regressions in PRs.
