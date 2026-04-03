/**
 * L9+: Resilience — Offline / network failure graceful degradation
 * Tests that the API module handles network errors gracefully.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

let api: typeof import("@/lib/api").api;

beforeEach(async () => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", vi.fn());
  const mod = await import("@/lib/api");
  api = mod.api;
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.resetModules();
});

/**
 * Advance all fake timers so that sleep() delays in retry logic complete instantly.
 * Attaches a noop catch first to prevent unhandled-rejection warnings during advancement.
 */
async function advanceRetryTimers<T>(promise: Promise<T>): Promise<void> {
  // Suppress "unhandled rejection" while timers are advancing
  promise.catch(() => undefined);
  await vi.runAllTimersAsync();
}

describe("L9: Offline / Network Failure Handling", () => {
  it("throws a meaningful error on network failure", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(
      new TypeError("Failed to fetch")
    );

    // Network errors trigger retry logic with sleep() delays — advance fake timers
    const promise = api.getProjects("tok");
    await advanceRetryTimers(promise);
    await expect(promise).rejects.toThrow("Failed to fetch");
  });

  it("throws on timeout (AbortError)", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(
      new DOMException("The operation was aborted.", "AbortError")
    );

    // AbortError is NOT retried, but fake timers may still need advancing for cleanup
    const promise = api.getProjects("tok");
    await advanceRetryTimers(promise);
    await expect(promise).rejects.toThrow("aborted");
  });

  it("handles 503 Service Unavailable gracefully", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      json: () => Promise.resolve({ message: "Server overloaded" }),
    });

    // 503 triggers retry logic with sleep() delays — advance fake timers
    const promise = api.simulate({ sample: "test" });
    await advanceRetryTimers(promise);
    await expect(promise).rejects.toThrow("Server overloaded");
  });

  it("handles empty response body on error", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      json: () => Promise.reject(new Error("empty body")),
    });

    // 502 triggers retry logic with sleep() delays — advance fake timers
    const promise = api.simulate({ sample: "test" });
    await advanceRetryTimers(promise);
    await expect(promise).rejects.toThrow("Bad Gateway");
  });
});
