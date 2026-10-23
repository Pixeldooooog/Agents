import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import type { FileReadState } from "../tools/toolContracts.js";
import { relativeWorkspacePath, resolveWorkspacePath } from "../tools/toolInputs.js";

export type SdkReadStateSeedOptions = {
  sessionId?: string;
};

const maxSdkSeedReadBytes = 200_000;
const binarySampleBytes = 8_192;
const utf16LeBom = Buffer.from([0xff, 0xfe]);
const utf16BeBom = Buffer.from([0xfe, 0xff]);
const utf8Bom = Buffer.from([0xef, 0xbb, 0xbf]);
const textControlBytes = new Set([9, 10, 12, 13]);
const binaryFileExtensions = new Set([
  ".7z",
  ".avi",
  ".bin",
  ".bmp",
  ".class",
  ".dmg",
  ".doc",
  ".docx",
  ".exe",
  ".gif",
  ".gz",
  ".ico",
  ".jar",
  ".jpeg",
  ".jpg",
  ".mov",
  ".mp3",
  ".mp4",
  ".o",
  ".pdf",
  ".png",
  ".pyc",
  ".so",
  ".tar",
  ".wasm",
  ".webp",
  ".xls",
  ".xlsx",
  ".zip"
]);

export class SdkFileReadStates {
  private readonly sessionStates = new Map<string, FileReadState>();
  private readonly pendingSeeds = new Map<string, FileReadState>();

  async seedReadState(repoRoot: string, requestedPath: string, observedMtime: number, options: SdkReadStateSeedOptions = {}): Promise<Record<string, unknown>> {
    try {
      const absolutePath = resolveWorkspacePath(repoRoot, requestedPath);
      const fileInfo = await stat(absolutePath);
      if (!fileInfo.isFile()) return { seeded: false, path: requestedPath, mtime: observedMtime };
      if (isSeedObservationStale(fileInfo.mtimeMs, observedMtime)) {
        return { seeded: false, path: relativeWorkspacePath(repoRoot, absolutePath), mtime: fileInfo.mtimeMs };
      }
      const seedText = await readSeedText(absolutePath);
      const relativePath = relativeWorkspacePath(repoRoot, absolutePath);
      this.pendingSeedsForSession(options.sessionId || "")[relativePath] = {
        path: relativePath,
        content: seedText.content,
        timestamp: fileInfo.mtimeMs,
        encoding: seedText.encoding,
        fullRead: true,
        source: "read",
        offset: 1,
        limit: null,
        isPartialView: false
      };
      return { seeded: true, path: relativePath, mtime: fileInfo.mtimeMs };
    } catch {
      return { seeded: false, path: requestedPath, mtime: observedMtime };
    }
  }

  forSession(sessionId: string): FileReadState {
    const resolvedSessionId = sessionId || "";
    const existing = this.sessionStates.get(resolvedSessionId);
    const state = existing || {};
    if (!existing) this.sessionStates.set(resolvedSessionId, state);
    this.applyPendingSeeds("", state);
    this.applyPendingSeeds(resolvedSessionId, state);
    return state;
  }

  private pendingSeedsForSession(sessionId: string): FileReadState {
    const resolvedSessionId = sessionId || "";
    const existing = this.pendingSeeds.get(resolvedSessionId);
    if (existing) return existing;
    const seeds: FileReadState = {};
    this.pendingSeeds.set(resolvedSessionId, seeds);
    return seeds;
  }

  private applyPendingSeeds(sessionId: string, state: FileReadState): void {
    const seeds = this.pendingSeeds.get(sessionId);
    if (!seeds) return;
    for (const [pathValue, seed] of Object.entries(seeds)) {
      state[pathValue] ||= { ...seed };
    }
    this.pendingSeeds.delete(sessionId);
  }
}

function isSeedObservationStale(diskMtimeMs: number, observedMtime: number): boolean {
  const observed = Number(observedMtime || 0);
  if (!Number.isFinite(observed) || observed <= 0) return true;
  if (observed > 10_000_000_000) return Math.floor(diskMtimeMs) > Math.floor(observed);
  return diskMtimeMs / 1000 > observed;
}

async function readSeedText(absolutePath: string): Promise<{ content: string; encoding: string }> {
  const content = await readFile(absolutePath);
  if (content.byteLength > maxSdkSeedReadBytes) throw new Error(`file is too large to seed read state: ${absolutePath}`);
  const encoding = detectSeedTextEncoding(absolutePath, content.subarray(0, binarySampleBytes));
  return { content: decodeSeedText(content, encoding), encoding: publicEncodingName(encoding) };
}

function detectSeedTextEncoding(filename: string, sample: Buffer): "utf-8" | "utf-8-sig" | "utf-16le" | "utf-16be" {
  if (sample.subarray(0, 2).equals(utf16LeBom)) return "utf-16le";
  if (sample.subarray(0, 2).equals(utf16BeBom)) return "utf-16be";
  if (sample.subarray(0, 3).equals(utf8Bom)) return "utf-8-sig";
  if (!binaryFileExtensions.has(path.extname(filename).toLowerCase())) {
    const utf16Encoding = detectUtf16WithoutBom(sample);
    if (utf16Encoding) return utf16Encoding;
  }
  if (looksLikeBinarySeedSample(filename, sample)) throw new Error(`file is not text: ${filename}`);
  return "utf-8";
}

function detectUtf16WithoutBom(sample: Buffer): "utf-16le" | "utf-16be" | undefined {
  const pairCount = Math.floor(sample.byteLength / 2);
  if (pairCount < 2) return undefined;
  let evenNuls = 0;
  let oddNuls = 0;
  for (let index = 0; index < pairCount * 2; index += 2) {
    if (sample[index] === 0) evenNuls += 1;
    if (sample[index + 1] === 0) oddNuls += 1;
  }
  const evenRatio = evenNuls / pairCount;
  const oddRatio = oddNuls / pairCount;
  if (oddRatio >= 0.25 && evenRatio <= 0.05) return "utf-16le";
  if (evenRatio >= 0.25 && oddRatio <= 0.05) return "utf-16be";
  return undefined;
}

function looksLikeBinarySeedSample(filename: string, sample: Buffer): boolean {
  if (binaryFileExtensions.has(path.extname(filename).toLowerCase())) return true;
  if (!sample.byteLength) return false;
  if (sample.includes(0)) return true;
  let controlBytes = 0;
  for (const byte of sample) {
    if (byte < 32 && !textControlBytes.has(byte)) controlBytes += 1;
  }
  return controlBytes / sample.byteLength > 0.1;
}

function decodeSeedText(content: Buffer, encoding: "utf-8" | "utf-8-sig" | "utf-16le" | "utf-16be"): string {
  if (encoding === "utf-16be") return stripLeadingBom(decodeUtf16Be(content));
  if (encoding === "utf-16le") return stripLeadingBom(content.toString("utf16le"));
  return stripLeadingBom(content.toString("utf8"));
}

function decodeUtf16Be(content: Buffer): string {
  const normalized = Buffer.alloc(content.byteLength);
  for (let index = 0; index < content.byteLength; index += 2) {
    normalized[index] = content[index + 1] ?? 0;
    normalized[index + 1] = content[index] ?? 0;
  }
  return normalized.toString("utf16le");
}

function publicEncodingName(encoding: "utf-8" | "utf-8-sig" | "utf-16le" | "utf-16be"): string {
  return encoding;
}

function stripLeadingBom(value: string): string {
  return value.startsWith("\ufeff") ? value.slice(1) : value;
}
