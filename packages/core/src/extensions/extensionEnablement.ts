import type { AgentSpec } from "../types/agentTypes.js";
import { emptyEffect, enabledExtensions, joinEnabled, type ExtensionEnablementEffect, type ExtensionMetadataKey } from "./extensionEnablementState.js";
import { setSkillEnabled } from "./extensionSkillEnablement.js";
import type { ExtensionManifest } from "./extensionManifestTypes.js";

export { enabledExtensions } from "./extensionEnablementState.js";
export { extensionToolsForEnable } from "./extensionSkillEnablement.js";

/** Manifests describe capabilities; only host/user policy may authorize them. */
export function enableExtensionInSpec(spec: AgentSpec | undefined, key: ExtensionMetadataKey, manifest: ExtensionManifest): ExtensionEnablementEffect {
  if (!spec) return emptyEffect();
  if (key === "enabled_skills") return setSkillEnabled(spec, manifest.name, true);
  const enabled = enabledExtensions(spec, key);
  enabled.add(manifest.name);
  spec.metadata[key] = joinEnabled(enabled);
  return emptyEffect();
}

export function disableExtensionInSpec(spec: AgentSpec | undefined, key: ExtensionMetadataKey, manifest: ExtensionManifest): ExtensionEnablementEffect {
  if (!spec) return emptyEffect();
  if (key === "enabled_skills") return setSkillEnabled(spec, manifest.name, false);
  const enabled = enabledExtensions(spec, key);
  enabled.delete(manifest.name);
  spec.metadata[key] = joinEnabled(enabled);
  return emptyEffect();
}
