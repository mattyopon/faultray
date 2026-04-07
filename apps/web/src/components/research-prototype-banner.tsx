"use client";

import { useLocale } from "@/lib/useLocale";

/**
 * LIABILITY-CAP: Site-wide research prototype disclaimer banner.
 *
 * Why: FaultRay landing previously claimed "DORA Compliance Reports",
 * "audit-ready reports", and "Prove DORA / SOC 2 compliance" across
 * 8 locales. Those claims created regulatory overclaim / civil liability
 * exposure for any financial institution SRE who might mistake FaultRay
 * outputs as DORA audit evidence.
 *
 * This banner is rendered site-wide inside the LocaleProvider so that
 * every page across every locale displays the disclaimer in the user's
 * own language. The translations are kept inline here (not in the main
 * i18n dict loader) so the banner renders even if dictionary loading
 * fails — liability cap must not depend on normal app happy-path.
 */
const DISCLAIMERS: Record<string, string> = {
  en: "⚠ Research prototype — outputs are NOT validated for DORA, FISC, or any regulatory audit. Do not rely on FaultRay evidence for compliance decisions without independent legal and technical review.",
  ja: "⚠ 研究プロトタイプ — 出力はDORA・FISC等の規制監査に対して検証されていません。独立した法務・技術レビューなしにコンプライアンス判断にFaultRayのエビデンスを使用しないでください。",
  de: "⚠ Forschungsprototyp — Ausgaben sind NICHT für DORA, FISC oder andere regulatorische Audits validiert. Verwenden Sie FaultRay-Evidenz nicht für Compliance-Entscheidungen ohne unabhängige juristische und technische Prüfung.",
  fr: "⚠ Prototype de recherche — les sorties ne sont PAS validées pour DORA, FISC ou tout audit réglementaire. Ne vous fiez pas aux preuves FaultRay pour des décisions de conformité sans examen juridique et technique indépendant.",
  es: "⚠ Prototipo de investigación — las salidas NO están validadas para DORA, FISC ni ninguna auditoría regulatoria. No confíe en la evidencia de FaultRay para decisiones de cumplimiento sin una revisión legal y técnica independiente.",
  pt: "⚠ Protótipo de pesquisa — as saídas NÃO são validadas para DORA, FISC ou qualquer auditoria regulatória. Não confie nas evidências do FaultRay para decisões de conformidade sem revisão jurídica e técnica independente.",
  ko: "⚠ 연구 프로토타입 — 출력은 DORA, FISC 또는 기타 규제 감사에 대해 검증되지 않았습니다. 독립적인 법률 및 기술 검토 없이 FaultRay 증거를 규정 준수 결정에 사용하지 마십시오.",
  zh: "⚠ 研究原型 — 输出未针对 DORA、FISC 或任何监管审计进行验证。在没有独立法律和技术审查的情况下，请勿依赖 FaultRay 证据进行合规决策。",
};

export function ResearchPrototypeBanner() {
  const locale = useLocale();
  const text = DISCLAIMERS[locale] ?? DISCLAIMERS.en;

  return (
    <div
      role="status"
      aria-label="Research prototype notice"
      className="fixed top-16 left-0 right-0 z-40 bg-amber-500 text-black text-center text-xs sm:text-sm font-medium px-4 py-2 border-b border-amber-700"
    >
      {text}
    </div>
  );
}
