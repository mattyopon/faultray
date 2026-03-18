# Terraform Guard Demo

This demo shows how FaultRay catches common resilience problems in a Terraform plan **before** `terraform apply` is ever run.

Two configurations are provided side by side:

| File | What it is |
|------|-----------|
| `main.tf` | Realistic AWS config with four intentional resilience problems |
| `main-fixed.tf` | The same config with all problems resolved |

## The problems in main.tf

| # | Resource | Problem | Risk |
|---|----------|---------|------|
| 1 | `aws_ecs_service.app` | `desired_count = 1` | Single-task SPOF: one crash takes the service offline |
| 2 | `aws_db_instance.main` | `multi_az = false` | AZ failure takes the database down with no standby to promote |
| 3 | `aws_elasticache_cluster.cache` | Single node, no replication | Any maintenance or failure causes a complete cache outage |
| 4 | `aws_security_group.bastion` | Inbound `0.0.0.0/0` on port 22 | SSH accessible from the public internet |

---

## Walkthrough

### Step 1: Initialize and plan

```bash
cd examples/terraform-guard-demo

# Initialize providers (requires AWS credentials if you want a real plan;
# otherwise the plan file is produced locally without applying anything)
terraform init

# Create a binary plan
terraform plan -out=plan.out

# Convert to JSON so FaultRay can parse it
terraform show -json plan.out > plan.json
```

### Step 2: Run faultray tf-check

```bash
faultray tf-check plan.json
```

Expected output for `main.tf`:

```
╭──────────────────────────────────────────────────────╮
│  FaultRay Terraform Check                            │
│  Plan: plan.json                                     │
│  Resources analyzed: 18                              │
╰──────────────────────────────────────────────────────╯

Resilience Score: 41/100

  CRITICAL  (9.1/10)  aws_ecs_service.app
    desired_count = 1 — single task is a SPOF.
    Any task failure or Fargate host maintenance will take this service offline.
    Fix: set desired_count >= 2, ideally 3 for AZ-level redundancy.

  CRITICAL  (8.7/10)  aws_db_instance.main
    multi_az = false — no standby replica exists.
    An AZ outage or instance failure will cause an unrecoverable outage
    until AWS replaces the instance (typically 20–30 min).
    Fix: set multi_az = true.

  WARNING   (6.4/10)  aws_elasticache_cluster.cache
    Single-node ElastiCache cluster (num_cache_nodes = 1).
    No replica means any maintenance window or node failure
    flushes the cache and forces all traffic to hit the database cold.
    Fix: use aws_elasticache_replication_group with num_cache_clusters >= 2
    and automatic_failover_enabled = true.

  WARNING   (5.8/10)  aws_security_group.bastion
    Ingress rule allows 0.0.0.0/0 on port 22 (SSH).
    This exposes the bastion to brute-force and credential-stuffing attacks
    from any IP on the internet.
    Fix: restrict cidr_blocks to your management IP range.

4 issues found (2 critical, 2 warning). Score: 41/100.
Exit code: 2
```

### Step 3: Apply the fixes and re-check

Swap `main.tf` for `main-fixed.tf` (or copy it over), then re-run:

```bash
cp main-fixed.tf main.tf
terraform plan -out=plan.out
terraform show -json plan.out > plan.json
faultray tf-check plan.json
```

Expected output after fixes:

```
╭──────────────────────────────────────────────────────╮
│  FaultRay Terraform Check                            │
│  Plan: plan.json                                     │
│  Resources analyzed: 18                              │
╰──────────────────────────────────────────────────────╯

Resilience Score: 87/100

  SUGGESTION  (2.1/10)  aws_ecs_service.app
    Consider adding an aws_appautoscaling_target to handle traffic spikes
    automatically beyond the baseline desired_count of 3.

0 critical issues, 0 warnings, 1 suggestion. Score: 87/100.
Exit code: 0
```

### Score comparison

| Configuration | Score | Critical | Warning | Suggestion |
|--------------|-------|----------|---------|------------|
| `main.tf` (before) | 41/100 | 2 | 2 | 0 |
| `main-fixed.tf` (after) | 87/100 | 0 | 0 | 1 |

---

## Gating applies in CI

Use `--min-score` to fail the pipeline if the score drops below a threshold:

```bash
faultray tf-check plan.json --min-score 70
# Exits 3 if score < 70, 2 if critical issues found, 0 otherwise
```

Use `--fail-on-regression` in pull requests to catch any decline relative to the current state:

```bash
# Check current state
terraform show -json terraform.tfstate > current.json
faultray tf-check current.json --output current-score.json

# Check proposed changes
terraform plan -out=plan.out && terraform show -json plan.out > plan.json
faultray tf-check plan.json --fail-on-regression current-score.json
```

See [Using FaultRay as a Terraform Safety Net](../../docs/guides/terraform-safety-net.md) for a complete CI/CD setup guide.
