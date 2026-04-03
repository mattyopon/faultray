"use client";

import { Logo } from "@/components/logo";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { NavLanguageSwitcher } from "@/components/language-switcher";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect, useMemo, useCallback } from "react";
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
  FileText,
  Bot,
  Settings,
  HelpCircle,
  LifeBuoy,
  Menu,
  X,
  LogOut,
  ChevronDown,
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
  TrendingDown,
  Brain,
  Swords,
  CircleDot,
  Landmark,
  FileSpreadsheet,
  Ghost,
  Cloud,
  Map,
  Lock,
} from "lucide-react";
import type { PlanTier } from "@/components/auth-provider";

/** Pages accessible on Free plan */
const FREE_PAGES = new Set(["/dashboard", "/simulate", "/topology", "/dora", "/reports", "/help", "/support", "/changelog", "/admin"]);
import { locales, type Locale } from "@/i18n/config";
import { appDict } from "@/i18n/app-dict";
import { useLocale } from "@/lib/useLocale";
import { CommandPalette, type CommandItem } from "@/components/command-palette";

function getNavGroups(t: Record<string, string>, te: Record<string, string>) {
  return [
    // ── 毎日使う（上） ──
    {
      label: t.observe ?? "OBSERVE",
      items: [
        { href: "/dashboard",     label: t.dashboard,                        icon: LayoutDashboard },
        { href: "/traffic-light", label: t.trafficLight ?? "Status",         icon: CircleDot },
        { href: "/apm",           label: t.monitor ?? "Monitor",             icon: Radio },
        { href: "/incidents",     label: t.incidents,                        icon: Activity },
      ],
    },
    // ── 分析 ──
    {
      label: t.analyze ?? "ANALYZE",
      items: [
        { href: "/simulate",   label: t.runSimulation,              icon: Zap },
        { href: "/whatif",     label: t.whatIf,                     icon: FlaskConical },
        { href: "/fmea",       label: t.fmea,                       icon: AlertOctagon },
        { href: "/benchmark",  label: t.benchmark ?? "Monte Carlo", icon: BarChart3 },
        { href: "/sla-budget", label: t.slaBudget ?? "SLA Budget",  icon: Gauge },
      ],
    },
    // ── 可視化 ──
    {
      label: t.visualize ?? "VISUALIZE",
      items: [
        { href: "/topology",      label: t.topology,                          icon: Network },
        { href: "/dependencies",  label: t.dependencies ?? "Dependencies",   icon: GitBranch },
        { href: "/heatmap",       label: t.heatmap,                           icon: Flame },
        { href: "/people-risk",   label: t.peopleRisk ?? "People Risk",       icon: Users },
        { href: "/score-detail",  label: t.scoreDetail,                       icon: BarChart3 },
        { href: "/topology-map",  label: t.topologyMap ?? "Interactive Map",  icon: Map },
      ],
    },
    // ── コンプライアンス ──
    {
      label: t.compliance,
      items: [
        { href: "/dora",              label: t.dora,                                    icon: ShieldAlert },
        { href: "/compliance",        label: t.complianceItem,                          icon: ShieldCheck },
        { href: "/fisc",              label: t.fisc ?? "FISC",                          icon: Landmark },
        { href: "/sla",               label: t.sla,                                     icon: FileCheck },
        { href: "/governance",        label: t.governance,                              icon: Scale },
        { href: "/compliance-report", label: t.complianceReport ?? "Evidence Report",  icon: FileSpreadsheet },
      ],
    },
    // ── リスク管理 ──
    {
      label: t.riskManagement ?? "RISK",
      items: [
        { href: "/shadow-it",       label: t.shadowIt ?? "Shadow IT",        icon: Ghost },
        { href: "/bus-factor",      label: t.busFactor ?? "Bus Factor",      icon: TrendingDown },
        { href: "/vuln-priority",   label: t.vulnPriority ?? "Vuln Priority", icon: ShieldAlert },
        { href: "/external-impact", label: t.externalImpact ?? "SaaS Impact", icon: Cloud },
      ],
    },
    // ── 監査・証跡 ──
    {
      label: te.audit ?? "AUDIT",
      items: [
        { href: "/evidence",     label: t.evidence,                      icon: FileSearch },
        { href: "/audit-report", label: t.auditReport ?? "Audit Report", icon: FileSpreadsheet },
      ],
    },
    // ── 改善アクション ──
    {
      label: te.improveActions ?? "IMPROVE",
      items: [
        { href: "/projects",  label: t.remediationPlan,      icon: FolderKanban },
        { href: "/iac",       label: t.iac,                  icon: FileCode2 },
        { href: "/optimize",  label: te.optimize,            icon: Gauge },
        { href: "/gameday",   label: t.gameday ?? "GameDay", icon: Swords },
      ],
    },
    // ── AI ──
    {
      label: t.aiSecurity ?? "AI",
      items: [
        { href: "/ai-reliability", label: t.aiReliability ?? "AI Reliability", icon: Brain },
        { href: "/advisor",        label: t.aiAdvisor,                          icon: Bot },
      ],
    },
    // ── 運用 ──
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
    // ── チーム・環境 ──
    {
      label: te.teams,
      items: [
        { href: "/teams",        label: te.teamMetrics, icon: Users },
        { href: "/env-compare",  label: te.envCompare,  icon: GitCompare },
        { href: "/canary",       label: te.canary,      icon: FlaskRound },
        { href: "/supply-chain", label: te.supplyChain, icon: PackageSearch },
      ],
    },
    // ── レポート・ログ ──
    {
      label: t.moreTools ?? "REPORTS",
      items: [
        { href: "/traces",  label: t.traces ?? "Traces",   icon: Activity },
        { href: "/logs",    label: t.logs ?? "Logs",        icon: FileText },
        { href: "/reports", label: t.reports ?? "Reports",  icon: FileText },
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
        { href: "/settings",   label: t.settings,             icon: Settings },
        { href: "/help",       label: t.help,                 icon: HelpCircle },
        { href: "/support",    label: t.support,              icon: LifeBuoy },
        { href: "/changelog",  label: t.changelog ?? "What's New",  icon: FileText },
        { href: "/admin",      label: t.adminDash ?? "Admin", icon: BarChart3 },
      ],
    },
  ];
}

function SidebarNavItem({
  href,
  label,
  icon: Icon,
  active,
  sidebarOpen,
  isFree,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ size?: number; className?: string }>;
  active: boolean;
  sidebarOpen: boolean;
  isFree: boolean;
}) {
  const locked = isFree && !FREE_PAGES.has(href);

  if (locked) {
    return (
      <Link
        href="/pricing"
        className="flex items-center gap-3 mx-2 px-3 py-2 rounded-lg text-sm transition-colors text-[#475569] hover:text-[#64748b] hover:bg-white/5"
        title={label}
      >
        <Icon size={16} className="shrink-0 opacity-40" />
        {sidebarOpen && (
          <span className="truncate flex-1 opacity-40">{label}</span>
        )}
        {sidebarOpen && <Lock size={10} className="shrink-0 opacity-40" />}
      </Link>
    );
  }

  return (
    <Link
      href={href}
      className={`flex items-center gap-3 mx-2 px-3 py-2 rounded-lg text-sm transition-colors ${
        active
          ? "text-[#FFD700] bg-[#FFD700]/10"
          : "text-[#94a3b8] hover:text-white hover:bg-white/5"
      }`}
      title={label}
    >
      <Icon size={16} className="shrink-0" />
      {sidebarOpen && <span className="truncate">{label}</span>}
    </Link>
  );
}

export function Navbar() {
  const pathname = usePathname();
  const { user, loading: authLoading, plan, signOut } = useAuth();
  const isFree = plan === "free";
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [cmdOpen, setCmdOpen] = useState(false);
  const locale = useLocale();
  const t = appDict.nav[locale] ?? appDict.nav.en;
  const te = appDict.navExtra[locale] ?? appDict.navExtra.en;
  const navGroups = useMemo(() => getNavGroups(t, te), [t, te]);

  // Flatten nav groups into a list of CommandItems
  const commandItems = useMemo<CommandItem[]>(
    () =>
      navGroups.flatMap((group) =>
        group.items.map((item) => ({
          href: item.href,
          label: item.label,
          group: group.label,
          icon: item.icon,
        }))
      ),
    [navGroups]
  );

  // Global ⌘K / Ctrl+K handler
  const handleGlobalKeyDown = useCallback((e: KeyboardEvent) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "k") {
      e.preventDefault();
      setCmdOpen((prev) => !prev);
    }
  }, []);

  useEffect(() => {
    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, [handleGlobalKeyDown]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  // NAV-DETAIL-08: ルート変更時にモバイルメニューを自動で閉じる
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

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

  // Set body data-app-page for CSS sidebar offset (prevents layout shift)
  useEffect(() => {
    if (isApp) {
      document.body.setAttribute("data-app-page", sidebarOpen ? "true" : "collapsed");
    } else {
      document.body.removeAttribute("data-app-page");
    }
  }, [isApp, sidebarOpen]);

  return (
    <>
      {/* Command Palette */}
      {isApp && (
        <CommandPalette
          open={cmdOpen}
          onClose={() => setCmdOpen(false)}
          items={commandItems}
        />
      )}

      {/* Top Navbar */}
      <nav
        role="navigation"
        aria-label="Main navigation"
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
                aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
                aria-expanded={mobileOpen}
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
                {/* COMPDIFF-02: "Get a Demo" always visible in navbar */}
                <Link
                  href="/contact?demo=1"
                  className="px-3 py-1.5 text-sm font-semibold text-[#0a0e1a] bg-[#FFD700] rounded-md hover:bg-[#ffe44d] transition-colors"
                >
                  Get a Demo
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
              aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
              aria-expanded={mobileOpen}
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
                    const active = pathname === item.href || pathname.startsWith(item.href + "/");
                    return (
                      <SidebarNavItem
                        key={item.href}
                        href={item.href}
                        label={item.label}
                        icon={item.icon}
                        active={active}
                        sidebarOpen={sidebarOpen}
                        isFree={isFree}
                      />
                    );
                  })}
                </div>
              ))}
              </>)}
            </div>
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
                        const active = pathname === item.href || pathname.startsWith(item.href + "/");
                        return (
                          <SidebarNavItem
                            key={item.href}
                            href={item.href}
                            label={item.label}
                            icon={item.icon}
                            active={active}
                            sidebarOpen={true}
                            isFree={isFree}
                          />
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

          {/* Sidebar offset managed via CSS in globals.css using data-app-page attribute */}
        </>
      )}
    </>
  );
}
