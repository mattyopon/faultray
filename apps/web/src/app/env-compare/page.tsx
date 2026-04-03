"use client";

import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { GitCompare, ArrowRight } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

const ENVS = {
  production: {
    label: "Production",
    score: 85,
    components: [
      { name: "API Service", score: 92, replicas: 5, version: "v3.1.2", region: "us-east-1, us-west-2" },
      { name: "Database Primary", score: 88, replicas: 1, version: "postgres-15.4", region: "us-east-1" },
      { name: "Cache Cluster", score: 90, replicas: 6, version: "redis-7.2", region: "multi-az" },
      { name: "Worker Service", score: 78, replicas: 3, version: "v2.8.0", region: "us-east-1" },
      { name: "CDN", score: 97, replicas: null, version: "cloudfront-v3", region: "global" },
    ],
    config: {
      "auto_scaling": "enabled",
      "log_level": "warn",
      "cache_ttl": "3600",
      "rate_limit": "10000/min",
      "debug_mode": "false",
      "replica_count": "5",
      "memory_limit": "4Gi",
    },
  },
  staging: {
    label: "Staging",
    score: 72,
    components: [
      { name: "API Service", score: 75, replicas: 2, version: "v3.1.3-rc1", region: "us-east-1" },
      { name: "Database Primary", score: 80, replicas: 1, version: "postgres-15.4", region: "us-east-1" },
      { name: "Cache Cluster", score: 70, replicas: 3, version: "redis-7.2", region: "single-az" },
      { name: "Worker Service", score: 65, replicas: 1, version: "v2.8.1-dev", region: "us-east-1" },
      { name: "CDN", score: 80, replicas: null, version: "cloudfront-v2", region: "us-east-1" },
    ],
    config: {
      "auto_scaling": "disabled",
      "log_level": "debug",
      "cache_ttl": "300",
      "rate_limit": "1000/min",
      "debug_mode": "true",
      "replica_count": "2",
      "memory_limit": "2Gi",
    },
  },
};

type EnvKey = keyof typeof ENVS;

function ScorePill({ score }: { score: number }) {
  const color = score >= 85 ? "#10b981" : score >= 70 ? "#f59e0b" : "#ef4444";
  return (
    <span className="font-mono font-bold text-sm" style={{ color }}>{score}</span>
  );
}

export default function EnvComparePage() {
  const locale = useLocale();
  const t = appDict.envCompare[locale] ?? appDict.envCompare.en;

  const envA = ENVS.production;
  const envB = ENVS.staging;

  const configKeys = Object.keys(envA.config) as Array<keyof typeof envA.config>;
  const diffKeys = configKeys.filter((k) => envA.config[k] !== envB.config[k]);
  const sameKeys = configKeys.filter((k) => envA.config[k] === envB.config[k]);

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-10">
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1 flex items-center gap-3">
          <GitCompare size={24} className="text-[#FFD700]" />
          {t.title}
        </h1>
        <p className="text-[#94a3b8] text-sm">{t.subtitle}</p>
      </div>

      {/* Score comparison */}
      <div className="grid md:grid-cols-3 gap-4 mb-8">
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{envA.label}</p>
          <p className={`text-4xl font-extrabold font-mono ${envA.score >= 85 ? "text-[#10b981]" : "text-[#f59e0b]"}`}>
            {envA.score}
          </p>
          <p className="text-xs text-[#64748b] mt-1">{locale === "ja" ? "レジリエンススコア" : "Resilience Score"}</p>
        </Card>
        <Card className="text-center flex flex-col items-center justify-center">
          <ArrowRight size={24} className="text-[#64748b]" />
          <p className="text-xs text-[#64748b] mt-2">{t.differences}: <span className="text-[#f59e0b] font-bold">{diffKeys.length}</span></p>
        </Card>
        <Card className="text-center">
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{envB.label}</p>
          <p className={`text-4xl font-extrabold font-mono ${envB.score >= 85 ? "text-[#10b981]" : "text-[#f59e0b]"}`}>
            {envB.score}
          </p>
          <p className="text-xs text-[#64748b] mt-1">{locale === "ja" ? "レジリエンススコア" : "Resilience Score"}</p>
        </Card>
      </div>

      {/* Component comparison */}
      <Card className="mb-6">
        <p className="text-sm font-semibold text-[#FFD700] mb-4">{t.component} {locale === "ja" ? "比較" : "Comparison"}</p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-[#64748b] text-xs uppercase tracking-wider border-b border-[#1e293b]">
                <th scope="col" className="text-left py-2 pr-4">{t.component}</th>
                <th scope="col" className="text-center py-2 pr-4">{envA.label} Score</th>
                <th scope="col" className="text-center py-2 pr-4">{locale === "ja" ? "バージョン（A）" : "Version (A)"}</th>
                <th scope="col" className="text-center py-2 pr-4">{envB.label} Score</th>
                <th scope="col" className="text-center py-2 pr-4">{locale === "ja" ? "バージョン（B）" : "Version (B)"}</th>
                <th scope="col" className="text-left py-2">{locale === "ja" ? "差分" : "Delta"}</th>
              </tr>
            </thead>
            <tbody>
              {envA.components.map((comp, i) => {
                const compB = envB.components[i];
                const delta = comp.score - compB.score;
                const versionSame = comp.version === compB.version;
                return (
                  <tr key={comp.name} className="border-b border-[#1e293b]/50 hover:bg-white/2">
                    <td className="py-2.5 pr-4 font-semibold">{comp.name}</td>
                    <td className="py-2.5 pr-4 text-center"><ScorePill score={comp.score} /></td>
                    <td className="py-2.5 pr-4 text-center font-mono text-xs text-[#94a3b8]">{comp.version}</td>
                    <td className="py-2.5 pr-4 text-center"><ScorePill score={compB.score} /></td>
                    <td className="py-2.5 pr-4 text-center font-mono text-xs text-[#94a3b8]">
                      <span className={versionSame ? "" : "text-[#f59e0b]"}>{compB.version}</span>
                    </td>
                    <td className="py-2.5">
                      <span className={`font-mono text-sm font-bold ${delta > 0 ? "text-[#10b981]" : delta < 0 ? "text-red-400" : "text-[#64748b]"}`}>
                        {delta > 0 ? `+${delta}` : delta}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Config diff */}
      <Card>
        <p className="text-sm font-semibold text-[#FFD700] mb-4">{t.configDiff}</p>

        {/* Different keys */}
        {diffKeys.length > 0 && (
          <div className="mb-4">
            <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.different} ({diffKeys.length})</p>
            <div className="space-y-2">
              {diffKeys.map((key) => (
                <div key={key} className="grid grid-cols-3 gap-2 bg-[#0a0e1a] rounded-lg p-3">
                  <div>
                    <p className="text-xs text-[#64748b] mb-1 font-mono">{key}</p>
                  </div>
                  <div className="bg-[#1e293b]/50 rounded p-1.5">
                    <p className="text-xs text-[#64748b] mb-0.5">{envA.label}</p>
                    <code className="text-xs text-[#94a3b8]">{envA.config[key]}</code>
                  </div>
                  <div className="bg-[#f59e0b]/10 rounded p-1.5 border border-[#f59e0b]/20">
                    <p className="text-xs text-[#64748b] mb-0.5">{envB.label}</p>
                    <code className="text-xs text-[#f59e0b]">{envB.config[key]}</code>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Identical keys */}
        <div>
          <p className="text-xs text-[#64748b] uppercase tracking-wider mb-2">{t.identical} ({sameKeys.length})</p>
          <div className="grid md:grid-cols-2 gap-2">
            {sameKeys.map((key) => (
              <div key={key} className="flex items-center justify-between bg-[#0a0e1a] rounded-lg px-3 py-2">
                <code className="text-xs text-[#64748b] font-mono">{key}</code>
                <code className="text-xs text-[#10b981] font-mono">{envA.config[key]}</code>
              </div>
            ))}
          </div>
        </div>
      </Card>
    </div>
  );
}
