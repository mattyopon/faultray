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
  ShieldAlert,
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
  Scale,
  Radio,
  FolderKanban,
  BookOpen,
  FileSearch,
  CalendarDays,
  Clock,
  GitBranch,
  Users,
  GitCompare,
  FlaskRound,
  Gauge,
  PackageSearch,
  FileCode2,
  Rocket,
  LayoutTemplate,
  TrendingUp,
  Brain,
  Swords,
  CircleDot,
  Landmark,
  FileSpreadsheet,
  UserX,
} from "lucide-react";
import { locales, type Locale } from "@/i18n/config";
import { appDict } from "@/i18n/app-dict";
import { useLocale } from "@/lib/useLocale";

function getNavGroups(t: Record<string, string>, te: Record<string, string>) {
  return [
    // ── 毎日使う（上） ──
    {
      label: t.observe ?? "OBSERVE",
      items: [
        { href: "/dashboard",     label: t.dashboard,                        icon: LayoutDashboard },
        { href: "/traffic-light", label: t.trafficLight ?? "Status",         icon: CircleDot },
        { href: "/apm",           label: t.apm,                              icon: Radio },
        { href: "/incidents",     label: t.incidents,                        icon: Activity },
      ],
    },
    // ── 週次で見る ──
    {
      label: t.simulate,
      items: [
        { href: "/simulate",    label: t.runSimulation,                icon: Zap },
        { href: "/remediation", label: t.remediationPlan,              icon: ClipboardCheck },
        { href: "/projects",    label: t.projects,                     icon: FolderKanban },
        { href: "/whatif",      label: t.whatIf,                       icon: FlaskConical },
      ],
    },
    {
      label: t.visualize ?? "VISUALIZE",
      items: [
        { href: "/topology",     label: t.topology,                       icon: Network },
        { href: "/dependencies", label: t.dependencies ?? "Dependencies", icon: GitBranch },
        { href: "/heatmap",      label: t.heatmap,                        icon: Flame },
        { href: "/people-risk",  label: t.peopleRisk ?? "People Risk",    icon: UserX },
        { href: "/score-detail", label: t.scoreDetail,                    icon: BarChart3 },
      ],
    },
    // ── 月次/必要時 ──
    {
      label: t.compliance,
      items: [
        { href: "/dora",         label: t.dora,                            icon: ShieldAlert },
        { href: "/governance",   label: t.governance,                      icon: Scale },
        { href: "/sla",          label: t.sla,                             icon: FileCheck },
        { href: "/compliance",   label: t.complianceItem,                  icon: ShieldCheck },
        { href: "/evidence",     label: t.evidence,                        icon: FileCheck },
        { href: "/audit-report", label: t.auditReport ?? "Audit Report",   icon: FileSpreadsheet },
        { href: "/fisc",         label: t.fisc ?? "FISC",                  icon: Landmark },
      ],
    },
    {
      label: t.improve ?? "IMPROVE",
      items: [
        { href: "/iac",      label: t.iac,         icon: FileCode2 },
        { href: "/optimize", label: te.optimize,    icon: Gauge },
        { href: "/gameday",  label: t.gameday ?? "GameDay", icon: Swords },
        { href: "/fmea",     label: t.fmea,         icon: AlertOctagon },
      ],
    },
    {
      label: t.aiSecurity ?? "AI & SECURITY",
      items: [
        { href: "/ai-reliability", label: t.aiReliability ?? "AI Reliability", icon: Brain },
        { href: "/advisor",        label: t.aiAdvisor,                          icon: Bot },
      ],
    },
    // ── たまに使う（下） ──
    {
      label: te.operations,
      items: [
        { href: "/runbooks",    label: te.runbooks,    icon: BookOpen },
        { href: "/postmortems", label: te.postmortems, icon: FileSearch },
        { href: "/calendar",    label: te.calendar,    icon: CalendarDays },
        { href: "/timeline",    label: te.timeline,    icon: Clock },
        { href: "/drift",       label: te.drift,       icon: GitBranch },
      ],
    },
    {
      label: te.teams,
      items: [
        { href: "/teams",        label: te.teamMetrics,  icon: Users },
        { href: "/env-compare",  label: te.envCompare,   icon: GitCompare },
        { href: "/canary",       label: te.canary,       icon: FlaskRound },
        { href: "/supply-chain", label: te.supplyChain,  icon: PackageSearch },
      ],
    },
    {
      label: t.observe ?? "MORE",
      items: [
        { href: "/traces",  label: t.traces ?? "Traces", icon: Activity },
        { href: "/logs",    label: t.logs ?? "Logs",     icon: FileText },
        { href: "/reports", label: t.reports ?? "Reports", icon: FileText },
        { href: "/benchmark", label: t.benchmark ?? "Benchmark", icon: BarChart3 },
      ],
    },
    // ── 初回/設定 ──
    {
      label: t.gettingStarted,
      items: [
        { href: "/onboarding",    label: t.onboarding,   icon: Rocket },
        { href: "/templates",     label: t.templates,    icon: LayoutTemplate },
        { href: "/ipo-readiness", label: t.ipoReadiness, icon: TrendingUp },
      ],
    },
    {
      label: t.account,
      items: [
        { href: "/settings", label: t.settings, icon: Settings },
        { href: "/help",     label: t.help,     icon: HelpCircle },
      ],
    },
  ];
}

export function Navbar() {
  const pathname = usePathname();
  const { user, loading: authLoading, signOut } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const locale = useLocale();
  const t = appDict.nav[locale] ?? appDict.nav.en;
  const te = appDict.navExtra[locale] ?? appDict.navExtra.en;
  const navGroups = useMemo(() => getNavGroups(t, te), [t, te]);

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
  const isAppPath = !isLanding && !pathname.startsWith("/login") && !pathname.startsWith("/pricing");
  // During auth loading on app paths, treat as app (avoid flash of landing nav)
  const isApp = isAppPath && (authLoading || !!user);

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
        <div className={`${isApp ? "pl-4 pr-6" : "max-w-[1200px] mx-auto px-6"} flex items-center justify-between h-16`}>
          <div className="flex items-center gap-2">
            {isApp && !authLoading && user && (
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

          {/* Desktop nav — hidden entirely during auth loading to prevent flash */}
          <div className={`hidden md:flex items-center gap-1 transition-opacity duration-200 ${authLoading ? "opacity-0 pointer-events-none" : "opacity-100"}`}>
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
          {!authLoading && !(isApp && user) && (
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

      {/* Sidebar for app pages — render skeleton during auth loading to prevent layout shift */}
      {isApp && (
        <>
          {/* Desktop Sidebar */}
          <aside
            className={`fixed top-16 left-0 bottom-0 z-40 bg-[#0a0e1a] border-r border-[#1e293b] transition-all duration-200 overflow-y-auto hidden md:block ${
              sidebarOpen ? "w-56" : "w-16"
            }`}
          >
            <div className="py-4">
              {/* Show nav content only after auth resolved */}
              {!authLoading && user && (<>
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
              </>)}
          </aside>

          {/* Mobile Sidebar Overlay */}
          {!authLoading && user && mobileOpen && (
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
              main > div[class*="max-w"] {
                max-width: 100% !important;
                padding-left: 1.5rem;
                padding-right: 1.5rem;
              }
            }
          `}</style>
        </>
      )}
    </>
  );
}
