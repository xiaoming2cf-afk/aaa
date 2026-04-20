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

function readCookie(name: string): string {
  const prefix = `${name}=`;
  const raw = document.cookie.split(";").map((item) => item.trim());
  const found = raw.find((item) => item.startsWith(prefix));
  return found ? decodeURIComponent(found.slice(prefix.length)) : "";
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method || "GET").toUpperCase();
  const headers = new Headers(init.headers || {});
  if (!headers.has("Accept")) {
    headers.set("Accept", "application/json");
  }
  const hasBody = init.body !== undefined && init.body !== null;
  if (hasBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = readCookie("erp_csrf_token");
    if (csrfToken) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }
  const response = await fetch(path, {
    credentials: "include",
    ...init,
    headers,
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    const detail = payload?.detail;
    const message = typeof detail === "string"
      ? detail
      : typeof detail?.message === "string"
        ? detail.message
        : `${response.status} ${response.statusText}`;
    throw new ApiError(message, {
      status: response.status,
      detail,
      payload,
    });
  }
  return payload as T;
}
