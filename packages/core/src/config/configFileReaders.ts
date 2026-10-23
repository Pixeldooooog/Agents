import { readFile } from "node:fs/promises";

export type ConfigTree = Record<string, Record<string, unknown>>;

export async function readEnvFile(filename: string): Promise<Record<string, string>> {
  try {
    const text = await readFile(filename, "utf8");
    return Object.fromEntries(text.split(/\r?\n/).flatMap((line) => {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith("#")) return [];
      const index = trimmed.indexOf("=");
      if (index < 0) return [];
      return [[trimmed.slice(0, index).trim(), unquote(trimmed.slice(index + 1).trim())]];
    }));
  } catch {
    return {};
  }
}

export async function readTomlFile(filename: string): Promise<ConfigTree> {
  try {
    return parseSimpleToml(await readFile(filename, "utf8"));
  } catch {
    return {};
  }
}

export function mergeConfig(...trees: ConfigTree[]): ConfigTree {
  const merged: ConfigTree = {};
  for (const tree of trees) {
    for (const [name, values] of Object.entries(tree)) {
      merged[name] = { ...(merged[name] || {}), ...values };
    }
  }
  return merged;
}

function parseSimpleToml(text: string): ConfigTree {
  const result: ConfigTree = {};
  let current = "";
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.replace(/#.*$/, "").trim();
    if (!line) continue;
    const sectionMatch = /^\[(.+)]$/.exec(line);
    if (sectionMatch) {
      current = sectionMatch[1];
      result[current] ||= {};
      continue;
    }
    const index = line.indexOf("=");
    if (index < 0 || !current) continue;
    result[current][line.slice(0, index).trim()] = parseTomlValue(line.slice(index + 1).trim());
  }
  return result;
}

function parseTomlValue(value: string): unknown {
  if (value.startsWith("[") && value.endsWith("]")) {
    const inner = value.slice(1, -1).trim();
    if (!inner) return [];
    return inner.split(",").map((item) => parseTomlValue(item.trim()));
  }
  if ((value.startsWith("\"") && value.endsWith("\"")) || (value.startsWith("'") && value.endsWith("'"))) {
    return unquote(value);
  }
  if (value === "true" || value === "false") return value === "true";
  const number = Number(value);
  return Number.isFinite(number) ? number : value;
}

function unquote(value: string): string {
  return value.replace(/^["']|["']$/g, "");
}
