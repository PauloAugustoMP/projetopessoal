/** Thin typed fetch wrapper over the backend REST API (docs/openapi/openapi.yaml).
 * Handles the JWT pair: attaches the access token, transparently refreshes it
 * once on a 401, and surfaces a session-expired signal when refresh fails. */

const BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

const ACCESS_TOKEN_KEY = "accessToken";
const REFRESH_TOKEN_KEY = "refreshToken";

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function isLoggedIn(): boolean {
  return getAccessToken() !== null;
}

export function storeTokens(accessToken: string, refreshToken?: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  if (refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

async function tryRefresh(): Promise<boolean> {
  const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
  if (!refreshToken) return false;
  const response = await fetch(`${BASE_URL}/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refreshToken }),
  });
  if (!response.ok) return false;
  const body = (await response.json()) as { accessToken: string };
  storeTokens(body.accessToken);
  return true;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  retrying = false,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!headers.has("Content-Type") && options.body && !(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${BASE_URL}${path}`, { ...options, headers });

  if (response.status === 401 && !retrying && path !== "/auth/login") {
    if (await tryRefresh()) return request<T>(path, options, true);
    clearTokens();
    window.dispatchEvent(new Event("session-expired"));
  }

  if (!response.ok) {
    let code = "UNKNOWN";
    let message = response.statusText;
    try {
      const body = (await response.json()) as { code?: string; message?: string };
      code = body.code ?? code;
      message = body.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, code, message);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
};

export function quotesWebSocketUrl(): string {
  const token = getAccessToken() ?? "";
  const wsBase = BASE_URL.replace(/^http/, "ws").replace(/\/api$/, "");
  return `${wsBase}/ws/quotes?token=${encodeURIComponent(token)}`;
}
