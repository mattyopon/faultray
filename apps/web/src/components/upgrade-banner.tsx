"use client";

import Link from "next/link";
import { Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useLocale } from "@/lib/useLocale";

const T: Record<string, Record<string, string>> = {
  en: {
    title: "Pro Plan Required",
    desc: "This feature is available on Pro plan and above.",
    cta: "Upgrade to Pro",
  },
  ja: {
    title: "Proプラン以上が必要です",
    desc: "この機能はProプラン以上でご利用いただけます。",
    cta: "Proにアップグレード",
  },
  de: {
    title: "Pro-Plan erforderlich",
    desc: "Diese Funktion ist im Pro-Plan und höher verfügbar.",
    cta: "Auf Pro upgraden",
  },
  fr: {
    title: "Plan Pro requis",
    desc: "Cette fonctionnalité est disponible avec le plan Pro et supérieur.",
    cta: "Passer au Pro",
  },
  zh: {
    title: "需要Pro计划",
    desc: "此功能在Pro计划及以上版本中可用。",
    cta: "升级到Pro",
  },
  ko: {
    title: "Pro 플랜 필요",
    desc: "이 기능은 Pro 플랜 이상에서 사용 가능합니다.",
    cta: "Pro로 업그레이드",
  },
  es: {
    title: "Plan Pro requerido",
    desc: "Esta función está disponible en el plan Pro y superiores.",
    cta: "Actualizar a Pro",
  },
  pt: {
    title: "Plano Pro necessário",
    desc: "Este recurso está disponível no plano Pro e acima.",
    cta: "Atualizar para Pro",
  },
};

export function UpgradeBanner() {
  const locale = useLocale();
  const t = T[locale] ?? T.en;

  return (
    <div className="max-w-[1200px] mx-auto px-6 py-20 flex flex-col items-center justify-center text-center">
      <div className="w-16 h-16 rounded-2xl bg-[var(--gold)]/10 border border-[var(--gold)]/20 flex items-center justify-center mb-6">
        <Lock size={28} className="text-[var(--gold)]" />
      </div>
      <h2 className="text-2xl font-bold mb-2">{t.title}</h2>
      <p className="text-[var(--text-secondary)] text-sm mb-8 max-w-xs">{t.desc}</p>
      <Link href="/pricing">
        <Button size="sm">
          {t.cta}
        </Button>
      </Link>
    </div>
  );
}
