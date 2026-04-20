import { NextRequest, NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const API_GATEWAY_URL =
  process.env.API_GATEWAY_URL || "http://localhost:8080";

async function proxyRequest(request: NextRequest) {
  const url = new URL(request.url);
  const targetUrl = `${API_GATEWAY_URL}${url.pathname}${url.search}`;

  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "host") {
      headers[key] = value;
    }
  });

  const fetchOptions: {
    method: string;
    headers: Record<string, string>;
    body?: string;
  } = {
    method: request.method,
    headers,
  };

  // Forward body for non-GET/HEAD requests
  if (request.method !== "GET" && request.method !== "HEAD") {
    try {
      fetchOptions.body = await request.text();
    } catch {
      // Body may already be consumed or empty
    }
  }

  try {
    const response = await fetch(targetUrl, fetchOptions);
    const body = await response.arrayBuffer();

    const responseHeaders = new Headers();
    response.headers.forEach((value, key) => {
      if (key.toLowerCase() !== "transfer-encoding") {
        responseHeaders.set(key, value);
      }
    });

    return new NextResponse(body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch {
    return NextResponse.json(
      { error: "API gateway unreachable" },
      { status: 502 }
    );
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const OPTIONS = proxyRequest;
