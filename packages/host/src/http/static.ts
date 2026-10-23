import { createReadStream } from "node:fs";
import { stat } from "node:fs/promises";
import type { ServerResponse } from "node:http";
import path from "node:path";

const mimeTypes: Record<string, string> = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp"
};

export async function serveWebUi(repoRoot: string, pathname: string, response: ServerResponse): Promise<boolean> {
  if (pathname === "/") {
    response.writeHead(302, { Location: "/ui/" });
    response.end();
    return true;
  }
  if (!pathname.startsWith("/ui/")) return false;
  const dist = path.join(repoRoot, "apps/web/dist");
  const relative = pathname === "/ui/" ? "index.html" : decodeURIComponent(pathname.slice(4));
  const file = safeJoin(dist, relative);
  if (!file) return false;
  try {
    const info = await stat(file);
    if (!info.isFile()) return false;
    response.writeHead(200, { "Content-Type": mimeTypes[path.extname(file)] || "application/octet-stream" });
    createReadStream(file).pipe(response);
    return true;
  } catch {
    return false;
  }
}

function safeJoin(root: string, relative: string): string | undefined {
  const resolved = path.resolve(root, relative);
  return resolved === root || resolved.startsWith(`${path.resolve(root)}${path.sep}`) ? resolved : undefined;
}
