import { API_BASE_URL, REQUEST_TIMEOUT_MS } from "../config";

export type ErrorKind =
  | "validation"
  | "business_rule"
  | "not_found"
  | "auth"
  | "network"
  | "timeout"
  | "server"
  | "unknown";

export class AppError extends Error {
  kind: ErrorKind;
  status?: number;
  fieldErrors?: Record<string, string>;
  detail?: string;
  constructor(kind: ErrorKind, message: string, opts?: { status?: number; fieldErrors?: Record<string, string>; detail?: string }) {
    super(message);
    this.kind = kind;
    this.status = opts?.status;
    this.fieldErrors = opts?.fieldErrors;
    this.detail = opts?.detail;
  }
}

function kindFor(status: number): ErrorKind {
  if (status === 422) return "validation";
  if (status === 404) return "not_found";
  if (status === 409) return "business_rule";
  if (status === 401 || status === 403) return "auth";
  if (status >= 500) return "server";
  return "unknown";
}

/** GET/POST/PATCH JSON behind one honest mapping. Throws AppError, never silent nulls. */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch (e) {
    clearTimeout(timer);
    if (e instanceof DOMException && e.name === "AbortError") throw new AppError("timeout", "Request timed out. Retry.");
    throw new AppError("network", "Cannot reach the API. Start the backend first.");
  } finally {
    clearTimeout(timer);
  }
  if (res.ok) return (await res.json()) as T;
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error */
  }
  const detail = body !== null && typeof body === "object" && "detail" in body ? (body as { detail: unknown }).detail : null;
  throw new AppError(kindFor(res.status), typeof detail === "string" ? detail : `Request failed (${res.status}).`, {
    status: res.status,
    detail: typeof detail === "string" ? detail : JSON.stringify(detail),
  });
}
