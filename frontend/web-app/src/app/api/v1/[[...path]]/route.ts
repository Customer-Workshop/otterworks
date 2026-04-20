import { NextRequest, NextResponse } from "next/server";

const API_GATEWAY_URL =
  process.env.API_GATEWAY_URL || "http://localhost:8080";

async function proxyRequest(request: NextRequest) {
  const url = new URL(request.url);
  const targetUrl = `${API_GATEWAY_URL}${url.pathname}${url.search}`;

  const headers = new Headers(request.headers);
  headers.delete("host");

  const init: RequestInit = {
    method: request.method,
    headers,
  };

  // Forward body for non-GET/HEAD requests
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = await request.text();
  }

  try {
    const response = await fetch(targetUrl, init);
    const body = await response.arrayBuffer();

    const responseHeaders = new Headers(response.headers);
    // Remove transfer-encoding since we're sending the full body
    responseHeaders.delete("transfer-encoding");

    return new NextResponse(body, {
      status: response.status,
      statusText: response.statusText,
      headers: responseHeaders,
    });
  } catch (error) {
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
