import type { AgentSpec } from "../types/agentTypes.js";

export type ExtensionMetadataKey = "enabled_skills" | "enabled_plugins";

export type ExtensionEnablementEffect = {
  added_tools: string[];
  removed_tools: string[];
  restored_tools: string[];
};

export function enabledExtensions(spec: AgentSpec | undefined, metadataKey: ExtensionMetadataKey): Set<string> {
  if (!spec) return new Set();
  return new Set(String(spec.metadata[metadataKey] || "").split(",").map((name) => name.trim()).filter(Boolean));
}

export function emptyEffect(): ExtensionEnablementEffect {
  return { added_tools: [], removed_tools: [], restored_tools: [] };
}

export function joinEnabled(enabled: Set<string>): string {
  return [...enabled].sort().join(",");
}
