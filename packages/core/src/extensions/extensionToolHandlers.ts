import { isPortableManifestName } from "./extensionManifestRecords.js";
import { disabledSkills, setSkillEnabled } from "./extensionSkillEnablement.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolContext } from "../tools/toolContracts.js";
import { booleanArg, numberArg, stringArg } from "../tools/toolInputs.js";
import {
  disableExtensionInSpec,
  enableExtensionInSpec,
  enabledExtensions,
  extensionToolsForEnable
} from "./extensionEnablement.js";
import {
  discoverPlugins,
  discoverSkills,
  installPlugin,
  installSkill,
  loadPlugin,
  loadSkill,
  publicExtensionPayload,
  renderExtensionPrompt,
  uninstallPlugin,
  uninstallSkill,
  type ExtensionManifest
} from "./extensionManifests.js";

export async function handleSkillDiscover(context: ToolContext, args: JsonObject) {
  const skills = await discoverSkills(context);
  return extensionDiscoveryPayload(context, skills, args, "skills", "total_available_skills");
}

export async function handlePluginDiscover(context: ToolContext, args: JsonObject) {
  const plugins = await discoverPlugins(context);
  return extensionDiscoveryPayload(context, plugins, args, "plugins", "total_available_plugins");
}

export async function handleSkillInstall(context: ToolContext, args: JsonObject) {
  const skill = await installSkill(context, stringArg(args.source));
  return { skill: publicExtensionPayload(context, skill), installed: true };
}

export async function handlePluginInstall(context: ToolContext, args: JsonObject) {
  const plugin = await installPlugin(context, stringArg(args.source));
  return { plugin: publicExtensionPayload(context, plugin), installed: true };
}

export async function handleSkillUninstall(context: ToolContext, args: JsonObject) {
  const name = stringArg(args.name);
  if (enabledExtensions(context.spec, "enabled_skills").has(name)) throw new Error(`disable skill before uninstalling: ${name}`);
  return { skill: await uninstallSkill(context, name), uninstalled: true };
}

export async function handlePluginUninstall(context: ToolContext, args: JsonObject) {
  const name = stringArg(args.name);
  if (enabledExtensions(context.spec, "enabled_plugins").has(name)) throw new Error(`disable plugin before uninstalling: ${name}`);
  return { plugin: await uninstallPlugin(context, name), uninstalled: true };
}

export async function handleSkillUse(context: ToolContext, args: JsonObject) {
  const skill = await loadSkill(context, stringArg(args.name));
  if (skill.disable_model_invocation) throw new Error(`skill does not allow model invocation: ${skill.name}`);
  const effect = enableExtensionInSpec(context.spec, "enabled_skills", skill);
  return { skill: publicExtensionPayload(context, skill), ...effect, enabled: true };
}

export async function handleSkillDisable(context: ToolContext, args: JsonObject) {
  const name = stringArg(args.name);
  if (!isPortableManifestName(name)) throw new Error("invalid skill name");
  const effect = context.spec ? setSkillEnabled(context.spec, name, false) : { added_tools: [], removed_tools: [], restored_tools: [] };
  return { skill: name, ...effect, enabled: false };
}

export async function handlePluginEnable(context: ToolContext, args: JsonObject) {
  const plugin = await loadPlugin(context, stringArg(args.name));
  const effect = enableExtensionInSpec(context.spec, "enabled_plugins", plugin);
  return { plugin: publicExtensionPayload(context, plugin), ...effect, enabled: true };
}

export async function handlePluginDisable(context: ToolContext, args: JsonObject) {
  const plugin = await loadPlugin(context, stringArg(args.name));
  const effect = disableExtensionInSpec(context.spec, "enabled_plugins", plugin);
  return { plugin: plugin.name, ...effect, enabled: false };
}

export async function handleSkillInvoke(context: ToolContext, args: JsonObject) {
  const skill = await loadSkill(context, stringArg(args.skill).replace(/^\//, ""));
  if (skill.disable_model_invocation) throw new Error(`skill does not allow model invocation: ${skill.name}`);
  if (disabledSkills(context.spec).has(skill.name)) throw new Error(`skill is disabled: ${skill.name}`);
  const rawArguments = stringArg(args.args);
  const prompt = await renderExtensionPrompt(skill, { arguments: rawArguments }, rawArguments);
  const requestedMode = stringArg(args.mode, skill.context === "fork" ? "fork" : "auto");
  const mode = requestedMode === "fork" ? "fork_unavailable" : "inline";
  const skillPayload = publicExtensionPayload(context, skill);
  return {
    success: true,
    commandName: skill.name,
    skill: skillPayload,
    path: skillPayload.path,
    manifestPath: skillPayload.manifest_path,
    toolPermissions: "declarative-only; runtime permissions and approvals remain authoritative",
    allowedTools: extensionToolsForEnable("enabled_skills", skill),
    disallowedTools: skill.disallowed_tools,
    model: skill.model,
    effort: skill.effort,
    agent: skill.agent,
    context: skill.context,
    disableModelInvocation: skill.disable_model_invocation,
    status: mode,
    args: rawArguments,
    prompt
  };
}

function extensionDiscoveryPayload(
  context: ToolContext,
  manifests: ExtensionManifest[],
  args: JsonObject,
  key: "skills" | "plugins",
  totalKey: "total_available_skills" | "total_available_plugins"
) {
  const query = stringArg(args.query).toLowerCase();
  const includePrompt = booleanArg(args.include_prompt);
  const matches = query ? manifests.filter((manifest) => manifestHaystack(manifest).includes(query)) : manifests;
  const limit = Math.max(1, Math.min(100, numberArg(args.max_results, 20)));
  return {
    query,
    [key]: matches.slice(0, limit).map((manifest) => publicExtensionPayload(context, manifest, includePrompt)),
    count: Math.min(matches.length, limit),
    [totalKey]: manifests.length,
    enabled_skills: key === "skills" ? [...enabledExtensions(context.spec, "enabled_skills")] : undefined,
    enabled_plugins: key === "plugins" ? [...enabledExtensions(context.spec, "enabled_plugins")] : undefined
  };
}

function manifestHaystack(manifest: ExtensionManifest): string {
  return [
    manifest.name,
    manifest.description,
    manifest.when_to_use,
    manifest.tools.join(" "),
    manifest.allowed_tools.join(" "),
    manifest.disallowed_tools.join(" "),
    manifest.paths.join(" "),
    manifest.prompt_fragments.join(" "),
    JSON.stringify(manifest.metadata)
  ].join(" ").toLowerCase();
}
