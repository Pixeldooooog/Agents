import { describe, expect, test } from "bun:test";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { executeBuiltinTool } from "../src/index.js";

describe("web and browser tools", () => {
  test("fetches, maps, searches URL queries, and downloads through TypeScript", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "kevin-web-tools-"));
    const server = Bun.serve({
      port: 0,
      fetch(request) {
        const url = new URL(request.url);
        if (url.pathname === "/asset.bin") return new Response("download-bytes", { headers: { "content-type": "application/octet-stream" } });
        if (url.pathname === "/next") return new Response("<title>Next Page</title><main>next content</main>", { headers: { "content-type": "text/html" } });
        return new Response([
          "<!doctype html>",
          "<title>Fixture Page</title>",
          "<main>alpha content for extraction</main>",
          "<a href=\"/next\">Next</a>"
        ].join(""), { headers: { "content-type": "text/html; charset=utf-8" } });
      }
    });
    try {
      const baseUrl = `http://127.0.0.1:${server.port}`;

      const extracted = await executeBuiltinTool(root, "web.extract", { urls: [`${baseUrl}/`] });
      const extractPayload = JSON.parse(extracted.result.content);
      expect(extractPayload.sources[0].title).toBe("Fixture Page");
      expect(extractPayload.sources[0].content).toContain("alpha content");

      const mapped = await executeBuiltinTool(root, "web.map", { url: `${baseUrl}/`, limit: 5 });
      expect(JSON.parse(mapped.result.content).urls).toContain(`${baseUrl}/next`);

      const searched = await executeBuiltinTool(root, "web.search", { query: `${baseUrl}/` });
      expect(JSON.parse(searched.result.content).sources[0].url).toBe(`${baseUrl}/`);

      const opened = await executeBuiltinTool(root, "browser.open", { url: `${baseUrl}/`, output_path: "downloads/page.html" });
      expect(JSON.parse(opened.result.content).text_preview).toContain("alpha content");
      expect(await readFile(path.join(root, "downloads/page.html"), "utf8")).toContain("Fixture Page");

      const downloaded = await executeBuiltinTool(root, "browser.download", { url: `${baseUrl}/asset.bin`, path: "downloads/asset.bin" });
      expect(JSON.parse(downloaded.result.content).bytes).toBe("download-bytes".length);
      expect(await readFile(path.join(root, "downloads/asset.bin"), "utf8")).toBe("download-bytes");
    } finally {
      server.stop(true);
      await rm(root, { recursive: true, force: true });
    }
  });
});
