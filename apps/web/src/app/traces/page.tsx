"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { useState } from "react";
import {
  Activity,
  ChevronDown,
  ChevronRight,
  Clock,
  Server,
  AlertTriangle,
  CheckCircle2,
  Filter,
  Search,
  FileText,
  BookOpen,
} from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Types
 * ============================================================ */

interface Span {
  id: string;
  service: string;
  operation: string;
  startMs: number;
  durationMs: number;
  status: "ok" | "error" | "slow";
  tags: Record<string, string>;
}

interface Trace {
  id: string;
  name: string;
  services: string[];
  durationMs: number;
  startTime: string;
  status: "ok" | "error" | "slow";
  spanCount: number;
  spans: Span[];
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const DEMO_TRACES: Trace[] = [
  {
    id: "a1b2c3d4e5f6",
    name: "POST /api/checkout",
    services: ["web", "api", "db", "cache"],
    durationMs: 342,
    startTime: "2026-04-01T09:12:34Z",
    status: "ok",
    spanCount: 8,
    spans: [
      { id: "s1", service: "web",   operation: "HTTP POST /api/checkout", startMs: 0,   durationMs: 342, status: "ok",    tags: { "http.status": "200" } },
      { id: "s2", service: "api",   operation: "checkout.handler",        startMs: 12,  durationMs: 298, status: "ok",    tags: { "component": "handler" } },
      { id: "s3", service: "cache", operation: "GET cart:user:8821",       startMs: 20,  durationMs: 4,   status: "ok",    tags: { "cache.hit": "true" } },
      { id: "s4", service: "api",   operation: "validateInventory",        startMs: 26,  durationMs: 85,  status: "ok",    tags: {} },
      { id: "s5", service: "db",    operation: "SELECT products WHERE ...", startMs: 30,  durationMs: 78,  status: "ok",    tags: { "db.type": "postgresql" } },
      { id: "s6", service: "api",   operation: "processPayment",           startMs: 115, durationMs: 155, status: "ok",    tags: { "payment.provider": "stripe" } },
      { id: "s7", service: "db",    operation: "INSERT orders",            startMs: 273, durationMs: 32,  status: "ok",    tags: { "db.type": "postgresql" } },
      { id: "s8", service: "cache", operation: "DEL cart:user:8821",       startMs: 308, durationMs: 2,   status: "ok",    tags: { "cache.hit": "true" } },
    ],
  },
  {
    id: "b2c3d4e5f6a1",
    name: "GET /api/recommendations",
    services: ["web", "api", "cache"],
    durationMs: 89,
    startTime: "2026-04-01T09:12:35Z",
    status: "ok",
    spanCount: 4,
    spans: [
      { id: "s1", service: "web",   operation: "HTTP GET /api/recommendations", startMs: 0,  durationMs: 89,  status: "ok", tags: { "http.status": "200" } },
      { id: "s2", service: "api",   operation: "recommendations.handler",       startMs: 8,  durationMs: 78,  status: "ok", tags: {} },
      { id: "s3", service: "cache", operation: "GET reco:user:8821",            startMs: 12, durationMs: 3,   status: "ok", tags: { "cache.hit": "false" } },
      { id: "s4", service: "api",   operation: "ml.score",                      startMs: 18, durationMs: 65,  status: "ok", tags: { "model": "collab_filter_v3" } },
    ],
  },
  {
    id: "c3d4e5f6a1b2",
    name: "POST /api/auth/login",
    services: ["web", "api", "db"],
    durationMs: 1247,
    startTime: "2026-04-01T09:12:30Z",
    status: "slow",
    spanCount: 5,
    spans: [
      { id: "s1", service: "web", operation: "HTTP POST /api/auth/login", startMs: 0,   durationMs: 1247, status: "slow",  tags: { "http.status": "200" } },
      { id: "s2", service: "api", operation: "auth.loginHandler",        startMs: 10,  durationMs: 1230, status: "slow",  tags: {} },
      { id: "s3", service: "db",  operation: "SELECT users WHERE email", startMs: 18,  durationMs: 1190, status: "slow",  tags: { "db.type": "postgresql", "db.slow": "true" } },
      { id: "s4", service: "api", operation: "bcrypt.compare",           startMs: 1212, durationMs: 22,  status: "ok",   tags: {} },
      { id: "s5", service: "api", operation: "session.create",           startMs: 1235, durationMs: 4,   status: "ok",   tags: {} },
    ],
  },
  {
    id: "d4e5f6a1b2c3",
    name: "GET /api/products",
    services: ["web", "api", "db", "cache"],
    durationMs: 2105,
    startTime: "2026-04-01T09:12:28Z",
    status: "error",
    spanCount: 6,
    spans: [
      { id: "s1", service: "web",   operation: "HTTP GET /api/products",       startMs: 0,   durationMs: 2105, status: "error", tags: { "http.status": "500" } },
      { id: "s2", service: "api",   operation: "products.listHandler",         startMs: 9,   durationMs: 2090, status: "error", tags: {} },
      { id: "s3", service: "cache", operation: "GET products:page:1",          startMs: 14,  durationMs: 3,    status: "ok",    tags: { "cache.hit": "false" } },
      { id: "s4", service: "db",    operation: "SELECT products LIMIT 50",     startMs: 20,  durationMs: 2060, status: "error", tags: { "db.type": "postgresql", "error": "connection timeout" } },
      { id: "s5", service: "api",   operation: "fallback.products",            startMs: 2082, durationMs: 10,  status: "ok",   tags: { "fallback": "true" } },
      { id: "s6", service: "cache", operation: "SET products:page:1 (stale)",  startMs: 2093, durationMs: 3,   status: "ok",   tags: {} },
    ],
  },
  {
    id: "e5f6a1b2c3d4",
    name: "POST /api/search",
    services: ["web", "api", "db"],
    durationMs: 156,
    startTime: "2026-04-01T09:12:26Z",
    status: "ok",
    spanCount: 4,
    spans: [
      { id: "s1", service: "web", operation: "HTTP POST /api/search",     startMs: 0,  durationMs: 156, status: "ok", tags: { "http.status": "200" } },
      { id: "s2", service: "api", operation: "search.handler",            startMs: 8,  durationMs: 146, status: "ok", tags: {} },
      { id: "s3", service: "db",  operation: "SELECT * FULL TEXT SEARCH", startMs: 14, durationMs: 132, status: "ok", tags: { "db.type": "postgresql" } },
      { id: "s4", service: "api", operation: "search.rankResults",        startMs: 148, durationMs: 5,  status: "ok", tags: {} },
    ],
  },
];

const SERVICE_COLORS: Record<string, string> = {
  web:   "#3b82f6",
  api:   "#10b981",
  db:    "#f59e0b",
  cache: "#8b5cf6",
};

const ALL_SERVICES = ["web", "api", "db", "cache"];

/* ============================================================
 * Helpers
 * ============================================================ */

function statusVariant(status: string): "green" | "yellow" | "red" | "default" {
  if (status === "ok") return "green";
  if (status === "slow") return "yellow";
  if (status === "error") return "red";
  return "default";
}

function latencyColor(ms: number): string {
  if (ms < 200) return "#10b981";
  if (ms < 1000) return "#f59e0b";
  return "#ef4444";
}

function WaterfallBar({ span, totalMs }: { span: Span; totalMs: number }) {
  const left = (span.startMs / totalMs) * 100;
  const width = Math.max(0.5, (span.durationMs / totalMs) * 100);
  const color = SERVICE_COLORS[span.service] ?? "#64748b";

  return (
    <div className="flex items-center gap-3 py-1 text-xs">
      <span className="w-16 text-right text-[#64748b] shrink-0">{span.service}</span>
      <span className="w-40 truncate text-[#94a3b8] shrink-0">{span.operation}</span>
      <div className="flex-1 h-5 bg-white/5 rounded relative overflow-hidden">
        <div
          className="absolute top-0 h-full rounded opacity-80"
          style={{ left: `${left}%`, width: `${width}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-16 text-right font-mono" style={{ color: latencyColor(span.durationMs) }}>
        {span.durationMs}ms
      </span>
    </div>
  );
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function TracesPage() {
  const locale = useLocale();

  const [expandedTrace, setExpandedTrace] = useState<string | null>(null);
  const [filterService, setFilterService] = useState<string>("all");
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [filterLatency, setFilterLatency] = useState<number>(0);
  const [searchQuery, setSearchQuery] = useState("");

  const filtered = DEMO_TRACES.filter((trace) => {
    if (filterService !== "all" && !trace.services.includes(filterService)) return false;
    if (filterStatus !== "all" && trace.status !== filterStatus) return false;
    if (filterLatency > 0 && trace.durationMs < filterLatency) return false;
    if (searchQuery && !trace.name.toLowerCase().includes(searchQuery.toLowerCase())) return false;
    return true;
  });

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <Activity size={24} className="text-[#FFD700]" />
          {locale === "ja" ? "分散トレーシング" : "Distributed Tracing"}
        </h1>
        <p className="text-[#94a3b8] text-sm">
          {locale === "ja"
            ? "サービス間のエンドツーエンドリクエストトレース — ボトルネックと障害を特定 (Layer 0)"
            : "End-to-end request traces across services — identify bottlenecks and failures (Layer 0)"}
        </p>
      </div>

      {/* DEMO-05: Sample data notice */}
      <div className="mb-6 px-4 py-2.5 rounded-lg border border-amber-500/20 bg-amber-500/[0.06] flex items-center gap-2 text-xs text-amber-400">
        <span className="shrink-0">📋</span>
        <span>{locale === "ja" ? "サンプルデータを表示中。APM連携後に実際のトレースデータが表示されます。" : "Showing sample data. Real trace data will appear after APM integration."}</span>
      </div>

      {/* Summary Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: locale === "ja" ? "総トレース数" : "Total Traces",  value: DEMO_TRACES.length, color: "#e2e8f0" },
          { label: locale === "ja" ? "エラー" : "Errors",              value: DEMO_TRACES.filter(t => t.status === "error").length, color: "#ef4444" },
          { label: locale === "ja" ? "低速 (>1s)" : "Slow (>1s)",     value: DEMO_TRACES.filter(t => t.durationMs > 1000).length, color: "#f59e0b" },
          { label: locale === "ja" ? "平均レイテンシ" : "Avg Latency", value: `${Math.round(DEMO_TRACES.reduce((s, t) => s + t.durationMs, 0) / DEMO_TRACES.length)}ms`, color: "#10b981" },
        ].map((stat) => (
          <Card key={stat.label} className="text-center">
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{stat.label}</p>
            <p className="text-3xl font-extrabold font-mono" style={{ color: stat.color }}>{stat.value}</p>
          </Card>
        ))}
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-[#64748b]">
            <Filter size={14} />
            <span className="text-xs font-medium uppercase tracking-wider">{locale === "ja" ? "フィルター" : "Filters"}</span>
          </div>
          <div className="relative flex-1 min-w-[200px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]" />
            <input
              className="w-full bg-white/5 border border-[#1e293b] rounded-lg pl-8 pr-3 py-1.5 text-sm text-[#e2e8f0] placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/40"
              placeholder={locale === "ja" ? "オペレーション名で検索..." : "Search by operation name..."}
              aria-label={locale === "ja" ? "オペレーション名で検索" : "Search by operation name"}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>
          <select
            className="bg-[#0d1526] border border-[#1e293b] rounded-lg px-3 py-1.5 text-sm text-[#94a3b8] focus:outline-none focus:border-[#FFD700]/30"
            value={filterService}
            onChange={(e) => setFilterService(e.target.value)}
            aria-label={locale === "ja" ? "サービスでフィルター" : "Filter by service"}
          >
            <option value="all">{locale === "ja" ? "全サービス" : "All Services"}</option>
            {ALL_SERVICES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>
          <select
            className="bg-[#0d1526] border border-[#1e293b] rounded-lg px-3 py-1.5 text-sm text-[#94a3b8] focus:outline-none focus:border-[#FFD700]/30"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            aria-label={locale === "ja" ? "ステータスでフィルター" : "Filter by status"}
          >
            <option value="all">{locale === "ja" ? "全ステータス" : "All Status"}</option>
            <option value="ok">OK</option>
            <option value="slow">{locale === "ja" ? "低速" : "Slow"}</option>
            <option value="error">{locale === "ja" ? "エラー" : "Error"}</option>
          </select>
          <select
            className="bg-[#0d1526] border border-[#1e293b] rounded-lg px-3 py-1.5 text-sm text-[#94a3b8] focus:outline-none focus:border-[#FFD700]/30"
            value={filterLatency}
            onChange={(e) => setFilterLatency(Number(e.target.value))}
            aria-label={locale === "ja" ? "レイテンシでフィルター" : "Filter by latency"}
          >
            <option value={0}>{locale === "ja" ? "全レイテンシ" : "Any Latency"}</option>
            <option value={100}>{">"} 100ms</option>
            <option value={500}>{">"} 500ms</option>
            <option value={1000}>{">"} 1s</option>
          </select>
        </div>
      </Card>

      {/* Trace List */}
      <Card>
        <div className="space-y-1">
          {/* Header row */}
          <div className="flex items-center gap-3 px-3 py-2 text-[10px] text-[#475569] uppercase tracking-wider border-b border-[#1e293b] mb-2">
            <span className="w-5" />
            <span className="flex-1">{locale === "ja" ? "トレース / オペレーション" : "Trace / Operation"}</span>
            <span className="w-32 hidden md:block">{locale === "ja" ? "サービス" : "Services"}</span>
            <span className="w-20 text-right">{locale === "ja" ? "スパン数" : "Spans"}</span>
            <span className="w-28 text-right">{locale === "ja" ? "所要時間" : "Duration"}</span>
            <span className="w-24 text-right">{locale === "ja" ? "ステータス" : "Status"}</span>
            <span className="w-32 hidden lg:block text-right">{locale === "ja" ? "日時" : "Time"}</span>
          </div>

          {filtered.length === 0 && (
            <p className="text-center text-[#64748b] py-8 text-sm">{locale === "ja" ? "フィルター条件に一致するトレースがありません。" : "No traces match the current filters."}</p>
          )}

          {filtered.map((trace) => {
            const isExpanded = expandedTrace === trace.id;
            const traceMax = trace.spans.reduce((m, s) => Math.max(m, s.startMs + s.durationMs), 0);

            return (
              <div key={trace.id}>
                <button
                  className="w-full text-left hover:bg-white/[0.02] rounded-lg transition-colors"
                  onClick={() => setExpandedTrace(isExpanded ? null : trace.id)}
                >
                  <div className="flex items-center gap-3 px-3 py-3">
                    {isExpanded
                      ? <ChevronDown size={14} className="text-[#64748b] shrink-0" />
                      : <ChevronRight size={14} className="text-[#64748b] shrink-0" />}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium text-[#e2e8f0] truncate">{trace.name}</p>
                      <p className="text-xs text-[#64748b] font-mono">{trace.id.slice(0, 12)}...</p>
                    </div>
                    <div className="w-32 hidden md:flex gap-1 flex-wrap">
                      {trace.services.map((svc) => (
                        <span
                          key={svc}
                          className="text-[10px] px-1.5 py-0.5 rounded font-medium"
                          style={{ backgroundColor: (SERVICE_COLORS[svc] ?? "#64748b") + "20", color: SERVICE_COLORS[svc] ?? "#64748b" }}
                        >
                          {svc}
                        </span>
                      ))}
                    </div>
                    <span className="w-20 text-right text-sm text-[#94a3b8]">{trace.spanCount}</span>
                    <span
                      className="w-28 text-right text-sm font-mono font-bold"
                      style={{ color: latencyColor(trace.durationMs) }}
                    >
                      {trace.durationMs >= 1000
                        ? `${(trace.durationMs / 1000).toFixed(2)}s`
                        : `${trace.durationMs}ms`}
                    </span>
                    <span className="w-24 flex justify-end">
                      <Badge variant={statusVariant(trace.status)}>
                        {trace.status === "ok" ? "OK" : trace.status === "slow" ? "SLOW" : "ERROR"}
                      </Badge>
                    </span>
                    <span className="w-32 hidden lg:block text-right text-xs text-[#64748b]">
                      {new Date(trace.startTime).toLocaleTimeString()}
                    </span>
                  </div>
                </button>

                {/* Waterfall View */}
                {isExpanded && (
                  <div className="mx-3 mb-4 p-4 rounded-xl bg-white/[0.02] border border-[#1e293b]">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-xs font-semibold text-[#64748b] uppercase tracking-wider flex items-center gap-2">
                        <Clock size={12} />
                        Span Waterfall — total {traceMax}ms
                      </h4>
                      <div className="flex gap-3">
                        {trace.services.map((svc) => (
                          <span key={svc} className="flex items-center gap-1 text-xs text-[#64748b]">
                            <span className="w-3 h-3 rounded-sm inline-block" style={{ backgroundColor: SERVICE_COLORS[svc] }} />
                            {svc}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="space-y-0.5">
                      {trace.spans.map((span) => (
                        <div key={span.id}>
                          <WaterfallBar span={span} totalMs={traceMax} />
                          {span.status === "error" && (
                            <div className="ml-20 text-xs text-red-400 flex items-center gap-1 mb-1">
                              <AlertTriangle size={10} />
                              {span.tags.error ?? "Error in span"}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                    {/* Tags for root span */}
                    <div className="mt-3 pt-3 border-t border-[#1e293b] flex flex-wrap gap-2">
                      {Object.entries(trace.spans[0]?.tags ?? {}).map(([k, v]) => (
                        <span key={k} className="text-xs bg-white/5 rounded px-2 py-0.5 font-mono">
                          <span className="text-[#64748b]">{k}=</span>
                          <span className="text-[#e2e8f0]">{v}</span>
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Service Legend */}
      <div className="mt-6 flex items-center gap-2 flex-wrap">
        <Server size={14} className="text-[#64748b]" />
        <span className="text-xs text-[#64748b]">Services:</span>
        {ALL_SERVICES.map((svc) => (
          <span
            key={svc}
            className="flex items-center gap-1.5 text-xs"
            style={{ color: SERVICE_COLORS[svc] }}
          >
            <span className="w-2 h-2 rounded-full inline-block" style={{ backgroundColor: SERVICE_COLORS[svc] }} />
            {svc}
          </span>
        ))}
        <span className="ml-4 flex items-center gap-1 text-xs text-emerald-400"><CheckCircle2 size={12} /> OK</span>
        <span className="flex items-center gap-1 text-xs text-yellow-400"><Clock size={12} /> Slow ({">"}1s)</span>
        <span className="flex items-center gap-1 text-xs text-red-400"><AlertTriangle size={12} /> Error</span>
      </div>

      {/* FLOW-11: Cross-links to related observability pages */}
      <div className="flex items-center gap-3 mt-6 pt-4 border-t border-[#1e293b]">
        <span className="text-xs text-[#475569]">{locale === "ja" ? "関連ページ:" : "Related:"}</span>
        <Link href="/logs" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <FileText size={12} />
          {locale === "ja" ? "ログ" : "Logs"}
        </Link>
        <Link href="/reports" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <BookOpen size={12} />
          {locale === "ja" ? "レポート" : "Reports"}
        </Link>
      </div>
    </div>
  );
}
