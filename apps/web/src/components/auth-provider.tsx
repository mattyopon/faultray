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
        .select("plan")
        .eq("id", uid)
        .single();
      if (data?.plan) {
        setPlan((data.plan as PlanTier) || "free");
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
      } = supabase.auth.onAuthStateChange((_event, session) => {
        const nextUser = session?.user ?? null;
        setUser(nextUser);
        setLoading(false);
        if (nextUser) {
          fetchPlan(nextUser.id);
        } else {
          setPlan("free");
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
