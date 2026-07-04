import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const PORT = Number(process.env.PORT || 3000);
const API_BASE = process.env.ORBITOPS_API_BASE || "http://localhost:4000";

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".geojson": "application/geo+json; charset=utf-8",
};

function send(res, status, body, contentType = "text/plain; charset=utf-8") {
  res.writeHead(status, {
    "content-type": contentType,
    "cache-control": "no-store",
  });
  res.end(body);
}

function resolveStaticPath(urlPath) {
  const pathname = new URL(urlPath, "http://localhost").pathname;
  const requested = pathname === "/" ? "/index.html" : pathname;
  const normalized = normalize(requested).replace(/^(\.\.[/\\])+/, "");
  return join(__dirname, normalized);
}

const server = createServer(async (req, res) => {
  if (req.method !== "GET") {
    send(res, 405, "Method not allowed");
    return;
  }

  try {
    const filePath = resolveStaticPath(req.url || "/");
    const ext = extname(filePath);
    let body = await readFile(filePath, ext === ".html" ? "utf8" : undefined);

    if (ext === ".html" && typeof body === "string") {
      body = body.replace(
        "</head>",
        `<script>window.ORBITOPS_API_BASE=${JSON.stringify(API_BASE)};</script></head>`,
      );
    }

    send(res, 200, body, MIME_TYPES[ext] || "application/octet-stream");
  } catch {
    send(res, 404, "Not found");
  }
});

server.listen(PORT, () => {
  console.log(`OrbitOps frontend listening on http://localhost:${PORT}`);
  console.log(`Using backend API: ${API_BASE}`);
});
