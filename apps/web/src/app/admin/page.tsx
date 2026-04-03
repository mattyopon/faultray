"use client";

import { useAuth } from "@/components/auth-provider";
import { Card } from "@/components/ui/card";
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMemo } from "react";
import {
  Users,
  Activity,
  TrendingUp,
  Zap,
  DollarSign,
  AlertTriangle,
} from "lucide-react";

// KPI-01: Admin KPI dashboard — shows high-level product metrics
// Access restricted to admin users (plan === "admin" or email in allowlist)

interface KpiMetric {
  label: string;
  value: string | number;
  change?: string;
  icon: React.ElementType;
  color: string;
}

const ADMIN_EMAILS = (process.env.NEXT_PUBLIC_ADMIN_EMAILS ?? "").split(",").map((e) => e.trim());

export default function AdminPage() {
  const { user } = useAuth();
  const router = useRouter();
  const isAdmin =
    (user?.email && ADMIN_EMAILS.includes(user.email)) ?? false;

  // Redirect non-admins
  useEffect(() => {
    if (user && !isAdmin) {
      router.replace("/dashboard");
    }
  }, [user, isAdmin, router]);

  // Static placeholder metrics — in production fetch from /api/admin/metrics
  const metrics = useMemo<KpiMetric[]>(() => [
    { label: "Total Users",       value: "—", change: "Connect Supabase to view",       icon: Users,         color: "text-blue-400" },
    { label: "Activation Rate",   value: "—", change: "% users who ran 1+ simulation",  icon: Zap,           color: "text-[var(--gold)]" },
    { label: "Simulations / Day", value: "—", change: "30-day average",                 icon: Activity,      color: "text-emerald-400" },
    { label: "MRR",               value: "—", change: "Monthly Recurring Revenue",       icon: DollarSign,    color: "text-emerald-400" },
    { label: "Churn Rate",        value: "—", change: "Last 30 days",                   icon: TrendingUp,    color: "text-amber-400" },
    { label: "Error Rate",        value: "—", change: "API errors / total requests",    icon: AlertTriangle, color: "text-red-400" },
  ], []);

  const loading = !user;

  if (!user || !isAdmin) return null;

  return (
    <div className="w-full px-6 py-12">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Admin Dashboard</h1>
        <p className="text-[var(--text-muted)] text-sm mt-1">
          Product KPIs and operational metrics. Visible to admin users only.
        </p>
      </div>

      {loading ? (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-28 rounded-2xl bg-[var(--bg-card)] border border-[var(--border-color)] animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {metrics.map((m) => (
            <Card key={m.label} className="p-6">
              <div className="flex items-center gap-3 mb-3">
                <m.icon size={18} className={m.color} />
                <span className="text-sm text-[var(--text-muted)]">{m.label}</span>
              </div>
              <p className="text-3xl font-bold text-white mb-1">{m.value}</p>
              {m.change && (
                <p className="text-xs text-[var(--text-muted)]">{m.change}</p>
              )}
            </Card>
          ))}
        </div>
      )}

      <div className="mt-12 p-5 rounded-xl border border-[var(--border-color)] bg-[var(--bg-card)]">
        <h2 className="text-sm font-semibold text-[var(--text-secondary)] mb-3">
          KPI-02: Activation Metric (Initial simulation run rate)
        </h2>
        <p className="text-xs text-[var(--text-muted)]">
          To track activation rate, configure{" "}
          <code className="text-[var(--text-secondary)]">NEXT_PUBLIC_GA_ID</code> and enable the GA4 conversion
          event <code className="text-[var(--text-secondary)]">simulation_run</code> in Google Analytics.
          This event is already fired in{" "}
          <code className="text-[var(--text-secondary)]">src/lib/analytics.ts</code>.
        </p>
      </div>
    </div>
  );
}
