"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState } from "react";
import { BookOpen, ChevronDown, ChevronRight, Copy, Search } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const DEMO_RUNBOOKS = [
  {
    id: "RB-001",
    title: "Database Primary Crash",
    component: "db_primary",
    severity: "critical",
    avgMttr: "12 min",
    lastUpdated: "2026-03-28",
    detection: [
      "Check CloudWatch: RDS CPU > 95% or connections at max",
      "Verify pg_stat_activity shows long-running queries",
      "Check error logs: `journalctl -u postgresql --since '5 min ago'`",
      "Confirm replica lag: `SELECT * FROM pg_stat_replication;`",
    ],
    diagnosis: [
      "Identify blocking query: `SELECT pid, query, now()-query_start FROM pg_stat_activity WHERE state='active' ORDER BY query_start;`",
      "Check disk I/O: `iostat -x 1 5`",
      "Review slow query log for last 30 minutes",
    ],
    mitigation: [
      "Kill offending long-running queries: `SELECT pg_terminate_backend(pid);`",
      "If disk I/O: rotate to replica immediately",
      "Enable connection pooling if exhausted",
    ],
    recovery: [
      "Promote replica: `pg_ctl promote -D /var/lib/postgresql/data`",
      "Update DNS/connection string to point to new primary",
      "Verify application reconnects within 60s",
      "Begin streaming replication on former primary after disk fix",
    ],
    postIncident: [
      "Document timeline in post-mortem template",
      "Review slow query threshold settings",
      "Add automated replica promotion to runbook",
    ],
    slackTemplate: ":rotating_light: *DB PRIMARY DOWN* | Severity: P1 | ETA: 15min | IC: @oncall | Bridge: #incident-bridge",
    emailTemplate: "Subject: [P1 INCIDENT] Database Primary Down\n\nWe are currently experiencing a database outage. Our team is actively working on restoration. ETA: 15 minutes. Updates every 5 minutes.",
  },
  {
    id: "RB-002",
    title: "Cache Cluster Network Partition",
    component: "cache",
    severity: "high",
    avgMttr: "8 min",
    lastUpdated: "2026-03-27",
    detection: [
      "Monitor Redis cluster: `redis-cli cluster info` shows cluster_state:fail",
      "Check cache hit rate drops below 60% in dashboards",
      "Verify network connectivity between AZs",
    ],
    diagnosis: [
      "Identify which nodes lost quorum: `redis-cli cluster nodes`",
      "Check network ACLs and security groups between AZs",
      "Review AWS VPC flow logs for dropped packets",
    ],
    mitigation: [
      "Route traffic to surviving AZ nodes only",
      "Enable local cache fallback in application config",
      "Reduce TTL to minimize stale data impact",
    ],
    recovery: [
      "Restore network connectivity between AZs",
      "Allow Redis to auto-resync partitioned nodes",
      "Monitor cluster_state returns to ok",
      "Gradually restore normal traffic routing",
    ],
    postIncident: [
      "Review AZ network redundancy",
      "Add split-brain detection to alerting",
      "Test application cache fallback behavior",
    ],
    slackTemplate: ":warning: *CACHE PARTITION* | Hit rate: 40% | AZ affected: us-east-1a | IC: @oncall",
    emailTemplate: "Subject: [P2] Cache Cluster Degradation\n\nCache cluster is experiencing a network partition. Availability degraded but not fully down. ETA: 10 minutes.",
  },
  {
    id: "RB-003",
    title: "DNS Resolution Failure",
    component: "dns",
    severity: "high",
    avgMttr: "6 min",
    lastUpdated: "2026-03-25",
    detection: [
      "Synthetic monitor alerts on external DNS resolution failure",
      "Check: `dig @8.8.8.8 yourdomain.com` returns SERVFAIL",
      "Verify DNS provider status page",
    ],
    diagnosis: [
      "Confirm TTL expiry: `dig yourdomain.com +ttl`",
      "Check if maintenance window was scheduled",
      "Test secondary DNS resolver: `dig @1.1.1.1 yourdomain.com`",
    ],
    mitigation: [
      "Switch to secondary DNS provider in Route53",
      "Lower TTL to 60s for faster propagation",
      "Enable GeoDNS failover if available",
    ],
    recovery: [
      "Confirm primary DNS provider restored service",
      "Gradually increase TTL back to production values",
      "Verify all regions resolve correctly",
    ],
    postIncident: [
      "Set up secondary DNS provider as active-active",
      "Add DNS health check to synthetic monitoring",
      "Review TTL strategy for critical records",
    ],
    slackTemplate: ":globe_with_meridians: *DNS FAILURE* | Domain: yourdomain.com | Fallback: ACTIVE | IC: @oncall",
    emailTemplate: "Subject: [P2] DNS Resolution Issues\n\nWe are experiencing DNS resolution issues. Some users may be unable to reach the service. Our team is actively working on a fix.",
  },
  {
    id: "RB-004",
    title: "API Gateway 502 Errors",
    component: "api_gateway",
    severity: "critical",
    avgMttr: "10 min",
    lastUpdated: "2026-03-20",
    detection: [
      "Error rate > 5% on API gateway metrics",
      "Check ALB access logs: `aws logs filter-log-events --log-group-name /aws/apigateway/access`",
      "Verify upstream health check endpoints",
    ],
    diagnosis: [
      "Check backend service health: `curl -v https://api/health`",
      "Review Lambda/ECS task logs for errors",
      "Check memory/CPU usage of backend services",
    ],
    mitigation: [
      "Enable API gateway cache for read endpoints",
      "Scale up backend services immediately",
      "Enable circuit breaker if available",
    ],
    recovery: [
      "Deploy hot fix if code error identified",
      "Scale down gradually once error rate < 0.1%",
      "Verify all endpoints return 200 in smoke tests",
    ],
    postIncident: [
      "Add automatic scaling trigger at 70% capacity",
      "Improve circuit breaker configuration",
      "Add canary deployment for future releases",
    ],
    slackTemplate: ":x: *API 502 ERRORS* | Rate: 8% | Endpoints: /api/v1/* | IC: @oncall | Bridge: #incident-bridge",
    emailTemplate: "Subject: [P1] API Gateway Errors\n\nOur API is currently returning elevated error rates. We are investigating and will provide updates every 5 minutes.",
  },
  {
    id: "RB-005",
    title: "Storage Volume I/O Saturation",
    component: "storage",
    severity: "high",
    avgMttr: "20 min",
    lastUpdated: "2026-03-15",
    detection: [
      "CloudWatch: VolumeQueueLength > 10 for 5 minutes",
      "Check: `iostat -x 1 10` shows %util > 95%",
      "Application logs show slow query timeouts",
    ],
    diagnosis: [
      "Identify top I/O processes: `iotop -o`",
      "Check for unexpected write patterns: `blktrace`",
      "Review recent deployments for new write-heavy operations",
    ],
    mitigation: [
      "Throttle write-heavy batch jobs immediately",
      "Enable EBS burst credits if applicable",
      "Move read-heavy queries to replica",
    ],
    recovery: [
      "Resize volume or migrate to io2 block express",
      "Implement write batching in application",
      "Monitor IOPS stabilize below 80% capacity",
    ],
    postIncident: [
      "Set IOPS alarm at 70% of provisioned limit",
      "Review storage sizing in capacity planning",
      "Evaluate NVMe instance storage for hot data",
    ],
    slackTemplate: ":floppy_disk: *STORAGE SATURATION* | Volume: vol-xxx | IOPS: 100% | IC: @oncall",
    emailTemplate: "Subject: [P2] Storage I/O Degradation\n\nStorage I/O is saturated causing application slowdowns. Our team is actively working on mitigation.",
  },
];

function RunbookCard({ rb, t }: { rb: typeof DEMO_RUNBOOKS[0]; t: Record<string, string> }) {
  const locale = useLocale();
  const [expanded, setExpanded] = useState(false);
  const [activeTab, setActiveTab] = useState<"steps" | "templates">("steps");
  const [copied, setCopied] = useState("");

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text).catch(() => {});
    setCopied(key);
    setTimeout(() => setCopied(""), 2000);
  };

  return (
    <Card>
      <button className="w-full text-left" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            {expanded ? <ChevronDown size={16} className="text-[#64748b]" /> : <ChevronRight size={16} className="text-[#64748b]" />}
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="font-mono text-xs text-[#64748b]">{rb.id}</span>
                <Badge variant={rb.severity === "critical" ? "red" : "yellow"}>{rb.severity}</Badge>
                <Badge variant="default">{rb.component}</Badge>
              </div>
              <p className="font-bold">{rb.title}</p>
            </div>
          </div>
          <div className="text-right shrink-0 ml-4">
            <p className="text-xs text-[#64748b]">{t.avgMttr}: <span className="text-white font-mono">{rb.avgMttr}</span></p>
            <p className="text-xs text-[#64748b] mt-1">{t.lastUpdated}: {rb.lastUpdated}</p>
          </div>
        </div>
      </button>

      {expanded && (
        <div className="mt-6 pt-4 border-t border-[#1e293b]">
          {/* Tabs */}
          <div className="flex gap-2 mb-4">
            <button
              onClick={() => setActiveTab("steps")}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${activeTab === "steps" ? "bg-[#FFD700]/10 text-[#FFD700]" : "text-[#64748b] hover:text-white"}`}
            >
              {locale === "ja" ? "対応手順" : "Response Steps"}
            </button>
            <button
              onClick={() => setActiveTab("templates")}
              className={`px-3 py-1.5 text-sm rounded-md transition-colors ${activeTab === "templates" ? "bg-[#FFD700]/10 text-[#FFD700]" : "text-[#64748b] hover:text-white"}`}
            >
              {locale === "ja" ? "通知テンプレート" : "Comm Templates"}
            </button>
          </div>

          {activeTab === "steps" && (
            <div className="grid md:grid-cols-2 gap-4">
              {[
                { label: t.detection, items: rb.detection, color: "#ef4444" },
                { label: t.diagnosis, items: rb.diagnosis, color: "#f59e0b" },
                { label: t.mitigation, items: rb.mitigation, color: "#3b82f6" },
                { label: t.recovery, items: rb.recovery, color: "#10b981" },
                { label: t.postIncident, items: rb.postIncident, color: "#8b5cf6" },
              ].map(({ label, items, color }) => (
                <div key={label} className="bg-[#0a0e1a] rounded-lg p-3">
                  <p className="text-xs font-semibold uppercase tracking-wider mb-2" style={{ color }}>{label}</p>
                  <ol className="space-y-1.5">
                    {items.map((item, i) => (
                      <li key={i} className="text-xs text-[#94a3b8] flex gap-2">
                        <span className="text-[#475569] shrink-0">{i + 1}.</span>
                        <span className="font-mono">{item}</span>
                      </li>
                    ))}
                  </ol>
                </div>
              ))}
            </div>
          )}

          {activeTab === "templates" && (
            <div className="space-y-4">
              {[
                { label: t.slackTemplate, content: rb.slackTemplate, key: "slack" },
                { label: t.emailTemplate, content: rb.emailTemplate, key: "email" },
              ].map(({ label, content, key }) => (
                <div key={key} className="bg-[#0a0e1a] rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <p className="text-xs font-semibold text-[#64748b] uppercase tracking-wider">{label}</p>
                    <button
                      onClick={() => handleCopy(content, key)}
                      className="flex items-center gap-1 text-xs text-[#64748b] hover:text-[#FFD700] transition-colors"
                    >
                      <Copy size={12} />
                      {copied === key ? (locale === "ja" ? "コピー済み!" : "Copied!") : t.copyTemplate}
                    </button>
                  </div>
                  <pre className="text-xs text-[#94a3b8] whitespace-pre-wrap font-mono">{content}</pre>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}

export default function RunbooksPage() {
  const locale = useLocale();
  const t = appDict.runbooks[locale] ?? appDict.runbooks.en;
  const [search, setSearch] = useState("");

  const filtered = DEMO_RUNBOOKS.filter(
    (rb) =>
      search === "" ||
      rb.title.toLowerCase().includes(search.toLowerCase()) ||
      rb.component.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <BookOpen size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {/* DEMO-05: Sample data notice */}
      <div className="mb-6 px-4 py-2.5 rounded-lg border border-amber-500/20 bg-amber-500/[0.06] flex items-center gap-2 text-xs text-amber-400">
        <span className="shrink-0">📋</span>
        <span>{locale === "ja" ? "サンプルデータを表示中。ランブック作成後に実際のデータが表示されます。" : "Showing sample data. Your runbooks will appear here after creation."}</span>
      </div>

      {/* Search */}
      <div className="relative mb-6">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t.searchPlaceholder}
          aria-label={t.searchPlaceholder}
          className="w-full bg-[#111827] border border-[#1e293b] rounded-lg pl-9 pr-4 py-2.5 text-sm text-white placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/50"
        />
      </div>

      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono">{DEMO_RUNBOOKS.length}</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{locale === "ja" ? "ランブック総数" : "Total Runbooks"}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-red-400">
            {DEMO_RUNBOOKS.filter((r) => r.severity === "critical").length}
          </p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{locale === "ja" ? "クリティカル" : "Critical"}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#f59e0b]">
            {DEMO_RUNBOOKS.filter((r) => r.severity === "high").length}
          </p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{locale === "ja" ? "高" : "High"}</p>
        </Card>
        <Card className="text-center">
          <p className="text-3xl font-extrabold font-mono text-[#10b981]">11 min</p>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mt-1">{t.avgMttr} Avg</p>
        </Card>
      </div>

      {/* Runbook list */}
      <div className="space-y-4">
        {filtered.map((rb) => (
          <RunbookCard key={rb.id} rb={rb} t={t} />
        ))}
        {filtered.length === 0 && (
          <Card className="text-center py-12">
            <p className="text-[#64748b]">{locale === "ja" ? "検索に一致するランブックがありません。" : "No runbooks match your search."}</p>
          </Card>
        )}
      </div>
    </div>
  );
}
