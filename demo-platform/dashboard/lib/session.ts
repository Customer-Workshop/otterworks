import crypto from "node:crypto";
import { NextRequest } from "next/server";
import { env } from "@/lib/env";

export const SESSION_COOKIE = "ow_ops_session";

interface SessionPayload {
  // Subject — a stable, non-identifying label for a passcode holder.
  sub: string;
  // Issued-at / expiry, epoch seconds.
  iat: number;
  exp: number;
}

function b64url(buf: Buffer): string {
  return buf.toString("base64url");
}

function hmac(secret: string, data: string): Buffer {
  return crypto.createHmac("sha256", secret).update(data).digest();
}

/**
 * Constant-time comparison of two UTF-8 strings. Length is compared in a way
 * that avoids leaking it via early return: both sides are hashed to a fixed
 * width before `timingSafeEqual`.
 */
export function constantTimeEqual(a: string, b: string): boolean {
  const ha = crypto.createHash("sha256").update(a, "utf8").digest();
  const hb = crypto.createHash("sha256").update(b, "utf8").digest();
  return crypto.timingSafeEqual(ha, hb);
}

/** Create a signed session token: base64url(payload).base64url(hmac). */
export function signSession(sub: string, secret: string): { token: string; exp: number } {
  const now = Math.floor(Date.now() / 1000);
  const exp = now + env.sessionTtlSeconds;
  const payload: SessionPayload = { sub, iat: now, exp };
  const body = b64url(Buffer.from(JSON.stringify(payload), "utf8"));
  const sig = b64url(hmac(secret, body));
  return { token: `${body}.${sig}`, exp };
}

/** Verify a session token; returns the payload or null. */
export function verifySession(token: string | undefined, secret: string): SessionPayload | null {
  if (!token) return null;
  const dot = token.indexOf(".");
  if (dot <= 0) return null;
  const body = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  const expected = b64url(hmac(secret, body));
  const sigBuf = Buffer.from(sig);
  const expBuf = Buffer.from(expected);
  if (sigBuf.length !== expBuf.length) return null;
  if (!crypto.timingSafeEqual(sigBuf, expBuf)) return null;
  let payload: SessionPayload;
  try {
    payload = JSON.parse(Buffer.from(body, "base64url").toString("utf8")) as SessionPayload;
  } catch {
    return null;
  }
  if (typeof payload.exp !== "number" || payload.exp < Math.floor(Date.now() / 1000)) {
    return null;
  }
  return payload;
}

export interface SessionCookieOptions {
  name: string;
  value: string;
  httpOnly: true;
  secure: true;
  sameSite: "strict";
  path: string;
  maxAge: number;
}

export function sessionCookie(token: string): SessionCookieOptions {
  return {
    name: SESSION_COOKIE,
    value: token,
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: env.sessionTtlSeconds,
  };
}

export function clearedSessionCookie(): SessionCookieOptions {
  return {
    name: SESSION_COOKIE,
    value: "",
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/",
    maxAge: 0,
  };
}

/** Read + validate the session token from a NextRequest. */
export function readSession(req?: NextRequest): SessionPayload | null {
  const secret = env.sessionSecret;
  if (!secret) return null;
  const token = req?.cookies.get(SESSION_COOKIE)?.value;
  return verifySession(token, secret);
}

export class UnauthorizedError extends Error {
  constructor() {
    super("unauthorized");
    this.name = "UnauthorizedError";
  }
}

/**
 * Defense-in-depth guard: every /api handler calls this first. Throws
 * UnauthorizedError when there is no valid session. Never trusts any
 * client-provided identity — the actor comes from the signed cookie only.
 */
export function requireSession(req?: NextRequest): SessionPayload {
  const s = readSession(req);
  if (!s) throw new UnauthorizedError();
  return s;
}
