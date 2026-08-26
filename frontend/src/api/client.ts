export class ApiError extends Error {
  status: number;
  code?: string;
  fieldErrors?: Record<string, string>;

  constructor(
    message: string,
    status = 500,
    extras?: { code?: string; fieldErrors?: Record<string, string> },
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = extras?.code;
    this.fieldErrors = extras?.fieldErrors;
  }
}

const TOKEN_KEY = "quote.access_token";
const REFRESH_KEY = "quote.refresh_token";

export function getAccessToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY);
}

export function setTokens(access: string, refresh: string) {
  localStorage.setItem(TOKEN_KEY, access);
  localStorage.setItem(REFRESH_KEY, refresh);
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

const apiBase = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

async function parseError(response: Response): Promise<ApiError> {
  try {
    const body = await response.json();
    return new ApiError(body.detail || response.statusText, response.status, {
      code: body.code,
      fieldErrors: body.field_errors,
    });
  } catch {
    return new ApiError(response.statusText || "请求失败", response.status);
  }
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  options: { auth?: boolean; raw?: boolean } = {},
): Promise<T> {
  const headers = new Headers(init.headers);
  if (options.auth !== false) {
    const token = getAccessToken();
    if (token) headers.set("Authorization", `Bearer ${token}`);
  }
  const isForm = init.body instanceof FormData;
  const isBlob = init.body instanceof Blob && !(init.body instanceof FormData);
  if (init.body && !isForm && !isBlob && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${apiBase}${path}`, { ...init, headers });
  if (response.status === 401 && options.auth !== false) {
    clearTokens();
    if (!window.location.pathname.startsWith("/login")) {
      window.location.assign("/login");
    }
  }
  if (!response.ok) throw await parseError(response);
  if (options.raw) return response as T;
  if (response.status === 204) return undefined as T;
  const text = await response.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

export async function requestBlob(path: string): Promise<Blob> {
  const response = await request<Response>(path, {}, { raw: true });
  return response.blob();
}

export function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function errorMessage(err: unknown, fallback = "请求失败") {
  if (err instanceof ApiError) return err.message;
  if (err instanceof TypeError) {
    return "无法连接后端，请确认服务已启动（默认 http://127.0.0.1:8000）";
  }
  if (err instanceof Error && err.message) return err.message;
  return fallback;
}

export function yuan(value: number) {
  return `¥${value.toLocaleString("zh-CN", { maximumFractionDigits: 0 })}`;
}

export function formatDateTime(iso: string | null | undefined) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function formatDate(iso: string | null | undefined) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso.slice(0, 10);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}
