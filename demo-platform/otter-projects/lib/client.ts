"use client";

// Client-side fetch helpers (same-origin, cookie session).

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(await errText(res));
  return (await res.json()) as T;
}

export async function apiSend<T>(path: string, method: "POST" | "PATCH" | "DELETE", body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errText(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function errText(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { error?: string };
    return data.error || `request failed (${res.status})`;
  } catch {
    return `request failed (${res.status})`;
  }
}

export function timeAgo(ts: number): string {
  const s = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}
