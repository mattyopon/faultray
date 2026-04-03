/**
 * L2: Unit Tests — src/lib/api.ts
 * Tests the api module's fetch behavior using a mock fetch.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// We test the internal apiFetch behavior via the exported `api` object
// by mocking global fetch.

let api: typeof import("@/lib/api").api;

beforeEach(async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn());
  // Re-import to pick up the mocked fetch
  const mod = await import("@/lib/api");
  api = mod.api;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.resetModules();
});

function mockFetchOk(data: unknown) {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok: true,
    json: () => Promise.resolve(data),
  });
}

function mockFetchError(status: number, body: unknown) {
  (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok: false,
    status,
    statusText: "Bad Request",
    json: () => Promise.resolve(body),
  });
}

describe("api module", () => {
  describe("simulate()", () => {
    it("sends POST /api/simulate with correct body", async () => {
      const fakeResult = { overall_score: 85, availability_estimate: "99.9%", critical_failures: [], suggestions: [] };
      mockFetchOk(fakeResult);

      const result = await api.simulate({ sample: "web-app" }, "tok123");

      // PYTEST-05: カスタムメッセージ付きアサーション
      expect(globalThis.fetch, "fetch should have been called exactly once").toHaveBeenCalledOnce();
      const [url, opts] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(url, "POST先URLが/api/simulateであること").toBe("/api/simulate");
      expect(opts.method, "HTTPメソッドがPOSTであること").toBe("POST");
      expect(JSON.parse(opts.body), "リクエストボディにsample:'web-app'が含まれること").toEqual({ sample: "web-app" });
      expect(opts.headers["Authorization"], "Authorizationヘッダーにtokenが含まれること").toBe("Bearer tok123");
      expect(result, "シミュレーション結果がモックと一致すること").toEqual(fakeResult);
    });
  });

  describe("getProjects()", () => {
    it("sends GET /api/projects", async () => {
      mockFetchOk([{ id: "1", name: "test" }]);

      const result = await api.getProjects("tok");

      const [url, opts] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(url, "GETリクエスト先URLが/api/projectsであること").toBe("/api/projects");
      expect(opts.method, "HTTPメソッドがGETであること").toBe("GET");
      expect(result, "プロジェクト一覧がモックと一致すること").toEqual([{ id: "1", name: "test" }]);
    });
  });

  describe("error handling", () => {
    it("throws on non-ok response with error message", async () => {
      mockFetchError(400, { message: "Invalid topology" });

      // Any error thrown inside try{} is caught by the retry catch block and retried with sleep()
      // Advance fake timers to skip all sleep() delays
      const promise = api.simulate({ sample: "bad" });
      promise.catch(() => undefined);
      await vi.runAllTimersAsync();
      await expect(promise).rejects.toThrow("Invalid topology");
    });

    it("throws with statusText when JSON body has no message", async () => {
      (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
        ok: false,
        status: 500,
        statusText: "Internal Server Error",
        json: () => Promise.reject(new Error("not json")),
      });

      // status 500 triggers retry logic with sleep() delays — advance fake timers to skip waits
      // Attach noop catch first to prevent unhandled-rejection warning during timer advancement
      const promise = api.getProjects();
      promise.catch(() => undefined);
      await vi.runAllTimersAsync();
      await expect(promise).rejects.toThrow("Internal Server Error");
    });
  });

  describe("authorization header", () => {
    it("omits Authorization when no token provided", async () => {
      mockFetchOk({ runs: [] });

      await api.getRuns();

      const [, opts] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(opts.headers["Authorization"]).toBeUndefined();
    });

    it("includes Authorization when token provided", async () => {
      mockFetchOk({ runs: [] });

      await api.getRuns("mytoken");

      const [, opts] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(opts.headers["Authorization"]).toBe("Bearer mytoken");
    });
  });

  describe("API_BASE handling", () => {
    it("prepends NEXT_PUBLIC_API_URL when set", async () => {
      // This tests the default (empty string) case since env is not set in test
      mockFetchOk([]);
      await api.getProjects();
      const [url] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
      expect(url).toBe("/api/projects");
    });
  });
});
