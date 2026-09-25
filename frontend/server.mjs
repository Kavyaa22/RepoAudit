/**
 * Production static server with /api reverse proxy.
 *
 * Browser calls same-origin /api/v1/*; this process forwards to BACKEND_URL.
 * VITE_* vars are build-time only — BACKEND_URL is read at runtime on Railway.
 */
import { createServer } from "node:http";
import { request as httpRequest } from "node:http";
import { request as httpsRequest } from "node:https";
import { readFileSync, statSync, createReadStream, existsSync } from "node:fs";
import { join, extname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const DIST = join(__dirname, "dist");
const PORT = Number(process.env.PORT || 8080);

/** Headers that must not be forwarded verbatim through a proxy. */
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
]);

function normalizeOrigin(value) {
  const trimmed = String(value || "").trim().replace(/\/$/, "");
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

function resolveBackendUrl() {
  const explicit = normalizeOrigin(process.env.BACKEND_URL);
  if (explicit) return explicit;

  const vite = String(process.env.VITE_API_BASE_URL || "").trim();
  if (vite.startsWith("/")) return "";

  const normalizedVite = normalizeOrigin(vite);
  if (normalizedVite) {
    return normalizedVite.replace(/\/api\/v1\/?$/i, "");
  }

  return "https://repository-audit-production.up.railway.app";
}

const BACKEND_URL = resolveBackendUrl();

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};

function sendJson(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body));
}

function filterHeaders(source, { dropEncoding = false } = {}) {
  const headers = {};
  for (const [key, value] of Object.entries(source)) {
    if (value == null) continue;
    const lower = key.toLowerCase();
    if (HOP_BY_HOP.has(lower)) continue;
    if (dropEncoding && (lower === "content-encoding" || lower === "content-length")) {
      continue;
    }
    headers[key] = value;
  }
  return headers;
}

function buildUpstreamHeaders(req, targetHost) {
  const headers = filterHeaders(req.headers);
  headers.host = targetHost;
  // Ask backend for uncompressed JSON so buffering (404 checks) never breaks gzip.
  headers["accept-encoding"] = "identity";
  return headers;
}

function proxyToBackend(req, res) {
  let target;
  try {
    target = new URL(req.url || "/", `${BACKEND_URL}/`);
  } catch (err) {
    sendJson(res, 502, {
      success: false,
      error: {
        code: "backend_misconfigured",
        message: `Invalid BACKEND_URL (${BACKEND_URL}): ${err.message}`,
      },
    });
    return;
  }

  const requestFn = target.protocol === "https:" ? httpsRequest : httpRequest;
  const proxyReq = requestFn(
    {
      hostname: target.hostname,
      port: target.port || (target.protocol === "https:" ? 443 : 80),
      path: `${target.pathname}${target.search}`,
      method: req.method,
      headers: buildUpstreamHeaders(req, target.host),
    },
    (proxyRes) => {
      const status = proxyRes.statusCode ?? 502;

      // Only buffer small 404 bodies to detect Railway "Application not found".
      if (status === 404) {
        const chunks = [];
        proxyRes.on("data", (chunk) => chunks.push(chunk));
        proxyRes.on("end", () => {
          const body = Buffer.concat(chunks);
          try {
            const parsed = JSON.parse(body.toString("utf8"));
            if (parsed?.message === "Application not found") {
              sendJson(res, 502, {
                success: false,
                error: {
                  code: "backend_not_found",
                  message:
                    `Backend service not found at ${BACKEND_URL}. ` +
                    "Redeploy the backend on Railway, copy its new public URL, " +
                    "and set BACKEND_URL on the frontend service.",
                },
              });
              return;
            }
          } catch {
            // not JSON — pass through below
          }
          const headers = filterHeaders(proxyRes.headers);
          res.writeHead(status, headers);
          res.end(body);
        });
        return;
      }

      // Stream all other responses unchanged (preserves gzip if backend sends it).
      const headers = filterHeaders(proxyRes.headers);
      res.writeHead(status, headers);
      proxyRes.pipe(res, { end: true });
    }
  );

  proxyReq.on("error", (err) => {
    console.error("[proxy]", req.method, req.url, "→", BACKEND_URL, err.message);
    if (!res.headersSent) {
      sendJson(res, 502, {
        success: false,
        error: {
          code: "backend_unreachable",
          message:
            `Could not reach the API at ${BACKEND_URL}. ` +
            "Redeploy the backend service and set BACKEND_URL on the frontend service.",
        },
      });
    }
  });

  req.pipe(proxyReq, { end: true });
}

function serveIndex(res) {
  const indexPath = join(DIST, "index.html");
  if (!existsSync(indexPath)) {
    res.writeHead(404);
    res.end("Not found");
    return;
  }
  const html = readFileSync(indexPath, "utf8").replace(
    "<head>",
    `<head><script>window.__REPOAUDIT_API_BASE_URL__="/api/v1";</script>`
  );
  res.writeHead(200, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-cache, no-store, must-revalidate",
  });
  res.end(html);
}

function serveStatic(req, res) {
  let pathname = decodeURIComponent(new URL(req.url, "http://local").pathname);
  if (pathname.endsWith("/")) pathname += "index.html";

  const filePath = join(DIST, pathname);
  const safeRoot = join(DIST, ".");
  if (!filePath.startsWith(safeRoot)) {
    res.writeHead(403);
    res.end("Forbidden");
    return;
  }

  if (existsSync(filePath) && statSync(filePath).isFile()) {
    if (extname(filePath) === ".html") {
      serveIndex(res);
      return;
    }
    const ext = extname(filePath);
    res.writeHead(200, {
      "Content-Type": MIME[ext] || "application/octet-stream",
      ...(ext.startsWith(".")
        ? { "Cache-Control": "public, max-age=31536000, immutable" }
        : {}),
    });
    createReadStream(filePath).pipe(res);
    return;
  }

  serveIndex(res);
}

const server = createServer((req, res) => {
  if (req.url?.startsWith("/api")) {
    proxyToBackend(req, res);
    return;
  }
  serveStatic(req, res);
});

server.listen(PORT, "0.0.0.0", () => {
  console.log(`RepoAudit frontend listening on :${PORT}`);
  console.log(`Proxying /api/* → ${BACKEND_URL}`);
});
