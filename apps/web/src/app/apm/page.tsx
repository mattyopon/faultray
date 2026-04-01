"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { Radio, RefreshCw } from "lucide-react";
import { useLocale } from "@/lib/useLocale";

const T: Record<string, Record<string, string>> = {
  en: { title: "APM Dashboard", subtitle: "Real-time monitoring of connected agents, metrics, and alerts", agents: "Connected Agents", alerts: "Active Alerts", cpu: "Avg CPU", mem: "Avg Memory", agentTable: "Agents", alertTable: "Recent Alerts", refresh: "Refresh" },
  ja: { title: "APM ダッシュボード", subtitle: "接続エージェント・メトリクス・アラートのリアルタイム監視", agents: "接続エージェント", alerts: "アクティブアラート", cpu: "平均CPU", mem: "平均メモリ", agentTable: "エージェント", alertTable: "最近のアラート", refresh: "更新" },
};

interface Agent { id: string; hostname: string; status: string; cpu: number; mem: number; }
interface Alert { id: string; severity: string; message: string; agent: string; }

const DEFAULT_AGENTS: Agent[] = [
  { id: "agt-001", hostname: "prod-web-01", status: "running", cpu: 42, mem: 61 },
  { id: "agt-002", hostname: "prod-web-02", status: "running", cpu: 38, mem: 55 },
  { id: "agt-003", hostname: "prod-db-01", status: "degraded", cpu: 78, mem: 82 },
  { id: "agt-004", hostname: "prod-worker-01", status: "offline", cpu: 0, mem: 0 },
];

const DEFAULT_ALERTS: Alert[] = [
  { id: "a1", severity: "critical", message: "CPU usage above 75%", agent: "prod-db-01" },
  { id: "a2", severity: "warning", message: "Memory usage above 80%", agent: "prod-db-01" },
  { id: "a3", severity: "warning", message: "Agent disconnected", agent: "prod-worker-01" },
];

export default function ApmPage() {
  const locale = useLocale();
  const t = T[locale] ?? T.en;
  const [agentList, setAgentList] = useState<Agent[]>(DEFAULT_AGENTS);
  const [alertList, setAlertList] = useState<Alert[]>(DEFAULT_ALERTS);

  const load = () => {
    fetch("/api/apm/agents")
      .then((r) => r.json())
      .then((d) => { if (Array.isArray(d?.agents)) setAgentList(d.agents); })
      .catch(() => {});
    fetch("/api/apm/alerts")
      .then((r) => r.json())
      .then((d) => { if (Array.isArray(d?.alerts)) setAlertList(d.alerts); })
      .catch(() => {});
  };

  useEffect(load, []);

  const avgCpu = agentList.filter((a) => a.status !== "offline").reduce((s, a) => s + a.cpu, 0) / Math.max(1, agentList.filter((a) => a.status !== "offline").length);
  const avgMem = agentList.filter((a) => a.status !== "offline").reduce((s, a) => s + a.mem, 0) / Math.max(1, agentList.filter((a) => a.status !== "offline").length);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Radio size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <Button variant="outline" size="sm" onClick={load}>
          <RefreshCw size={14} className="mr-1" /> {t.refresh}
        </Button>
      </div>
      <p className="text-[#94a3b8] text-sm mb-8">{t.subtitle}</p>

      <div className="grid md:grid-cols-4 gap-4 mb-8">
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.agents}</p>
          <p className="text-3xl font-bold text-[#FFD700]">{agentList.length}</p>
        </Card>
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.alerts}</p>
          <p className="text-3xl font-bold text-[#FFD700]">{alertList.length}</p>
        </Card>
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.cpu}</p>
          <p className="text-3xl font-bold text-[#FFD700]">{avgCpu.toFixed(0)}%</p>
        </Card>
        <Card>
          <p className="text-xs text-[#64748b] uppercase mb-2">{t.mem}</p>
          <p className="text-3xl font-bold text-[#FFD700]">{avgMem.toFixed(0)}%</p>
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <h2 className="text-lg font-bold mb-4">{t.agentTable}</h2>
          <div className="space-y-2">
            {agentList.map((a) => (
              <div key={a.id} className="flex items-center gap-3 text-sm">
                <span className="font-mono text-xs text-[#475569] w-20">{a.id}</span>
                <span className="flex-1 text-[#94a3b8]">{a.hostname}</span>
                <Badge variant={a.status === "running" ? "green" : a.status === "degraded" ? "yellow" : "red"}>{a.status}</Badge>
                <span className="font-mono w-14 text-right">CPU {a.cpu}%</span>
                <span className="font-mono w-14 text-right">Mem {a.mem}%</span>
              </div>
            ))}
          </div>
        </Card>

        <Card>
          <h2 className="text-lg font-bold mb-4">{t.alertTable}</h2>
          <div className="space-y-3">
            {alertList.map((a) => (
              <div key={a.id} className="flex items-start gap-3">
                <Badge variant={a.severity === "critical" ? "red" : a.severity === "warning" ? "yellow" : "default"}>{a.severity}</Badge>
                <div>
                  <p className="text-sm text-[#94a3b8]">{a.message}</p>
                  <p className="text-xs text-[#475569]">{a.agent}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
