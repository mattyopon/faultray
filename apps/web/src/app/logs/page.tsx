"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useMemo } from "react";
import {
  FileText,
  Search,
  AlertTriangle,
  Info,
  XCircle,
  CheckCircle2,
  Filter,
  RefreshCw,
  Zap,
  Activity,
  BookOpen,
} from "lucide-react";
import Link from "next/link";
import { useLocale } from "@/lib/useLocale";

/* ============================================================
 * Types
 * ============================================================ */

type LogLevel = "INFO" | "WARN" | "ERROR" | "DEBUG";

interface LogEntry {
  id: string;
  timestamp: string;
  level: LogLevel;
  service: string;
  message: string;
  traceId?: string;
  anomaly?: string;
}

/* ============================================================
 * Demo Data
 * ============================================================ */

const DEMO_LOGS: LogEntry[] = [
  { id: "l01", timestamp: "2026-04-01T09:12:45.123Z", level: "INFO",  service: "api",   message: "POST /api/checkout completed in 342ms", traceId: "a1b2c3d4" },
  { id: "l02", timestamp: "2026-04-01T09:12:44.891Z", level: "INFO",  service: "cache", message: "Cache hit for key cart:user:8821" },
  { id: "l03", timestamp: "2026-04-01T09:12:44.302Z", level: "ERROR", service: "db",    message: "Connection timeout after 2000ms — pool exhausted", traceId: "d4e5f6a1", anomaly: "DB pool exhaustion detected (3rd occurrence in 5 min)" },
  { id: "l04", timestamp: "2026-04-01T09:12:43.778Z", level: "WARN",  service: "api",   message: "Retry attempt 2/3 for downstream service db" },
  { id: "l05", timestamp: "2026-04-01T09:12:42.567Z", level: "INFO",  service: "web",   message: "GET /api/recommendations 200 OK 89ms" },
  { id: "l06", timestamp: "2026-04-01T09:12:41.234Z", level: "DEBUG", service: "api",   message: "Cache miss for reco:user:8821 — fetching from ML service" },
  { id: "l07", timestamp: "2026-04-01T09:12:40.999Z", level: "INFO",  service: "api",   message: "ML inference completed: 12 recommendations scored" },
  { id: "l08", timestamp: "2026-04-01T09:12:40.500Z", level: "WARN",  service: "db",    message: "Slow query detected: SELECT products — 1190ms (threshold: 500ms)", anomaly: "Query P99 degradation" },
  { id: "l09", timestamp: "2026-04-01T09:12:39.124Z", level: "INFO",  service: "web",   message: "POST /api/auth/login 200 OK 1247ms", traceId: "c3d4e5f6" },
  { id: "l10", timestamp: "2026-04-01T09:12:38.441Z", level: "INFO",  service: "api",   message: "User session created: session_id=sess_9a8b7c" },
  { id: "l11", timestamp: "2026-04-01T09:12:37.109Z", level: "ERROR", service: "api",   message: "Unhandled exception in products.listHandler: TypeError: Cannot read properties of null", traceId: "d4e5f6a1", anomaly: "New error type (first occurrence)" },
  { id: "l12", timestamp: "2026-04-01T09:12:36.883Z", level: "INFO",  service: "cache", message: "Eviction: 142 expired keys removed from LRU cache" },
  { id: "l13", timestamp: "2026-04-01T09:12:35.654Z", level: "DEBUG", service: "db",    message: "Transaction committed: orders INSERT rowcount=1" },
  { id: "l14", timestamp: "2026-04-01T09:12:34.210Z", level: "INFO",  service: "web",   message: "POST /api/search 200 OK 156ms", traceId: "e5f6a1b2" },
  { id: "l15", timestamp: "2026-04-01T09:12:33.871Z", level: "WARN",  service: "api",   message: "Rate limit approaching: user:8821 at 87/100 requests/min" },
  { id: "l16", timestamp: "2026-04-01T09:12:33.100Z", level: "INFO",  service: "db",    message: "Vacuum analyze completed on table products: 38,241 rows" },
  { id: "l17", timestamp: "2026-04-01T09:12:32.445Z", level: "DEBUG", service: "api",   message: "Health check passed: all 4 downstream services reachable" },
  { id: "l18", timestamp: "2026-04-01T09:12:31.773Z", level: "INFO",  service: "web",   message: "Static asset served from CDN: /assets/bundle.js (cached)" },
  { id: "l19", timestamp: "2026-04-01T09:12:30.321Z", level: "WARN",  service: "cache", message: "Memory usage at 78% — consider increasing cache size" },
  { id: "l20", timestamp: "2026-04-01T09:12:29.012Z", level: "INFO",  service: "api",   message: "Deployment health check: version=v2.14.3 status=healthy" },
];

const ALL_SERVICES = ["api", "web", "db", "cache"];
const ALL_LEVELS: LogLevel[] = ["INFO", "WARN", "ERROR", "DEBUG"];

/* ============================================================
 * Helpers
 * ============================================================ */

function levelIcon(level: LogLevel) {
  switch (level) {
    case "ERROR": return <XCircle size={14} className="text-red-400 shrink-0" />;
    case "WARN":  return <AlertTriangle size={14} className="text-yellow-400 shrink-0" />;
    case "INFO":  return <Info size={14} className="text-blue-400 shrink-0" />;
    case "DEBUG": return <CheckCircle2 size={14} className="text-[#64748b] shrink-0" />;
  }
}

function levelVariant(level: LogLevel): "green" | "yellow" | "red" | "default" {
  switch (level) {
    case "ERROR": return "red";
    case "WARN":  return "yellow";
    case "INFO":  return "default";
    case "DEBUG": return "default";
  }
}

function levelBg(level: LogLevel): string {
  switch (level) {
    case "ERROR": return "bg-red-500/5 border-red-500/15";
    case "WARN":  return "bg-yellow-500/5 border-yellow-500/15";
    case "INFO":  return "bg-white/[0.02] border-[#1e293b]";
    case "DEBUG": return "bg-white/[0.01] border-[#1e293b]/50";
  }
}

/* ============================================================
 * Main Page
 * ============================================================ */

export default function LogsPage() {
  const locale = useLocale();

  const [searchQuery, setSearchQuery]     = useState("");
  const [filterLevel, setFilterLevel]     = useState<string>("all");
  const [filterService, setFilterService] = useState<string>("all");
  const [showAnomaly, setShowAnomaly]     = useState(false);
  const [refreshKey, setRefreshKey]       = useState(0);

  const filtered = useMemo(() => {
    return DEMO_LOGS.filter((log) => {
      if (filterLevel !== "all" && log.level !== filterLevel) return false;
      if (filterService !== "all" && log.service !== filterService) return false;
      if (showAnomaly && !log.anomaly) return false;
      if (searchQuery && !log.message.toLowerCase().includes(searchQuery.toLowerCase()) && !log.service.toLowerCase().includes(searchQuery.toLowerCase())) return false;
      return true;
    });
  }, [searchQuery, filterLevel, filterService, showAnomaly, refreshKey]);

  const errorCount = DEMO_LOGS.filter((l) => l.level === "ERROR").length;
  const warnCount  = DEMO_LOGS.filter((l) => l.level === "WARN").length;
  const anomalyCount = DEMO_LOGS.filter((l) => l.anomaly).length;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <FileText size={24} className="text-[#FFD700]" />
          {locale === "ja" ? "ログエクスプローラー" : "Log Explorer"}
        </h1>
        <p className="text-[#94a3b8] text-sm">
          {locale === "ja"
            ? "全サービスの構造化ログ検索・異常検知 (Layer 0)"
            : "Structured log search with anomaly detection across all services (Layer 0)"}
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
        {[
          { label: locale === "ja" ? "総エントリー数" : "Total Entries", value: DEMO_LOGS.length, color: "#e2e8f0" },
          { label: locale === "ja" ? "エラー" : "Errors",                value: errorCount,        color: "#ef4444" },
          { label: locale === "ja" ? "警告" : "Warnings",                value: warnCount,         color: "#f59e0b" },
          { label: locale === "ja" ? "異常検知" : "Anomalies",           value: anomalyCount,      color: "#a855f7" },
        ].map((stat) => (
          <Card key={stat.label} className="text-center">
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-1">{stat.label}</p>
            <p className="text-3xl font-extrabold font-mono" style={{ color: stat.color }}>{stat.value}</p>
          </Card>
        ))}
      </div>

      {/* Search + Filters */}
      <Card className="mb-6">
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex items-center gap-2 text-[#64748b]">
            <Filter size={14} />
            <span className="text-xs font-medium uppercase tracking-wider">{locale === "ja" ? "フィルター" : "Filters"}</span>
          </div>

          {/* Search */}
          <div className="relative flex-1 min-w-[220px]">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-[#64748b]" />
            <input
              className="w-full bg-white/5 border border-[#1e293b] rounded-lg pl-8 pr-3 py-1.5 text-sm text-[#e2e8f0] placeholder-[#475569] focus:outline-none focus:border-[#FFD700]/40 font-mono"
              placeholder='message contains "timeout" OR service:db'
              aria-label={locale === "ja" ? "ログメッセージを検索" : "Search log messages"}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
          </div>

          {/* Level filter */}
          <select
            className="bg-[#0d1526] border border-[#1e293b] rounded-lg px-3 py-1.5 text-sm text-[#94a3b8] focus:outline-none"
            value={filterLevel}
            onChange={(e) => setFilterLevel(e.target.value)}
            aria-label={locale === "ja" ? "ログレベルでフィルター" : "Filter by log level"}
          >
            <option value="all">{locale === "ja" ? "全レベル" : "All Levels"}</option>
            {ALL_LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>

          {/* Service filter */}
          <select
            className="bg-[#0d1526] border border-[#1e293b] rounded-lg px-3 py-1.5 text-sm text-[#94a3b8] focus:outline-none"
            value={filterService}
            onChange={(e) => setFilterService(e.target.value)}
            aria-label={locale === "ja" ? "サービスでフィルター" : "Filter by service"}
          >
            <option value="all">{locale === "ja" ? "全サービス" : "All Services"}</option>
            {ALL_SERVICES.map((s) => <option key={s} value={s}>{s}</option>)}
          </select>

          {/* Anomaly toggle */}
          <button
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm border transition-colors ${
              showAnomaly
                ? "bg-purple-500/10 border-purple-500/30 text-purple-400"
                : "border-[#1e293b] text-[#64748b] hover:border-[#475569]"
            }`}
            onClick={() => setShowAnomaly(!showAnomaly)}
          >
            <Zap size={13} />
            {locale === "ja" ? "異常のみ表示" : "Anomalies Only"}
          </button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => setRefreshKey((k) => k + 1)}
          >
            <RefreshCw size={13} />
            {locale === "ja" ? "更新" : "Refresh"}
          </Button>
        </div>
      </Card>

      {/* Log Entries */}
      <Card>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-semibold text-[#94a3b8]">
            {locale === "ja"
              ? `${filtered.length} / ${DEMO_LOGS.length} 件を表示中`
              : `Showing ${filtered.length} of ${DEMO_LOGS.length} entries`}
          </h3>
          <div className="flex gap-2">
            {ALL_LEVELS.map((level) => (
              <span key={level} className="flex items-center gap-1 text-xs text-[#64748b]">
                {levelIcon(level)}
                {DEMO_LOGS.filter((l) => l.level === level).length}
              </span>
            ))}
          </div>
        </div>

        <div className="space-y-1.5 font-mono text-xs">
          {filtered.length === 0 && (
            <p className="text-center text-[#64748b] py-8">
              {locale === "ja" ? "現在のフィルターに一致するログがありません。" : "No log entries match the current filters."}
            </p>
          )}

          {filtered.map((log) => (
            <div
              key={log.id}
              className={`p-3 rounded-lg border ${levelBg(log.level)}`}
            >
              <div className="flex items-start gap-3">
                {levelIcon(log.level)}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap mb-0.5">
                    <span className="text-[#475569]">{new Date(log.timestamp).toISOString().replace("T", " ").slice(0, 23)}</span>
                    <Badge variant={levelVariant(log.level)} className="text-[10px] py-0 px-1.5">{log.level}</Badge>
                    <span
                      className="px-1.5 py-0.5 rounded text-[10px] font-medium"
                      style={{ backgroundColor: "#1e293b", color: "#94a3b8" }}
                    >
                      {log.service}
                    </span>
                    {log.traceId && (
                      <span className="text-[#475569]">trace={log.traceId}</span>
                    )}
                  </div>
                  <p className={`leading-relaxed ${log.level === "ERROR" ? "text-red-300" : log.level === "WARN" ? "text-yellow-200" : "text-[#e2e8f0]"}`}>
                    {log.message}
                  </p>
                  {log.anomaly && (
                    <div className="mt-1.5 flex items-center gap-2 text-purple-400">
                      <Zap size={11} />
                      <span className="text-[11px]">Anomaly: {log.anomaly}</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* Time Range hint */}
      <p className="text-xs text-[#475569] mt-4 text-center">
        {locale === "ja"
          ? <>直近5分を表示中 · 10秒ごとに自動更新 · クエリ構文: <span className="text-[#64748b]">level:ERROR service:db timeout</span></>
          : <>Showing last 5 minutes · Auto-refresh every 10s · Use query syntax: <span className="text-[#64748b]">level:ERROR service:db timeout</span></>
        }
      </p>

      {/* FLOW-11: Cross-links to related observability pages */}
      <div className="flex items-center gap-3 mt-6 pt-4 border-t border-[#1e293b]">
        <span className="text-xs text-[#475569]">{locale === "ja" ? "関連:" : "Related:"}</span>
        <Link href="/traces" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <Activity size={12} />
          {locale === "ja" ? "トレース" : "Traces"}
        </Link>
        <Link href="/reports" className="flex items-center gap-1.5 text-xs text-[#64748b] hover:text-[#94a3b8] transition-colors">
          <BookOpen size={12} />
          {locale === "ja" ? "レポート" : "Reports"}
        </Link>
      </div>
    </div>
  );
}
