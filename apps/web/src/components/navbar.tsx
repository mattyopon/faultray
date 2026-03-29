"use client";

import { Logo } from "@/components/logo";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import {
  LayoutDashboard,
  Zap,
  FileText,
  Lightbulb,
  Settings,
  Menu,
  X,
  LogOut,
} from "lucide-react";

const navItems = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/simulate", label: "Simulate", icon: Zap },
  { href: "/results", label: "Results", icon: FileText },
  { href: "/suggestions", label: "Suggestions", icon: Lightbulb },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Navbar() {
  const pathname = usePathname();
  const { user, signOut } = useAuth();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const isLanding = pathname === "/";
  const isApp = !isLanding && !pathname.startsWith("/login") && !pathname.startsWith("/pricing");

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 backdrop-blur-xl transition-colors ${
        scrolled
          ? "border-b border-[#1e293b] bg-[#0a0e1a]/90"
          : "bg-[#0a0e1a]/80"
      }`}
    >
      <div className="max-w-[1200px] mx-auto px-6 flex items-center justify-between h-16">
        <Link href="/" className="flex items-center gap-2.5 font-bold text-white">
          <Logo size={28} />
          <span>FaultRay</span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-1">
          {isApp && user ? (
            <>
              {navItems.map((item) => {
                const Icon = item.icon;
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
                      active
                        ? "text-[#FFD700] bg-[#FFD700]/10"
                        : "text-[#94a3b8] hover:text-white hover:bg-white/5"
                    }`}
                  >
                    <Icon size={16} />
                    {item.label}
                  </Link>
                );
              })}
              <div className="ml-4 pl-4 border-l border-[#1e293b] flex items-center gap-2">
                <span className="text-xs text-[#64748b] truncate max-w-[120px]">
                  {user.email}
                </span>
                <button
                  onClick={signOut}
                  className="p-2 text-[#64748b] hover:text-red-400 transition-colors"
                  title="Sign out"
                >
                  <LogOut size={16} />
                </button>
              </div>
            </>
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
                href="https://github.com/yutaro-and-and-and/faultray"
                target="_blank"
                className="px-3 py-1.5 text-sm text-[#94a3b8] border border-[#1e293b] rounded-md hover:border-[#64748b] transition-colors"
              >
                GitHub
              </Link>
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

        {/* Mobile toggle */}
        <button
          className="md:hidden p-2 text-[#94a3b8]"
          onClick={() => setMobileOpen(!mobileOpen)}
        >
          {mobileOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden border-t border-[#1e293b] bg-[#0a0e1a]/98 backdrop-blur-xl px-6 py-4 space-y-2">
          {isApp && user ? (
            <>
              {navItems.map((item) => {
                const Icon = item.icon;
                const active = pathname.startsWith(item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    onClick={() => setMobileOpen(false)}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium ${
                      active
                        ? "text-[#FFD700] bg-[#FFD700]/10"
                        : "text-[#94a3b8] hover:text-white"
                    }`}
                  >
                    <Icon size={16} />
                    {item.label}
                  </Link>
                );
              })}
              <button
                onClick={signOut}
                className="flex items-center gap-3 px-3 py-2.5 text-sm text-red-400 w-full"
              >
                <LogOut size={16} />
                Sign Out
              </button>
            </>
          ) : (
            <>
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
            </>
          )}
        </div>
      )}
    </nav>
  );
}
