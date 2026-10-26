import type { AgentSpec } from "../types/agentTypes.js";
import type { ExtensionManifest } from "./extensionManifestTypes.js";
import { emptyEffect, enabledExtensions, joinEnabled, type ExtensionEnablementEffect, type ExtensionMetadataKey } from "./extensionEnablementState.js";

/** Skill state controls instruction availability, never the run's tool authority. */
export function setSkillEnabled(spec: AgentSpec, name: string, enabled: boolean): ExtensionEnablementEffect {
  const active = enabledExtensions(spec, "enabled_skills");
  const disabled = disabledSkills(spec);
  if (enabled) { active.add(name); disabled.delete(name); }
  else { active.delete(name); disabled.add(name); }
  spec.metadata.enabled_skills = joinEnabled(active);
  spec.metadata.disabled_skills = joinEnabled(disabled);
  return emptyEffect();
}

export function disabledSkills(spec: AgentSpec | undefined): Set<string> {
  return new Set((spec?.metadata.disabled_skills || "").split(",").map(name => name.trim()).filter(Boolean));
}

/** Declared tool hints are descriptive; they do not grant or revoke runtime permissions. */
export function extensionToolsForEnable(metadataKey: ExtensionMetadataKey, manifest: ExtensionManifest): string[] {
  if (metadataKey !== "enabled_skills") return manifest.tools;
  const disallowed = new Set(manifest.disallowed_tools);
  return manifest.allowed_tools.filter(tool => !disallowed.has(tool));
}
