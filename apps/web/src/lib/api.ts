export const CONNECTION_KEY = "tracehunt.connection";
export interface Connection { baseUrl: string; apiKey: string }
export const defaultConnection: Connection = { baseUrl: "/api/v1", apiKey: "" };

export function readConnection(): Connection {
  if (typeof window === "undefined") return defaultConnection;
  try {
    const saved = JSON.parse(localStorage.getItem(CONNECTION_KEY) || "{}");
    return { baseUrl: saved.baseUrl || defaultConnection.baseUrl, apiKey: sessionStorage.getItem("tracehunt.apiKey") || "" };
  } catch { return defaultConnection; }
}

export function saveConnection(value: Connection) {
  const baseUrl = value.baseUrl.trim().replace(/\/+$/, "") || "/api/v1";
  if (baseUrl !== "/api/v1") {
    const url = new URL(baseUrl);
    if (!["http:", "https:"].includes(url.protocol)) throw new Error("Use an HTTP or HTTPS API URL.");
  }
  localStorage.setItem(CONNECTION_KEY, JSON.stringify({ baseUrl }));
  sessionStorage.setItem("tracehunt.apiKey", value.apiKey.trim());
  window.dispatchEvent(new Event("tracehunt-connection"));
}

export async function api<T>(path: string, init: RequestInit = {}, connection?: Connection): Promise<T> {
  const config = connection || readConnection();
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), path.endsWith("/analyze") ? 90000 : 30000);
  try {
    const response = await fetch(`${config.baseUrl.replace(/\/$/, "")}${path}`, {
      ...init, signal: controller.signal,
      headers: { "Content-Type": "application/json", ...(config.apiKey ? { "X-API-Key": config.apiKey } : {}), ...init.headers },
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const detail = body?.detail;
      const message = Array.isArray(detail) ? detail.map((item: { msg: string }) => item.msg).join("; ") : typeof detail === "string" ? detail : `Request failed (${response.status})`;
      throw new Error(response.status === 401 ? "Authentication required. Add your API key in Connection settings." : message);
    }
    if (response.status === 204) return undefined as T;
    return await response.json() as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw new Error("The request timed out. Check the API connection and try again.");
    if (error instanceof TypeError) throw new Error("Cannot reach the API. Start the backend or update your connection in Settings.");
    throw error;
  } finally { clearTimeout(timeout); }
}

export const post = <T,>(path: string, data?: unknown) => api<T>(path, { method: "POST", ...(data === undefined ? {} : { body: JSON.stringify(data) }) });
export const patch = <T,>(path: string, data: unknown) => api<T>(path, { method: "PATCH", body: JSON.stringify(data) });
export const number = (value: number | undefined) => new Intl.NumberFormat("en", { notation: (value || 0) >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(value || 0);
export const when = (value?: string | null) => value ? new Date(value).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : "Not checked yet";
export function ago(value?: string | null) {
  if (!value) return "Awaiting first check";
  const minutes = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 60000));
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1440)}d ago`;
}
export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Something went wrong. Please try again.";
