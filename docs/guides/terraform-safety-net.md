# Using FaultRay as a Terraform Safety Net

Every team that uses Terraform has experienced some version of this: someone runs `terraform apply`, the plan looks fine, and twenty minutes later the on-call alert fires. The resource that was changed had a subtle configuration that introduced a single point of failure — `multi_az = false`, `desired_count = 1`, a security group open to the world — and nobody noticed during review because the Terraform diff only shows *what changed*, not *what the consequences are*.

FaultRay closes that gap. It reads your Terraform plan, builds a resilience model of the resulting infrastructure, and tells you what will break before you apply a single byte to your cloud account.

---

## Problem statement

Terraform is excellent at describing *what* infrastructure to create. It is silent about whether that infrastructure is resilient. The following are all valid Terraform configurations that will apply cleanly and silently create operational time bombs:

```hcl
# Deploys, but the service goes offline if one task dies
resource "aws_ecs_service" "app" {
  desired_count = 1
}

# Deploys, but an AZ failure takes down the database
resource "aws_db_instance" "main" {
  multi_az = false
}

# Deploys, but exposes SSH to every IP on the internet
resource "aws_security_group" "bastion" {
  ingress {
    from_port   = 22
    cidr_blocks = ["0.0.0.0/0"]
  }
}
```

Code review catches some of these. `tflint`, `checkov`, and `terraform validate` catch others. But none of them model the *system-level* effects: what happens if this database loses its AZ while traffic is live? Does that cascade? How long is the outage?

FaultRay answers those questions without touching production.

---

## Setup

### Install FaultRay

```bash
pip install faultray
```

Verify:

```bash
faultray --version
```

### Install Terraform

FaultRay reads standard Terraform plan JSON. Any Terraform version >= 1.0 works.

```bash
# macOS
brew install terraform

# Linux
# See https://developer.hashicorp.com/terraform/install
```

---

## Basic usage

### 1. Generate a plan JSON file

```bash
# Initialize Terraform (if not already done)
terraform init

# Create a binary plan
terraform plan -out=plan.out

# Convert to JSON — this is what FaultRay reads
terraform show -json plan.out > plan.json
```

### 2. Run the check

```bash
faultray tf-check plan.json
```

FaultRay analyzes every resource in the planned configuration, scores the system on a 0-100 resilience scale, and reports issues by severity:

```
╭──────────────────────────────────────────────────────╮
│  FaultRay Terraform Check                            │
│  Plan: plan.json                                     │
│  Resources analyzed: 18                              │
╰──────────────────────────────────────────────────────╯

Resilience Score: 41/100

  CRITICAL  (9.1/10)  aws_ecs_service.app
    desired_count = 1 — single task is a SPOF.
    Fix: set desired_count >= 2, ideally 3 for AZ-level redundancy.

  CRITICAL  (8.7/10)  aws_db_instance.main
    multi_az = false — no standby replica exists.
    Fix: set multi_az = true.

  WARNING   (6.4/10)  aws_elasticache_cluster.cache
    Single-node ElastiCache cluster. No replica.
    Fix: use aws_elasticache_replication_group with automatic_failover_enabled = true.

  WARNING   (5.8/10)  aws_security_group.bastion
    Ingress 0.0.0.0/0 on port 22.
    Fix: restrict cidr_blocks to your management IP range.

Exit code: 2
```

### 3. Fix and re-check

After resolving the issues and re-planning:

```bash
terraform plan -out=plan.out
terraform show -json plan.out > plan.json
faultray tf-check plan.json
```

```
Resilience Score: 87/100

  SUGGESTION  (2.1/10)  aws_ecs_service.app
    Consider aws_appautoscaling_target for traffic spike handling.

0 critical, 0 warnings. Exit code: 0
```

---

## CI/CD integration

The real value of FaultRay comes from running it automatically on every pull request that changes infrastructure. The check runs on the *plan* — not the live environment — so it is safe to run in any CI environment without cloud permissions beyond what Terraform itself needs.

### GitHub Actions

```yaml
name: Terraform Resilience Check

on:
  pull_request:
    paths:
      - 'terraform/**'
      - '**.tf'

jobs:
  faultray:
    name: FaultRay tf-check
    runs-on: ubuntu-latest

    permissions:
      contents: read
      pull-requests: write   # needed to post a PR comment

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install FaultRay
        run: pip install faultray

      - name: Set up Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: '1.8'

      - name: Terraform init
        working-directory: ./terraform
        run: terraform init -backend=false

      - name: Terraform plan
        working-directory: ./terraform
        run: |
          terraform plan -out=plan.out
          terraform show -json plan.out > plan.json
        env:
          AWS_ACCESS_KEY_ID:     ${{ secrets.AWS_ACCESS_KEY_ID }}
          AWS_SECRET_ACCESS_KEY: ${{ secrets.AWS_SECRET_ACCESS_KEY }}

      - name: FaultRay check
        working-directory: ./terraform
        run: faultray tf-check plan.json --min-score 70 --output results.json

      - name: Upload results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: faultray-results
          path: terraform/results.json

      - name: Comment on PR
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const results = JSON.parse(fs.readFileSync('terraform/results.json', 'utf8'));
            const score = results.resilience_score;
            const critical = results.critical_count;
            const warnings = results.warning_count;
            const icon = critical > 0 ? ':x:' : score >= 70 ? ':white_check_mark:' : ':warning:';
            const body = [
              `## ${icon} FaultRay Resilience Check`,
              `**Score:** ${score}/100`,
              `**Critical:** ${critical}  **Warnings:** ${warnings}`,
              '',
              critical > 0
                ? '> Pipeline blocked: critical resilience issues found. See uploaded artifact for details.'
                : score < 70
                  ? '> Pipeline blocked: score below minimum threshold (70). See uploaded artifact for details.'
                  : '> All checks passed.',
            ].join('\n');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body,
            });
```

### GitLab CI

```yaml
faultray-check:
  image: python:3.12-slim
  stage: validate
  rules:
    - changes:
        - terraform/**/*.tf
  before_script:
    - pip install faultray
    - apt-get update -q && apt-get install -y unzip curl
    - curl -fsSL https://releases.hashicorp.com/terraform/1.8.5/terraform_1.8.5_linux_amd64.zip -o tf.zip
    - unzip tf.zip && mv terraform /usr/local/bin/
  script:
    - cd terraform
    - terraform init -backend=false
    - terraform plan -out=plan.out
    - terraform show -json plan.out > plan.json
    - faultray tf-check plan.json --min-score 70
  artifacts:
    paths:
      - terraform/plan.json
    when: always
  allow_failure: false
```

---

## Policy enforcement

### Minimum score

Block the pipeline if the planned infrastructure scores below a threshold:

```bash
faultray tf-check plan.json --min-score 70
# Exit code 3 if score < 70
# Exit code 2 if any critical issues found (regardless of score)
# Exit code 0 if all checks pass
```

Recommended thresholds by environment:

| Environment | Recommended threshold |
|-------------|----------------------|
| Development | 50 |
| Staging | 65 |
| Production | 75 |
| Regulated (PCI/HIPAA) | 85 |

### Fail on regression

In a pull request workflow, you often care less about the absolute score and more about whether the PR makes things *worse*. Use `--fail-on-regression` to compare the planned state against the current state:

```bash
# Snapshot the current live state
terraform show -json terraform.tfstate > current.json
faultray tf-check current.json --output current-score.json

# Check the proposed plan
terraform plan -out=plan.out
terraform show -json plan.out > plan.json
faultray tf-check plan.json --fail-on-regression current-score.json
# Exit code 4 if the score regresses by more than 5 points
```

This is useful for teams that are gradually improving their infrastructure: you don't block merges because the score is below 70 (it might be a legacy system), but you do block any change that makes things worse.

### Combining both policies

```bash
faultray tf-check plan.json \
  --min-score 70 \
  --fail-on-regression current-score.json \
  --output results.json
```

Exit code priority: critical issues (2) > score below threshold (3) > regression (4) > clean (0).

---

## FAQ

**Is this a replacement for chaos engineering?**

No. It is complementary. Think of FaultRay's Terraform check as a pre-flight check — the same kind of systematic review a pilot does before takeoff. It catches known failure modes in your configuration *before* you deploy. Real chaos engineering (AWS FIS, Gremlin, Chaos Monkey) runs *after* you deploy, injecting actual failures into a live system to find unknown failure modes.

Both are valuable. Pre-flight checks prevent the obvious mistakes. Live chaos engineering finds the surprises your model didn't anticipate. Use both.

---

**Does FaultRay need AWS credentials to run the check?**

No. `faultray tf-check` reads the Terraform plan JSON file, which is a static document that describes the planned configuration. It does not make any API calls to AWS. You only need AWS credentials to run `terraform plan` itself.

---

**Does it work with Terraform Cloud / Terraform Enterprise?**

Yes. Terraform Cloud can export plan files in JSON format. Download the plan JSON from the run page (or use the Terraform Cloud API) and pass it to `faultray tf-check` as usual.

---

**What if I use a monorepo with multiple Terraform roots?**

Run `faultray tf-check` once per root, or use the `--dir` flag to point at a directory of plan files:

```bash
faultray tf-check --dir ./tf-plans/ --min-score 70
```

FaultRay will analyze each plan file and report a combined score.

---

**Can I suppress specific findings?**

Yes. Add a `.faultray-ignore` file to your Terraform directory:

```
# .faultray-ignore
# Suppress SSH-open-to-world for the development bastion only
aws_security_group.dev_bastion:open-ssh-ingress:acknowledged
```

Suppressed findings are still shown in the report (as acknowledged) but do not affect the score or exit code.

---

**How does the score relate to actual availability?**

The score is a composite of multiple resilience dimensions: redundancy, failover coverage, blast radius, and security posture. A score of 70+ corresponds roughly to a configuration capable of surviving single-AZ failures without data loss or extended outage. A score of 85+ typically implies multi-region readiness. See [3-Layer Availability Model](../concepts/five-layer-model.md) for the mathematical foundation.

---

## See also

- [Terraform Integration reference](../integrations/terraform.md) — full `tf-import` and `tf-check` command reference
- [CI/CD Integration](../integrations/cicd.md) — GitHub Actions, GitLab CI, and Jenkins examples
- [terraform-guard-demo example](../../examples/terraform-guard-demo/) — runnable demo with before/after configs
