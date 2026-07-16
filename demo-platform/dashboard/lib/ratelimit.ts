// In-memory login rate limiter: max 5 attempts / IP / 15 min, with exponential
// backoff between attempts. This is per-pod state — adequate for a single-pod
// ops dashboard; a distributed limiter would move this into the control table.

const WINDOW_MS = 15 * 60 * 1000;
const MAX_ATTEMPTS = 5;
const BASE_BACKOFF_MS = 1000;

interface Bucket {
  count: number;
  windowStart: number;
  lastAttempt: number;
}

const buckets = new Map<string, Bucket>();

export interface RateResult {
  allowed: boolean;
  // Milliseconds the caller must wait before the next attempt is permitted.
  retryAfterMs: number;
  remaining: number;
}

export function checkRateLimit(ip: string, now: number = Date.now()): RateResult {
  let b = buckets.get(ip);
  if (!b || now - b.windowStart > WINDOW_MS) {
    b = { count: 0, windowStart: now, lastAttempt: 0 };
    buckets.set(ip, b);
  }

  if (b.count >= MAX_ATTEMPTS) {
    return {
      allowed: false,
      retryAfterMs: b.windowStart + WINDOW_MS - now,
      remaining: 0,
    };
  }

  // Exponential backoff between successive failed attempts within the window.
  if (b.count > 0) {
    const backoff = BASE_BACKOFF_MS * 2 ** (b.count - 1);
    const waited = now - b.lastAttempt;
    if (waited < backoff) {
      return { allowed: false, retryAfterMs: backoff - waited, remaining: MAX_ATTEMPTS - b.count };
    }
  }

  return { allowed: true, retryAfterMs: 0, remaining: MAX_ATTEMPTS - b.count };
}

/** Record a failed attempt (advances the backoff + count). */
export function recordFailure(ip: string, now: number = Date.now()): void {
  const b = buckets.get(ip) ?? { count: 0, windowStart: now, lastAttempt: 0 };
  b.count += 1;
  b.lastAttempt = now;
  buckets.set(ip, b);
}

/** Clear the bucket on a successful login. */
export function recordSuccess(ip: string): void {
  buckets.delete(ip);
}

export function clientIp(headers: Headers): string {
  const xff = headers.get("x-forwarded-for");
  if (xff) {
    const first = xff.split(",")[0]?.trim();
    if (first) return first;
  }
  return headers.get("x-real-ip") || "unknown";
}
