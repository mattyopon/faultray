"use client";

import { useAuth } from "@/components/auth-provider";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  User,
  CreditCard,
  Key,
  Bell,
  Globe,
  Copy,
  Check,
  Trash2,
  Plus,
  AlertTriangle,
  Shield,
  Clock,
  Minus,
  Link2,
  Gift,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useLocale, useSetLocale } from "@/lib/useLocale";
import type { Locale } from "@/i18n/config";
import { appDict } from "@/i18n/app-dict";

const LANGUAGES = [
  { code: "en", label: "English", flag: "\u{1F1FA}\u{1F1F8}" },
  { code: "ja", label: "\u65E5\u672C\u8A9E", flag: "\u{1F1EF}\u{1F1F5}" },
  { code: "de", label: "Deutsch", flag: "\u{1F1E9}\u{1F1EA}" },
  { code: "fr", label: "Fran\u00E7ais", flag: "\u{1F1EB}\u{1F1F7}" },
  { code: "zh", label: "\u4E2D\u6587", flag: "\u{1F1E8}\u{1F1F3}" },
  { code: "ko", label: "\uD55C\uAD6D\uC5B4", flag: "\u{1F1F0}\u{1F1F7}" },
  { code: "es", label: "Espa\u00F1ol", flag: "\u{1F1EA}\u{1F1F8}" },
  { code: "pt", label: "Portugu\u00EAs", flag: "\u{1F1E7}\u{1F1F7}" },
];

function generateApiKey(): string {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  let key = "fray_sk_";
  for (let i = 0; i < 32; i++) {
    key += chars[Math.floor(Math.random() * chars.length)];
  }
  return key;
}

export default function SettingsPage() {
  const { user } = useAuth();
  const router = useRouter();
  const locale = useLocale();
  const setLocale = useSetLocale();
  const t = appDict.settings[locale] ?? appDict.settings.en;

  // API Keys
  const [apiKeys, setApiKeys] = useState<Array<{ key: string; created: string }>>([]);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Notifications — persisted to localStorage (SAAS-04 / RETAIN-02)
  const [notifications, setNotifications] = useState({
    simulationCompleted: true,
    scoreDegradation: true,
    weeklySummary: false,
  });
  const [notificationSaved, setNotificationSaved] = useState(false);

  // Admin plan switch
  const [isAdmin, setIsAdmin] = useState(false);
  const [currentPlan, setCurrentPlan] = useState<string>("free");
  const [switchingPlan, setSwitchingPlan] = useState(false);

  // Trial state
  const [trialEndsAt, setTrialEndsAt] = useState<string | null>(null);
  const trialDaysLeft = trialEndsAt
    ? Math.max(0, Math.ceil((new Date(trialEndsAt).getTime() - Date.now()) / (1000 * 60 * 60 * 24)))
    : 0;
  const isTrialActive = trialEndsAt ? new Date(trialEndsAt).getTime() > Date.now() : false;

  const fetchProfile = useCallback(async () => {
    if (!user) return;
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const { data } = await supabase
        .from("profiles")
        .select("plan, trial_ends_at")
        .eq("id", user.id)
        .single();
      if (data) {
        setCurrentPlan(data.plan || "free");
        setTrialEndsAt(data.trial_ends_at || null);
      }
    } catch {
      // Supabase not configured
    }
    try {
      const res = await fetch("/api/health", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: user.email }),
      });
      const { is_admin } = await res.json();
      setIsAdmin(!!is_admin);
    } catch {
      setIsAdmin(false);
    }
  }, [user]);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const [planFeedback, setPlanFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Coupon code
  const [couponCode, setCouponCode] = useState("");
  const [redeemingCoupon, setRedeemingCoupon] = useState(false);
  const [couponFeedback, setCouponFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  async function handlePlanSwitch(plan: string) {
    if (!user?.email) return;
    setSwitchingPlan(true);
    setPlanFeedback(null);
    try {
      const res = await fetch("/api/health", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: "switch-plan", email: user.email, plan }),
      });
      const data = await res.json();
      if (data.error) {
        setPlanFeedback({ type: "error", message: data.error });
        return;
      }
      await fetchProfile();
      setPlanFeedback({
        type: "success",
        message: locale === "ja"
          ? `プランを ${plan.charAt(0).toUpperCase() + plan.slice(1)} に変更しました`
          : `Plan switched to ${plan.charAt(0).toUpperCase() + plan.slice(1)}`,
      });
      setTimeout(() => setPlanFeedback(null), 3000);
    } catch {
      setPlanFeedback({ type: "error", message: locale === "ja" ? "プラン変更に失敗しました" : "Failed to switch plan" });
    } finally {
      setSwitchingPlan(false);
    }
  }

  async function handleRedeemCoupon() {
    setRedeemingCoupon(true);
    setCouponFeedback(null);
    try {
      const res = await fetch("/api/coupon/redeem", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: couponCode }),
      });
      const data = await res.json() as { success?: boolean; tier?: string; expires_at?: string; error?: string };
      if (data.success && data.tier && data.expires_at) {
        setCouponFeedback({
          type: "success",
          message:
            locale === "ja"
              ? `${data.tier} プランが ${new Date(data.expires_at).toLocaleDateString("ja-JP")} まで有効になりました`
              : `${data.tier} plan active until ${new Date(data.expires_at).toLocaleDateString()}`,
        });
        setCouponCode("");
        fetchProfile();
      } else {
        setCouponFeedback({ type: "error", message: data.error ?? "Failed to apply coupon" });
      }
    } catch {
      setCouponFeedback({ type: "error", message: "Failed to apply coupon" });
    }
    setRedeemingCoupon(false);
  }

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  // Integration settings
  const [integrations, setIntegrations] = useState({
    jiraDomain: "",
    backlogSpace: "",
    slackWebhook: "",
  });
  const [integrationsSaved, setIntegrationsSaved] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem("faultray_integrations");
      if (raw) {
        const parsed = JSON.parse(raw);
        setIntegrations({
          jiraDomain: parsed.jiraDomain || "",
          backlogSpace: parsed.backlogSpace || "",
          slackWebhook: parsed.slackWebhook || "",
        });
      }
    } catch {
      // ignore
    }
    // Restore notification preferences (SAAS-04)
    try {
      const notifRaw = localStorage.getItem("faultray_notifications");
      if (notifRaw) {
        const parsed = JSON.parse(notifRaw);
        setNotifications({
          simulationCompleted: parsed.simulationCompleted ?? true,
          scoreDegradation: parsed.scoreDegradation ?? true,
          weeklySummary: parsed.weeklySummary ?? false,
        });
      }
    } catch {
      // ignore
    }
  }, []);

  function handleSaveIntegrations() {
    // Validate slackWebhook URL before saving (SSRF prevention)
    if (
      integrations.slackWebhook &&
      !integrations.slackWebhook.startsWith("https://hooks.slack.com/")
    ) {
      alert("Slack Webhook URL must start with https://hooks.slack.com/");
      return;
    }
    localStorage.setItem("faultray_integrations", JSON.stringify(integrations));
    setIntegrationsSaved(true);
    setTimeout(() => setIntegrationsSaved(false), 2500);
  }

  function setLanguage(lang: string) {
    setLocale(lang as Locale);
  }

  function handleGenerateKey() {
    const newKey = generateApiKey();
    setApiKeys((prev) => [
      { key: newKey, created: new Date().toLocaleDateString() },
      ...prev,
    ]);
  }

  function handleCopyKey(key: string) {
    navigator.clipboard.writeText(key);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  }

  function handleDeleteKey(key: string) {
    setApiKeys((prev) => prev.filter((k) => k.key !== key));
  }

  function toggleNotification(key: keyof typeof notifications) {
    setNotifications((prev) => {
      const next = { ...prev, [key]: !prev[key] };
      // Persist to localStorage so the setting survives page reloads (SAAS-04)
      try { localStorage.setItem("faultray_notifications", JSON.stringify(next)); } catch { /* ignore */ }
      setNotificationSaved(true);
      setTimeout(() => setNotificationSaved(false), 2000);
      return next;
    });
  }

  return (
    <div className="max-w-[800px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1">{t.title}</h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {/* Language */}
      <Card className="mb-6">
        <div className="flex items-center gap-3 mb-6">
          <Globe size={20} className="text-[#FFD700]" />
          <h2 className="text-lg font-bold">{t.language}</h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => setLanguage(lang.code)}
              className={`flex items-center gap-2 px-4 py-3 rounded-lg border transition-all text-sm ${
                locale === lang.code
                  ? "border-[#FFD700] bg-[#FFD700]/10 text-white"
                  : "border-[#1e293b] text-[#94a3b8] hover:border-[#64748b] hover:text-white"
              }`}
            >
              <span className="text-lg">{lang.flag}</span>
              <span>{lang.label}</span>
            </button>
          ))}
        </div>
      </Card>

      {/* Profile */}
      <Card className="mb-6">
        <div className="flex items-center gap-3 mb-6">
          <User size={20} className="text-[#FFD700]" />
          <h2 className="text-lg font-bold">{t.profile}</h2>
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">{t.email}</span>
            <span className="text-sm">{user?.email || t.notSignedIn}</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">{t.name}</span>
            <span className="text-sm">{user?.user_metadata?.full_name || t.notSet}</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">{t.provider}</span>
            <span className="text-sm capitalize">{user?.app_metadata?.provider || "N/A"}</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">{t.memberSince}</span>
            <span className="text-sm">
              {user?.created_at ? new Date(user.created_at).toLocaleDateString() : "N/A"}
            </span>
          </div>
        </div>
      </Card>

      {/* Subscription */}
      <Card className="mb-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <CreditCard size={20} className="text-[#FFD700]" />
            <h2 className="text-lg font-bold">{t.subscription}</h2>
          </div>
          <Badge variant="gold">{currentPlan.charAt(0).toUpperCase() + currentPlan.slice(1)} Plan</Badge>
        </div>
        {isTrialActive && (
          <div className="flex items-center gap-2 px-4 py-3 mb-4 rounded-lg bg-[#FFD700]/10 border border-[#FFD700]/20">
            <Clock size={16} className="text-[#FFD700]" />
            <span className="text-sm text-[#FFD700] font-medium">
              {t.proTrial} {trialDaysLeft} {t.trialRemaining}
            </span>
          </div>
        )}

        {/* Plan comparison table */}
        {(() => {
          const plans = [
            { id: "free", name: "Free", price: "$0", features: [
              { label: locale === "ja" ? "シミュレーション" : "Simulations", value: locale === "ja" ? "月5回" : "5 / month" },
              { label: locale === "ja" ? "コンポーネント" : "Components", value: locale === "ja" ? "最大5個" : "Up to 5" },
              { label: locale === "ja" ? "DORAレポート" : "DORA Report", value: false },
              { label: locale === "ja" ? "AI分析" : "AI Analysis", value: false },
              { label: locale === "ja" ? "カスタムSSO" : "Custom SSO", value: false },
              { label: locale === "ja" ? "保険API" : "Insurance API", value: false },
              { label: locale === "ja" ? "サポート" : "Support", value: locale === "ja" ? "コミュニティ" : "Community" },
            ]},
            { id: "pro", name: "Pro", price: "$299/mo", features: [
              { label: locale === "ja" ? "シミュレーション" : "Simulations", value: locale === "ja" ? "月100回" : "100 / month" },
              { label: locale === "ja" ? "コンポーネント" : "Components", value: locale === "ja" ? "最大50個" : "Up to 50" },
              { label: locale === "ja" ? "DORAレポート" : "DORA Report", value: "PDF" },
              { label: locale === "ja" ? "AI分析" : "AI Analysis", value: true },
              { label: locale === "ja" ? "カスタムSSO" : "Custom SSO", value: false },
              { label: locale === "ja" ? "保険API" : "Insurance API", value: false },
              { label: locale === "ja" ? "サポート" : "Support", value: locale === "ja" ? "メール24h" : "Email (24h)" },
            ]},
            { id: "business", name: "Business", price: "$999/mo", features: [
              { label: locale === "ja" ? "シミュレーション" : "Simulations", value: locale === "ja" ? "無制限" : "Unlimited" },
              { label: locale === "ja" ? "コンポーネント" : "Components", value: locale === "ja" ? "無制限" : "Unlimited" },
              { label: locale === "ja" ? "DORAレポート" : "DORA Report", value: "PDF + API" },
              { label: locale === "ja" ? "AI分析" : "AI Analysis", value: true },
              { label: locale === "ja" ? "カスタムSSO" : "Custom SSO", value: true },
              { label: locale === "ja" ? "保険API" : "Insurance API", value: true },
              { label: locale === "ja" ? "サポート" : "Support", value: locale === "ja" ? "専任1h" : "Dedicated (1h)" },
            ]},
          ];
          return (
            <div className="mb-6">
              <div className="grid grid-cols-3 gap-3">
                {plans.map((plan) => {
                  const isCurrent = currentPlan === plan.id;
                  return (
                    <div
                      key={plan.id}
                      className={`rounded-xl border p-4 transition-all ${
                        isCurrent
                          ? "border-[#FFD700] bg-[#FFD700]/5"
                          : "border-[#1e293b] bg-[#0d1117]"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-3">
                        <span className={`text-sm font-bold ${isCurrent ? "text-[#FFD700]" : "text-white"}`}>{plan.name}</span>
                        <span className="text-xs text-[#64748b]">{plan.price}</span>
                      </div>
                      {isCurrent && (
                        <div className="text-[10px] text-[#FFD700] bg-[#FFD700]/10 rounded px-2 py-0.5 inline-block mb-3">
                          {locale === "ja" ? "現在のプラン" : "Current"}
                        </div>
                      )}
                      <div className="space-y-2">
                        {plan.features.map((f) => (
                          <div key={f.label} className="flex items-center justify-between text-xs">
                            <span className="text-[#64748b]">{f.label}</span>
                            {f.value === true ? (
                              <Check size={14} className="text-emerald-400" />
                            ) : f.value === false ? (
                              <Minus size={14} className="text-[#334155]" />
                            ) : (
                              <span className="text-[#e2e8f0] font-medium">{f.value}</span>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })()}

        <Link href="/pricing">
          <Button size="sm">
            <CreditCard size={14} /> {t.upgradePro}
          </Button>
        </Link>

        {/* Coupon Code */}
        <div className="mt-6 pt-6 border-t border-[#1e293b]">
          <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
            <Gift size={16} className="text-[#FFD700]" />
            {locale === "ja" ? "クーポンコード" : "Coupon Code"}
          </h3>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="FRAY-XXXX-XXXX-XXXX"
              value={couponCode}
              onChange={(e) => setCouponCode(e.target.value.toUpperCase())}
              className="flex-1 px-3 py-2 rounded-lg bg-[#0d1117] border border-[#1e293b] text-white text-sm placeholder-[#475569] focus:border-[#FFD700] focus:outline-none"
            />
            <Button onClick={handleRedeemCoupon} disabled={!couponCode || redeemingCoupon} size="sm">
              {redeemingCoupon
                ? (locale === "ja" ? "適用中..." : "Applying...")
                : (locale === "ja" ? "適用" : "Apply")}
            </Button>
          </div>
          {couponFeedback && (
            <div className={`mt-2 text-sm ${couponFeedback.type === "success" ? "text-emerald-400" : "text-red-400"}`}>
              {couponFeedback.message}
            </div>
          )}
        </div>

        {isAdmin && (
          <div className="mt-6 pt-6 border-t border-[#1e293b]">
            <div className="flex items-center gap-2 mb-3">
              <Shield size={16} className="text-red-400" />
              <span className="text-sm font-semibold text-red-400">{t.adminSwitch}</span>
            </div>
            <div className="flex gap-2">
              {(["free", "pro", "business"] as const).map((plan) => (
                <button
                  key={plan}
                  disabled={switchingPlan || currentPlan === plan}
                  onClick={() => handlePlanSwitch(plan)}
                  className={`px-4 py-2 text-sm rounded-lg font-medium transition-all ${
                    currentPlan === plan
                      ? "bg-[#FFD700] text-[#0a0e1a]"
                      : "border border-[#1e293b] text-[#94a3b8] hover:border-[#64748b] hover:text-white disabled:opacity-50"
                  }`}
                >
                  {switchingPlan ? "..." : plan.charAt(0).toUpperCase() + plan.slice(1)}
                </button>
              ))}
            </div>
            {planFeedback && (
              <div className={`mt-3 px-4 py-2 rounded-lg text-sm font-medium ${
                planFeedback.type === "success"
                  ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                  : "bg-red-500/10 text-red-400 border border-red-500/20"
              }`}>
                {planFeedback.message}
              </div>
            )}
          </div>
        )}
      </Card>

      {/* API Keys */}
      <Card className="mb-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Key size={20} className="text-[#FFD700]" />
            <h2 className="text-lg font-bold">{t.apiKeys}</h2>
          </div>
          <Button variant="secondary" size="sm" onClick={handleGenerateKey}>
            <Plus size={14} /> {t.generateKey}
          </Button>
        </div>
        <p className="text-sm text-[#94a3b8] mb-4">{t.apiKeysDesc}</p>

        {apiKeys.length === 0 ? (
          <div className="p-6 rounded-xl border border-dashed border-[#1e293b] text-center">
            <Key size={20} className="mx-auto mb-2 text-[#64748b]" />
            <p className="text-sm text-[#94a3b8]">{t.noApiKeys}</p>
            <p className="text-xs text-[#64748b]">{t.noApiKeysDesc}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {apiKeys.map((k) => (
              <div key={k.key} className="flex items-center gap-3 p-3 rounded-lg bg-[#0d1117] border border-[#1e293b]">
                <code className="flex-1 text-sm font-mono text-[#e2e8f0] truncate">{k.key}</code>
                <span className="text-xs text-[#64748b] shrink-0">{t.created} {k.created}</span>
                <button
                  onClick={() => handleCopyKey(k.key)}
                  className="p-1.5 rounded-md hover:bg-white/10 transition-colors text-[#64748b] hover:text-white"
                  title="Copy"
                >
                  {copiedKey === k.key ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                </button>
                <button
                  onClick={() => handleDeleteKey(k.key)}
                  className="p-1.5 rounded-md hover:bg-red-500/10 transition-colors text-[#64748b] hover:text-red-400"
                  title="Delete"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* Notifications */}
      <Card className="mb-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Bell size={20} className="text-[#FFD700]" />
            <h2 className="text-lg font-bold">{t.notifications}</h2>
          </div>
          {notificationSaved && (
            <span className="text-xs text-emerald-400 font-medium flex items-center gap-1">
              <Check size={12} /> {locale === "ja" ? "保存しました" : "Saved"}
            </span>
          )}
        </div>
        <div className="space-y-4">
          {([
            { key: "simulationCompleted" as const, label: t.simCompleted, desc: t.simCompletedDesc },
            { key: "scoreDegradation" as const, label: t.scoreDegradation, desc: t.scoreDegradationDesc },
            { key: "weeklySummary" as const, label: t.weeklySummary, desc: t.weeklySummaryDesc },
          ]).map((n) => (
            <div key={n.key} className="flex items-center justify-between py-2">
              <div>
                <p className="text-sm font-medium">{n.label}</p>
                <p className="text-xs text-[#64748b]">{n.desc}</p>
              </div>
              <button
                onClick={() => toggleNotification(n.key)}
                className={`relative w-11 h-6 rounded-full transition-colors ${
                  notifications[n.key] ? "bg-[#FFD700]" : "bg-[#1e293b]"
                }`}
              >
                <span
                  className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-transform ${
                    notifications[n.key] ? "left-[22px]" : "left-0.5"
                  }`}
                />
              </button>
            </div>
          ))}
        </div>
      </Card>

      {/* Integrations */}
      <Card className="mb-6">
        <div className="flex items-center gap-3 mb-6">
          <Link2 size={20} className="text-[#FFD700]" />
          <h2 className="text-lg font-bold">{t.integrations}</h2>
        </div>
        <p className="text-sm text-[#94a3b8] mb-6">{t.integrationsDesc}</p>
        <div className="space-y-4">
          <div>
            <label className="block text-sm text-[#64748b] mb-1">{t.jiraDomain}</label>
            <input
              type="text"
              value={integrations.jiraDomain}
              onChange={(e) => setIntegrations({ ...integrations, jiraDomain: e.target.value })}
              className="w-full bg-white/[0.05] border border-[#1e293b] rounded-lg px-3 py-2 text-sm text-white focus:border-[#FFD700] focus:outline-none"
              placeholder={t.jiraDomainPlaceholder}
            />
          </div>
          <div>
            <label className="block text-sm text-[#64748b] mb-1">{t.backlogSpace}</label>
            <input
              type="text"
              value={integrations.backlogSpace}
              onChange={(e) => setIntegrations({ ...integrations, backlogSpace: e.target.value })}
              className="w-full bg-white/[0.05] border border-[#1e293b] rounded-lg px-3 py-2 text-sm text-white focus:border-[#FFD700] focus:outline-none"
              placeholder={t.backlogSpacePlaceholder}
            />
          </div>
          <div>
            <label className="block text-sm text-[#64748b] mb-1">{t.slackWebhook}</label>
            <input
              type="text"
              value={integrations.slackWebhook}
              onChange={(e) => setIntegrations({ ...integrations, slackWebhook: e.target.value })}
              className="w-full bg-white/[0.05] border border-[#1e293b] rounded-lg px-3 py-2 text-sm text-white focus:border-[#FFD700] focus:outline-none"
              placeholder={t.slackWebhookPlaceholder}
            />
          </div>
          <div className="flex items-center gap-3">
            <Button size="sm" onClick={handleSaveIntegrations}>
              <Check size={14} />
              {t.saveIntegrations}
            </Button>
            {integrationsSaved && (
              <span className="text-sm text-emerald-400 font-medium">{t.integrationsSaved}</span>
            )}
          </div>
        </div>
      </Card>

      {/* Danger Zone */}
      <Card className="border-red-500/20">
        <h2 className="text-lg font-bold text-red-400 mb-4">{t.dangerZone}</h2>
        {!showDeleteConfirm ? (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">{t.deleteAccount}</p>
              <p className="text-xs text-[#64748b]">{t.deleteAccountDesc}</p>
            </div>
            <Button variant="danger" size="sm" onClick={() => setShowDeleteConfirm(true)}>
              {t.deleteAccount}
            </Button>
          </div>
        ) : (
          <div className="p-4 rounded-xl bg-red-500/5 border border-red-500/20">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle size={16} className="text-red-400" />
              <p className="text-sm font-medium text-red-400">{t.areYouSure}</p>
            </div>
            <p className="text-xs text-[#94a3b8] mb-4">{t.deleteConfirm}</p>
            <div className="flex gap-3">
              <Button variant="danger" size="sm" onClick={async () => {
                try {
                  const res = await fetch("/api/account/delete", {
                    method: "DELETE",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ confirm: true }),
                  });
                  if (res.ok) {
                    // Session is gone — redirect to home
                    router.push("/");
                  } else {
                    const data = await res.json().catch(() => ({})) as { error?: string };
                    alert(data.error || "Account deletion failed. Please contact support.");
                    setShowDeleteConfirm(false);
                  }
                } catch {
                  alert("Network error. Please try again or contact support.");
                  setShowDeleteConfirm(false);
                }
              }}>
                {t.yesDelete}
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setShowDeleteConfirm(false)}>
                {t.cancel}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
