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
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import Link from "next/link";

const LANGUAGES = [
  { code: "en", label: "English", flag: "🇺🇸" },
  { code: "ja", label: "日本語", flag: "🇯🇵" },
  { code: "de", label: "Deutsch", flag: "🇩🇪" },
  { code: "fr", label: "Français", flag: "🇫🇷" },
  { code: "zh", label: "中文", flag: "🇨🇳" },
  { code: "ko", label: "한국어", flag: "🇰🇷" },
  { code: "es", label: "Español", flag: "🇪🇸" },
  { code: "pt", label: "Português", flag: "🇧🇷" },
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

  // Language
  const [currentLang, setCurrentLang] = useState(() => {
    if (typeof document !== "undefined") {
      const match = document.cookie.match(/NEXT_LOCALE=(\w+)/);
      if (match) return match[1];
    }
    return "en";
  });

  // API Keys
  const [apiKeys, setApiKeys] = useState<Array<{ key: string; created: string }>>([]);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Notifications
  const [notifications, setNotifications] = useState({
    simulationCompleted: true,
    scoreDegradation: true,
    weeklySummary: false,
  });

  // Delete account confirmation
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);

  function setLanguage(lang: string) {
    document.cookie = `NEXT_LOCALE=${lang};path=/;max-age=31536000`;
    setCurrentLang(lang);
    router.refresh();
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
    setNotifications((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className="max-w-[800px] mx-auto px-6 py-10">
      <div className="mb-10">
        <h1 className="text-2xl font-bold mb-1">Settings</h1>
        <p className="text-[#94a3b8] text-sm">Manage your account and subscription</p>
      </div>

      {/* Language */}
      <Card className="mb-6">
        <div className="flex items-center gap-3 mb-6">
          <Globe size={20} className="text-[#FFD700]" />
          <h2 className="text-lg font-bold">Language</h2>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {LANGUAGES.map((lang) => (
            <button
              key={lang.code}
              onClick={() => setLanguage(lang.code)}
              className={`flex items-center gap-2 px-4 py-3 rounded-lg border transition-all text-sm ${
                currentLang === lang.code
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
          <h2 className="text-lg font-bold">Profile</h2>
        </div>
        <div className="space-y-4">
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Email</span>
            <span className="text-sm">{user?.email || "Not signed in"}</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Name</span>
            <span className="text-sm">{user?.user_metadata?.full_name || "Not set"}</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Provider</span>
            <span className="text-sm capitalize">{user?.app_metadata?.provider || "N/A"}</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Member since</span>
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
            <h2 className="text-lg font-bold">Subscription</h2>
          </div>
          <Badge variant="gold">Free Plan</Badge>
        </div>
        <div className="space-y-4 mb-6">
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Plan</span>
            <span className="text-sm">Free</span>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Simulations</span>
            <div>
              <div className="flex items-center gap-2">
                <div className="h-2 w-32 bg-white/5 rounded-full overflow-hidden">
                  <div className="h-full w-2/5 bg-[#FFD700] rounded-full" />
                </div>
                <span className="text-xs text-[#64748b]">2 / 5 this month</span>
              </div>
            </div>
          </div>
          <div className="grid grid-cols-[120px_1fr] items-center gap-4">
            <span className="text-sm text-[#64748b]">Components</span>
            <span className="text-sm">5 max</span>
          </div>
        </div>
        <Link href="/pricing">
          <Button size="sm">
            <CreditCard size={14} /> Upgrade to Pro
          </Button>
        </Link>
      </Card>

      {/* API Keys */}
      <Card className="mb-6">
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <Key size={20} className="text-[#FFD700]" />
            <h2 className="text-lg font-bold">API Keys</h2>
          </div>
          <Button variant="secondary" size="sm" onClick={handleGenerateKey}>
            <Plus size={14} /> Generate Key
          </Button>
        </div>
        <p className="text-sm text-[#94a3b8] mb-4">
          Use API keys to authenticate requests to the FaultRay API from your CI/CD pipeline or the FaultRay agent.
        </p>

        {apiKeys.length === 0 ? (
          <div className="p-6 rounded-xl border border-dashed border-[#1e293b] text-center">
            <Key size={20} className="mx-auto mb-2 text-[#64748b]" />
            <p className="text-sm text-[#94a3b8]">No API keys yet</p>
            <p className="text-xs text-[#64748b]">Click &quot;Generate Key&quot; to create one</p>
          </div>
        ) : (
          <div className="space-y-3">
            {apiKeys.map((k) => (
              <div key={k.key} className="flex items-center gap-3 p-3 rounded-lg bg-[#0d1117] border border-[#1e293b]">
                <code className="flex-1 text-sm font-mono text-[#e2e8f0] truncate">{k.key}</code>
                <span className="text-xs text-[#64748b] shrink-0">Created {k.created}</span>
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
        <div className="flex items-center gap-3 mb-6">
          <Bell size={20} className="text-[#FFD700]" />
          <h2 className="text-lg font-bold">Notifications</h2>
        </div>
        <div className="space-y-4">
          {([
            { key: "simulationCompleted" as const, label: "Simulation completed", desc: "Get notified when a simulation finishes" },
            { key: "scoreDegradation" as const, label: "Score degradation", desc: "Alert when resilience score drops below threshold" },
            { key: "weeklySummary" as const, label: "Weekly summary", desc: "Receive a weekly resilience report" },
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

      {/* Danger Zone */}
      <Card className="border-red-500/20">
        <h2 className="text-lg font-bold text-red-400 mb-4">Danger Zone</h2>
        {!showDeleteConfirm ? (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium">Delete Account</p>
              <p className="text-xs text-[#64748b]">Permanently delete your account and all data</p>
            </div>
            <Button variant="danger" size="sm" onClick={() => setShowDeleteConfirm(true)}>
              Delete Account
            </Button>
          </div>
        ) : (
          <div className="p-4 rounded-xl bg-red-500/5 border border-red-500/20">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle size={16} className="text-red-400" />
              <p className="text-sm font-medium text-red-400">Are you sure?</p>
            </div>
            <p className="text-xs text-[#94a3b8] mb-4">
              This action cannot be undone. All your data, API keys, and simulation history will be permanently deleted.
            </p>
            <div className="flex gap-3">
              <Button variant="danger" size="sm" onClick={() => {
                // TODO: Call Supabase delete account API
                alert("Account deletion is not yet implemented. Please contact support.");
                setShowDeleteConfirm(false);
              }}>
                Yes, delete my account
              </Button>
              <Button variant="secondary" size="sm" onClick={() => setShowDeleteConfirm(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}
