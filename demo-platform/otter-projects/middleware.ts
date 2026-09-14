import { NextRequest, NextResponse } from "next/server";

// Runs on the Edge runtime (no node:crypto): re-verifies the HMAC session
// cookie with Web Crypto. Route handlers independently call requireAuth().
// Requests carrying an Authorization header are passed through so API-key
// clients reach the handler, which validates the key itself.

const SESSION_COOKIE = "ow_projects_session";

function base64urlToBytes(input: string): Uint8Array {
  const b64 = input.replace(/-/g, "+").replace(/_/g, "/");
  const pad = b64.length % 4 === 0 ? "" : "=".repeat(4 - (b64.length % 4));
  const bin = atob(b64 + pad);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i += 1) bytes[i] = bin.charCodeAt(i);
  return bytes;
}

async function verifyToken(token: string | undefined, secret: string): Promise<boolean> {
  if (!token) return false;
  const dot = token.indexOf(".");
  if (dot <= 0) return false;
  const body = token.slice(0, dot);
  const sig = token.slice(dot + 1);
  let sigBytes: Uint8Array;
  try {
    sigBytes = base64urlToBytes(sig);
  } catch {
    return false;
  }
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["verify"]);
  const valid = await crypto.subtle.verify(
    "HMAC",
    key,
    sigBytes as unknown as ArrayBuffer,
    enc.encode(body) as unknown as ArrayBuffer,
  );
  if (!valid) return false;
  try {
    const payload = JSON.parse(new TextDecoder().decode(base64urlToBytes(body))) as { exp?: number };
    return typeof payload.exp === "number" && payload.exp >= Math.floor(Date.now() / 1000);
  } catch {
    return false;
  }
}

function isPublicPath(pathname: string): boolean {
  return (
    pathname === "/login" ||
    pathname === "/api/auth/login" ||
    pathname === "/api/health" ||
    pathname === "/health" ||
    pathname === "/api/webhooks/devin" ||
    pathname === "/api/devin/poll" ||
    pathname === "/favicon.ico"
  );
}

export async function middleware(req: NextRequest): Promise<NextResponse> {
  const { pathname } = req.nextUrl;
  if (isPublicPath(pathname)) return NextResponse.next();
  if (pathname.startsWith("/api/") && req.headers.get("authorization")) return NextResponse.next();

  const secret = process.env.SESSION_SECRET;
  const token = req.cookies.get(SESSION_COOKIE)?.value;
  const ok = secret ? await verifyToken(token, secret) : false;
  if (ok) return NextResponse.next();

  if (pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const url = req.nextUrl.clone();
  url.pathname = "/login";
  url.search = pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|assets|favicon.ico).*)"],
};
