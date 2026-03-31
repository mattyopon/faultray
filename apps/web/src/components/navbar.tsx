"use client";

import { Logo } from "@/components/logo";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { NavLanguageSwitcher } from "@/components/language-switcher";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useMemo } from "react";
import {
  LayoutDashboard,
  Network,
  Flame,
  BarChart3,
  Zap,
  FlaskConical,
  AlertOctagon,
  Activity,
  ShieldCheck,
  Shield,
  DollarSign,
  FileText,
  Trophy,
  Bot,
  Settings,
  HelpCircle,
  Menu,
  X,
  LogOut,
  ChevronDown,
  ClipboardCheck,
  FileCheck,
  Radio,
  FolderKanban,
} from "lucide-react";
import { locales, type Locale } from "@/i18n/config";
import { appDict } from "@/i18n/app-dict";
import { useLocale } from "@/lib/useLocale";

function getNavGroups(t: Record<string, string>) {
  return [
    {
      label: t.analyze,
      items: [
        { href: "/projects", label: t.projects, icon: FolderKanban },
        { href: "/dashboard", label: t.dashboard, icon: LayoutDashboard },
        { href: "/topology", label: t.topology, icon: Network },
        { href: "/heatmap", label: t.heatmap, icon: Flame },
        { href: "/score-detail", label: t.scoreDetail, icon: BarChart3 },
      ],
    },
    {
      label: t.simulate,
      items: [
        { href: "/simulate", label: t.runSimulation, icon: Zap },
        { href: "/whatif", label: t.whatIf, icon: FlaskConical },
        { href: "/fmea", label: t.fmea, icon: AlertOctagon },
        { href: "/incidents", label: t.incidents, icon: Activity },
      ],
    },
    {
      label: t.compliance,
      items: [
        { href: "/compliance", label: t.complianceItem, icon: ShieldCheck },
        { href: "/security", label: t.security, icon: Shield },
        { href: "/cost", label: t.costAnalysis, icon: DollarSign },
        { href: "/reports", label: t.reports, icon: FileText },
        { href: "/benchmark", label: t.benchmark, icon: Trophy },
        { href: "/remediation", label: t.remediationPlan, icon: ClipboardCheck },
        { href: "/evidence", label: t.evidence, icon: FileCheck },
      ],
    },
    {
      label: t.monitor,
      items: [
        { href: "/apm", label: t.apm, icon: Radio },
      ],
    },
    {
      label: t.ai,
      items: [
        { href: "/advisor", label: t.aiAdvisor, icon: Bot },
      ],
    },
    {
      label: t.account,
      items: [
        { href: "/settings", label: t.settings, icon: Settings },
        { href: "/help", label: t.help, icon: HelpCircle },
      ],
    },
  ];
}

export function Navbar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const locale = useLocale();
  const t = appDict.nav[locale] ?? appDict.nav.en;
  const navGroups = useMemo(() => getNavGroups(t), [t]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // locale is from Context (useLocale) — no need to detect from URL

  // Check if we're on a localized LP page
  const isLocalizedLP = useMemo(() => {
    return locales.some(
      (loc) => pathname === `/${loc}` || pathname.startsWith(`/${loc}/`)
    );
  }, [pathname]);

  const isLanding = pathname === "/" || isLocalizedLP;
  const isApp = !isLanding && !pathname.startsWith("/login") && !pathname.startsWith("/pricing");

  // Mobile: close sidebar on navigate
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  return (
    <>
      {/* Top Navbar */}
      <nav
        className={`fixed top-0 left-0 right-0 z-50 backdrop-blur-xl transition-colors ${
          scrolled
            ? "border-b border-[#1e293b] bg-[#0a0e1a]/90"
            : "bg-[#0a0e1a]/80"
        }`}
      >
        <div className={`${isApp && user ? "pl-4 pr-6" : "max-w-[1200px] mx-auto px-6"} flex items-center justify-between h-16`}>
          <div className="flex items-center gap-2">
            {isApp && user && (
              <button
                className="p-2 text-[#94a3b8] hover:text-white transition-colors md:hidden"
                onClick={() => setMobileOpen(!mobileOpen)}
              >
                {mobileOpen ? <X size={20} /> : <Menu size={20} />}
              </button>
            )}
            <Link href={isLocalizedLP ? `/${locale}` : "/"} className="flex items-center gap-2.5 font-bold text-white">
              <Logo size={28} />
              <span>FaultRay</span>
            </Link>
          </div>

          {/* Desktop nav for non-app pages */}
          <div className="hidden md:flex items-center gap-1">
            {isApp && user ? (
              <div className="flex items-center gap-2">
                <span className="text-xs text-[#64748b] truncate max-w-[120px]">
                  {user.email}
                </span>
                <button
                  onClick={signOut}
                  className="p-2 text-[#64748b] hover:text-red-400 transition-colors"
                  title={t.signOut}
                >
                  <LogOut size={16} />
                </button>
              </div>
            ) : (
              <>
                <Link
                  href="#features"
                  className="px-3 py-2 text-sm text-[#94a3b8] hover:text-white transition-colors"
                >
                  Features
                </Link>
                <Link
                  href="#comparison"
                  className="px-3 py-2 text-sm text-[#94a3b8] hover:text-white transition-colors"
                >
                  Compare
                </Link>
                <Link
                  href="/pricing"
                  className="px-3 py-2 text-sm text-[#94a3b8] hover:text-white transition-colors"
                >
                  Pricing
                </Link>
                <Link
                  href="https://github.com/mattyopon/faultray"
                  target="_blank"
                  className="px-3 py-1.5 text-sm text-[#94a3b8] border border-[#1e293b] rounded-md hover:border-[#64748b] transition-colors"
                >
                  GitHub
                </Link>
                <div className="ml-2">
                  <NavLanguageSwitcher />
                </div>
                {user ? (
                  <Link href="/dashboard">
                    <Button size="sm" className="ml-2">
                      Dashboard
                    </Button>
                  </Link>
                ) : (
                  <Link href="/login">
                    <Button size="sm" className="ml-2">
                      Sign In
                    </Button>
                  </Link>
                )}
              </>
            )}
          </div>

          {/* Mobile toggle for non-app pages */}
          {!(isApp && user) && (
            <button
              className="md:hidden p-2 text-[#94a3b8]"
              onClick={() => setMobileOpen(!mobileOpen)}
            >
              {mobileOpen ? <X size={22} /> : <Menu size={22} />}
            </button>
          )}
        </div>

        {/* Mobile menu for non-app pages (landing, pricing, etc.) */}
        {mobileOpen && !(isApp && user) && (
          <div className="md:hidden border-t border-[#1e293b] bg-[#0a0e1a]/98 backdrop-blur-xl px-6 py-4 space-y-2">
            <Link
              href="/pricing"
              onClick={() => setMobileOpen(false)}
              className="block px-3 py-2.5 text-sm text-[#94a3b8]"
            >
              Pricing
            </Link>
            <Link
              href="/login"
              onClick={() => setMobileOpen(false)}
              className="block px-3 py-2.5 text-sm text-[#FFD700]"
            >
              Sign In
            </Link>
            <div className="px-3 py-2.5">
              <NavLanguageSwitcher />
            </div>
          </div>
        )}
      </nav>

      {/* Sidebar for app pages */}
      {isApp && user && (
        <>
          {/* Desktop Sidebar */}
          <aside
            className={`fixed top-16 left-0 bottom-0 z-40 bg-[#0a0e1a] border-r border-[#1e293b] transition-all duration-200 overflow-y-auto hidden md:block ${
              sidebarOpen ? "w-56" : "w-16"
            }`}
          >
            <div className="py-4">
              {/* Collapse toggle */}
              <button
                onClick={() => setSidebarOpen(!sidebarOpen)}
                className="w-full px-4 py-2 text-[#64748b] hover:text-white transition-colors flex items-center justify-end"
              >
                <ChevronDown size={14} className={`transition-transform ${sidebarOpen ? "rotate-0" : "-rotate-90"}`} />
              </button>

              {navGroups.map((group) => (
                <div key={group.label} className="mb-2">
                  {sidebarOpen && (
                    <p className="px-4 py-1 text-[10px] text-[#475569] uppercase tracking-wider font-semibold">
                      {group.label}
                    </p>
                  )}
                  {group.items.map((item) => {
                    const Icon = item.icon;
                    const active = pathname === item.href || pathname.startsWith(item.href + "/");
                    return (
                      <Link
                        key={item.href}
                        href={item.href}
                        className={`flex items-center gap-3 mx-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                          active
                            ? "text-[#FFD700] bg-[#FFD700]/10"
                            : "text-[#94a3b8] hover:text-white hover:bg-white/5"
                        }`}
                        title={item.label}
                      >
                        <Icon size={16} className="shrink-0" />
                        {sidebarOpen && <span className="truncate">{item.label}</span>}
                      </Link>
                    );
                  })}
                </div>
              ))}
            </div>
          </aside>

          {/* Mobile Sidebar Overlay */}
          {mobileOpen && (
            <div className="fixed inset-0 z-40 md:hidden">
              <div className="absolute inset-0 bg-black/50" onClick={() => setMobileOpen(false)} />
              <aside className="absolute top-16 left-0 bottom-0 w-64 bg-[#0a0e1a] border-r border-[#1e293b] overflow-y-auto">
                <div className="py-4">
                  {navGroups.map((group) => (
                    <div key={group.label} className="mb-2">
                      <p className="px-4 py-1 text-[10px] text-[#475569] uppercase tracking-wider font-semibold">
                        {group.label}
                      </p>
                      {group.items.map((item) => {
                        const Icon = item.icon;
                        const active = pathname === item.href || pathname.startsWith(item.href + "/");
                        return (
                          <Link
                            key={item.href}
                            href={item.href}
                            className={`flex items-center gap-3 mx-2 px-3 py-2 rounded-lg text-sm transition-colors ${
                              active
                                ? "text-[#FFD700] bg-[#FFD700]/10"
                                : "text-[#94a3b8] hover:text-white hover:bg-white/5"
                            }`}
                          >
                            <Icon size={16} className="shrink-0" />
                            <span>{item.label}</span>
                          </Link>
                        );
                      })}
                    </div>
                  ))}
                  <div className="mx-4 mt-4 pt-4 border-t border-[#1e293b]">
                    <button
                      onClick={signOut}
                      className="flex items-center gap-3 px-3 py-2 text-sm text-red-400 w-full"
                    >
                      <LogOut size={16} />
                      {t.signOut}
                    </button>
                  </div>
                </div>
              </aside>
            </div>
          )}

          {/* Content offset style for desktop sidebar */}
          <style>{`
            @media (min-width: 768px) {
              main {
                margin-left: ${sidebarOpen ? "14rem" : "4rem"} !important;
                transition: margin-left 0.2s;
              }
            }
          `}</style>
        </>
      )}
    </>
  );
}
