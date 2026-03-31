/**
 * L9+: Resilience — Offline / network failure graceful degradation
 * Tests that the API module handles network errors gracefully.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

let api: typeof import("@/lib/api").api;

beforeEach(async () => {
  vi.stubGlobal("fetch", vi.fn());
  const mod = await import("@/lib/api");
  api = mod.api;
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.resetModules();
});

describe("L9: Offline / Network Failure Handling", () => {
  it("throws a meaningful error on network failure", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(
      new TypeError("Failed to fetch")
    );

    await expect(api.getProjects("tok")).rejects.toThrow("Failed to fetch");
  });

  it("throws on timeout (AbortError)", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockRejectedValue(
      new DOMException("The operation was aborted.", "AbortError")
    );

    await expect(api.getProjects("tok")).rejects.toThrow("aborted");
  });

  it("handles 503 Service Unavailable gracefully", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 503,
      statusText: "Service Unavailable",
      json: () => Promise.resolve({ message: "Server overloaded" }),
    });

    await expect(api.simulate({ sample: "test" })).rejects.toThrow("Server overloaded");
  });

  it("handles empty response body on error", async () => {
    (globalThis.fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
      ok: false,
      status: 502,
      statusText: "Bad Gateway",
      json: () => Promise.reject(new Error("empty body")),
    });

    await expect(api.simulate({ sample: "test" })).rejects.toThrow("Bad Gateway");
  });
});
