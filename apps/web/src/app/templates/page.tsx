"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import {
  LayoutTemplate,
  DollarSign,
  Activity,
  Heart,
  ShoppingCart,
  Layers,
  Radio,
  Building2,
  Search,
  ChevronRight,
  Shield,
  Server,
  Database,
  Cloud,
  ArrowRight,
} from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";
import { useRouter } from "next/navigation";

/* ------------------------------------------------------------------ */
/*  Template data                                                      */
/* ------------------------------------------------------------------ */

type IndustryFilter = "all" | "fintech" | "healthcare" | "ecommerce" | "saas" | "media" | "enterprise";

interface Template {
  id: string;
  industry: Exclude<IndustryFilter, "all">;
  icon: React.ElementType;
  iconColor: string;
  nameKey: string;
  descKey: string;
  componentCount: number;
  compliance: string[];
  resilienceScore: number;
  monthlyEst: string;
  yaml: string;
}

const TEMPLATES: Template[] = [
  {
    id: "fintech-trading",
    industry: "fintech",
    icon: DollarSign,
    iconColor: "text-yellow-400",
    nameKey: "fintechName",
    descKey: "fintechDesc",
    componentCount: 18,
    compliance: ["DORA", "PCI DSS", "SOX"],
    resilienceScore: 94,
    monthlyEst: "$4,200",
    yaml: `topology:\n  name: FinTech Trading Platform\n  components:\n    - id: api-gateway\n      type: aws_api_gateway\n    - id: trading-engine\n      type: aws_ecs_service\n    - id: rds-primary\n      type: aws_db_instance\n      multi_az: true\n    - id: rds-replica\n      type: aws_db_instance\n      replicate_source_db: rds-primary\n    - id: redis-sentinel\n      type: aws_elasticache_replication_group`,
  },
  {
    id: "healthcare-ehr",
    industry: "healthcare",
    icon: Heart,
    iconColor: "text-red-400",
    nameKey: "healthcareName",
    descKey: "healthcareDesc",
    componentCount: 22,
    compliance: ["HIPAA", "SOC2", "HITRUST"],
    resilienceScore: 91,
    monthlyEst: "$5,800",
    yaml: `topology:\n  name: Healthcare EHR System\n  components:\n    - id: ehr-api\n      type: aws_ecs_service\n      encryption: true\n    - id: patient-db\n      type: aws_rds_cluster\n      storage_encrypted: true\n    - id: audit-log\n      type: aws_cloudwatch_log_group\n      retention_days: 2555\n    - id: phi-vault\n      type: aws_secretsmanager_secret`,
  },
  {
    id: "ecommerce-checkout",
    industry: "ecommerce",
    icon: ShoppingCart,
    iconColor: "text-green-400",
    nameKey: "ecommerceName",
    descKey: "ecommerceDesc",
    componentCount: 16,
    compliance: ["PCI DSS", "GDPR"],
    resilienceScore: 89,
    monthlyEst: "$2,900",
    yaml: `topology:\n  name: E-Commerce Checkout\n  components:\n    - id: storefront\n      type: aws_cloudfront_distribution\n    - id: payment-api\n      type: aws_ecs_service\n    - id: tokenization\n      type: aws_lambda_function\n    - id: fraud-detection\n      type: aws_sagemaker_endpoint\n    - id: order-db\n      type: aws_rds_cluster`,
  },
  {
    id: "saas-multitenant",
    industry: "saas",
    icon: Layers,
    iconColor: "text-blue-400",
    nameKey: "saasName",
    descKey: "saasDesc",
    componentCount: 20,
    compliance: ["SOC2", "ISO 27001"],
    resilienceScore: 92,
    monthlyEst: "$3,500",
    yaml: `topology:\n  name: SaaS Multi-Tenant Platform\n  components:\n    - id: tenant-router\n      type: aws_api_gateway\n    - id: app-cluster\n      type: aws_ecs_cluster\n    - id: tenant-db\n      type: aws_rds_cluster\n    - id: auth-service\n      type: aws_cognito_user_pool\n    - id: audit-trail\n      type: aws_cloudtrail`,
  },
  {
    id: "media-streaming",
    industry: "media",
    icon: Radio,
    iconColor: "text-purple-400",
    nameKey: "mediaName",
    descKey: "mediaDesc",
    componentCount: 14,
    compliance: ["COPPA", "GDPR"],
    resilienceScore: 87,
    monthlyEst: "$6,100",
    yaml: `topology:\n  name: Media Streaming Platform\n  components:\n    - id: cdn\n      type: aws_cloudfront_distribution\n    - id: origin\n      type: aws_s3_bucket\n    - id: transcoder\n      type: aws_mediaconvert_queue\n    - id: streaming-server\n      type: aws_medialive_channel\n    - id: analytics\n      type: aws_kinesis_stream`,
  },
  {
    id: "enterprise-hybrid",
    industry: "enterprise",
    icon: Building2,
    iconColor: "text-orange-400",
    nameKey: "enterpriseName",
    descKey: "enterpriseDesc",
    componentCount: 25,
    compliance: ["ISO 27001", "SOC2", "NIST"],
    resilienceScore: 88,
    monthlyEst: "$7,400",
    yaml: `topology:\n  name: Enterprise Hybrid\n  components:\n    - id: vpn-gateway\n      type: aws_vpn_gateway\n    - id: direct-connect\n      type: aws_dx_connection\n    - id: sso\n      type: aws_iam_identity_center\n    - id: logging\n      type: aws_cloudwatch_log_group\n    - id: on-prem-server\n      type: on_premises_server`,
  },
];

const INDUSTRY_FILTERS: { id: IndustryFilter; label: string; icon: React.ElementType }[] = [
  { id: "all", label: "All", icon: LayoutTemplate },
  { id: "fintech", label: "FinTech", icon: DollarSign },
  { id: "healthcare", label: "Healthcare", icon: Heart },
  { id: "ecommerce", label: "E-Commerce", icon: ShoppingCart },
  { id: "saas", label: "SaaS", icon: Layers },
  { id: "media", label: "Media", icon: Radio },
  { id: "enterprise", label: "Enterprise", icon: Building2 },
];

function ScoreRing({ score }: { score: number }) {
  const color = score >= 90 ? "#4ade80" : score >= 80 ? "#facc15" : "#f87171";
  return (
    <div className="relative inline-flex items-center justify-center w-10 h-10">
      <svg viewBox="0 0 36 36" className="w-10 h-10 -rotate-90">
        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#1e293b" strokeWidth="3" />
        <circle
          cx="18" cy="18" r="15.9" fill="none"
          stroke={color} strokeWidth="3"
          strokeDasharray={`${score} ${100 - score}`}
          strokeLinecap="round"
        />
      </svg>
      <span className="absolute text-[10px] font-bold" style={{ color }}>{score}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  Page                                                               */
/* ------------------------------------------------------------------ */

export default function TemplatesPage() {
  const locale = useLocale();
  const t = (appDict.templates as Record<string, Record<string, string>>)[locale] ?? appDict.templates.en;
  const router = useRouter();

  const [filter, setFilter] = useState<IndustryFilter>("all");
  const [search, setSearch] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);

  const filtered = TEMPLATES.filter((tpl) => {
    const matchesFilter = filter === "all" || tpl.industry === filter;
    const matchesSearch =
      search === "" ||
      t[tpl.nameKey]?.toLowerCase().includes(search.toLowerCase()) ||
      t[tpl.descKey]?.toLowerCase().includes(search.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  function handleUseTemplate(tpl: Template) {
    // Store YAML in localStorage so /simulate can pick it up
    try {
      localStorage.setItem("faultray_template_yaml", tpl.yaml);
      localStorage.setItem("faultray_template_name", t[tpl.nameKey] ?? tpl.id);
    } catch {}
    router.push("/simulate");
  }

  const previewTemplate = TEMPLATES.find((t) => t.id === previewId);

  return (
    <main className="min-h-screen bg-[#0a0e1a] text-white pt-20 pb-12">
      <div className="max-w-[1200px] mx-auto px-4 sm:px-6">
        {/* Header */}
        <div className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <LayoutTemplate size={28} className="text-[#FFD700]" />
            <h1 className="text-2xl font-bold">{t.title}</h1>
          </div>
          <p className="text-[#94a3b8]">{t.subtitle}</p>
        </div>

        {/* Filter + Search bar */}
        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          <div className="relative flex-1">
            <Search size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#475569]" />
            <input
              type="text"
              placeholder={t.searchPlaceholder}
              aria-label={t.searchPlaceholder}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-[#0f1629] border border-[#1e293b] rounded-lg pl-9 pr-4 py-2.5 text-sm text-white placeholder-[#475569] focus:outline-none focus:border-[#334155]"
            />
          </div>
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
            {INDUSTRY_FILTERS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setFilter(id)}
                className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium whitespace-nowrap transition-colors border ${
                  filter === id
                    ? "border-[#FFD700]/40 bg-[#FFD700]/5 text-[#FFD700]"
                    : "border-[#1e293b] text-[#64748b] hover:border-[#334155] hover:text-white"
                }`}
              >
                <Icon size={13} />
                {label}
              </button>
            ))}
          </div>
        </div>

        {/* Template grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((tpl) => {
            const Icon = tpl.icon;
            return (
              <Card
                key={tpl.id}
                className="bg-[#0f1629] border-[#1e293b] p-5 hover:border-[#334155] transition-colors flex flex-col"
              >
                {/* Card header */}
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-lg bg-[#1e293b] flex items-center justify-center">
                      <Icon size={20} className={tpl.iconColor} />
                    </div>
                    <div>
                      <p className="text-sm font-semibold text-white leading-tight">
                        {t[tpl.nameKey]}
                      </p>
                      <p className="text-[10px] text-[#475569] capitalize mt-0.5">{tpl.industry}</p>
                    </div>
                  </div>
                  <ScoreRing score={tpl.resilienceScore} />
                </div>

                {/* Description */}
                <p className="text-xs text-[#64748b] leading-relaxed mb-4 flex-1">
                  {t[tpl.descKey]}
                </p>

                {/* Meta row */}
                <div className="flex items-center gap-3 mb-4 text-xs text-[#475569]">
                  <div className="flex items-center gap-1">
                    <Server size={11} />
                    <span>{tpl.componentCount} {t.components}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Database size={11} />
                    <span>{tpl.monthlyEst}</span>
                  </div>
                </div>

                {/* Compliance badges */}
                <div className="flex flex-wrap gap-1.5 mb-4">
                  {tpl.compliance.map((c) => (
                    <Badge
                      key={c}
                      className="text-[9px] px-1.5 py-0.5 bg-[#1e293b] text-[#94a3b8] border-[#334155]"
                    >
                      <Shield size={8} className="mr-1" />
                      {c}
                    </Badge>
                  ))}
                </div>

                {/* Actions */}
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setPreviewId(previewId === tpl.id ? null : tpl.id)}
                    className="flex-1 h-8 text-xs border-[#1e293b] text-[#64748b] hover:text-white hover:border-[#334155]"
                  >
                    {t.preview}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => handleUseTemplate(tpl)}
                    className="flex-1 h-8 text-xs bg-[#FFD700] text-black hover:bg-[#FFD700]/90"
                  >
                    {t.useTemplate}
                    <ArrowRight size={11} className="ml-1" />
                  </Button>
                </div>

                {/* YAML preview */}
                {previewId === tpl.id && (
                  <div className="mt-3 bg-[#060b16] rounded-lg p-3 overflow-x-auto">
                    <pre className="text-[10px] text-[#475569] font-mono leading-relaxed whitespace-pre">
                      {tpl.yaml}
                    </pre>
                  </div>
                )}
              </Card>
            );
          })}
        </div>

        {filtered.length === 0 && (
          <div className="text-center py-16">
            <LayoutTemplate size={40} className="text-[#1e293b] mx-auto mb-3" />
            <p className="text-[#64748b] text-sm">{(t as Record<string, string>).noTemplatesFound ?? "No templates found"}</p>
            <p className="text-[#475569] text-xs mt-1">{(t as Record<string, string>).noTemplatesDesc ?? "Try adjusting your search or industry filter."}</p>
          </div>
        )}

        {/* Info footer */}
        <div className="mt-8 p-4 rounded-lg border border-[#1e293b] bg-[#0f1629] flex items-center gap-3">
          <Cloud size={18} className="text-[#FFD700] shrink-0" />
          <p className="text-xs text-[#64748b]">
            Templates include pre-configured YAML topologies. Click <strong className="text-[#94a3b8]">{t.useTemplate}</strong> to load a template in the simulation engine and run a resilience analysis.
          </p>
          <Link href="/simulate">
            <Button size="sm" variant="secondary" className="border-[#1e293b] text-[#64748b] hover:text-white whitespace-nowrap">
              {t.useTemplate} <ChevronRight size={12} className="ml-1" />
            </Button>
          </Link>
        </div>
      </div>
    </main>
  );
}
