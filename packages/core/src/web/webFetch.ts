import { createHash } from "node:crypto";
import path from "node:path";
import { domainFromUrl, parseHttpUrl } from "./webPolicy.js";
import type { FetchedWebResource, WebSource } from "./webTypes.js";

const defaultUserAgent = "Kevin/0.1";

export async function fetchWebResource(url: string, maxBytes: number, timeoutSeconds: number): Promise<FetchedWebResource> {
  parseHttpUrl(url);
  const response = await fetch(url, {
    headers: { "User-Agent": defaultUserAgent },
    signal: AbortSignal.timeout(Math.max(1, timeoutSeconds) * 1000)
  });
  const body = await readResponseBody(response, Math.max(1, maxBytes));
  const contentType = response.headers.get("content-type") || "";
  return {
    url,
    finalUrl: response.url || url,
    status: response.status,
    statusText: response.statusText,
    contentType,
    bytes: body.buffer.byteLength,
    truncated: body.truncated,
    body: body.buffer,
    text: decodeBody(body.buffer, contentType)
  };
}

export function sourceFromFetchedResource(
  resource: FetchedWebResource,
  index: number,
  includeRawContent: boolean,
  contentLimit = 100000
): WebSource {
  const title = extractHtmlTitle(resource.text) || resource.finalUrl;
  const text = htmlToText(resource.text).slice(0, contentLimit);
  return {
    source_id: `S${index}`,
    title,
    url: resource.finalUrl,
    domain: domainFromUrl(resource.finalUrl),
    content: text,
    score: 1,
    raw_content: includeRawContent ? resource.text.slice(0, contentLimit) : undefined
  };
}

export function extractLinks(html: string, baseUrl: string): string[] {
  const links: string[] = [];
  const seen = new Set<string>();
  const matcher = /\bhref\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/gi;
  for (const match of html.matchAll(matcher)) {
    const href = (match[1] || match[2] || match[3] || "").trim();
    if (!href || href.startsWith("#") || href.startsWith("mailto:") || href.startsWith("tel:")) continue;
    try {
      const url = new URL(href, baseUrl);
      if (!["http:", "https:"].includes(url.protocol)) continue;
      url.hash = "";
      const normalized = url.toString();
      if (seen.has(normalized)) continue;
      seen.add(normalized);
      links.push(normalized);
    } catch {
      continue;
    }
  }
  return links;
}

export function extractHtmlTitle(html: string): string {
  const match = /<title\b[^>]*>([\s\S]*?)<\/title>/i.exec(html);
  return match ? decodeHtmlEntities(stripTags(match[1])).trim() : "";
}

export function htmlToText(html: string): string {
  const withoutBlocks = html
    .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
    .replace(/<noscript\b[\s\S]*?<\/noscript>/gi, " ");
  return decodeHtmlEntities(stripTags(withoutBlocks)).replace(/\s+/g, " ").trim();
}

export function defaultDownloadPath(url: string, fallbackName: string): string {
  const parsed = parseHttpUrl(url);
  const basename = path.basename(parsed.pathname).replace(/[^\w.-]+/g, "_");
  const filename = basename && basename !== "." && basename !== "/" ? basename : fallbackName;
  const digest = createHash("sha256").update(url).digest("hex").slice(0, 8);
  const extension = path.extname(filename);
  const stem = extension ? filename.slice(0, -extension.length) : filename;
  return path.join(".kevin", "downloads", `${stem}-${digest}${extension || ".bin"}`);
}

async function readResponseBody(response: Response, maxBytes: number): Promise<{ buffer: Buffer; truncated: boolean }> {
  if (!response.body) {
    const buffer = Buffer.from(await response.arrayBuffer()).subarray(0, maxBytes);
    return { buffer, truncated: buffer.byteLength >= maxBytes };
  }
  const reader = response.body.getReader();
  const chunks: Buffer[] = [];
  let bytes = 0;
  let truncated = false;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = Buffer.from(value);
    bytes += chunk.byteLength;
    chunks.push(chunk);
    if (bytes > maxBytes) {
      truncated = true;
      await reader.cancel();
      break;
    }
  }
  return { buffer: Buffer.concat(chunks).subarray(0, maxBytes), truncated };
}

function decodeBody(buffer: Buffer, contentType: string): string {
  if (!contentType || /charset\s*=\s*utf-?8/i.test(contentType) || /^text\//i.test(contentType) || /json|xml|html/i.test(contentType)) {
    return buffer.toString("utf8");
  }
  return buffer.toString("utf8");
}

function stripTags(html: string): string {
  return html.replace(/<[^>]+>/g, " ");
}

function decodeHtmlEntities(value: string): string {
  return value
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&#(\d+);/g, (_match, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_match, code) => String.fromCodePoint(Number.parseInt(code, 16)));
}
