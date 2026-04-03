"use client";

import { Logo } from "@/components/logo";
import { createClient } from "@/lib/supabase/client";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

function LoginForm() {
  const searchParams = useSearchParams();
  // Validate redirectTo to prevent open redirect — only allow internal paths
  const rawRedirectTo = searchParams.get("redirectTo") || "/dashboard";
  const redirectTo =
    rawRedirectTo.startsWith("/") && !rawRedirectTo.startsWith("//")
      ? rawRedirectTo
      : "/dashboard";
  const isProduction = process.env.NEXT_PUBLIC_SITE_URL === "https://faultray.com";

  const supabase = createClient();

  const signInWith = async (provider: "github" | "google") => {
    await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/auth/callback?redirectTo=${encodeURIComponent(redirectTo)}`,
      },
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6 gap-16">
      {/* Value proposition — hidden on small screens */}
      <div className="hidden lg:flex flex-col gap-8 max-w-[380px]">
        <div>
          <h2 className="text-2xl font-bold text-white mb-2">
            Why SRE teams choose FaultRay
          </h2>
          <p className="text-[#64748b] text-sm">
            Chaos engineering that proves resilience — without the risk.
          </p>
        </div>
        <ul className="space-y-5">
          {[
            {
              icon: "⚡",
              title: "2,000+ failure scenarios",
              desc: "From single AZ outages to cascading multi-region failures — all simulated, zero production impact.",
            },
            {
              icon: "🛡",
              title: "Production stays safe",
              desc: "Pure mathematical simulation. We never touch your infrastructure. Ever.",
            },
            {
              icon: "📊",
              title: "DORA compliance in 1 click",
              desc: "Auto-generate audit-ready resilience reports aligned to DORA Article 25 requirements.",
            },
          ].map(({ icon, title, desc }) => (
            <li key={title} className="flex gap-4">
              <span className="text-2xl mt-0.5" aria-hidden="true">{icon}</span>
              <div>
                <p className="font-semibold text-white text-sm">{title}</p>
                <p className="text-[#64748b] text-sm mt-0.5 leading-relaxed">{desc}</p>
              </div>
            </li>
          ))}
        </ul>
        <p className="text-xs text-[#475569]">
          Trusted by SRE teams at companies of all sizes.
        </p>
      </div>

      <div className="w-full max-w-[400px]">
        <div className="text-center mb-10">
          <div className="flex justify-center mb-4">
            <Logo size={48} />
          </div>
          <h1 className="text-2xl font-bold mb-2">Welcome to FaultRay</h1>
          <p className="text-[#94a3b8] text-sm">
            Sign in to access your chaos engineering dashboard
          </p>
        </div>

        <div className="p-8 rounded-2xl border border-[#1e293b] bg-[#111827] space-y-4">
          {isProduction && (
          <button
            onClick={() => signInWith("github")}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl bg-white text-[#0a0e1a] font-semibold hover:bg-gray-100 transition-colors"
          >
            <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
            </svg>
            Continue with GitHub
          </button>
          )}

          <button
            onClick={() => signInWith("google")}
            className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl border border-[#1e293b] text-white font-semibold hover:bg-white/5 transition-colors"
          >
            <svg width="20" height="20" viewBox="0 0 24 24">
              <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
              <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
              <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
              <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
            </svg>
            Continue with Google
          </button>
        </div>

        <p className="text-center text-xs text-[#64748b] mt-6">
          By signing in, you agree to our Terms of Service and Privacy Policy.
        </p>
      </div>
    </div>
  );

}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-[#64748b]">Loading...</div>
      </div>
    }>
      <LoginForm />
    </Suspense>
  );
}
