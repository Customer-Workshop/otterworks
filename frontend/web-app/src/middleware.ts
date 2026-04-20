import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  // Proxy /api/v1/* requests to the API gateway.
  // Middleware rewrites are evaluated at runtime (unlike next.config.js rewrites
  // which are baked at build time and don't work with standalone output).
  const apiUrl = process.env.API_GATEWAY_URL || "http://localhost:8080";
  const target = new URL(
    request.nextUrl.pathname + request.nextUrl.search,
    apiUrl
  );
  return NextResponse.rewrite(target);
}

export const config = {
  matcher: "/api/v1/:path*",
};
