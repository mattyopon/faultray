"use client";

import { Logo } from "@/components/logo";
import { createClient } from "@/lib/supabase/client";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { Mail, Loader2, CheckCircle2 } from "lucide-react";
import { useLocale } from "@/lib/useLocale";
import { appDict } from "@/i18n/app-dict";

function LoginForm() {
  const locale = useLocale();
  const t = appDict.login[locale] ?? appDict.login.en;
  const searchParams = useSearchParams();
  // Validate redirectTo to prevent open redirect — only allow internal paths
  const rawRedirectTo = searchParams.get("redirectTo") || "/dashboard";
  const redirectTo =
    rawRedirectTo.startsWith("/") && !rawRedirectTo.startsWith("//")
      ? rawRedirectTo
      : "/dashboard";
  const isProduction = process.env.NEXT_PUBLIC_SITE_URL === "https://faultray.com";

  // AUTH-01: Show error message when OAuth fails
  const authError = searchParams.get("error");
  const errorMessages: Record<string, string> = {
    auth_failed: "Sign-in failed. Please try again or use a different provider.",
    access_denied: "Access was denied. Please allow the requested permissions and try again.",
    session_expired: "Your session has expired. Please sign in again.",
  };
  const errorMessage = authError ? (errorMessages[authError] ?? "An authentication error occurred. Please try again.") : null;

  // AUTH-02: Email OTP fallback (eliminates Social SPoF)
  const [emailMode, setEmailMode] = useState(false);
  const [emailInput, setEmailInput] = useState("");
  const [otpSending, setOtpSending] = useState(false);
  const [otpSent, setOtpSent] = useState(false);
  const [emailError, setEmailError] = useState<string | null>(null);

  const supabase = createClient();

  const signInWith = async (provider: "github" | "google") => {
    await supabase.auth.signInWithOAuth({
      provider,
      options: {
        redirectTo: `${window.location.origin}/auth/callback?redirectTo=${encodeURIComponent(redirectTo)}`,
      },
    });
  };

  // MISSED-05: ディスポーザブルメールドメインのブロックリスト
  const DISPOSABLE_DOMAINS = new Set([
    "mailinator.com", "guerrillamail.com", "10minutemail.com", "tempmail.com",
    "throwaway.email", "yopmail.com", "sharklasers.com", "guerrillamailblock.com",
    "grr.la", "guerrillamail.info", "spam4.me", "trashmail.at",
    "dispostable.com", "spamgourmet.com", "maildrop.cc", "getairmail.com",
  ]);

  // AUTH-02: Send magic link / OTP via email
  const sendOtp = async () => {
    const trimmed = emailInput.trim().toLowerCase();
    if (!trimmed || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmed)) {
      setEmailError("Please enter a valid email address.");
      return;
    }
    // MISSED-05: ディスポーザブルメールのブロック
    const domain = trimmed.split("@")[1] ?? "";
    if (DISPOSABLE_DOMAINS.has(domain)) {
      setEmailError("Disposable email addresses are not allowed. Please use a permanent email address.");
      return;
    }
    setEmailError(null);
    setOtpSending(true);
    try {
      const { error } = await supabase.auth.signInWithOtp({
        email: trimmed,
        options: {
          emailRedirectTo: `${window.location.origin}/auth/callback?redirectTo=${encodeURIComponent(redirectTo)}`,
        },
      });
      if (error) {
        setEmailError(error.message || (locale === "ja" ? "マジックリンクの送信に失敗しました。もう一度お試しください。" : "Failed to send magic link. Please try again."));
      } else {
        setOtpSent(true);
      }
    } catch {
      setEmailError(locale === "ja" ? "予期しないエラーが発生しました。もう一度お試しください。" : "An unexpected error occurred. Please try again.");
    } finally {
      setOtpSending(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-6 gap-16">
      {/* Value proposition — hidden on small screens */}
      <div className="hidden lg:flex flex-col gap-8 max-w-[380px]">
        <div>
          <h2 className="text-2xl font-bold text-[var(--text-primary)] mb-2">
            {t.whyTitle}
          </h2>
          <p className="text-[var(--text-muted)] text-sm">
            {t.whySubtitle}
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
                <p className="font-semibold text-[var(--text-primary)] text-sm">{title}</p>
                <p className="text-[var(--text-muted)] text-sm mt-0.5 leading-relaxed">{desc}</p>
              </div>
            </li>
          ))}
        </ul>
        {/* CVR-01: Trust badges */}
        <div className="flex flex-wrap gap-3 mt-2">
          {[
            { icon: "⚡", text: locale === "ja" ? "30秒で始められます" : "Get started in 30 seconds" },
            { icon: "💳", text: locale === "ja" ? "クレカ不要" : "No credit card required" },
            { icon: "🔓", text: locale === "ja" ? "14日間フルアクセス" : "14-day full access" },
          ].map(({ icon, text }) => (
            <span key={text} className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium text-[var(--text-secondary)] border border-[var(--border-color)] rounded-full bg-[var(--bg-card)]">
              <span aria-hidden="true">{icon}</span>
              {text}
            </span>
          ))}
        </div>
        <p className="text-xs text-[var(--text-muted)] mt-4">
          {t.trustedBy}
        </p>
      </div>

      <div className="w-full max-w-[400px]">
        <div className="text-center mb-10">
          <div className="flex justify-center mb-4">
            <Logo size={48} />
          </div>
          <h1 className="text-2xl font-bold mb-2">{t.title}</h1>
          <p className="text-[var(--text-secondary)] text-sm">
            {t.subtitle}
          </p>
        </div>

        {/* AUTH-01: OAuth error display */}
        {errorMessage && (
          <div role="alert" className="mb-4 p-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-sm">
            <p className="font-semibold mb-1">{t.signInFailed}</p>
            <p>{errorMessage}</p>
            <p className="mt-2 text-xs text-red-300">
              {t.needHelp}{" "}
              <a href="mailto:support@faultray.com" className="underline hover:text-red-200">
                {t.contactSupport}
              </a>
            </p>
          </div>
        )}

        <div className="p-8 rounded-2xl border border-[var(--border-color)] bg-[var(--bg-card)] space-y-4">
          {/* AUTH-02: Email OTP mode */}
          {emailMode ? (
            otpSent ? (
              <div className="text-center py-4">
                <CheckCircle2 size={40} className="text-emerald-400 mx-auto mb-3" />
                <p className="font-semibold text-[var(--text-primary)] mb-1">{t.checkEmail}</p>
                <p className="text-sm text-[var(--text-secondary)]">
                  {t.magicLinkSent} <span className="text-[var(--text-primary)] font-medium">{emailInput}</span>.{" "}
                  {t.magicLinkDesc}
                </p>
                <button
                  onClick={() => { setOtpSent(false); setEmailMode(false); setEmailInput(""); }}
                  className="mt-4 text-sm text-[var(--gold)] hover:underline"
                >
                  {t.backToSignIn}
                </button>
              </div>
            ) : (
              <div className="space-y-3">
                <label className="block text-sm text-[var(--text-secondary)] font-medium">{t.emailLabel}</label>
                <input
                  type="email"
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") sendOtp(); }}
                  placeholder={t.emailPlaceholder}
                  autoFocus
                  className="w-full px-4 py-3 rounded-xl bg-[var(--bg-primary)] border border-[var(--border-color)] text-[var(--text-primary)] placeholder-[var(--text-muted)] focus:outline-none focus:border-[var(--gold)]/50 text-sm"
                />
                {emailError && (
                  <p className="text-red-400 text-xs">{emailError}</p>
                )}
                <button
                  onClick={sendOtp}
                  disabled={otpSending}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-[var(--gold)] text-white font-semibold hover:bg-[#044a99] disabled:opacity-60 transition-colors"
                >
                  {otpSending ? <Loader2 size={16} className="animate-spin" /> : <Mail size={16} />}
                  {otpSending ? t.sending : t.sendMagicLink}
                </button>
                <button
                  onClick={() => { setEmailMode(false); setEmailError(null); }}
                  className="w-full text-center text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
                >
                  {t.backToSocial}
                </button>
              </div>
            )
          ) : (
            <>
              {isProduction && (
              <button
                onClick={() => signInWith("github")}
                className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl bg-white text-[#0a0e1a] font-semibold hover:bg-gray-100 transition-colors min-h-[48px]"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                  <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z" />
                </svg>
                {t.continueGithub}
              </button>
              )}

              <button
                onClick={() => signInWith("google")}
                className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl border border-[var(--border-color)] text-[var(--text-primary)] font-semibold hover:bg-black/5 transition-colors min-h-[48px]"
              >
                <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z" fill="#4285F4" />
                  <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
                  <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05" />
                  <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
                </svg>
                {t.continueGoogle}
              </button>

              <div className="relative flex items-center">
                <div className="flex-1 border-t border-[var(--border-color)]" />
                <span className="mx-3 text-xs text-[var(--text-muted)]">{t.or}</span>
                <div className="flex-1 border-t border-[var(--border-color)]" />
              </div>

              {/* AUTH-02: Email magic link as SPoF fallback */}
              <button
                onClick={() => setEmailMode(true)}
                className="w-full flex items-center justify-center gap-3 px-4 py-3 rounded-xl border border-[var(--border-color)] text-[var(--text-secondary)] font-medium hover:bg-black/5 hover:text-[var(--text-primary)] transition-colors text-sm min-h-[48px]"
              >
                <Mail size={16} />
                {t.continueEmail}
              </button>
            </>
          )}
        </div>

        <p className="text-center text-xs text-[var(--text-muted)] mt-6">
          {t.terms}
        </p>
      </div>
    </div>
  );

}

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse text-[var(--text-muted)]">読み込み中...</div>
      </div>
    }>
      <LoginForm />
    </Suspense>
  );
}
