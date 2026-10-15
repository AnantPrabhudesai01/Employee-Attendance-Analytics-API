// Runtime config. VITE_API_BASE_URL is baked into the browser bundle,
// so it can never hold a secret — plain host only.
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
export const REQUEST_TIMEOUT_MS = 15_000;
