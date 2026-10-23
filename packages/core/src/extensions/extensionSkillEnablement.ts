import type { AgentSpec } from "../types/agentTypes.js";
import {
  allowedToolsKey,
  baseToolsKey,
  currentEnabledTools,
  disallowedToolsKey,
  emptyEffect,
  enabledExtensions,
  hasMetadata,
  joinEnabled,
  metadataList,
  metadataTools,
  setMetadataList,
  toolDiff,
  uniqueStrings,
  type ExtensionEnablementEffect,
  type ExtensionEnablementOptions,
  type ExtensionMetadataKey
} from "./extensionEnablementState.js";
import type { ExtensionManifest } from "./extensionManifestTypes.js";

export function enableSkillInSpec(
  spec: AgentSpec,
  metadataKey: ExtensionMetadataKey,
  manifest: ExtensionManifest,
  options: ExtensionEnablementOptions
): ExtensionEnablementEffect {
  const enabled = enabledExtensions(spec, metadataKey);
  if (enabled.has(manifest.name)) return emptyEffect();
  ensureSkillBaseTools(spec, metadataKey, options);
  const previousTools = currentEnabledTools(spec, options);

  spec.metadata[metadataKey] = joinEnabled(new Set([...enabled, manifest.name]));
  setMetadataList(spec, allowedToolsKey(metadataKey, manifest.name), extensionToolsForEnable(metadataKey, manifest));
  setMetadataList(spec, disallowedToolsKey(metadataKey, manifest.name), extensionDisallowedTools(metadataKey, manifest));
  spec.enabled_tools = effectiveSkillTools(spec, metadataKey, options);

  const effect = toolDiff(previousTools, spec.enabled_tools);
  return { added_tools: effect.added, removed_tools: effect.removed, restored_tools: [] };
}

export function disableSkillInSpec(
  spec: AgentSpec,
  metadataKey: ExtensionMetadataKey,
  manifest: ExtensionManifest,
  options: ExtensionEnablementOptions
): ExtensionEnablementEffect {
  ensureSkillBaseTools(spec, metadataKey, options);
  const previousTools = currentEnabledTools(spec, options);
  delete spec.metadata[allowedToolsKey(metadataKey, manifest.name)];
  delete spec.metadata[disallowedToolsKey(metadataKey, manifest.name)];

  const enabled = enabledExtensions(spec, metadataKey);
  enabled.delete(manifest.name);
  spec.metadata[metadataKey] = joinEnabled(enabled);
  spec.enabled_tools = effectiveSkillTools(spec, metadataKey, options);
  if (!enabled.size) delete spec.metadata[baseToolsKey(metadataKey)];

  const effect = toolDiff(previousTools, spec.enabled_tools);
  return { added_tools: [], removed_tools: effect.removed, restored_tools: effect.added };
}

export function ensureSkillBaseTools(spec: AgentSpec, metadataKey: ExtensionMetadataKey, options: ExtensionEnablementOptions): void {
  const key = baseToolsKey(metadataKey);
  if (hasMetadata(spec, key)) return;
  const pluginOwnedTools = metadataTools(spec, "enabled_plugins", ".added_tools");
  const baseTools = currentEnabledTools(spec, options).filter((tool) => !pluginOwnedTools.has(tool));
  setMetadataList(spec, key, baseTools, true);
}

export function effectiveSkillTools(spec: AgentSpec, metadataKey: ExtensionMetadataKey, options: ExtensionEnablementOptions): string[] {
  ensureSkillBaseTools(spec, metadataKey, options);
  const baseTools = metadataList(spec, baseToolsKey(metadataKey));
  const pluginTools = metadataTools(spec, "enabled_plugins", ".tools");
  const allowedTools = metadataTools(spec, metadataKey, ".allowed_tools");
  const disallowedTools = metadataTools(spec, metadataKey, ".disallowed_tools");
  return uniqueStrings([...baseTools, ...pluginTools, ...allowedTools]).filter((tool) => !disallowedTools.has(tool));
}

export function extensionToolsForEnable(metadataKey: ExtensionMetadataKey, manifest: ExtensionManifest): string[] {
  if (metadataKey !== "enabled_skills") return manifest.tools;
  const disallowed = new Set(manifest.disallowed_tools);
  return manifest.allowed_tools.filter((tool) => !disallowed.has(tool));
}

function extensionDisallowedTools(metadataKey: ExtensionMetadataKey, manifest: ExtensionManifest): string[] {
  return metadataKey === "enabled_skills" ? manifest.disallowed_tools : [];
}
