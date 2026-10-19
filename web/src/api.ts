const TOKEN_KEY = "nexcora.session";
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public requestId?: string,
  ) {
    super(message);
  }
}
export const session = {
  get: () => sessionStorage.getItem(TOKEN_KEY),
  set: (value: string) => sessionStorage.setItem(TOKEN_KEY, value),
  clear: () => sessionStorage.removeItem(TOKEN_KEY),
};
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  const token = session.get();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (options.body && typeof options.body === "string")
    headers.set("Content-Type", "application/json");
  let response: Response;
  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    options.body instanceof Blob ? 150_000 : 20_000,
  );
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      headers,
      signal: controller.signal,
      credentials: "same-origin",
    });
  } catch {
    throw new ApiError(
      0,
      "network",
      "Проверьте соединение с интернетом и повторите действие.",
    );
  } finally {
    window.clearTimeout(timeout);
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    if (response.status === 401 && path !== "/auth/telegram") {
      session.clear();
      window.dispatchEvent(new Event("nexcora:expired"));
    }
    throw new ApiError(
      response.status,
      body?.error?.code || "request_failed",
      body?.error?.message || "Не удалось выполнить запрос. Повторите позже.",
      body?.error?.request_id,
    );
  }
  if (
    options.headers &&
    new Headers(options.headers).get("Accept") === "application/octet-stream"
  )
    return (await response.blob()) as T;
  return (await response.json()) as T;
}
export function json(method: string, body: unknown): RequestInit {
  return { method, body: JSON.stringify(body) };
}
// Persist one key for the exact intent, including retries after a lost response/reload.
export async function intent<T>(path: string, body: unknown): Promise<T> {
  const signature = JSON.stringify({ path, body });
  const keyName = `nexcora.intent:${path}`;
  let saved: { signature: string; key: string } | null = null;
  try {
    saved = JSON.parse(sessionStorage.getItem(keyName) || "null");
  } catch {
    /* discard malformed storage */
  }
  const key = saved?.signature === signature ? saved.key : crypto.randomUUID();
  sessionStorage.setItem(keyName, JSON.stringify({ signature, key }));
  const result = await api<T>(path, {
    ...json("POST", body),
    headers: { "Idempotency-Key": key },
  });
  sessionStorage.removeItem(keyName);
  return result;
}
export async function download(id: string, filename: string) {
  const blob = await api<Blob>(`/attachments/${id}/download`, {
    headers: { Accept: "application/octet-stream" },
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
