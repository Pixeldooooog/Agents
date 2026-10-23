import type { AgentSpec } from "../types/agentTypes.js";
import {
  addedToolsKey,
  baseToolsKey,
  currentEnabledTools,
  emptyEffect,
  enabledExtensions,
  joinEnabled,
  metadataList,
  metadataTools,
  pluginToolsKey,
  setMetadataList,
  toolDiff,
  uniqueStrings,
  type ExtensionEnablementEffect,
  type ExtensionEnablementOptions,
  type ExtensionMetadataKey
} from "./extensionEnablementState.js";
import {
  disableSkillInSpec,
  effectiveSkillTools,
  enableSkillInSpec,
  ensureSkillBaseTools,
  extensionToolsForEnable
} from "./extensionSkillEnablement.js";
import type { ExtensionManifest } from "./extensionManifestTypes.js";

export { enabledExtensions } from "./extensionEnablementState.js";
export { extensionToolsForEnable } from "./extensionSkillEnablement.js";

export function enableExtensionInSpec(
  spec: AgentSpec | undefined,
  metadataKey: ExtensionMetadataKey,
  manifest: ExtensionManifest,
  options: ExtensionEnablementOptions = {}
): ExtensionEnablementEffect {
  if (!spec) return emptyEffect();
  if (metadataKey === "enabled_skills") return enableSkillInSpec(spec, metadataKey, manifest, options);

  const enabled = enabledExtensions(spec, metadataKey);
  if (enabled.has(manifest.name)) return emptyEffect();
  const previousTools = currentEnabledTools(spec, options);
  const tools = extensionToolsForEnable(metadataKey, manifest);
  if (enabledExtensions(spec, "enabled_skills").size) ensureSkillBaseTools(spec, "enabled_skills", options);
  const pluginOwnedTools = pluginOwnedToolsForEnable(spec, tools, options);

  spec.metadata[metadataKey] = joinEnabled(new Set([...enabled, manifest.name]));
  setMetadataList(spec, pluginToolsKey(metadataKey, manifest.name), tools);
  setMetadataList(spec, addedToolsKey(metadataKey, manifest.name), pluginOwnedTools);
  spec.enabled_tools = enabledExtensions(spec, "enabled_skills").size
    ? effectiveSkillTools(spec, "enabled_skills", options)
    : uniqueStrings([...previousTools, ...tools]);

  const effect = toolDiff(previousTools, spec.enabled_tools);
  return { added_tools: effect.added, removed_tools: effect.removed, restored_tools: [] };
}

export function disableExtensionInSpec(
  spec: AgentSpec | undefined,
  metadataKey: ExtensionMetadataKey,
  manifest: ExtensionManifest,
  options: ExtensionEnablementOptions = {}
): ExtensionEnablementEffect {
  if (!spec) return emptyEffect();
  if (metadataKey === "enabled_skills") return disableSkillInSpec(spec, metadataKey, manifest, options);

  const addedKey = addedToolsKey(metadataKey, manifest.name);
  const addedTools = metadataList(spec, addedKey);
  const previousTools = currentEnabledTools(spec, options);
  delete spec.metadata[addedKey];
  delete spec.metadata[pluginToolsKey(metadataKey, manifest.name)];

  const enabled = enabledExtensions(spec, metadataKey);
  enabled.delete(manifest.name);
  spec.metadata[metadataKey] = joinEnabled(enabled);

  if (enabledExtensions(spec, "enabled_skills").size) {
    spec.enabled_tools = effectiveSkillTools(spec, "enabled_skills", options);
  } else {
    const toolsAddedByOthers = metadataTools(spec, metadataKey, ".added_tools");
    const toolsDeclaredByOthers = metadataTools(spec, metadataKey, ".tools");
    const protectedTools = new Set([...toolsAddedByOthers, ...toolsDeclaredByOthers]);
    const actuallyRemoved = addedTools.filter((tool) => !protectedTools.has(tool));
    spec.enabled_tools = uniqueStrings(previousTools.filter((tool) => !actuallyRemoved.includes(tool)));
  }

  const effect = toolDiff(previousTools, spec.enabled_tools);
  return { added_tools: [], removed_tools: effect.removed, restored_tools: effect.added };
}

function pluginOwnedToolsForEnable(spec: AgentSpec, tools: string[], options: ExtensionEnablementOptions): string[] {
  const existingPluginTools = metadataTools(spec, "enabled_plugins", ".tools");
  const sourceTools = enabledExtensions(spec, "enabled_skills").size
    ? metadataList(spec, baseToolsKey("enabled_skills"))
    : currentEnabledTools(spec, options);
  const existingSources = new Set([...sourceTools, ...existingPluginTools]);
  return tools.filter((tool) => !existingSources.has(tool));
}
