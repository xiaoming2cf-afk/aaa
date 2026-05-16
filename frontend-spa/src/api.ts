export type JsonValue = string | number | boolean | null | JsonValue[] | { [key: string]: JsonValue };

export class ApiError extends Error {
  status: number;
  detail: unknown;
  payload: unknown;

  constructor(message: string, options: { status: number; detail: unknown; payload: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = options.status;
    this.detail = options.detail;
    this.payload = options.payload;
  }
}

export type ApiFetchInit = RequestInit & {
  timeoutMs?: number;
};

function readCookie(name: string): string {
  const prefix = `${name}=`;
  const raw = document.cookie.split(";").map((item) => item.trim());
  const found = raw.find((item) => item.startsWith(prefix));
  return found ? decodeURIComponent(found.slice(prefix.length)) : "";
}

function isJsonResponse(response: Response): boolean {
  const contentType = response.headers.get("content-type") || "";
  return /\bapplication\/json\b|\+json\b/i.test(contentType);
}

function detailFromPayload(payload: unknown): unknown {
  if (payload && typeof payload === "object" && "detail" in payload) {
    return (payload as { detail?: unknown }).detail;
  }
  return typeof payload === "string" ? payload : undefined;
}

function messageFromDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    const message = (detail as { message?: unknown }).message;
    if (typeof message === "string" && message.trim()) {
      return message;
    }
  }
  return fallback;
}

function errorName(error: unknown): string {
  return error && typeof error === "object" && "name" in error
    ? String((error as { name?: unknown }).name)
    : "";
}

function errorMessage(error: unknown): string {
  return error && typeof error === "object" && "message" in error
    ? String((error as { message?: unknown }).message)
    : "";
}

function isTimeoutError(error: unknown): boolean {
  return errorName(error) === "TimeoutError";
}

function isAbortError(error: unknown): boolean {
  const name = errorName(error);
  return name === "AbortError" || name === "TimeoutError";
}

function createAbortReason(message: string, name: "AbortError" | "TimeoutError"): DOMException | Error {
  if (typeof DOMException !== "undefined") {
    return new DOMException(message, name);
  }
  const error = new Error(message);
  error.name = name;
  return error;
}

function createRequestSignal(baseSignal?: AbortSignal | null, timeoutMs?: number): { signal?: AbortSignal; cleanup: () => void } {
  if (!baseSignal && !timeoutMs) {
    return { signal: undefined, cleanup: () => undefined };
  }

  const controller = new AbortController();
  let timeoutId: ReturnType<typeof setTimeout> | undefined;

  const abortFromBaseSignal = (): void => {
    if (!controller.signal.aborted) {
      controller.abort(baseSignal?.reason || createAbortReason("Request aborted.", "AbortError"));
    }
  };

  if (baseSignal?.aborted) {
    abortFromBaseSignal();
  } else if (baseSignal) {
    baseSignal.addEventListener("abort", abortFromBaseSignal, { once: true });
  }

  if (timeoutMs && timeoutMs > 0) {
    timeoutId = setTimeout(() => {
      if (!controller.signal.aborted) {
        controller.abort(createAbortReason(`Request timed out after ${timeoutMs}ms.`, "TimeoutError"));
      }
    }, timeoutMs);
  }

  return {
    signal: controller.signal,
    cleanup: () => {
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
      if (baseSignal) {
        baseSignal.removeEventListener("abort", abortFromBaseSignal);
      }
    },
  };
}

async function readPayload(response: Response, method: string): Promise<unknown> {
  if (method === "HEAD" || response.status === 204 || response.status === 205 || response.status === 304) {
    return undefined;
  }

  const text = await response.text();
  if (!text) {
    return undefined;
  }

  if (!isJsonResponse(response)) {
    return text;
  }

  try {
    return JSON.parse(text) as JsonValue;
  } catch (error) {
    throw new ApiError("Response was not valid JSON.", {
      status: response.status,
      detail: errorMessage(error) || "JSON parse failed.",
      payload: text,
    });
  }
}

function toNetworkError(error: unknown, signal?: AbortSignal): ApiError {
  const reason = signal?.reason;
  const timedOut = isTimeoutError(error) || isTimeoutError(reason);
  const aborted = timedOut || isAbortError(error) || isAbortError(reason) || signal?.aborted;
  const message = timedOut
    ? "Request timed out."
    : aborted
      ? "Request aborted."
      : "Network request failed.";

  return new ApiError(message, {
    status: 0,
    detail: errorMessage(error) || errorMessage(reason) || message,
    payload: error,
  });
}

export async function apiFetch<T>(path: string, init: ApiFetchInit = {}): Promise<T> {
  const { timeoutMs, signal: baseSignal, ...fetchInit } = init;
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  const hasBody = init.body !== undefined && init.body !== null;
  const shouldInferContentType = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (hasBody && !shouldInferContentType && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = readCookie("erp_csrf_token");
    if (csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }

  const requestSignal = createRequestSignal(baseSignal, timeoutMs);
  try {
    const response = await fetch(path, {
      credentials: "include",
      ...fetchInit,
      headers,
      signal: requestSignal.signal,
    });
    const payload = await readPayload(response, method);
    if (!response.ok) {
      const detail = detailFromPayload(payload);
      throw new ApiError(messageFromDetail(detail, `${response.status} ${response.statusText}`), {
        status: response.status,
        detail,
        payload,
      });
    }
    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) {
      throw error;
    }
    throw toNetworkError(error, requestSignal.signal);
  } finally {
    requestSignal.cleanup();
  }
}
