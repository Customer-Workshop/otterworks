/**
 * Tests for Next.js middleware — validates /api/v1/* rewrite behavior
 * and ensures API_GATEWAY_URL env var is respected.
 *
 * Related to CVE-2025-29927 (authorization bypass via middleware).
 */

const mockRewrite = jest.fn().mockImplementation((url: URL) => ({
  headers: new Map([["x-middleware-rewrite", url.toString()]]),
}));

jest.mock("next/server", () => ({
  NextResponse: { rewrite: mockRewrite },
}));

import { middleware, config } from "./middleware";

function createMockRequest(url: string) {
  const parsed = new URL(url);
  return {
    nextUrl: {
      pathname: parsed.pathname,
      search: parsed.search,
    },
  } as any;
}

describe("middleware", () => {
  const defaultGateway = "http://localhost:8080";

  beforeEach(() => {
    delete process.env.API_GATEWAY_URL;
    mockRewrite.mockClear();
    mockRewrite.mockImplementation((url: URL) => ({
      headers: new Map([["x-middleware-rewrite", url.toString()]]),
    }));
  });

  it("rewrites /api/v1/* routes to the default API gateway", () => {
    const req = createMockRequest("http://localhost:3000/api/v1/auth/login");
    const res = middleware(req);
    expect(res.headers.get("x-middleware-rewrite")).toContain(defaultGateway);
    expect(res.headers.get("x-middleware-rewrite")).toContain("/api/v1/auth/login");
  });

  it("respects the API_GATEWAY_URL environment variable", () => {
    process.env.API_GATEWAY_URL = "https://gateway.otterworks.io";
    const req = createMockRequest("http://localhost:3000/api/v1/files");
    const res = middleware(req);
    expect(res.headers.get("x-middleware-rewrite")).toContain(
      "https://gateway.otterworks.io"
    );
  });

  it("preserves query string parameters", () => {
    const req = createMockRequest("http://localhost:3000/api/v1/search?q=test&page=2");
    const res = middleware(req);
    const rewriteUrl = res.headers.get("x-middleware-rewrite") || "";
    expect(rewriteUrl).toContain("q=test");
    expect(rewriteUrl).toContain("page=2");
  });

  it("preserves the full path including nested segments", () => {
    const req = createMockRequest(
      "http://localhost:3000/api/v1/documents/abc-123/versions"
    );
    const res = middleware(req);
    expect(res.headers.get("x-middleware-rewrite")).toContain(
      "/api/v1/documents/abc-123/versions"
    );
  });
});

describe("middleware config", () => {
  it("only matches /api/v1/* routes", () => {
    expect(config.matcher).toBe("/api/v1/:path*");
  });
});
