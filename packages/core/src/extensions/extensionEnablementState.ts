import type { AgentSpec } from "../types/agentTypes.js";

export type ExtensionMetadataKey = "enabled_skills" | "enabled_plugins";

export type ExtensionEnablementEffect = {
  added_tools: string[];
  removed_tools: string[];
  restored_tools: string[];
};

export type ExtensionEnablementOptions = {
  defaultTools?: string[];
};

export type ToolListMetadataSuffix = ".added_tools" | ".allowed_tools" | ".disallowed_tools" | ".tools";

export function enabledExtensions(spec: AgentSpec | undefined, metadataKey: ExtensionMetadataKey): Set<string> {
  if (!spec) return new Set();
  return new Set(String(spec.metadata[metadataKey] || "").split(",").map((name) => name.trim()).filter(Boolean));
}

export function emptyEffect(): ExtensionEnablementEffect {
  return { added_tools: [], removed_tools: [], restored_tools: [] };
}

export function toolDiff(previousTools: string[], nextTools: string[]): { added: string[]; removed: string[] } {
  const previous = new Set(previousTools);
  const next = new Set(nextTools);
  return {
    added: nextTools.filter((tool) => !previous.has(tool)),
    removed: previousTools.filter((tool) => !next.has(tool))
  };
}

export function setMetadataList(spec: AgentSpec, key: string, values: string[], keepEmpty = false): void {
  if (values.length) spec.metadata[key] = values.join(",");
  else if (keepEmpty) spec.metadata[key] = "";
  else delete spec.metadata[key];
}

export function metadataList(spec: AgentSpec, key: string): string[] {
  return String(spec.metadata[key] || "").split(",").map((tool) => tool.trim()).filter(Boolean);
}

export function metadataTools(spec: AgentSpec, metadataKey: ExtensionMetadataKey, suffix: ToolListMetadataSuffix): Set<string> {
  const tools = new Set<string>();
  const prefix = `${metadataKey}.`;
  for (const [key, value] of Object.entries(spec.metadata)) {
    if (!key.startsWith(prefix)) continue;
    if (!key.endsWith(suffix)) continue;
    for (const tool of String(value || "").split(",")) {
      const name = tool.trim();
      if (name) tools.add(name);
    }
  }
  return tools;
}

export function addedToolsKey(metadataKey: ExtensionMetadataKey, extensionName: string): string {
  return `${metadataKey}.${extensionName}.added_tools`;
}

export function pluginToolsKey(metadataKey: ExtensionMetadataKey, extensionName: string): string {
  return `${metadataKey}.${extensionName}.tools`;
}

export function baseToolsKey(metadataKey: ExtensionMetadataKey): string {
  return `${metadataKey}.base_tools`;
}

export function allowedToolsKey(metadataKey: ExtensionMetadataKey, extensionName: string): string {
  return `${metadataKey}.${extensionName}.allowed_tools`;
}

export function disallowedToolsKey(metadataKey: ExtensionMetadataKey, extensionName: string): string {
  return `${metadataKey}.${extensionName}.disallowed_tools`;
}

export function joinEnabled(enabled: Set<string>): string {
  return [...enabled].sort().join(",");
}

export function currentEnabledTools(spec: AgentSpec, options: ExtensionEnablementOptions): string[] {
  return spec.enabled_tools.length ? spec.enabled_tools : uniqueStrings(options.defaultTools || []);
}

export function hasMetadata(spec: AgentSpec, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(spec.metadata, key);
}

export function uniqueStrings(values: string[]): string[] {
  return [...new Set(values.filter(Boolean))];
}
