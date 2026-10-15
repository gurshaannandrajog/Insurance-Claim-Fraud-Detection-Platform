import axios, { AxiosError } from "axios";

/**
 * Single HTTP client. Session cookie is HttpOnly (never readable by JS); the CSRF token is read from the
 * `csrftoken` cookie and sent back in X-CSRFToken, which is Django's standard protection for SPAs.
 * No credentials or tokens are stored in localStorage.
 */
export const api = axios.create({
  baseURL: "/api",
  withCredentials: true,
  xsrfCookieName: "csrftoken",
  xsrfHeaderName: "X-CSRFToken",
  headers: { "X-Requested-With": "XMLHttpRequest" },
});

export interface ApiErrorBody {
  code: string;
  message: string;
  fields?: Record<string, string[] | string>;
  [k: string]: unknown;
}

export class ApiError extends Error {
  status: number;
  code: string;
  fields: Record<string, string>;
  extra: Record<string, unknown>;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message || "Request failed");
    this.status = status;
    this.code = body.code || "error";
    this.fields = {};
    for (const [k, v] of Object.entries(body.fields || {})) {
      this.fields[k] = Array.isArray(v) ? v.join(" ") : String(v);
    }
    this.extra = body;
  }
}

type Listener = (code: "session_expired" | "not_authenticated") => void;
const authListeners = new Set<Listener>();
export const onAuthLost = (fn: Listener) => {
  authListeners.add(fn);
  return () => {
    authListeners.delete(fn);
  };
};

api.interceptors.response.use(
  (r) => r,
  (err: AxiosError<{ error?: ApiErrorBody } | Blob>) => {
    const status = err.response?.status ?? 0;
    const data = err.response?.data as { error?: ApiErrorBody } | undefined;
    const body: ApiErrorBody =
      data && typeof data === "object" && "error" in data && data.error
        ? data.error
        : status === 0
          ? { code: "network_error", message: "Cannot reach the server. Check that the backend is running." }
          : { code: "error", message: `Request failed (HTTP ${status}).` };
    if (status === 401 && (body.code === "session_expired" || body.code === "not_authenticated")) {
      authListeners.forEach((fn) => fn(body.code as "session_expired" | "not_authenticated"));
    }
    return Promise.reject(new ApiError(status, body));
  },
);

export const ensureCsrf = () => api.get("/auth/csrf/");

export interface Page<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export function errorMessage(e: unknown): string {
  if (e instanceof ApiError) return e.message;
  if (e instanceof Error) return e.message;
  return "Something went wrong.";
}

/** Download a protected file through the API (keeps the session cookie; nothing is publicly served). */
export async function downloadFile(url: string, fallbackName: string) {
  const res = await api.get(url.replace(/^\/api/, ""), { responseType: "blob" });
  const cd = (res.headers["content-disposition"] as string) || "";
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  const name = m ? decodeURIComponent(m[1]) : fallbackName;
  const href = URL.createObjectURL(res.data as Blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(href), 2000);
}
