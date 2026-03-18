# Reddit Post — r/devops

---

## Title Options

1. **Added pre-deploy resilience checking to our CI pipeline — open source tool, curious if others do this**

2. **Our CI now blocks deploys that would introduce single points of failure — here's how**

3. **Tool: gate your infrastructure deploys on a resilience score (GitHub Action, free/OSS)**

Recommended: **#2** — specific outcome, tells a story, doesn't lead with "I built a thing."

---

## Body Text

Hey r/devops,

We added a step to our CI pipeline that runs resilience simulation against every infrastructure change before it gets merged. If the change introduces a critical single point of failure or drops the resilience score below our threshold, the PR fails. Wanted to share what we're using and see if others have solved this problem differently.

**The gap in standard CI**

Most CI pipelines validate infrastructure changes for:
- Syntax / formatting (`terraform validate`, `tflint`)
- Security (`tfsec`, `checkov`)
- Cost (`infracost`)

None of those tell you what happens to your system's failure behavior. A change can be syntactically valid, pass all security checks, be cost-neutral, and still introduce a single point of failure that will take you down at 3am.

**What we added**

We use FaultRay — open source, `pip install faultray`, no agents or cloud access required. It reads your terraform/IaC files, builds a dependency graph, simulates 2,000+ failure scenarios in memory, and outputs a resilience score + detailed breakdown.

GitHub Action setup:

```yaml
name: Resilience Check

on:
  pull_request:
    paths:
      - 'terraform/**'
      - 'k8s/**'

jobs:
  resilience:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install FaultRay
        run: pip install faultray

      - name: Import infrastructure model
        run: faultray tf-import --dir ./terraform --output model.json

      - name: Run simulation
        run: faultray simulate -m model.json --json > results.json

      - name: Enforce resilience threshold
        run: faultray evaluate -m model.json --threshold 70

      - name: Upload report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: resilience-report
          path: report.html
```

Exit code 2 = critical findings, exit code 3 = below threshold. Both block the pipeline.

There's also an official GitHub Action on the marketplace (`mattyopon/faultray`) if you want the simpler setup:

```yaml
- uses: mattyopon/faultray@v1
  with:
    yaml-file: ./terraform/infra.yaml
    comment-on-pr: true
```

That one comments the resilience score directly on the PR.

**What it actually catches**

- New single points of failure introduced by the change
- Cascade paths (component A goes down → takes B and C with it)
- Replicas being removed or consolidated
- Changes that lower the theoretical availability ceiling
- Dependency ordering issues that create downtime windows during apply

It does not catch:
- Application-level bugs under failure
- Real timing and race conditions
- Anything requiring actual runtime observation

This is pre-deploy structural analysis, not runtime chaos testing. For real chaos testing you still want AWS FIS / Gremlin in staging.

**Performance**

Simulation runs in 2-4 seconds for most infrastructure models. Adds negligible time to CI.

**Installation / links**

```bash
pip install faultray
faultray demo    # try it on a sample infrastructure
```

GitHub: https://github.com/mattyopon/faultray
PyPI: https://pypi.org/project/faultray/

Free and open source (BSL 1.1, converts to Apache 2.0 in 2030).

---

Curious how others are handling this gap in their pipelines. Do you do any structural resilience validation before deploy? If so, what tooling?
