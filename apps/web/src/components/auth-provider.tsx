"use client";

import type { User } from "@supabase/supabase-js";
import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";

export type PlanTier = "free" | "pro" | "business";

interface AuthContextType {
  user: User | null;
  loading: boolean;
  plan: PlanTier;
  planLoading: boolean;
  refreshPlan: () => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  plan: "free",
  planLoading: false,
  refreshPlan: async () => {},
  signOut: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [plan, setPlan] = useState<PlanTier>("free");
  const [planLoading, setPlanLoading] = useState(false);

  const fetchPlan = useCallback(async (uid: string) => {
    setPlanLoading(true);
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      const { data } = await supabase
        .from("profiles")
        .select("plan, trial_ends_at, subscription_status")
        .eq("id", uid)
        .single();
      if (data?.plan) {
        // trial_ends_at が過去でも、subscription_status が paid (active /
        // trialing / past_due) なら downgrade しない (CodeRabbit Major):
        // Stripe webhook で trial→paid の遷移後に subscription_status だけが
        // 'active' に更新され trial_ends_at は古いまま残るケースがあり、
        // その場合に UI を強制 'free' にするとユーザーは突然有料機能が
        // 使えなくなる (server は paid アクセスを継続維持しているのに UI
        // 側だけ食い違う)。
        //
        // DB 側の `plan` 列は migration 013 で authenticated に対する UPDATE が
        // revoke されている (billing-bypass 防止) ため、ここから `update({plan})`
        // を発行すると silent fail し、ユーザー体験は free だが DB は trial 値の
        // ままドリフトする。DB の修正は server-side cron `/api/cron/trial-expiry`
        // が SECURITY DEFINER 関数 `downgrade_expired_trials()` で行う。
        const isExpired =
          data.trial_ends_at != null &&
          new Date(data.trial_ends_at as string) < new Date();
        const subStatus = (
          data as { subscription_status?: string | null }
        ).subscription_status;
        const hasPaidStatus =
          subStatus === "active" ||
          subStatus === "trialing" ||
          subStatus === "past_due";
        if (isExpired && data.plan !== "free" && !hasPaidStatus) {
          setPlan("free");
        } else {
          setPlan((data.plan as PlanTier) || "free");
        }
      }
    } catch {
      // Supabase not configured — remain "free"
    } finally {
      setPlanLoading(false);
    }
  }, []);

  const refreshPlan = useCallback(async () => {
    if (user) await fetchPlan(user.id);
  }, [user, fetchPlan]);

  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

    if (!url || !key) {
      setLoading(false);
      return;
    }

    // Dynamic import to avoid build-time errors
    import("@/lib/supabase/client").then(({ createClient }) => {
      const supabase = createClient();
      const {
        data: { subscription },
      } = supabase.auth.onAuthStateChange((event, session) => {
        const nextUser = session?.user ?? null;
        setUser(nextUser);
        setLoading(false);
        if (nextUser) {
          fetchPlan(nextUser.id);
        } else {
          setPlan("free");
          // ERRMSG-03: Redirect to login with session_expired flag when session is lost
          // while user was on an app page (not the landing / login pages)
          if (event === "SIGNED_OUT" || event === "TOKEN_REFRESHED") {
            if (typeof window !== "undefined") {
              const isAppPage = !["", "/", "/login", "/pricing", "/features",
                "/en", "/ja", "/de", "/fr", "/zh", "/ko", "/es", "/pt",
                "/case-studies", "/changelog", "/contact", "/demo",
                "/privacy", "/terms", "/tokushoho", "/dpa", "/help", "/support",
              ].some((p) => window.location.pathname === p || window.location.pathname.startsWith(p + "/"));
              if (isAppPage && event === "SIGNED_OUT") {
                window.location.href = "/login?error=session_expired";
              }
            }
          }
        }
      });

      return () => subscription.unsubscribe();
    }).catch(() => {
      setLoading(false);
    });
  }, [fetchPlan]);

  const signOut = async () => {
    try {
      const { createClient } = await import("@/lib/supabase/client");
      const supabase = createClient();
      await supabase.auth.signOut();
    } catch {
      // Supabase not configured
    }
    setUser(null);
    window.location.href = "/";
  };

  return (
    <AuthContext.Provider value={{ user, loading, plan, planLoading, refreshPlan, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}
