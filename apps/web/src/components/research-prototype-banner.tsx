"use client";

import { useLocale } from "@/lib/useLocale";

/**
 * LIABILITY-CAP: Site-wide decision-support disclosure banner.
 *
 * Why: FaultRay assists with DORA resilience preparation, but its outputs are
 * not certified audit evidence. We must keep a clear, site-wide disclosure that
 * caps regulatory-overclaim / civil-liability exposure — WITHOUT the alarmist
 * "do not rely on this" framing that drove away the compliance buyers who are
 * the only audience with budget. The copy below preserves the legal substance
 * (not legal advice / not an audit opinion / not certification; validate before
 * submission) while positioning FaultRay as professional decision-support
 * software rather than an unusable "research prototype".
 *
 * Rendered site-wide inside the LocaleProvider so every page shows the
 * disclosure in the user's language. Translations are kept inline (not in the
 * i18n dict loader) so the disclosure renders even if dictionary loading fails
 * — the liability cap must not depend on the normal app happy-path.
 */
const DISCLAIMERS: Record<string, string> = {
  en: "FaultRay is decision-support software for DORA resilience preparation — it helps generate resilience scenarios and evidence for internal review. It is not legal advice, an audit opinion, or regulatory certification; validate outputs with your engineering, risk, and compliance teams before audit submission.",
  ja: "FaultRayはDORAレジリエンス準備のための意思決定支援ソフトウェアです。社内レビュー用のレジリエンスシナリオとエビデンス作成を支援します。法的助言・監査意見・規制認証ではありません。監査提出前に、自社のエンジニアリング・リスク・コンプライアンス部門で出力を検証してください。",
  de: "FaultRay ist Entscheidungsunterstützungssoftware für die DORA-Resilienzvorbereitung — sie hilft, Resilienzszenarien und Nachweise für die interne Prüfung zu erstellen. Sie ist keine Rechtsberatung, kein Prüfungsurteil und keine regulatorische Zertifizierung; validieren Sie die Ergebnisse vor der Audit-Einreichung mit Ihren Engineering-, Risiko- und Compliance-Teams.",
  fr: "FaultRay est un logiciel d'aide à la décision pour la préparation à la résilience DORA — il aide à générer des scénarios de résilience et des preuves pour une revue interne. Ce n'est pas un conseil juridique, un avis d'audit ni une certification réglementaire ; validez les résultats avec vos équipes d'ingénierie, de risque et de conformité avant toute soumission d'audit.",
  es: "FaultRay es software de apoyo a la decisión para la preparación de resiliencia DORA — ayuda a generar escenarios de resiliencia y evidencia para revisión interna. No es asesoramiento legal, una opinión de auditoría ni una certificación regulatoria; valide los resultados con sus equipos de ingeniería, riesgo y cumplimiento antes de presentar la auditoría.",
  pt: "O FaultRay é um software de apoio à decisão para a preparação de resiliência DORA — ajuda a gerar cenários de resiliência e evidências para revisão interna. Não é aconselhamento jurídico, parecer de auditoria nem certificação regulatória; valide os resultados com as suas equipas de engenharia, risco e conformidade antes da submissão da auditoria.",
  ko: "FaultRay는 DORA 복원력 준비를 위한 의사결정 지원 소프트웨어로, 내부 검토용 복원력 시나리오와 증거 생성을 지원합니다. 법률 자문, 감사 의견 또는 규제 인증이 아니며, 감사 제출 전에 엔지니어링·리스크·컴플라이언스 팀과 함께 출력을 검증하십시오.",
  zh: "FaultRay 是用于 DORA 韧性准备的决策支持软件——它帮助生成供内部审查的韧性场景与证据。它并非法律意见、审计意见或监管认证；在提交审计之前，请与您的工程、风险与合规团队一起验证输出。",
};

export function ResearchPrototypeBanner() {
  const locale = useLocale();
  const text = DISCLAIMERS[locale] ?? DISCLAIMERS.en;

  return (
    <div
      role="note"
      aria-label="Product disclosure"
      className="fixed top-16 left-0 right-0 z-40 bg-[var(--bg-secondary)] text-[var(--text-muted)] text-center text-xs sm:text-sm px-4 py-2 border-b border-[var(--border-color)]"
    >
      {text}
    </div>
  );
}
