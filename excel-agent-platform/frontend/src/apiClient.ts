const configuredBase = import.meta.env.VITE_API_BASE_URL;
const API_BASE = configuredBase === undefined ? "http://localhost:8000" : configuredBase;

type ErrorEnvelope = {
  ok: false;
  error?: {
    code?: string;
    message?: string;
    recoverable?: boolean;
    next_action?: string | null;
  } | null;
  meta?: {
    request_id?: string | null;
  };
};

export class ApiClientError extends Error {
  status: number;
  code: string;
  requestId?: string;
  recoverable: boolean;
  nextAction?: string | null;

  constructor({
    status,
    code,
    message,
    requestId,
    recoverable,
    nextAction,
  }: {
    status: number;
    code: string;
    message: string;
    requestId?: string;
    recoverable: boolean;
    nextAction?: string | null;
  }) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.recoverable = recoverable;
    this.nextAction = nextAction;
  }
}

function requestId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function statusCodeName(status: number) {
  if (status === 400 || status === 422) return "VALIDATION_ERROR";
  if (status === 401 || status === 403) return "PERMISSION_DENIED";
  if (status === 404) return "NOT_FOUND";
  if (status === 409) return "CONFLICT";
  if (status === 429) return "RATE_LIMITED";
  if (status >= 500) return "SERVER_ERROR";
  return "HTTP_ERROR";
}

function fallbackMessage(status: number) {
  if (status === 400) return "The request is invalid.";
  if (status === 401) return "Authentication is required.";
  if (status === 403) return "This action is not permitted.";
  if (status === 404) return "The requested resource was not found.";
  if (status === 409) return "The run is in a state that conflicts with this action.";
  if (status === 422) return "Some submitted fields are invalid.";
  if (status === 429) return "Too many requests. Please retry later.";
  if (status >= 500) return "The server failed while processing the request.";
  return `Request failed with HTTP ${status}.`;
}

async function parseError(response: Response): Promise<ApiClientError> {
  const requestId = response.headers.get("X-Request-ID") ?? undefined;
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      const body = (await response.json()) as Partial<ErrorEnvelope> & { detail?: unknown };
      if (body.error) {
        return new ApiClientError({
          status: response.status,
          code: body.error.code ?? statusCodeName(response.status),
          message: body.error.message ?? fallbackMessage(response.status),
          requestId: body.meta?.request_id ?? requestId,
          recoverable: body.error.recoverable ?? response.status >= 500,
          nextAction: body.error.next_action,
        });
      }
      if (body.detail) {
        return new ApiClientError({
          status: response.status,
          code: statusCodeName(response.status),
          message: typeof body.detail === "string" ? body.detail : fallbackMessage(response.status),
          requestId,
          recoverable: response.status >= 500,
        });
      }
    } catch {
      // Fall through to text parsing.
    }
  }

  const text = await response.text().catch(() => "");
  return new ApiClientError({
    status: response.status,
    code: statusCodeName(response.status),
    message: text || fallbackMessage(response.status),
    requestId,
    recoverable: response.status >= 500,
  });
}

async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("X-Request-ID", requestId());
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });
  if (!response.ok) {
    throw await parseError(response);
  }
  return (await response.json()) as T;
}

export function apiGet<T>(path: string) {
  return apiFetch<T>(path);
}

export function apiPost<T>(path: string) {
  return apiFetch<T>(path, { method: "POST" });
}

export function apiPostForm<T>(path: string, body: FormData) {
  return apiFetch<T>(path, { method: "POST", body });
}

export function apiPatchForm<T>(path: string, body: FormData) {
  return apiFetch<T>(path, { method: "PATCH", body });
}

export function apiDownloadUrl(path: string) {
  return `${API_BASE}${path}`;
}

export function formatApiError(error: unknown) {
  if (error instanceof ApiClientError) {
    const request = error.requestId ? ` Request ID: ${error.requestId}.` : "";
    return `${error.status} ${error.code}: ${error.message}.${request}`;
  }
  return error instanceof Error ? error.message : String(error);
}
