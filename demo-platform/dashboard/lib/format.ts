// Client-safe formatting helpers (no server-only imports).

export function formatCountdown(expiresAtSeconds: number, nowMs: number = Date.now()): string {
  const remaining = expiresAtSeconds * 1000 - nowMs;
  if (remaining <= 0) return "expired";
  const totalMin = Math.floor(remaining / 60000);
  const days = Math.floor(totalMin / (60 * 24));
  const hours = Math.floor((totalMin % (60 * 24)) / 60);
  const mins = totalMin % 60;
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${mins}m`;
  return `${mins}m`;
}

export function formatTimestamp(ms: number): string {
  if (!ms) return "—";
  return new Date(ms).toISOString().replace("T", " ").replace(/\.\d+Z$/, "Z");
}
