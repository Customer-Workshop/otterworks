import { NextRequest, NextResponse } from "next/server";
import { env } from "@/lib/env";
import { constantTimeEqual, readSession, UnauthorizedError } from "@/lib/session";
import { SIGNATURE_HEADER, verifySignature } from "@/lib/hmac";
import { HttpError } from "@/lib/errors";

export { HttpError };

export interface Actor {
  /** Display name recorded on comments / activity events. */
  name: string;
  via: "session" | "api-key" | "hmac";
}

function bearer(req: NextRequest): string | null {
  const h = req.headers.get("authorization");
  if (!h) return null;
  const m = /^Bearer\s+(.+)$/i.exec(h.trim());
  return m?.[1]?.trim() || null;
}

/** True when the request carries a valid `Authorization: Bearer <PROJECTS_API_KEY>`. */
export function hasValidApiKey(req: NextRequest): boolean {
  const key = env.apiKey;
  const token = bearer(req);
  if (!key || !token) return false;
  return constantTimeEqual(token, key);
}

/**
 * Every /api handler (except login, health and the inbound webhook) calls this
 * first. Accepts either the signed passcode session cookie or the API key.
 */
export function requireAuth(req: NextRequest): Actor {
  if (hasValidApiKey(req)) return { name: "api", via: "api-key" };
  const s = readSession(req);
  if (s) return { name: s.sub, via: "session" };
  throw new UnauthorizedError();
}

/**
 * Inbound webhook auth: API key OR an HMAC signature over the raw body with
 * PROJECTS_WEBHOOK_SECRET. The raw body must be read once by the caller.
 */
export function requireWebhookAuth(req: NextRequest, rawBody: string): Actor {
  if (hasValidApiKey(req)) return { name: "devin", via: "api-key" };
  const secret = env.webhookSecret;
  if (secret && verifySignature(rawBody, req.headers.get(SIGNATURE_HEADER), secret)) {
    return { name: "devin", via: "hmac" };
  }
  throw new UnauthorizedError();
}

/** Map thrown errors to JSON responses; used by every route handler. */
export function errorResponse(err: unknown): NextResponse {
  if (err instanceof UnauthorizedError) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (err instanceof HttpError) {
    return NextResponse.json({ error: err.message }, { status: err.status });
  }
  console.error(err);
  return NextResponse.json({ error: "internal error" }, { status: 500 });
}

export async function readJson<T>(req: NextRequest): Promise<T> {
  try {
    return (await req.json()) as T;
  } catch {
    throw new HttpError(400, "invalid JSON body");
  }
}
