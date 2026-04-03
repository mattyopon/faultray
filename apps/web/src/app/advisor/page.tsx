"use client";

import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useState, useRef, useEffect } from "react";
import { api } from "@/lib/api";
import { Bot, Send, Loader2, User, Zap, Target, Server, Cloud, Globe, Shield } from "lucide-react";
import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

interface Message {
  role: "user" | "assistant";
  content: string;
  sources?: string[];
  actions?: Array<{ label: string; href: string }>;
}

const SUGGESTIONS = [
  "How can I improve my resilience score?",
  "What is FaultRay?",
  "Explain the availability model",
  "How should I configure replicas?",
  "What is a circuit breaker pattern?",
  "How does failover work?",
];

// ---- Configuration Wizard data ----
const WIZARD_INDUSTRIES = [
  { key: "saas", en: "SaaS", ja: "SaaS", icon: Cloud },
  { key: "ec", en: "E-commerce", ja: "EC・小売", icon: Globe },
  { key: "api", en: "API Platform", ja: "APIプラットフォーム", icon: Server },
  { key: "mobile", en: "Mobile App", ja: "モバイルアプリ", icon: Zap },
  { key: "finance", en: "Finance", ja: "金融", icon: Shield },
] as const;

const WIZARD_CHALLENGES = [
  { key: "k8s", en: "Should I migrate to K8s?", ja: "K8sに移行すべき？" },
  { key: "ecs_lambda", en: "ECS vs Lambda?", ja: "ECS vs Lambda？" },
  { key: "scale", en: "Auto-scaling setup", ja: "オートスケーリング設計" },
  { key: "ha", en: "High availability design", ja: "高可用性設計" },
  { key: "cost", en: "Cost optimization", ja: "コスト最適化" },
] as const;

type WizardIndustry = typeof WIZARD_INDUSTRIES[number]["key"];
type WizardChallenge = typeof WIZARD_CHALLENGES[number]["key"];

interface WizardRecommendation {
  title: string;
  titleJa: string;
  desc: string;
  descJa: string;
  services: string[];
  score: number;
}

const RECOMMENDATIONS: Record<string, Record<string, WizardRecommendation>> = {
  k8s: {
    saas: { title: "EKS + Fargate recommended", titleJa: "EKS + Fargate を推奨", desc: "For SaaS with 10+ microservices, K8s provides better orchestration. Start with Fargate to minimize ops overhead.", descJa: "10以上のマイクロサービスを持つSaaSにはK8sが最適。Fargateから始めて運用負荷を最小化。", services: ["EKS", "Fargate", "ALB", "ECR", "CloudWatch"], score: 91 },
    ec: { title: "ECS recommended over K8s", titleJa: "K8sよりECSを推奨", desc: "E-commerce typically has fewer services. ECS is simpler and sufficient for most retail workloads.", descJa: "ECサイトはサービス数が少なく、ECSの方がシンプルで十分。", services: ["ECS", "ALB", "RDS Multi-AZ", "ElastiCache"], score: 87 },
    _default: { title: "Evaluate based on team size", titleJa: "チーム規模で判断", desc: "K8s needs 2+ dedicated engineers. If your team < 5, stick with ECS or Lambda.", descJa: "K8sには専任2名以上が必要。チーム5名未満ならECSかLambdaを推奨。", services: ["ECS or EKS", "ALB", "CloudWatch"], score: 85 },
  },
  ecs_lambda: {
    saas: { title: "ECS for long-running, Lambda for events", titleJa: "常駐はECS、イベント処理はLambda", desc: "Use ECS for API servers (predictable load). Lambda for webhooks, cron, async processing.", descJa: "APIサーバーはECS(予測可能な負荷)。Webhook・cron・非同期処理はLambda。", services: ["ECS Fargate", "Lambda", "API Gateway", "SQS"], score: 89 },
    _default: { title: "Hybrid ECS + Lambda", titleJa: "ECS + Lambda ハイブリッド", desc: "Most workloads benefit from both. ECS for core services, Lambda for glue and events.", descJa: "多くのワークロードは両方を活用。コアサービスはECS、接着剤・イベント処理はLambda。", services: ["ECS", "Lambda", "EventBridge"], score: 86 },
  },
  scale: {
    _default: { title: "Target Tracking + Scheduled Scaling", titleJa: "ターゲット追跡 + スケジュールスケーリング", desc: "Use Target Tracking for CPU/request-based scaling. Add Scheduled Scaling for known traffic patterns.", descJa: "CPU/リクエスト数ベースのターゲット追跡スケーリング。既知のトラフィックパターンにはスケジュールスケーリングを追加。", services: ["ASG", "Target Tracking", "CloudWatch Alarms"], score: 88 },
  },
  ha: {
    finance: { title: "Multi-AZ + Multi-Region DR", titleJa: "マルチAZ + マルチリージョンDR", desc: "Financial services require multi-region failover with RTO < 15min. Use Route53 health checks.", descJa: "金融サービスにはRTO 15分以内のマルチリージョンフェイルオーバーが必要。Route53ヘルスチェックを使用。", services: ["Multi-AZ RDS", "Route53", "S3 CRR", "Global Accelerator"], score: 95 },
    _default: { title: "Multi-AZ with automated failover", titleJa: "マルチAZ + 自動フェイルオーバー", desc: "Deploy across 2+ AZs. Use RDS Multi-AZ, ElastiCache replication, and ALB health checks.", descJa: "2つ以上のAZにデプロイ。RDS Multi-AZ、ElastiCacheレプリケーション、ALBヘルスチェックを使用。", services: ["Multi-AZ", "ALB", "RDS", "ElastiCache"], score: 90 },
  },
  cost: {
    _default: { title: "Right-sizing + Reserved Instances", titleJa: "ライトサイジング + リザーブドインスタンス", desc: "Start with right-sizing (most orgs are 30-40% over-provisioned). Then commit to 1-year Reserved or Savings Plans.", descJa: "まずライトサイジング(多くの組織は30-40%過剰プロビジョニング)。次に1年リザーブドまたはSavings Plansを適用。", services: ["Compute Optimizer", "Cost Explorer", "Savings Plans"], score: 85 },
  },
};

function getRecommendation(challenge: WizardChallenge, industry: WizardIndustry): WizardRecommendation {
  const challengeRecs = RECOMMENDATIONS[challenge];
  if (!challengeRecs) return RECOMMENDATIONS.ha._default;
  return challengeRecs[industry] ?? challengeRecs._default ?? RECOMMENDATIONS.ha._default;
}

export default function AdvisorPage() {
  const locale = useLocale();
  const ta = appDict.advisor[locale] ?? appDict.advisor.en;
  const isJa = locale === "ja";
  const [wizardIndustry, setWizardIndustry] = useState<WizardIndustry | null>(null);
  const [wizardChallenge, setWizardChallenge] = useState<WizardChallenge | null>(null);
  const wizardResult = wizardIndustry && wizardChallenge ? getRecommendation(wizardChallenge, wizardIndustry) : null;
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: ta.greeting,
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = async (text?: string) => {
    const message = text || input;
    if (!message.trim() || loading) return;

    const userMsg: Message = { role: "user", content: message };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await api.chat(message);
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.response,
          sources: res.sources,
          actions: res.suggested_actions,
        },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: ta.fallback,
        },
      ]);
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  return (
    <div className="max-w-[900px] mx-auto px-6 py-10 flex flex-col" style={{ height: "calc(100vh - 64px)" }}>
      <div className="mb-6">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Bot size={24} className="text-[#FFD700]" />
          {ta.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">
          {ta.subtitle}
        </p>
      </div>

      {/* Configuration Wizard */}
      <Card className="mb-6 p-5">
        <h2 className="text-base font-bold mb-4 flex items-center gap-2">
          <Target size={16} className="text-[#FFD700]" />
          {isJa ? "構成提案ウィザード" : "Architecture Advisor Wizard"}
        </h2>

        {/* Step 1: Industry */}
        <div className="mb-4">
          <p className="text-xs text-[#64748b] uppercase tracking-wide mb-2">
            {isJa ? "1. 業種を選択" : "1. Select your industry"}
          </p>
          <div className="flex flex-wrap gap-2">
            {WIZARD_INDUSTRIES.map((ind) => {
              const Icon = ind.icon;
              return (
                <button
                  key={ind.key}
                  onClick={() => setWizardIndustry(ind.key)}
                  className={`inline-flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm transition-all ${
                    wizardIndustry === ind.key
                      ? "border-[#FFD700] bg-[#FFD700]/10 text-[#FFD700]"
                      : "border-[#1e293b] text-[#94a3b8] hover:border-[#334155]"
                  }`}
                >
                  <Icon size={14} />
                  {isJa ? ind.ja : ind.en}
                </button>
              );
            })}
          </div>
        </div>

        {/* Step 2: Challenge */}
        {wizardIndustry && (
          <div className="mb-4">
            <p className="text-xs text-[#64748b] uppercase tracking-wide mb-2">
              {isJa ? "2. 課題を選択" : "2. Select your challenge"}
            </p>
            <div className="flex flex-wrap gap-2">
              {WIZARD_CHALLENGES.map((ch) => (
                <button
                  key={ch.key}
                  onClick={() => setWizardChallenge(ch.key)}
                  className={`px-3 py-2 rounded-lg border text-sm transition-all ${
                    wizardChallenge === ch.key
                      ? "border-[#FFD700] bg-[#FFD700]/10 text-[#FFD700]"
                      : "border-[#1e293b] text-[#94a3b8] hover:border-[#334155]"
                  }`}
                >
                  {isJa ? ch.ja : ch.en}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 3: Result */}
        {wizardResult && (
          <div className="mt-4 p-4 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.03]">
            <div className="flex items-start justify-between mb-3">
              <div>
                <p className="text-sm font-bold text-emerald-300">
                  {isJa ? wizardResult.titleJa : wizardResult.title}
                </p>
                <p className="text-xs text-[#94a3b8] mt-1">
                  {isJa ? wizardResult.descJa : wizardResult.desc}
                </p>
              </div>
              <Badge variant="green">{isJa ? "推定スコア" : "Est. Score"} {wizardResult.score}</Badge>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-3">
              {wizardResult.services.map((s) => (
                <span key={s} className="px-2 py-1 rounded text-[11px] font-mono bg-[#1e293b] text-[#94a3b8]">
                  {s}
                </span>
              ))}
            </div>
            <div className="mt-3 pt-3 border-t border-emerald-500/10">
              <Link href={`/simulate?sample=web-saas`} className="text-xs text-[#FFD700] hover:underline inline-flex items-center gap-1">
                {isJa ? "この構成でシミュレーションを実行 →" : "Simulate this architecture →"}
              </Link>
            </div>
          </div>
        )}
      </Card>

      {/* Chat Messages */}
      <Card className="flex-1 overflow-y-auto mb-4 p-4">
        <div className="space-y-4">
          {messages.map((msg, i) => (
            <div key={i} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}>
              {msg.role === "assistant" && (
                <div className="w-8 h-8 rounded-lg bg-[#FFD700]/10 flex items-center justify-center shrink-0">
                  <Bot size={16} className="text-[#FFD700]" />
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-xl p-4 ${
                  msg.role === "user"
                    ? "bg-[#FFD700]/10 text-[#e2e8f0]"
                    : "bg-white/[0.03] border border-[#1e293b]"
                }`}
              >
                <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
                {msg.actions && msg.actions.length > 0 && (
                  <div className="flex flex-wrap gap-2 mt-3 pt-3 border-t border-[#1e293b]">
                    {msg.actions.map((action) => (
                      <Link key={action.href} href={action.href}>
                        <Button variant="secondary" size="sm">
                          {action.label}
                        </Button>
                      </Link>
                    ))}
                  </div>
                )}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-2 text-xs text-[#64748b]">
                    Sources: {msg.sources.join(", ")}
                  </div>
                )}
              </div>
              {msg.role === "user" && (
                <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center shrink-0">
                  <User size={16} className="text-blue-400" />
                </div>
              )}
            </div>
          ))}
          {loading && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-lg bg-[#FFD700]/10 flex items-center justify-center shrink-0">
                <Bot size={16} className="text-[#FFD700]" />
              </div>
              <div className="bg-white/[0.03] border border-[#1e293b] rounded-xl p-4">
                <Loader2 size={16} className="animate-spin text-[#FFD700]" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </Card>

      {/* Suggestions */}
      {messages.length <= 1 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              onClick={() => sendMessage(s)}
              className="px-3 py-1.5 rounded-full text-xs border border-[#1e293b] text-[#94a3b8] hover:border-[#FFD700]/30 hover:text-[#FFD700] transition-all"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Input */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          sendMessage();
        }}
        className="flex gap-3"
      >
        <div className="flex-1 relative">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={ta.placeholder}
            className="w-full px-4 py-3 bg-[#0d1117] border border-[#1e293b] rounded-xl text-sm text-[#e2e8f0] placeholder-[#3a4558] focus:border-[#FFD700]/50 focus:outline-none pr-16"
            disabled={loading}
            maxLength={500}
            aria-label={ta.placeholder}
          />
          {input.length > 400 && (
            <span className={`absolute right-3 top-1/2 -translate-y-1/2 text-xs ${input.length >= 490 ? "text-red-400" : "text-[#64748b]"}`}>
              {input.length}/500
            </span>
          )}
        </div>
        <Button type="submit" disabled={!input.trim() || loading} aria-label="Send message">
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
        </Button>
      </form>
      <p className="text-xs text-[#475569] mt-2 text-right">
        {locale === "ja" ? "Enter で送信" : "Press Enter to send"}
      </p>
    </div>
  );
}
