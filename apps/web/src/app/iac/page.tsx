"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  FileCode2,
  Cloud,
  Box,
  Terminal,
  Code,
  Copy,
  Download,
  CheckCircle2,
  TrendingUp,
  DollarSign,
  Server,
  Database,
  Shield,
  Globe,
} from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

/* ------------------------------------------------------------------ */
/*  Demo Terraform code — 3 phases                                     */
/* ------------------------------------------------------------------ */

const DEMO_PHASE1 = `# FaultRay Auto-Generated — Phase 1: SPOF Elimination
# Generated: 2026-04-01 | Score: 85.5 → 91.2 (+5.7)

resource "aws_db_instance" "replica" {
  identifier          = "faultray-db-replica"
  replicate_source_db = aws_db_instance.primary.identifier
  instance_class      = "db.r5.large"
  multi_az            = true
  storage_encrypted   = true

  tags = {
    ManagedBy = "FaultRay"
    Phase     = "1-spof-elimination"
  }
}

resource "aws_elasticache_replication_group" "cache" {
  replication_group_id          = "faultray-cache-ha"
  description                   = "FaultRay HA cache cluster"
  num_cache_clusters            = 2
  automatic_failover_enabled    = true
  at_rest_encryption_enabled    = true
  transit_encryption_enabled    = true

  tags = {
    ManagedBy = "FaultRay"
    Phase     = "1-spof-elimination"
  }
}

resource "aws_lb" "app" {
  name               = "faultray-alb"
  internal           = false
  load_balancer_type = "application"
  subnets            = var.public_subnet_ids
  security_groups    = [aws_security_group.alb.id]

  enable_deletion_protection = true

  tags = {
    ManagedBy = "FaultRay"
    Phase     = "1-spof-elimination"
  }
}

resource "aws_autoscaling_group" "app" {
  name                = "faultray-asg"
  min_size            = 2
  max_size            = 10
  desired_capacity    = 2
  vpc_zone_identifier = var.private_subnet_ids
  target_group_arns   = [aws_lb_target_group.app.arn]

  health_check_type         = "ELB"
  health_check_grace_period = 300

  tag {
    key                 = "ManagedBy"
    value               = "FaultRay"
    propagate_at_launch = true
  }
}`;

const DEMO_PHASE2 = `# FaultRay Auto-Generated — Phase 2: Security Hardening
# Generated: 2026-04-01 | Score: 91.2 → 94.8 (+3.6)

resource "aws_wafv2_web_acl" "app" {
  name  = "faultray-waf"
  scope = "REGIONAL"

  default_action {
    allow {}
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 1
    override_action { none {} }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "CommonRules"
      sampled_requests_enabled   = true
    }
  }

  tags = {
    ManagedBy = "FaultRay"
    Phase     = "2-security-hardening"
  }
}

resource "aws_security_group" "db" {
  name        = "faultray-db-sg"
  description = "Database security group — no public access"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    ManagedBy = "FaultRay"
    Phase     = "2-security-hardening"
  }
}

resource "aws_acm_certificate" "app" {
  domain_name       = var.domain_name
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }

  tags = {
    ManagedBy = "FaultRay"
    Phase     = "2-security-hardening"
  }
}`;

const DEMO_PHASE3 = `# FaultRay Auto-Generated — Phase 3: Disaster Recovery
# Generated: 2026-04-01 | Score: 94.8 → 97.1 (+2.3)

resource "aws_s3_bucket" "backup" {
  bucket = "faultray-backup-\${var.environment}"

  tags = {
    ManagedBy = "FaultRay"
    Phase     = "3-disaster-recovery"
  }
}

resource "aws_s3_bucket_versioning" "backup" {
  bucket = aws_s3_bucket.backup.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_replication_configuration" "backup" {
  role   = aws_iam_role.replication.arn
  bucket = aws_s3_bucket.backup.id

  rule {
    id     = "cross-region-replication"
    status = "Enabled"
    destination {
      bucket        = aws_s3_bucket.backup_replica.arn
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_backup_plan" "app" {
  name = "faultray-backup-plan"

  rule {
    rule_name         = "daily-backup"
    target_vault_name = aws_backup_vault.app.name
    schedule          = "cron(0 2 * * ? *)"
    start_window      = 60
    completion_window = 180

    lifecycle {
      delete_after = 30
    }
  }

  tags = {
    ManagedBy = "FaultRay"
    Phase     = "3-disaster-recovery"
  }
}

resource "aws_route53_health_check" "primary" {
  fqdn              = var.primary_domain
  port              = 443
  type              = "HTTPS"
  resource_path     = "/health"
  failure_threshold = 3
  request_interval  = 30

  tags = {
    ManagedBy = "FaultRay"
    Phase     = "3-disaster-recovery"
  }
}`;

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

type InputMode = "latest" | "sample" | "paste";
type SampleTopology = "web-saas" | "microservices" | "data-pipeline" | "multi-region";
type ExportFormat = "terraform" | "cloudformation" | "kubernetes" | "docker-compose" | "ansible" | "pulumi";
type GeneratedPhase = 1 | 2 | 3;

interface FormatCard {
  id: ExportFormat;
  icon: React.ElementType;
  nameKey: string;
  descKey: string;
  popular?: boolean;
}

interface PhaseInfo {
  phase: GeneratedPhase;
  labelKey: "phase1" | "phase2" | "phase3";
  icon: React.ElementType;
  files: string[];
  costEstimate: string;
  scoreGain: string;
  code: string;
}

const FORMAT_CARDS: FormatCard[] = [
  { id: "terraform", icon: FileCode2, nameKey: "Terraform HCL", descKey: "tfDesc", popular: true },
  { id: "cloudformation", icon: Cloud, nameKey: "AWS CloudFormation", descKey: "cfDesc" },
  { id: "kubernetes", icon: Server, nameKey: "Kubernetes YAML", descKey: "k8sDesc" },
  { id: "docker-compose", icon: Box, nameKey: "Docker Compose", descKey: "composeDesc" },
  { id: "ansible", icon: Terminal, nameKey: "Ansible Playbook", descKey: "ansibleDesc" },
  { id: "pulumi", icon: Code, nameKey: "Pulumi Python", descKey: "pulumiDesc" },
];

const PHASES: PhaseInfo[] = [
  {
    phase: 1,
    labelKey: "phase1",
    icon: Database,
    files: ["main.tf", "variables.tf", "rds.tf", "elasticache.tf", "alb.tf"],
    costEstimate: "$1,240 / mo",
    scoreGain: "+5.7",
    code: DEMO_PHASE1,
  },
  {
    phase: 2,
    labelKey: "phase2",
    icon: Shield,
    files: ["waf.tf", "security_groups.tf", "acm.tf", "iam.tf"],
    costEstimate: "$380 / mo",
    scoreGain: "+3.6",
    code: DEMO_PHASE2,
  },
  {
    phase: 3,
    labelKey: "phase3",
    icon: Globe,
    files: ["backup.tf", "s3_replication.tf", "route53.tf", "dr.tf"],
    costEstimate: "$210 / mo",
    scoreGain: "+2.3",
    code: DEMO_PHASE3,
  },
];

const SPOF_FIXES = [
  { name: "Single DB Instance", fixed: true, impact: "High" },
  { name: "No Cache Redundancy", fixed: true, impact: "High" },
  { name: "Single AZ Deployment", fixed: true, impact: "Critical" },
  { name: "No WAF Protection", fixed: true, impact: "High" },
  { name: "No Cross-Region Backup", fixed: true, impact: "Medium" },
  { name: "Missing Health Checks", fixed: true, impact: "Medium" },
];

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export default function IaCPage() {
  const locale = useLocale();
  const t = (appDict.iac as Record<string, Record<string, string>>)[locale] ?? appDict.iac.en;

  const [inputMode, setInputMode] = useState<InputMode>("sample");
  const [sampleTopology, setSampleTopology] = useState<SampleTopology>("web-saas");
  const [pastedYaml, setPastedYaml] = useState("");
  const [selectedFormat, setSelectedFormat] = useState<ExportFormat | null>(null);
  const [activePhase, setActivePhase] = useState<GeneratedPhase>(1);
  const [generated, setGenerated] = useState(false);
  const [copied, setCopied] = useState(false);

  const currentPhase = PHASES.find((p) => p.phase === activePhase)!;
  const currentCode = currentPhase.code;

  function handleGenerate(fmt: ExportFormat) {
    setSelectedFormat(fmt);
    setGenerated(true);
    setActivePhase(1);
  }

  function handleCopy() {
    navigator.clipboard.writeText(currentCode).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function handleDownload() {
    const ext = selectedFormat === "terraform" ? "tf" : selectedFormat === "cloudformation" ? "yaml" : selectedFormat === "kubernetes" ? "yaml" : selectedFormat === "docker-compose" ? "yml" : selectedFormat === "ansible" ? "yml" : "py";
    const blob = new Blob([currentCode], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `faultray-phase${activePhase}-remediation.${ext}`;
    a.click();
    URL.revokeObjectURL(url);
  }

  const totalScore = PHASES.reduce((acc, p) => acc + parseFloat(p.scoreGain), 0);

  return (
    <main className="min-h-screen bg-[#0a0e1a] text-white pt-20 pb-12">
      <div className="w-full px-4 sm:px-6">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <FileCode2 size={28} className="text-[#FFD700]" />
            <h1 className="text-2xl font-bold">{t.title}</h1>
          </div>
          <p className="text-[#94a3b8]">{t.subtitle}</p>
        </div>

        {/* IaC Coverage Score */}
        <Card className="bg-[#0f1629] border-[#1e293b] p-5 mb-6">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-white">{t.iacScoreTitle}</h2>
            <div className="flex items-center gap-3 text-xs text-[#64748b]">
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-sm bg-[#334155] inline-block" />
                {t.iacScoreCurrent}: <span className="text-white font-semibold ml-1">35%</span>
              </span>
              <span className="flex items-center gap-1">
                <span className="w-2.5 h-2.5 rounded-sm bg-[#FFD700] inline-block" />
                {t.iacScoreTarget}: <span className="text-[#FFD700] font-semibold ml-1">92%</span>
              </span>
            </div>
          </div>
          {/* Progress bar */}
          <div className="relative w-full h-4 bg-[#1e293b] rounded-full overflow-hidden mb-2">
            {/* Target bar (gold, behind) */}
            <div
              className="absolute inset-y-0 left-0 bg-[#FFD700]/30 rounded-full"
              style={{ width: "92%" }}
            />
            {/* Current bar (gray, on top) */}
            <div
              className="absolute inset-y-0 left-0 bg-[#475569] rounded-full transition-all"
              style={{ width: "35%" }}
            />
            {/* 35% label */}
            <span className="absolute inset-y-0 flex items-center text-[10px] font-bold text-white" style={{ left: "calc(35% - 22px)" }}>
              35%
            </span>
            {/* 92% label */}
            <span className="absolute inset-y-0 flex items-center text-[10px] font-bold text-[#FFD700]" style={{ left: "calc(92% - 24px)" }}>
              92%
            </span>
          </div>
          <p className="text-xs text-[#64748b] mt-1">{t.iacScoreNote}</p>
        </Card>

        {/* Terraform Roadmap */}
        <Card className="bg-[#0f1629] border-[#1e293b] p-5 mb-6">
          <h2 className="text-sm font-semibold text-white mb-5">{t.roadmapTitle}</h2>
          <div className="space-y-0">
            {PHASES.map((p, idx) => {
              const Icon = p.icon;
              const efforts = [t.roadmapEffort1, t.roadmapEffort2, t.roadmapEffort3];
              const resourcesList = [t.roadmapResources1, t.roadmapResources2, t.roadmapResources3];
              const isLast = idx === PHASES.length - 1;
              return (
                <div key={p.phase} className="flex gap-4">
                  {/* Stepper line */}
                  <div className="flex flex-col items-center">
                    <div className="w-8 h-8 rounded-full bg-[#FFD700]/10 border border-[#FFD700]/30 flex items-center justify-center flex-shrink-0 z-10">
                      <span className="text-xs font-bold text-[#FFD700]">{p.phase}</span>
                    </div>
                    {!isLast && (
                      <div className="w-px flex-1 bg-[#1e293b] my-1" style={{ minHeight: "24px" }} />
                    )}
                  </div>
                  {/* Content */}
                  <div className={`flex-1 pb-5 ${isLast ? "" : ""}`}>
                    <div className="flex items-start justify-between gap-3 mb-2">
                      <div className="flex items-center gap-2">
                        <Icon size={14} className="text-[#FFD700] mt-0.5 flex-shrink-0" />
                        <p className="text-sm font-semibold text-white">
                          {(t as Record<string, string>)[p.labelKey]}
                        </p>
                      </div>
                      <Badge className="text-[9px] bg-green-500/10 text-green-400 border-green-500/20 flex-shrink-0">
                        {p.scoreGain} pt
                      </Badge>
                    </div>
                    <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-[#64748b] mb-2">
                      <span>{t.roadmapEffort}: <span className="text-[#94a3b8]">{efforts[idx]}</span></span>
                      <span>{t.roadmapResources}: <span className="text-[#94a3b8]">{p.files.length}</span></span>
                    </div>
                    <p className="text-[10px] text-[#475569] mb-3 font-mono">{resourcesList[idx]}</p>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => {
                        const code = p.code;
                        const blob = new Blob([code], { type: "text/plain" });
                        const url = URL.createObjectURL(blob);
                        const a = document.createElement("a");
                        a.href = url;
                        a.download = `faultray-phase${p.phase}-remediation.tf`;
                        a.click();
                        URL.revokeObjectURL(url);
                      }}
                      className="h-7 text-xs border-[#1e293b] text-[#94a3b8] hover:text-white"
                    >
                      <Download size={12} className="mr-1" />
                      {t.roadmapDownload}
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left column: Input + Format */}
          <div className="lg:col-span-1 space-y-6">
            {/* Section 1: Input */}
            <Card className="bg-[#0f1629] border-[#1e293b] p-5">
              <h2 className="text-sm font-semibold text-white mb-4">{t.inputTitle}</h2>

              {/* Mode selector */}
              <div className="space-y-2 mb-4">
                {(["latest", "sample", "paste"] as InputMode[]).map((mode) => (
                  <label
                    key={mode}
                    className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
                      inputMode === mode
                        ? "border-[#FFD700]/40 bg-[#FFD700]/5"
                        : "border-[#1e293b] hover:border-[#334155]"
                    }`}
                  >
                    <input
                      type="radio"
                      name="inputMode"
                      value={mode}
                      checked={inputMode === mode}
                      onChange={() => setInputMode(mode)}
                      className="mt-0.5 accent-[#FFD700]"
                    />
                    <div>
                      <p className="text-sm text-white font-medium">
                        {mode === "latest" ? t.optionLatest : mode === "sample" ? t.optionSample : t.optionPaste}
                      </p>
                      {mode === "latest" && (
                        <p className="text-xs text-[#64748b] mt-0.5">{t.optionLatestDesc}</p>
                      )}
                    </div>
                  </label>
                ))}
              </div>

              {/* Sample topology selector */}
              {inputMode === "sample" && (
                <div className="grid grid-cols-2 gap-2">
                  {(["web-saas", "microservices", "data-pipeline", "multi-region"] as SampleTopology[]).map((topo) => (
                    <button
                      key={topo}
                      onClick={() => setSampleTopology(topo)}
                      className={`px-3 py-2 rounded-lg text-xs font-medium transition-colors border ${
                        sampleTopology === topo
                          ? "border-[#FFD700]/40 bg-[#FFD700]/10 text-[#FFD700]"
                          : "border-[#1e293b] text-[#94a3b8] hover:border-[#334155] hover:text-white"
                      }`}
                    >
                      {topo === "web-saas" ? t.webSaas : topo === "microservices" ? t.microservices : topo === "data-pipeline" ? t.dataPipeline : t.multiRegion}
                    </button>
                  ))}
                </div>
              )}

              {/* YAML paste */}
              {inputMode === "paste" && (
                <textarea
                  className="w-full h-32 bg-[#060b16] border border-[#1e293b] rounded-lg p-3 text-xs text-[#94a3b8] font-mono resize-none focus:outline-none focus:border-[#334155]"
                  placeholder={t.pastePlaceholder}
                  aria-label={t.pastePlaceholder}
                  value={pastedYaml}
                  maxLength={50000}
                  onChange={(e) => setPastedYaml(e.target.value)}
                />
              )}
            </Card>

            {/* Section 2: Format cards */}
            <Card className="bg-[#0f1629] border-[#1e293b] p-5">
              <h2 className="text-sm font-semibold text-white mb-4">{t.formatTitle}</h2>
              <div className="grid grid-cols-2 gap-2">
                {FORMAT_CARDS.map((fmt) => {
                  const Icon = fmt.icon;
                  const isSelected = selectedFormat === fmt.id;
                  return (
                    <div
                      key={fmt.id}
                      className={`relative p-3 rounded-lg border transition-colors ${
                        isSelected
                          ? "border-[#FFD700]/40 bg-[#FFD700]/5"
                          : "border-[#1e293b] hover:border-[#334155]"
                      }`}
                    >
                      {fmt.popular && (
                        <Badge className="absolute -top-2 -right-2 text-[9px] px-1.5 py-0.5 bg-[#FFD700] text-black border-0">
                          Popular
                        </Badge>
                      )}
                      <div className="flex flex-col gap-2">
                        <Icon size={18} className={isSelected ? "text-[#FFD700]" : "text-[#64748b]"} />
                        <p className="text-xs font-medium text-white">{fmt.nameKey}</p>
                        <p className="text-[10px] text-[#64748b] leading-tight">
                          {(t as Record<string, string>)[fmt.descKey]}
                        </p>
                        <Button
                          size="sm"
                          onClick={() => handleGenerate(fmt.id)}
                          className={`w-full text-xs h-7 ${
                            isSelected
                              ? "bg-[#FFD700] text-black hover:bg-[#FFD700]/90"
                              : "bg-[#1e293b] text-[#94a3b8] hover:bg-[#334155] hover:text-white"
                          }`}
                        >
                          {t.generateBtn}
                        </Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          </div>

          {/* Right column: Generated output */}
          <div className="lg:col-span-2 space-y-6">
            {generated ? (
              <>
                {/* Phase tabs */}
                <Card className="bg-[#0f1629] border-[#1e293b] p-5">
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-sm font-semibold text-white">{t.generatedTitle}</h2>
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-[#64748b]">
                        faultray-phase{activePhase}-remediation.tf
                      </span>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={handleCopy}
                        className="h-7 text-xs border-[#1e293b] text-[#94a3b8] hover:text-white"
                      >
                        {copied ? <CheckCircle2 size={12} className="mr-1 text-green-400" /> : <Copy size={12} className="mr-1" />}
                        {copied ? "Copied!" : t.copyBtn}
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={handleDownload}
                        className="h-7 text-xs border-[#1e293b] text-[#94a3b8] hover:text-white"
                      >
                        <Download size={12} className="mr-1" />
                        {t.downloadBtn}
                      </Button>
                    </div>
                  </div>

                  {/* Phase tab buttons */}
                  <div className="flex gap-2 mb-4">
                    {PHASES.map((p) => (
                      <button
                        key={p.phase}
                        onClick={() => setActivePhase(p.phase)}
                        className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                          activePhase === p.phase
                            ? "bg-[#FFD700]/10 text-[#FFD700] border border-[#FFD700]/20"
                            : "text-[#64748b] hover:text-white border border-transparent hover:border-[#1e293b]"
                        }`}
                      >
                        {t.tabPhase} {p.phase}
                      </button>
                    ))}
                  </div>

                  {/* Code block */}
                  <div className="bg-[#060b16] rounded-lg p-4 overflow-x-auto">
                    <pre className="text-xs text-[#94a3b8] font-mono whitespace-pre leading-relaxed">
                      {currentCode.split("\n").map((line, i) => {
                        const isComment = line.trim().startsWith("#");
                        const isKey = /^\s*\w+ *=/.test(line) || /^\s*\w+ *\{/.test(line);
                        const isResource = line.startsWith("resource ");
                        return (
                          <span key={i} className="block">
                            <span className={
                              isComment ? "text-[#475569]" :
                              isResource ? "text-[#38bdf8]" :
                              isKey ? "text-[#a78bfa]" :
                              "text-[#94a3b8]"
                            }>
                              {line}
                            </span>
                          </span>
                        );
                      })}
                    </pre>
                  </div>
                </Card>

                {/* Remediation Plan */}
                <Card className="bg-[#0f1629] border-[#1e293b] p-5">
                  <h2 className="text-sm font-semibold text-white mb-4">{t.remediationTitle}</h2>
                  <p className="text-xs text-[#64748b] mb-4">{t.remediationDesc}</p>

                  <div className="grid grid-cols-3 gap-3 mb-4">
                    <div className="bg-[#060b16] rounded-lg p-3 text-center">
                      <p className="text-xs text-[#64748b] mb-1">{t.scoreFrom}</p>
                      <p className="text-xl font-bold text-white">85.5</p>
                    </div>
                    <div className="bg-[#060b16] rounded-lg p-3 text-center flex flex-col items-center justify-center">
                      <TrendingUp size={20} className="text-green-400 mb-1" />
                      <p className="text-sm font-bold text-green-400">+{totalScore.toFixed(1)}</p>
                    </div>
                    <div className="bg-[#060b16] rounded-lg p-3 text-center">
                      <p className="text-xs text-[#64748b] mb-1">{t.scoreTo}</p>
                      <p className="text-xl font-bold text-[#FFD700]">{(85.5 + totalScore).toFixed(1)}</p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 bg-[#060b16] rounded-lg p-3 mb-4">
                    <DollarSign size={16} className="text-[#64748b]" />
                    <span className="text-xs text-[#64748b]">{t.estimatedCost}:</span>
                    <span className="text-sm font-semibold text-white">$1,830 / mo</span>
                  </div>

                  <div className="space-y-2">
                    {SPOF_FIXES.map((fix) => (
                      <div key={fix.name} className="flex items-center justify-between py-1.5 border-b border-[#1e293b] last:border-0">
                        <div className="flex items-center gap-2">
                          <CheckCircle2 size={14} className="text-green-400" />
                          <span className="text-xs text-[#94a3b8]">{fix.name}</span>
                        </div>
                        <Badge className={`text-[9px] ${
                          fix.impact === "Critical" ? "bg-red-500/10 text-red-400 border-red-500/20" :
                          fix.impact === "High" ? "bg-orange-500/10 text-orange-400 border-orange-500/20" :
                          "bg-yellow-500/10 text-yellow-400 border-yellow-500/20"
                        }`}>
                          {fix.impact}
                        </Badge>
                      </div>
                    ))}
                  </div>
                </Card>

                {/* Phase Breakdown */}
                <Card className="bg-[#0f1629] border-[#1e293b] p-5">
                  <h2 className="text-sm font-semibold text-white mb-4">{t.phasesTitle}</h2>
                  <div className="space-y-3">
                    {PHASES.map((p) => {
                      const Icon = p.icon;
                      return (
                        <div
                          key={p.phase}
                          className={`p-4 rounded-lg border transition-colors cursor-pointer ${
                            activePhase === p.phase
                              ? "border-[#FFD700]/30 bg-[#FFD700]/5"
                              : "border-[#1e293b] hover:border-[#334155]"
                          }`}
                          onClick={() => setActivePhase(p.phase)}
                        >
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <div className="w-6 h-6 rounded-full bg-[#FFD700]/10 flex items-center justify-center">
                                <Icon size={13} className="text-[#FFD700]" />
                              </div>
                              <p className="text-xs font-semibold text-white">
                                {(t as Record<string, string>)[p.labelKey]}
                              </p>
                            </div>
                            <Badge className="text-[9px] bg-green-500/10 text-green-400 border-green-500/20">
                              {p.scoreGain}
                            </Badge>
                          </div>
                          <div className="grid grid-cols-3 gap-2 text-center">
                            <div>
                              <p className="text-[10px] text-[#475569]">{t.filesGenerated}</p>
                              <p className="text-sm font-semibold text-white">{p.files.length}</p>
                            </div>
                            <div>
                              <p className="text-[10px] text-[#475569]">{t.costEstimate}</p>
                              <p className="text-sm font-semibold text-white">{p.costEstimate}</p>
                            </div>
                            <div>
                              <p className="text-[10px] text-[#475569]">{t.scoreGain}</p>
                              <p className="text-sm font-semibold text-green-400">{p.scoreGain}</p>
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-1 mt-2">
                            {p.files.map((f) => (
                              <span key={f} className="text-[9px] text-[#475569] bg-[#0a0e1a] px-1.5 py-0.5 rounded font-mono">
                                {f}
                              </span>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              </>
            ) : (
              <Card className="bg-[#0f1629] border-[#1e293b] p-12 flex flex-col items-center justify-center text-center min-h-[400px]">
                <FileCode2 size={48} className="text-[#1e293b] mb-4" />
                <p className="text-[#64748b] text-sm mb-2">Select a format and click Generate</p>
                <p className="text-[#475569] text-xs">
                  Generated IaC will appear here with syntax highlighting
                </p>
              </Card>
            )}
          </div>
        </div>
      </div>
    </main>
  );
}
