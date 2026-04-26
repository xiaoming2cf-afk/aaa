import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { ApiError, apiFetch } from "../api";

let fetchMock: ReturnType<typeof vi.fn>;

describe("apiFetch", () => {
  beforeEach(() => {
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.useRealTimers();
    document.cookie = "erp_csrf_token=; Max-Age=0";
  });

  test("returns undefined for 204 and empty responses", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));

    await expect(apiFetch<undefined>("/api/empty")).resolves.toBeUndefined();
  });

  test("returns text for non JSON responses", async () => {
    fetchMock.mockResolvedValueOnce(new Response("plain text", {
      status: 200,
      headers: { "content-type": "text/plain" },
    }));

    await expect(apiFetch<string>("/api/plain")).resolves.toBe("plain text");
  });

  test("throws ApiError when JSON parsing fails", async () => {
    fetchMock.mockResolvedValueOnce(new Response("{not-json", {
      status: 200,
      headers: { "content-type": "application/json" },
    }));

    await expect(apiFetch("/api/bad-json")).rejects.toMatchObject({
      name: "ApiError",
      status: 200,
      message: "Response was not valid JSON.",
      payload: "{not-json",
    });
  });

  test("preserves ApiError details for HTTP errors", async () => {
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({
      detail: { message: "Workspace unavailable" },
    }), {
      status: 503,
      statusText: "Service Unavailable",
      headers: { "content-type": "application/json" },
    }));

    await expect(apiFetch("/api/failing")).rejects.toMatchObject({
      name: "ApiError",
      status: 503,
      message: "Workspace unavailable",
      detail: { message: "Workspace unavailable" },
    });
  });

  test("wraps network failures in ApiError", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));

    await expect(apiFetch("/api/offline")).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      message: "Network request failed.",
      detail: "Failed to fetch",
    });
  });

  test("supports request timeouts through AbortSignal", async () => {
    fetchMock.mockImplementationOnce((_path: string, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => {
        reject(init.signal?.reason);
      });
    }));
    const signal = typeof AbortSignal.timeout === "function"
      ? AbortSignal.timeout(1)
      : (() => {
        const controller = new AbortController();
        setTimeout(() => controller.abort(new DOMException("The operation timed out.", "TimeoutError")), 1);
        return controller.signal;
      })();

    await expect(apiFetch("/api/slow", { signal })).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      message: "Request timed out.",
    });
  });

  test("adds CSRF token to unsafe methods only", async () => {
    document.cookie = "erp_csrf_token=csrf-123";
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }));
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }));

    await apiFetch("/api/items", { method: "POST", body: JSON.stringify({ name: "A" }) });
    await apiFetch("/api/items");

    const postHeaders = fetchMock.mock.calls[0][1]?.headers as Headers;
    const getHeaders = fetchMock.mock.calls[1][1]?.headers as Headers;
    expect(postHeaders.get("X-CSRF-Token")).toBe("csrf-123");
    expect(getHeaders.get("X-CSRF-Token")).toBeNull();
  });

  test("aborts requests when timeoutMs elapses", async () => {
    vi.useFakeTimers();
    fetchMock.mockImplementationOnce((_path: string, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => {
        reject(init.signal?.reason);
      });
    }));

    const promise = apiFetch("/api/slow", { timeoutMs: 25 });
    const assertion = expect(promise).rejects.toMatchObject({
      name: "ApiError",
      status: 0,
      message: "Request timed out.",
    });
    await vi.advanceTimersByTimeAsync(25);

    await assertion;
  });

  test("keeps thrown HTTP errors as ApiError instances", async () => {
    fetchMock.mockResolvedValueOnce(new Response("No access", {
      status: 403,
      statusText: "Forbidden",
      headers: { "content-type": "text/plain" },
    }));

    try {
      await apiFetch("/api/forbidden");
      throw new Error("apiFetch should have thrown");
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error).toMatchObject({
        status: 403,
        message: "No access",
        payload: "No access",
      });
    }
  });
});
