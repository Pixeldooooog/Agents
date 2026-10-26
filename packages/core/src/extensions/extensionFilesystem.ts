import { constants } from "node:fs";
import { lstat, open, readdir, realpath } from "node:fs/promises";
import path from "node:path";

export const MAX_MANIFEST_BYTES = 256 * 1024;

/** Resolve existing ancestry too, so a missing child cannot escape via a symlinked parent. */
export async function confinedExtensionPath(root: string, candidate: string): Promise<string> {
  const canonicalRoot = await realpath(root);
  const resolved = path.resolve(candidate);
  let existing = resolved;
  const suffix: string[] = [];
  let canonical: string;
  while (true) {
    try { canonical = await realpath(existing); break; }
    catch (error) {
      if (!(error instanceof Error && "code" in error && error.code === "ENOENT") || path.dirname(existing) === existing) throw error;
      suffix.unshift(path.basename(existing));
      existing = path.dirname(existing);
    }
  }
  const target = path.join(canonical, ...suffix);
  const relative = path.relative(canonicalRoot, target);
  if (relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) throw new Error("extension path escapes its root");
  return target;
}

export async function readExtensionManifest(filename: string): Promise<string> {
  const file = await open(filename, constants.O_RDONLY | constants.O_NONBLOCK);
  try {
    const info = await file.stat();
    if (!info.isFile() || info.size > MAX_MANIFEST_BYTES) throw new Error("extension manifest must be a regular file within 256 KiB");
    const buffer = Buffer.alloc(MAX_MANIFEST_BYTES + 1);
    let size = 0;
    while (size < buffer.length) {
      const chunk = await file.read(buffer, size, buffer.length - size, null);
      if (!chunk.bytesRead) break;
      size += chunk.bytesRead;
    }
    if (size > MAX_MANIFEST_BYTES) throw new Error("extension manifest exceeds 256 KiB");
    return new TextDecoder("utf-8", { fatal: true }).decode(buffer.subarray(0, size));
  } finally { await file.close(); }
}

/** Local packages may contain data and scripts, but installation never follows links or runs scripts. */
export async function validateExtensionPackage(root: string): Promise<void> {
  const queue = [root];
  let bytes = 0;
  let count = 0;
  for (let cursor = 0; cursor < queue.length; cursor++) {
    const filename = queue[cursor];
    const info = await lstat(filename);
    if (++count > 2048 || info.isSymbolicLink() || (!info.isFile() && !info.isDirectory())) throw new Error("extension package contains links, special files, or too many entries");
    if (info.isDirectory()) {
      const entries = await readdir(filename);
      if (queue.length + entries.length > 2048) throw new Error("extension package exceeds entry limit");
      queue.push(...entries.map(name => path.join(filename, name)));
    } else {
      bytes += info.size;
      if (bytes > 64 * 1024 * 1024) throw new Error("extension package exceeds 64 MiB");
    }
  }
}
