import { createHash } from "node:crypto";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import type { JsonObject } from "../types/jsonTypes.js";
import { defineTool, type RegisteredTool, type ToolContext } from "../tools/toolContracts.js";
import { numberArg, relativeWorkspacePath, resolveWorkspacePath, stringArg } from "../tools/toolInputs.js";
import { defaultDownloadPath, fetchWebResource } from "./webFetch.js";

const browserOpenSchema = {
  type: "object",
  properties: {
    url: { type: "string", description: "HTTP or HTTPS URL to fetch inside the sandbox." },
    output_path: { type: "string", description: "Workspace-relative file path for the fetched page." },
    max_bytes: { type: "integer", minimum: 1, maximum: 2000000 }
  },
  required: ["url"]
};

const browserDownloadSchema = {
  type: "object",
  properties: {
    url: { type: "string", description: "HTTP or HTTPS URL to download inside the sandbox." },
    path: { type: "string", description: "Workspace-relative output file path." },
    max_bytes: { type: "integer", minimum: 1, maximum: 20000000 }
  },
  required: ["url"]
};

export const browserToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "browser.open",
    description: "Fetch an HTTP page into the workspace and return a text preview.",
    risk: "medium",
    parameters: browserOpenSchema,
    requires: [],
    uses: ["settings"],
    handler: browserOpen
  }),
  defineTool({
    name: "browser.download",
    description: "Download an HTTP resource into the workspace.",
    risk: "medium",
    parameters: browserDownloadSchema,
    requires: [],
    uses: ["settings"],
    handler: browserDownload
  })
];

async function browserOpen(context: ToolContext<never, "settings">, args: JsonObject) {
  const url = stringArg(args.url);
  const maxBytes = Math.max(1, Math.min(2000000, numberArg(args.max_bytes, 200000)));
  const outputPath = stringArg(args.output_path) || defaultBrowserOpenPath(url);
  const resource = await fetchWebResource(url, maxBytes, context.settings?.webSearch.timeout || 30);
  const pathInfo = await writeWorkspaceBytes(context.repoRoot, outputPath, resource.body);
  return {
    url,
    path: pathInfo.relativePath,
    status: resource.status,
    content_type: resource.contentType,
    bytes: resource.bytes,
    truncated: resource.truncated,
    text_preview: resource.text.slice(0, 4000),
    sha256: sha256(resource.body)
  };
}

async function browserDownload(context: ToolContext<never, "settings">, args: JsonObject) {
  const url = stringArg(args.url);
  const maxBytes = Math.max(1, Math.min(20000000, numberArg(args.max_bytes, 20000000)));
  const outputPath = stringArg(args.path) || defaultDownloadPath(url, "download.bin");
  const resource = await fetchWebResource(url, maxBytes, context.settings?.webSearch.timeout || 30);
  const pathInfo = await writeWorkspaceBytes(context.repoRoot, outputPath, resource.body);
  return {
    url,
    path: pathInfo.relativePath,
    status: resource.status,
    content_type: resource.contentType,
    bytes: resource.bytes,
    truncated: resource.truncated,
    sha256: sha256(resource.body)
  };
}

async function writeWorkspaceBytes(repoRoot: string, requestedPath: string, body: Buffer): Promise<{ absolutePath: string; relativePath: string }> {
  const absolutePath = resolveWorkspacePath(repoRoot, requestedPath);
  await mkdir(path.dirname(absolutePath), { recursive: true });
  await writeFile(absolutePath, body);
  return { absolutePath, relativePath: relativeWorkspacePath(repoRoot, absolutePath) };
}

function defaultBrowserOpenPath(url: string): string {
  const digest = createHash("sha256").update(url).digest("hex").slice(0, 8);
  return path.join(".kevin", "downloads", `browser-open-${digest}.html`);
}

function sha256(buffer: Buffer): string {
  return createHash("sha256").update(buffer).digest("hex");
}
