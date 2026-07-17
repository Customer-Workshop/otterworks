"use client";

// Thin client-side fetch helpers for the dashboard UI.

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(await errText(res));
  return (await res.json()) as T;
}

export async function apiSend<T>(
  path: string,
  method: "POST" | "PUT" | "DELETE",
  body?: unknown,
): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errText(res));
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
