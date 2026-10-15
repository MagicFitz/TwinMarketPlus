function trimSlash(value: string) {
  return value.replace(/\/+$/, "");
}

const injectedApiBase = typeof window === "undefined" ? "" : window.__TWINMARKET_CONFIG__?.apiBaseUrl;
const host = trimSlash(injectedApiBase || import.meta.env.VITE_API_BASE_URL || "");

export const API_ROOT = host.endsWith("/api") ? host : `${host}/api`;

export function apiUrl(path: string) {
  return `${API_ROOT}${path.startsWith("/") ? path : `/${path}`}`;
}
