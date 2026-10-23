import path from "node:path";
import {
  booleanValue,
  isPortableManifestName,
  objectRecord,
  stringList
} from "./extensionManifestRecords.js";

export function parseSkillMarkdownManifest(content: string, manifestPath: string): Record<string, unknown> {
  const { frontmatter, body } = splitFrontmatter(content);
  const metadata = objectRecord(frontmatter.metadata);
  const declaredName = String(frontmatter.name || "").trim();
  if (!declaredName) throw new Error("skill frontmatter requires name");
  if (!isPortableManifestName(declaredName)) throw new Error("skill name must contain only letters, numbers, dots, underscores, or hyphens");
  const name = declaredName;
  metadata.format = "skill-md";

  const description = String(frontmatter.description || "").trim();
  const instructions = body.trim();
  if (!description) throw new Error("skill frontmatter requires description");
  if (!instructions) throw new Error("skill body is required");
  const promptFragments = stringList(frontmatter.prompt_fragments);
  return {
    ...frontmatter,
    name,
    version: String(frontmatter.version || "0.1.0"),
    description,
    when_to_use: String(frontmatter.when_to_use || description),
    tools: [],
    allowed_tools: stringList(frontmatter.allowed_tools),
    disallowed_tools: stringList(frontmatter.disallowed_tools),
    prompt_fragments: promptFragments.length ? promptFragments : [path.basename(manifestPath)],
    instructions: [instructions],
    paths: stringList(frontmatter.paths),
    context: String(frontmatter.context || ""),
    model: String(frontmatter.model || metadata.model || ""),
    effort: String(frontmatter.effort || metadata.effort || ""),
    agent: String(frontmatter.agent || metadata.agent || ""),
    user_invocable: booleanValue(frontmatter.user_invocable, true),
    disable_model_invocation: booleanValue(frontmatter.disable_model_invocation, false),
    metadata,
    format: "skill-md"
  };
}

function splitFrontmatter(content: string): { frontmatter: Record<string, unknown>; body: string } {
  const text = content.replace(/^\uFEFF/, "");
  const lines = text.split(/\r?\n/);
  if (lines[0]?.trim() !== "---") throw new Error("SKILL.md requires YAML frontmatter");
  const endIndex = lines.findIndex((line, index) => index > 0 && (line.trim() === "---" || line.trim() === "..."));
  if (endIndex < 0) throw new Error("SKILL.md frontmatter is not closed");
  return {
    frontmatter: parseYamlSubset(lines.slice(1, endIndex).join("\n")),
    body: lines.slice(endIndex + 1).join("\n")
  };
}

function parseYamlSubset(content: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  const lines = content.split(/\r?\n/);
  let currentKey = "";
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;

    const listMatch = trimmed.match(/^-\s+(.*)$/);
    if (listMatch && currentKey) {
      if (!Array.isArray(result[currentKey])) result[currentKey] = [];
      const existing = Array.isArray(result[currentKey]) ? result[currentKey] as unknown[] : [];
      existing.push(parseScalar(listMatch[1]));
      result[currentKey] = existing;
      continue;
    }

    const nestedMatch = line.match(/^\s{2,}([^:]+):\s*(.*)$/);
    if (nestedMatch && currentKey) {
      const parent = objectRecord(result[currentKey]);
      parent[normalizeKey(nestedMatch[1])] = parseScalar(nestedMatch[2]);
      result[currentKey] = parent;
      continue;
    }

    const keyMatch = line.match(/^([^:\s][^:]*):\s*(.*)$/);
    if (!keyMatch) continue;
    currentKey = normalizeKey(keyMatch[1]);
    const rawValue = keyMatch[2].trim();
    const blockStyle = rawValue.match(/^([|>])[-+]?$/);
    if (blockStyle) {
      const block = readBlockScalar(lines, index + 1, blockStyle[1] || "|");
      result[currentKey] = block.value;
      index = block.endIndex - 1;
      continue;
    }
    result[currentKey] = rawValue ? parseScalar(rawValue) : emptyYamlBlockValue(lines, index + 1);
  }
  return result;
}

function readBlockScalar(lines: string[], startIndex: number, style: string): { value: string; endIndex: number } {
  const blockLines: string[] = [];
  let endIndex = startIndex;
  for (; endIndex < lines.length; endIndex += 1) {
    const line = lines[endIndex];
    if (line.trim() && !/^\s/.test(line)) break;
    blockLines.push(line);
  }
  const content = stripSharedIndent(blockLines).join("\n").trimEnd();
  return {
    value: style === ">" ? foldBlockScalar(content) : content,
    endIndex
  };
}

function stripSharedIndent(lines: string[]): string[] {
  const indents = lines.filter((line) => line.trim()).map((line) => line.match(/^\s*/)?.[0].length || 0);
  const indent = indents.length ? Math.min(...indents) : 0;
  return lines.map((line) => line.slice(Math.min(indent, line.length)));
}

function foldBlockScalar(content: string): string {
  return content.split(/\n\s*\n/).map((paragraph) => paragraph.split(/\n/).map((line) => line.trim()).join(" ")).join("\n\n");
}

function emptyYamlBlockValue(lines: string[], startIndex: number): unknown[] | Record<string, unknown> {
  const next = lines.slice(startIndex).find((line) => {
    const trimmed = line.trim();
    return trimmed && !trimmed.startsWith("#");
  });
  return next?.trim().startsWith("- ") ? [] : {};
}

function parseScalar(value: string): unknown {
  const text = value.trim();
  if (!text) return "";
  if (text.startsWith("[") && text.endsWith("]")) return stringList(text.slice(1, -1));
  if (text === "true") return true;
  if (text === "false") return false;
  if ((text.startsWith("\"") && text.endsWith("\"")) || (text.startsWith("'") && text.endsWith("'"))) return text.slice(1, -1);
  return text;
}

function normalizeKey(value: string): string {
  return value.trim().replace(/-/g, "_");
}
