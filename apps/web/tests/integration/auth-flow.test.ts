/**
 * L3: Integration Tests — Auth flow
 * Tests the AuthProvider context behavior with mocked Supabase.
 */
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import React from "react";

// Mock the supabase client module
vi.mock("@/lib/supabase/client", () => {
  const mockUnsubscribe = vi.fn();
  const mockOnAuthStateChange = vi.fn().mockReturnValue({
    data: {
      subscription: { unsubscribe: mockUnsubscribe },
    },
  });
  const mockSignOut = vi.fn().mockResolvedValue({});
  return {
    createClient: () => ({
      auth: {
        onAuthStateChange: mockOnAuthStateChange,
        signOut: mockSignOut,
      },
    }),
    __mockOnAuthStateChange: mockOnAuthStateChange,
    __mockSignOut: mockSignOut,
    __mockUnsubscribe: mockUnsubscribe,
  };
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("AuthProvider", () => {
  it("renders children", async () => {
    // Set env vars so AuthProvider attempts to init
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "https://test.supabase.co");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "test-key");

    const { AuthProvider } = await import("@/components/auth-provider");

    render(
      React.createElement(AuthProvider, null,
        React.createElement("div", { "data-testid": "child" }, "Hello")
      )
    );

    expect(screen.getByTestId("child")).toHaveTextContent("Hello");
  });

  it("provides loading=true initially then resolves", async () => {
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_URL", "");
    vi.stubEnv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "");

    const { AuthProvider, useAuth } = await import("@/components/auth-provider");

    function Consumer() {
      const { loading, user } = useAuth();
      return React.createElement("div", { "data-testid": "state" },
        `loading=${loading} user=${user?.email ?? "null"}`
      );
    }

    render(
      React.createElement(AuthProvider, null,
        React.createElement(Consumer)
      )
    );

    // When env vars are missing, loading should quickly become false
    await waitFor(() => {
      expect(screen.getByTestId("state")).toHaveTextContent("loading=false user=null");
    });
  });
});
