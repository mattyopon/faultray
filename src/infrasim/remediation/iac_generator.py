"""IaC remediation code generator for ChaosProof.

Generates Terraform and Kubernetes code that fixes infrastructure issues
found by ChaosProof's analysis engines.  Remediations are organized into
three phases (critical SPOF elimination, security hardening, disaster
recovery) and include cost estimates and expected resilience score impact.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from infrasim.model.components import Component, ComponentType
from infrasim.model.graph import InfraGraph


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RemediationFile:
    """A single generated IaC file with metadata."""

    path: str  # e.g., "phase1-critical/01-rds-multi-az.tf"
    content: str  # The actual Terraform/K8s code
    description: str  # Human-readable description
    phase: int  # 1, 2, or 3
    impact_score_delta: float  # Expected resilience score improvement
    monthly_cost: float  # Estimated monthly cost in USD
    category: str  # "redundancy", "security", "dr", "monitoring"


@dataclass
class RemediationPlan:
    """Complete remediation plan with files, cost, and impact summary."""

    files: list[RemediationFile] = field(default_factory=list)
    total_phases: int = 0
    total_monthly_cost: float = 0.0
    expected_score_before: float = 0.0
    expected_score_after: float = 0.0
    risk_reduction_percent: float = 0.0
    roi_percent: float = 0.0
    readme_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the plan to a JSON-friendly dict."""
        return {
            "total_phases": self.total_phases,
            "total_monthly_cost": round(self.total_monthly_cost, 2),
            "expected_score_before": round(self.expected_score_before, 2),
            "expected_score_after": round(self.expected_score_after, 2),
            "risk_reduction_percent": round(self.risk_reduction_percent, 2),
            "roi_percent": round(self.roi_percent, 2),
            "files": [
                {
                    "path": f.path,
                    "description": f.description,
                    "phase": f.phase,
                    "impact_score_delta": round(f.impact_score_delta, 2),
                    "monthly_cost": round(f.monthly_cost, 2),
                    "category": f.category,
                }
                for f in self.files
            ],
        }


# ---------------------------------------------------------------------------
# Remediation rule definitions
# ---------------------------------------------------------------------------

_PHASE_DIR = {1: "phase1-critical", 2: "phase2-security", 3: "phase3-dr"}


def _rule_condition_database_no_replica(comp: Component) -> bool:
    return comp.type.value == "database" and comp.replicas <= 1


def _rule_condition_cache_no_replica(comp: Component) -> bool:
    return comp.type.value == "cache" and comp.replicas <= 1


def _rule_condition_no_autoscaling(comp: Component) -> bool:
    return comp.type.value == "app_server" and not comp.autoscaling.enabled


def _rule_condition_no_encryption(comp: Component) -> bool:
    return (
        comp.type.value in ("database", "storage", "cache")
        and not comp.security.encryption_at_rest
    )


def _rule_condition_no_waf(comp: Component) -> bool:
    return (
        comp.type.value in ("load_balancer", "web_server", "app_server")
        and not comp.security.waf_protected
    )


def _rule_condition_no_network_segmentation(comp: Component) -> bool:
    return (
        comp.type.value in ("database", "cache", "app_server")
        and not comp.security.network_segmented
    )


def _rule_condition_no_tls(comp: Component) -> bool:
    return (
        comp.type.value in ("load_balancer", "web_server", "app_server")
        and not comp.security.encryption_in_transit
    )


def _rule_condition_no_cross_region(comp: Component) -> bool:
    return (
        comp.type.value in ("database", "storage")
        and not comp.region.dr_target_region
    )


def _rule_condition_no_backup(comp: Component) -> bool:
    return (
        comp.type.value in ("database", "storage")
        and not comp.security.backup_enabled
    )


def _rule_condition_no_dns_failover(comp: Component) -> bool:
    return comp.type.value == "dns" and not comp.failover.enabled


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

_TEMPLATE_DATABASE_REPLICA = '''\
resource "aws_rds_cluster_instance" "replica_{comp_id}" {{
  count              = 2
  cluster_identifier = aws_rds_cluster.{comp_id}.id
  instance_class     = "db.r6g.large"
  engine             = aws_rds_cluster.{comp_id}.engine
}}
'''

_TEMPLATE_CACHE_REPLICA = '''\
resource "aws_elasticache_replication_group" "{comp_id}" {{
  replication_group_id       = "{comp_id}-ha"
  num_cache_clusters         = 3
  automatic_failover_enabled = true
}}
'''

_TEMPLATE_HPA = '''\
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {comp_id}-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {comp_id}
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
'''

_TEMPLATE_KMS = '''\
resource "aws_kms_key" "{comp_id}_key" {{
  description         = "Encryption key for {comp_name}"
  enable_key_rotation = true
}}

resource "aws_kms_alias" "{comp_id}_key_alias" {{
  name          = "alias/{comp_id}"
  target_key_id = aws_kms_key.{comp_id}_key.key_id
}}
'''

_TEMPLATE_WAF = '''\
resource "aws_wafv2_web_acl" "{comp_id}_waf" {{
  name        = "{comp_id}-waf"
  scope       = "REGIONAL"
  description = "WAF for {comp_name}"

  default_action {{
    allow {{}}
  }}

  rule {{
    name     = "rate-limit"
    priority = 1

    action {{
      block {{}}
    }}

    statement {{
      rate_based_statement {{
        limit              = 2000
        aggregate_key_type = "IP"
      }}
    }}

    visibility_config {{
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "{comp_id}-rate-limit"
    }}
  }}

  rule {{
    name     = "aws-managed-common"
    priority = 2

    override_action {{
      none {{}}
    }}

    statement {{
      managed_rule_group_statement {{
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }}
    }}

    visibility_config {{
      sampled_requests_enabled   = true
      cloudwatch_metrics_enabled = true
      metric_name                = "{comp_id}-common-rules"
    }}
  }}

  visibility_config {{
    sampled_requests_enabled   = true
    cloudwatch_metrics_enabled = true
    metric_name                = "{comp_id}-waf"
  }}
}}
'''

_TEMPLATE_NETWORK_SEGMENTATION = '''\
resource "aws_vpc" "{comp_id}_vpc" {{
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {{
    Name = "{comp_id}-vpc"
  }}
}}

resource "aws_subnet" "{comp_id}_private" {{
  vpc_id            = aws_vpc.{comp_id}_vpc.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"

  tags = {{
    Name = "{comp_id}-private"
  }}
}}

resource "aws_security_group" "{comp_id}_sg" {{
  name        = "{comp_id}-sg"
  description = "Security group for {comp_name}"
  vpc_id      = aws_vpc.{comp_id}_vpc.id

  ingress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    self        = true
    description = "Allow internal traffic"
  }}

  egress {{
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound"
  }}

  tags = {{
    Name = "{comp_id}-sg"
  }}
}}
'''

_TEMPLATE_TLS = '''\
resource "aws_acm_certificate" "{comp_id}_cert" {{
  domain_name       = "{comp_id}.example.com"
  validation_method = "DNS"

  lifecycle {{
    create_before_destroy = true
  }}
}}

resource "aws_lb_listener" "{comp_id}_https" {{
  load_balancer_arn = aws_lb.{comp_id}.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.{comp_id}_cert.arn

  default_action {{
    type             = "forward"
    target_group_arn = aws_lb_target_group.{comp_id}.arn
  }}
}}
'''

_TEMPLATE_CROSS_REGION = '''\
resource "aws_rds_global_cluster" "{comp_id}_global" {{
  global_cluster_identifier = "{comp_id}-global"
  engine                    = "aurora-postgresql"
  engine_version            = "15.4"
  database_name             = "{comp_id}"
  storage_encrypted         = true
}}

resource "aws_s3_bucket" "{comp_id}_replica" {{
  bucket   = "{comp_id}-dr-replica"
  provider = aws.dr_region
}}

resource "aws_s3_bucket_replication_configuration" "{comp_id}_replication" {{
  bucket = aws_s3_bucket.{comp_id}.id
  role   = aws_iam_role.{comp_id}_replication.arn

  rule {{
    id     = "dr-replication"
    status = "Enabled"

    destination {{
      bucket        = aws_s3_bucket.{comp_id}_replica.arn
      storage_class = "STANDARD"
    }}
  }}
}}
'''

_TEMPLATE_BACKUP = '''\
resource "aws_backup_plan" "{comp_id}_backup" {{
  name = "{comp_id}-backup-plan"

  rule {{
    rule_name         = "daily-backup"
    target_vault_name = aws_backup_vault.{comp_id}_vault.name
    schedule          = "cron(0 3 * * ? *)"

    lifecycle {{
      delete_after = 30
    }}
  }}

  rule {{
    rule_name         = "weekly-backup"
    target_vault_name = aws_backup_vault.{comp_id}_vault.name
    schedule          = "cron(0 3 ? * SUN *)"

    lifecycle {{
      delete_after = 90
    }}
  }}
}}

resource "aws_backup_vault" "{comp_id}_vault" {{
  name = "{comp_id}-backup-vault"
}}

resource "aws_backup_selection" "{comp_id}_selection" {{
  name         = "{comp_id}-backup-selection"
  plan_id      = aws_backup_plan.{comp_id}_backup.id
  iam_role_arn = aws_iam_role.{comp_id}_backup.arn

  resources = [
    aws_db_instance.{comp_id}.arn
  ]
}}
'''

_TEMPLATE_DNS_FAILOVER = '''\
resource "aws_route53_health_check" "{comp_id}_health" {{
  fqdn              = "{comp_id}.example.com"
  port               = 443
  type               = "HTTPS"
  resource_path      = "/health"
  failure_threshold  = 3
  request_interval   = 30
  measure_latency    = true
}}

resource "aws_route53_record" "{comp_id}_primary" {{
  zone_id = aws_route53_zone.main.zone_id
  name    = "{comp_id}.example.com"
  type    = "A"

  failover_routing_policy {{
    type = "PRIMARY"
  }}

  set_identifier  = "{comp_id}-primary"
  health_check_id = aws_route53_health_check.{comp_id}_health.id

  alias {{
    name                   = aws_lb.{comp_id}_primary.dns_name
    zone_id                = aws_lb.{comp_id}_primary.zone_id
    evaluate_target_health = true
  }}
}}

resource "aws_route53_record" "{comp_id}_secondary" {{
  zone_id = aws_route53_zone.main.zone_id
  name    = "{comp_id}.example.com"
  type    = "A"

  failover_routing_policy {{
    type = "SECONDARY"
  }}

  set_identifier = "{comp_id}-secondary"

  alias {{
    name                   = aws_lb.{comp_id}_secondary.dns_name
    zone_id                = aws_lb.{comp_id}_secondary.zone_id
    evaluate_target_health = true
  }}
}}
'''


# ---------------------------------------------------------------------------
# Rule registry
# ---------------------------------------------------------------------------

@dataclass
class _RemediationRule:
    """Internal rule definition mapping an issue to IaC output."""

    key: str
    condition: Callable[[Component], bool]
    template: str
    output_type: str  # "terraform" or "kubernetes"
    phase: int
    category: str
    impact: float
    cost: float
    description_template: str
    file_extension: str = ""

    def __post_init__(self) -> None:
        if not self.file_extension:
            self.file_extension = ".tf" if self.output_type == "terraform" else ".yaml"


REMEDIATION_RULES: list[_RemediationRule] = [
    # --- Phase 1: Critical (SPOF elimination) --------------------------------
    _RemediationRule(
        key="database_no_replica",
        condition=_rule_condition_database_no_replica,
        template=_TEMPLATE_DATABASE_REPLICA,
        output_type="terraform",
        phase=1,
        category="redundancy",
        impact=10.0,
        cost=800.0,
        description_template="Add read replicas to {comp_name} for high availability",
    ),
    _RemediationRule(
        key="cache_no_replica",
        condition=_rule_condition_cache_no_replica,
        template=_TEMPLATE_CACHE_REPLICA,
        output_type="terraform",
        phase=1,
        category="redundancy",
        impact=8.0,
        cost=400.0,
        description_template="Add replication group to {comp_name} for high availability",
    ),
    _RemediationRule(
        key="no_autoscaling",
        condition=_rule_condition_no_autoscaling,
        template=_TEMPLATE_HPA,
        output_type="kubernetes",
        phase=1,
        category="redundancy",
        impact=5.0,
        cost=0.0,
        description_template="Add HorizontalPodAutoscaler to {comp_name} for auto-scaling",
    ),
    # --- Phase 2: Security ---------------------------------------------------
    _RemediationRule(
        key="no_encryption",
        condition=_rule_condition_no_encryption,
        template=_TEMPLATE_KMS,
        output_type="terraform",
        phase=2,
        category="security",
        impact=3.0,
        cost=1.0,
        description_template="Enable encryption at rest for {comp_name} with KMS",
    ),
    _RemediationRule(
        key="no_waf",
        condition=_rule_condition_no_waf,
        template=_TEMPLATE_WAF,
        output_type="terraform",
        phase=2,
        category="security",
        impact=4.0,
        cost=20.0,
        description_template="Add WAF protection to {comp_name}",
    ),
    _RemediationRule(
        key="no_network_segmentation",
        condition=_rule_condition_no_network_segmentation,
        template=_TEMPLATE_NETWORK_SEGMENTATION,
        output_type="terraform",
        phase=2,
        category="security",
        impact=3.0,
        cost=50.0,
        description_template="Add network segmentation for {comp_name}",
    ),
    _RemediationRule(
        key="no_tls",
        condition=_rule_condition_no_tls,
        template=_TEMPLATE_TLS,
        output_type="terraform",
        phase=2,
        category="security",
        impact=3.0,
        cost=0.0,
        description_template="Enable TLS/HTTPS for {comp_name}",
    ),
    # --- Phase 3: DR ---------------------------------------------------------
    _RemediationRule(
        key="no_cross_region",
        condition=_rule_condition_no_cross_region,
        template=_TEMPLATE_CROSS_REGION,
        output_type="terraform",
        phase=3,
        category="dr",
        impact=6.0,
        cost=500.0,
        description_template="Add cross-region replication for {comp_name}",
    ),
    _RemediationRule(
        key="no_backup",
        condition=_rule_condition_no_backup,
        template=_TEMPLATE_BACKUP,
        output_type="terraform",
        phase=3,
        category="dr",
        impact=5.0,
        cost=30.0,
        description_template="Add automated backup plan for {comp_name}",
    ),
    _RemediationRule(
        key="no_dns_failover",
        condition=_rule_condition_no_dns_failover,
        template=_TEMPLATE_DNS_FAILOVER,
        output_type="terraform",
        phase=3,
        category="dr",
        impact=4.0,
        cost=5.0,
        description_template="Add DNS failover routing for {comp_name}",
    ),
]


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class IaCGenerator:
    """Generate Terraform/Kubernetes remediation code from ChaosProof analysis.

    The generator inspects every component in the infrastructure graph,
    checks each remediation rule, and produces templated IaC code for any
    issues found.  Results are organized into a phased :class:`RemediationPlan`.
    """

    def __init__(self, graph: InfraGraph) -> None:
        self._graph = graph

    # ---- public API -------------------------------------------------------

    def generate(self, target_score: float = 90.0) -> RemediationPlan:
        """Generate a remediation plan to reach *target_score*.

        Args:
            target_score: The desired resilience score (0-100).  Remediations
                are generated in priority order (phase 1 first) and stop once
                the cumulative projected score meets the target.

        Returns:
            A :class:`RemediationPlan` with all generated files.
        """
        current_score = self._graph.resilience_score()

        # Collect all applicable remediations
        all_files: list[RemediationFile] = []
        counters: dict[str, int] = {}  # per-rule counter for unique filenames

        for comp in self._graph.components.values():
            for rule in REMEDIATION_RULES:
                if rule.condition(comp):
                    counters.setdefault(rule.key, 0)
                    counters[rule.key] += 1
                    idx = counters[rule.key]

                    rendered = rule.template.format(
                        comp_id=comp.id,
                        comp_name=comp.name,
                    )

                    description = rule.description_template.format(
                        comp_id=comp.id,
                        comp_name=comp.name,
                    )

                    phase_dir = _PHASE_DIR[rule.phase]
                    filename = f"{idx:02d}-{comp.id}-{rule.key}{rule.file_extension}"
                    file_path = f"{phase_dir}/{filename}"

                    all_files.append(
                        RemediationFile(
                            path=file_path,
                            content=rendered,
                            description=description,
                            phase=rule.phase,
                            impact_score_delta=rule.impact,
                            monthly_cost=rule.cost,
                            category=rule.category,
                        )
                    )

        # Sort by phase then by descending impact within each phase
        all_files.sort(key=lambda f: (f.phase, -f.impact_score_delta))

        # Trim files if we can reach the target score with fewer remediations.
        # When the current score already meets or exceeds the target, include
        # all detected issues since the resilience score may not capture every
        # specific configuration gap that the rules detect.
        if current_score >= target_score:
            selected = all_files
        else:
            selected: list[RemediationFile] = []
            projected_score = current_score
            for f in all_files:
                selected.append(f)
                projected_score += f.impact_score_delta
                if projected_score >= target_score:
                    break

            # If we exhausted all files without hitting the target, keep all
            if projected_score < target_score:
                selected = all_files

        # Calculate plan summary
        total_cost = sum(f.monthly_cost for f in selected)
        total_impact = sum(f.impact_score_delta for f in selected)
        projected_after = min(100.0, current_score + total_impact)
        phases_used = sorted({f.phase for f in selected}) if selected else []

        risk_before = 100.0 - current_score
        risk_after = 100.0 - projected_after
        risk_reduction = (
            ((risk_before - risk_after) / risk_before * 100.0)
            if risk_before > 0
            else 0.0
        )

        # ROI: score improvement per $100/month spent
        roi = (total_impact / (total_cost / 100.0)) if total_cost > 0 else 0.0

        readme = self._generate_readme(
            selected, current_score, projected_after, total_cost
        )

        return RemediationPlan(
            files=selected,
            total_phases=len(phases_used),
            total_monthly_cost=total_cost,
            expected_score_before=current_score,
            expected_score_after=projected_after,
            risk_reduction_percent=risk_reduction,
            roi_percent=roi,
            readme_content=readme,
        )

    def dry_run(self, plan: RemediationPlan) -> str:
        """Generate a human-readable diff preview of what would change.

        Similar to ``terraform plan`` output.  Shows each file that would
        be created with ``+`` prefixed lines, and a summary of resources
        to add / change / destroy.

        Args:
            plan: the remediation plan to preview.

        Returns:
            A multi-line string suitable for printing to the terminal.
        """
        if not plan.files:
            return "No changes. Infrastructure meets the target score."

        lines: list[str] = []
        adds = 0
        changes = 0
        destroys = 0

        phase_titles = {
            1: "Phase 1: Critical (SPOF Elimination)",
            2: "Phase 2: Security Hardening",
            3: "Phase 3: Disaster Recovery",
        }

        current_phase: int | None = None

        for f in plan.files:
            if f.phase != current_phase:
                current_phase = f.phase
                title = phase_titles.get(f.phase, f"Phase {f.phase}")
                lines.append("")
                lines.append(f"--- {title} ---")
                lines.append("")

            lines.append(f"# {f.description}")
            lines.append(f"# File: {f.path}  (impact: +{f.impact_score_delta:.1f}, cost: ${f.monthly_cost:,.2f}/mo)")

            for content_line in f.content.splitlines():
                lines.append(f"+ {content_line}")

            lines.append("")

            # Count resources in content (heuristic)
            resource_count = f.content.count("resource ")
            resource_count += f.content.count("kind:")
            adds += max(1, resource_count)

        lines.append("------------------------------------------------------------------------")
        lines.append(f"Plan: {adds} to add, {changes} to change, {destroys} to destroy.")
        lines.append("")
        lines.append(
            f"Resilience score: {plan.expected_score_before:.1f} -> "
            f"{plan.expected_score_after:.1f}  "
            f"(+{plan.expected_score_after - plan.expected_score_before:.1f})"
        )
        lines.append(f"Estimated monthly cost: ${plan.total_monthly_cost:,.2f}")

        return "\n".join(lines)

    def write_to_directory(self, plan: RemediationPlan, output_dir: Path) -> None:
        """Write all remediation files and README to *output_dir*.

        Creates subdirectories for each phase automatically.
        """
        output_dir.mkdir(parents=True, exist_ok=True)

        for f in plan.files:
            file_path = output_dir / f.path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(f.content, encoding="utf-8")

        readme_path = output_dir / "README.md"
        readme_path.write_text(plan.readme_content, encoding="utf-8")

    # ---- internal ---------------------------------------------------------

    def _generate_readme(
        self,
        files: list[RemediationFile],
        score_before: float,
        score_after: float,
        total_cost: float,
    ) -> str:
        """Generate a README.md summarizing the remediation plan."""
        lines: list[str] = []
        lines.append("# ChaosProof Remediation Plan")
        lines.append("")
        lines.append("Auto-generated IaC remediation code for improving infrastructure resilience.")
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- **Resilience Score (before):** {score_before:.1f}")
        lines.append(f"- **Resilience Score (after):** {score_after:.1f}")
        lines.append(f"- **Estimated Monthly Cost:** ${total_cost:,.2f}")
        lines.append(f"- **Total Files:** {len(files)}")
        lines.append("")

        # Group by phase
        phases: dict[int, list[RemediationFile]] = {}
        for f in files:
            phases.setdefault(f.phase, []).append(f)

        phase_titles = {
            1: "Phase 1 -- Critical (SPOF Elimination)",
            2: "Phase 2 -- Security Hardening",
            3: "Phase 3 -- Disaster Recovery",
        }

        for phase_num in sorted(phases.keys()):
            phase_files = phases[phase_num]
            title = phase_titles.get(phase_num, f"Phase {phase_num}")
            lines.append(f"## {title}")
            lines.append("")
            phase_cost = sum(pf.monthly_cost for pf in phase_files)
            phase_impact = sum(pf.impact_score_delta for pf in phase_files)
            lines.append(f"**Expected impact:** +{phase_impact:.1f} points | "
                         f"**Cost:** ${phase_cost:,.2f}/month")
            lines.append("")
            lines.append("| File | Description | Category | Impact | Cost |")
            lines.append("|------|-------------|----------|--------|------|")
            for pf in phase_files:
                lines.append(
                    f"| `{pf.path}` | {pf.description} | {pf.category} | "
                    f"+{pf.impact_score_delta:.1f} | ${pf.monthly_cost:,.2f}/mo |"
                )
            lines.append("")

        lines.append("## How to Apply")
        lines.append("")
        lines.append("Apply remediations **in phase order** (Phase 1 first, then 2, then 3).")
        lines.append("")
        lines.append("### Terraform files (.tf)")
        lines.append("")
        lines.append("```bash")
        lines.append("# Review the plan")
        lines.append("terraform plan")
        lines.append("")
        lines.append("# Apply changes")
        lines.append("terraform apply")
        lines.append("```")
        lines.append("")
        lines.append("### Kubernetes files (.yaml)")
        lines.append("")
        lines.append("```bash")
        lines.append("# Apply Kubernetes manifests")
        lines.append("kubectl apply -f <file>.yaml")
        lines.append("")
        lines.append("# Verify")
        lines.append("kubectl get hpa")
        lines.append("```")
        lines.append("")

        return "\n".join(lines)
