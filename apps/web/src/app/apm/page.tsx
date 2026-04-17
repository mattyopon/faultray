"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useState, useEffect } from "react";
import { Radio, RefreshCw } from "lucide-react";
import { useLocale } from "@/lib/useLocale";

const T: Record<string, Record<string, string>> = {
  en: { title: "Infrastructure Monitor", subtitle: "Near-real-time infrastructure metrics (refresh interval-based) linked to simulation results — correlate observed performance with modeled failure scenarios", agents: "Connected Agents", alerts: "Active Alerts", cpu: "Avg CPU", mem: "Avg Memory", agentTable: "Agents", alertTable: "Recent Alerts", refresh: "Refresh" },
  ja: { title: "インフラストラクチャ モニター", subtitle: "シミュレーション結果とのニアリアルタイム・インフラメトリクス連携（更新間隔ベース） — モデル化された障害シナリオと観測されたパフォーマンスを照合", agents: "接続エージェント", alerts: "アクティブアラート", cpu: "平均CPU", mem: "平均メモリ", agentTable: "エージェント", alertTable: "最近のアラート", refresh: "更新" },
  de: { title: "Infrastruktur-Monitor", subtitle: "Nahezu-Echtzeit-Infrastrukturmetriken (intervallbasiert) verknüpft mit Simulationsergebnissen", agents: "Verbundene Agents", alerts: "Aktive Warnungen", cpu: "Ø CPU", mem: "Ø Speicher", agentTable: "Agents", alertTable: "Aktuelle Warnungen", refresh: "Aktualisieren" },
  fr: { title: "Moniteur d'Infrastructure", subtitle: "Métriques d'infrastructure en quasi-temps réel (basées sur intervalle de rafraîchissement) liées aux résultats de simulation", agents: "Agents connectés", alerts: "Alertes actives", cpu: "CPU moy.", mem: "Mémoire moy.", agentTable: "Agents", alertTable: "Alertes récentes", refresh: "Actualiser" },
  zh: { title: "基础设施监控", subtitle: "近实时基础设施指标（基于刷新间隔）与模拟结果关联 — 将观测到的性能与模型故障场景相关联", agents: "已连接代理", alerts: "活跃警报", cpu: "平均CPU", mem: "平均内存", agentTable: "代理", alertTable: "最近警报", refresh: "刷新" },
  ko: { title: "인프라 모니터", subtitle: "시뮬레이션 결과와 연동된 준실시간(새로고침 간격 기반) 인프라 메트릭", agents: "연결된 에이전트", alerts: "활성 경고", cpu: "평균 CPU", mem: "평균 메모리", agentTable: "에이전트", alertTable: "최근 경고", refresh: "새로 고침" },
  es: { title: "Monitor de Infraestructura", subtitle: "Métricas de infraestructura casi en tiempo real (basadas en intervalo de actualización) vinculadas a resultados de simulación", agents: "Agentes conectados", alerts: "Alertas activas", cpu: "CPU prom.", mem: "Memoria prom.", agentTable: "Agentes", alertTable: "Alertas recientes", refresh: "Actualizar" },
  pt: { title: "Monitor de Infraestrutura", subtitle: "Métricas de infraestrutura quase em tempo real (baseadas em intervalo de atualização) vinculadas aos resultados de simulação", agents: "Agentes conectados", alerts: "Alertas ativos", cpu: "CPU méd.", mem: "Memória méd.", agentTable: "Agentes", alertTable: "Alertas recentes", refresh: "Atualizar" },
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
    const controller = new AbortController();
    fetch("/api/apm/agents", { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => { if (Array.isArray(d?.agents)) setAgentList(d.agents); })
      .catch((err) => console.error("[apm] fetch error:", err));
    fetch("/api/apm/alerts", { signal: controller.signal })
      .then((r) => r.json())
      .then((d) => { if (Array.isArray(d?.alerts)) setAlertList(d.alerts); })
      .catch((err) => console.error("[apm] fetch error:", err));
    return () => controller.abort();
  };

  useEffect(load, []);

  const avgCpu = agentList.filter((a) => a.status !== "offline").reduce((s, a) => s + a.cpu, 0) / Math.max(1, agentList.filter((a) => a.status !== "offline").length);
  const avgMem = agentList.filter((a) => a.status !== "offline").reduce((s, a) => s + a.mem, 0) / Math.max(1, agentList.filter((a) => a.status !== "offline").length);

  return (
    <div className="w-full px-6 py-10">
      <div className="flex items-center justify-between mb-1">
        <h1 className="text-2xl font-bold flex items-center gap-3">
          <Radio size={24} className="text-[var(--gold)]" />
          {t.title}
        </h1>
        <Button variant="secondary" size="sm" onClick={load}>
          <RefreshCw size={14} className="mr-1" /> {t.refresh}
        </Button>
      </div>
      <p className="text-[var(--text-secondary)] text-sm mb-8">{t.subtitle}</p>

      <div className="grid md:grid-cols-4 gap-4 mb-8">
        <Card>
          <p className="text-xs text-[var(--text-muted)] uppercase mb-2">{t.agents}</p>
          <p className="text-3xl font-bold text-[var(--gold)]">{agentList.length}</p>
        </Card>
        <Card>
          <p className="text-xs text-[var(--text-muted)] uppercase mb-2">{t.alerts}</p>
          <p className="text-3xl font-bold text-[var(--gold)]">{alertList.length}</p>
        </Card>
        <Card>
          <p className="text-xs text-[var(--text-muted)] uppercase mb-2">{t.cpu}</p>
          <p className="text-3xl font-bold text-[var(--gold)]">{avgCpu.toFixed(0)}%</p>
        </Card>
        <Card>
          <p className="text-xs text-[var(--text-muted)] uppercase mb-2">{t.mem}</p>
          <p className="text-3xl font-bold text-[var(--gold)]">{avgMem.toFixed(0)}%</p>
        </Card>
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <Card>
          <h2 className="text-lg font-bold mb-4">{t.agentTable}</h2>
          <div className="space-y-2">
            {agentList.map((a) => (
              <div key={a.id} className="flex items-center gap-3 text-sm">
                <span className="font-mono text-xs text-[var(--text-muted)] w-20">{a.id}</span>
                <span className="flex-1 text-[var(--text-secondary)]">{a.hostname}</span>
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
                  <p className="text-sm text-[var(--text-secondary)]">{a.message}</p>
                  <p className="text-xs text-[var(--text-muted)]">{a.agent}</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
