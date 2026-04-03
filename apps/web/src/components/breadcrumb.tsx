"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";

/** Map of path segments to human-readable labels */
const SEGMENT_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  simulate: "Simulate",
  topology: "Topology",
  dora: "DORA",
  compliance: "Compliance",
  reports: "Reports",
  incidents: "Incidents",
  fmea: "FMEA",
  benchmark: "Monte Carlo",
  heatmap: "Heatmap",
  apm: "Monitor",
  "sla-budget": "SLA Budget",
  "score-detail": "Score Detail",
  "topology-map": "Topology Map",
  dependencies: "Dependencies",
  "people-risk": "People Risk",
  "bus-factor": "Bus Factor",
  "shadow-it": "Shadow IT",
  "vuln-priority": "Vuln Priority",
  "external-impact": "SaaS Impact",
  whatif: "What-If",
  runbooks: "Runbooks",
  postmortems: "Post-Mortems",
  templates: "Templates",
  gameday: "Game Day",
  calendar: "Calendar",
  timeline: "Timeline",
  logs: "Logs",
  traces: "Traces",
  evidence: "Evidence",
  "audit-report": "Audit Report",
  projects: "Projects",
  iac: "IaC",
  optimize: "Optimize",
  remediation: "Remediation",
  settings: "Settings",
  help: "Help",
  support: "Support",
  "supply-chain": "Supply Chain",
  "traffic-light": "Status",
  governance: "Governance",
  sla: "SLA",
  fisc: "FISC",
  canary: "Canary",
  drift: "Drift",
  "env-compare": "Env Compare",
  cost: "Cost",
  "ai-reliability": "AI Reliability",
  "ipo-readiness": "IPO Readiness",
  security: "Security",
  "people-risk-detail": "People Risk",
};

export function Breadcrumb() {
  const pathname = usePathname();

  // Strip locale prefix if present (e.g. /ja/dashboard → /dashboard)
  const locales = ["en", "ja", "de", "fr", "zh", "ko", "es", "pt"];
  let cleanPath = pathname;
  for (const locale of locales) {
    if (cleanPath.startsWith(`/${locale}/`) || cleanPath === `/${locale}`) {
      cleanPath = cleanPath.slice(locale.length + 1) || "/";
      break;
    }
  }

  // Don't show breadcrumb on root/LP pages
  const skipPaths = ["/", ""];
  if (skipPaths.includes(cleanPath)) return null;

  const segments = cleanPath.split("/").filter(Boolean);
  if (segments.length === 0) return null;

  const crumbs = segments.map((seg, i) => {
    const href = "/" + segments.slice(0, i + 1).join("/");
    const label = SEGMENT_LABELS[seg] ?? seg.charAt(0).toUpperCase() + seg.slice(1).replace(/-/g, " ");
    return { href, label };
  });

  return (
    <nav
      aria-label="Breadcrumb"
      className="flex items-center gap-1.5 px-4 py-2 text-xs text-[var(--text-muted)] border-b border-[var(--border-color)] bg-[var(--bg-secondary)]"
    >
      <Link
        href="/dashboard"
        className="flex items-center gap-1 hover:text-[var(--text-primary)] transition-colors"
        aria-label="Dashboard home"
      >
        <Home size={12} />
      </Link>
      {crumbs.map((crumb, i) => (
        <span key={crumb.href} className="flex items-center gap-1.5">
          <ChevronRight size={10} className="shrink-0" aria-hidden="true" />
          {i === crumbs.length - 1 ? (
            <span className="text-[var(--text-secondary)]" aria-current="page">
              {crumb.label}
            </span>
          ) : (
            <Link
              href={crumb.href}
              className="hover:text-[var(--text-primary)] transition-colors"
            >
              {crumb.label}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}
