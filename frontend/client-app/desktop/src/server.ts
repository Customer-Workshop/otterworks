import http from "node:http";
import https from "node:https";
import net from "node:net";
import path from "node:path";
import { promises as fs } from "node:fs";

// Embedded equivalent of nginx/default.conf.template: serves the built SPA from
// `webRoot` with an index.html fallback, and reverse-proxies /api/v1/* (HTTP and
// WebSocket upgrades) to the API gateway so the renderer only ever talks
// same-origin - exactly like the web build served by Vite (dev) or nginx (prod).

const MIME_TYPES: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".webp": "image/webp",
  ".ico": "image/x-icon",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".map": "application/json",
  ".txt": "text/plain; charset=utf-8",
};

export interface AppServerOptions {
  webRoot: string;
  gatewayUrl: string;
  /** Preferred port; falls back to an ephemeral port if unavailable. */
  port: number;
  host?: string;
}

export interface AppServer {
  server: http.Server;
  url: string;
  close: () => Promise<void>;
}

function isApiPath(url: string): boolean {
  return url === "/api/v1" || url.startsWith("/api/v1/") || url.startsWith("/api/v1?");
}

// Header keys that could pollute Object.prototype if copied onto a plain object.
const UNSAFE_HEADER_KEYS = new Set(["__proto__", "constructor", "prototype"]);

// Build the outbound target strictly on top of the trusted gateway origin,
// copying over only the client request's path + query. Because the destination
// URL is derived from `gateway` (never from the request), the upstream host,
// scheme, and port can't be influenced by a client-supplied absolute URL - the
// path always starts with "/" so it can only ever be a relative sub-path of the
// gateway origin.
function forwardTarget(gateway: URL, rawUrl: string | undefined): URL {
  const requested = new URL(rawUrl ?? "/", "http://localhost");
  const target = new URL(gateway.toString());
  target.pathname = requested.pathname;
  target.search = requested.search;
  return target;
}

// Copy upstream response headers onto a prototype-less object, dropping keys
// that could pollute Object.prototype, so a compromised gateway can't inject
// prototype-polluting or unexpected control headers into our response.
function sanitizeHeaders(headers: http.IncomingHttpHeaders): http.OutgoingHttpHeaders {
  const clean: http.OutgoingHttpHeaders = Object.create(null);
  for (const [key, value] of Object.entries(headers)) {
    if (value !== undefined && !UNSAFE_HEADER_KEYS.has(key.toLowerCase())) {
      clean[key] = value;
    }
  }
  return clean;
}

async function serveStatic(
  webRoot: string,
  reqUrl: string,
  res: http.ServerResponse
): Promise<void> {
  const pathname = decodeURIComponent(new URL(reqUrl, "http://localhost").pathname);
  const safePath = path.normalize(pathname).replace(/^(\.\.[/\\])+/, "");
  let filePath = path.join(webRoot, safePath);
  if (!filePath.startsWith(path.resolve(webRoot))) {
    res.writeHead(403).end("Forbidden");
    return;
  }

  let body: Buffer;
  try {
    const stat = await fs.stat(filePath);
    if (stat.isDirectory()) filePath = path.join(filePath, "index.html");
    body = await fs.readFile(filePath);
  } catch {
    // SPA fallback, mirroring nginx `try_files $uri $uri/ /index.html`
    filePath = path.join(webRoot, "index.html");
    body = await fs.readFile(filePath);
  }

  const headers: http.OutgoingHttpHeaders = {
    "Content-Type": MIME_TYPES[path.extname(filePath).toLowerCase()] || "application/octet-stream",
    "Content-Length": body.length,
  };
  // Hashed bundle assets are immutable, mirroring the nginx config
  if (pathname.startsWith("/assets/")) {
    headers["Cache-Control"] = "public, max-age=31536000, immutable";
  }
  res.writeHead(200, headers).end(body);
}

function proxyRequest(gateway: URL, req: http.IncomingMessage, res: http.ServerResponse): void {
  const transport = gateway.protocol === "https:" ? https : http;
  const proxyReq = transport.request(
    forwardTarget(gateway, req.url),
    {
      method: req.method,
      headers: {
        ...req.headers,
        host: gateway.host,
        "x-forwarded-for": req.socket.remoteAddress ?? "",
        "x-forwarded-proto": "http",
      },
    },
    (proxyRes) => {
      res.writeHead(proxyRes.statusCode ?? 502, sanitizeHeaders(proxyRes.headers));
      proxyRes.pipe(res);
    }
  );
  proxyReq.on("error", (err) => {
    res.writeHead(502, { "Content-Type": "application/json" });
    res.end(JSON.stringify({ error: "bad_gateway", message: err.message }));
  });
  req.pipe(proxyReq);
}

function proxyUpgrade(
  gateway: URL,
  req: http.IncomingMessage,
  socket: net.Socket,
  head: Buffer
): void {
  const transport = gateway.protocol === "https:" ? https : http;
  const proxyReq = transport.request(forwardTarget(gateway, req.url), {
    method: req.method,
    headers: { ...req.headers, host: gateway.host },
  });
  proxyReq.on("upgrade", (proxyRes, proxySocket, proxyHead) => {
    const lines = [`HTTP/1.1 101 Switching Protocols`];
    for (const [key, value] of Object.entries(proxyRes.headers)) {
      for (const v of Array.isArray(value) ? value : [value]) {
        if (v !== undefined) lines.push(`${key}: ${v}`);
      }
    }
    socket.write(lines.join("\r\n") + "\r\n\r\n");
    // Return early bytes to the stream they were read from so the pipes forward them
    if (proxyHead.length) proxySocket.unshift(proxyHead);
    if (head.length) socket.unshift(head);
    proxySocket.pipe(socket);
    socket.pipe(proxySocket);
    const destroyBoth = () => {
      proxySocket.destroy();
      socket.destroy();
    };
    proxySocket.on("error", destroyBoth).on("close", destroyBoth);
    socket.on("error", destroyBoth).on("close", destroyBoth);
  });
  proxyReq.on("error", () => socket.destroy());
  proxyReq.end();
}

function listen(server: http.Server, port: number, host: string): Promise<number> {
  return new Promise((resolve, reject) => {
    const onError = (err: NodeJS.ErrnoException) => {
      if (err.code === "EADDRINUSE" && port !== 0) {
        console.warn(`[desktop] port ${port} in use, falling back to an ephemeral port`);
        server.removeListener("error", onError);
        resolve(listen(server, 0, host));
      } else {
        reject(err);
      }
    };
    server.once("error", onError);
    server.listen(port, host, () => {
      server.removeListener("error", onError);
      resolve((server.address() as net.AddressInfo).port);
    });
  });
}

export async function startAppServer(options: AppServerOptions): Promise<AppServer> {
  const { webRoot, gatewayUrl, port } = options;
  const host = options.host ?? "127.0.0.1";
  const gateway = new URL(gatewayUrl);

  const server = http.createServer((req, res) => {
    if (req.url && isApiPath(req.url)) {
      proxyRequest(gateway, req, res);
    } else {
      serveStatic(webRoot, req.url ?? "/", res).catch((err) => {
        res.writeHead(500).end(`Internal error: ${err.message}`);
      });
    }
  });
  // Upgraded sockets escape closeAllConnections(), so track them for shutdown
  const upgradedSockets = new Set<net.Socket>();
  server.on("upgrade", (req, socket, head) => {
    if (req.url && isApiPath(req.url)) {
      upgradedSockets.add(socket as net.Socket);
      socket.on("close", () => upgradedSockets.delete(socket as net.Socket));
      proxyUpgrade(gateway, req, socket as net.Socket, head);
    } else {
      socket.destroy();
    }
  });

  const boundPort = await listen(server, port, host);
  return {
    server,
    url: `http://${host}:${boundPort}`,
    close: () =>
      new Promise((resolve, reject) => {
        server.close((err) => (err ? reject(err) : resolve()));
        server.closeAllConnections();
        for (const s of upgradedSockets) s.destroy();
      }),
  };
}
