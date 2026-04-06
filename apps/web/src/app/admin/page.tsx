import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import { Card } from "@/components/ui/card";
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
// Server Component: auth + admin check run on the server; ADMIN_EMAILS is never exposed to the client.

interface KpiMetric {
  label: string;
  value: string | number;
  change?: string;
  icon: React.ElementType;
  color: string;
}

const metrics: KpiMetric[] = [
  { label: "Total Users",       value: "—", change: "Connect Supabase to view",       icon: Users,         color: "text-blue-400" },
  { label: "Activation Rate",   value: "—", change: "% users who ran 1+ simulation",  icon: Zap,           color: "text-[var(--gold)]" },
  { label: "Simulations / Day", value: "—", change: "30-day average",                 icon: Activity,      color: "text-emerald-400" },
  { label: "MRR",               value: "—", change: "Monthly Recurring Revenue",       icon: DollarSign,    color: "text-emerald-400" },
  { label: "Churn Rate",        value: "—", change: "Last 30 days",                   icon: TrendingUp,    color: "text-amber-400" },
  { label: "Error Rate",        value: "—", change: "API errors / total requests",    icon: AlertTriangle, color: "text-red-400" },
];

export default async function AdminPage() {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/");
  }

  // ADMIN_EMAILS is a server-side only env var (no NEXT_PUBLIC_ prefix)
  const adminEmails = (process.env.ADMIN_EMAILS ?? "").split(",").map((e) => e.trim()).filter(Boolean);
  const isAdmin = user.email != null && adminEmails.includes(user.email);

  if (!isAdmin) {
    redirect("/");
  }

  return (
    <div className="w-full px-6 py-12">
      <div className="mb-8">
        <h1 className="text-2xl font-bold">Admin Dashboard</h1>
        <p className="text-[var(--text-muted)] text-sm mt-1">
          Product KPIs and operational metrics. Visible to admin users only.
        </p>
      </div>

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
