import type { ToolDefinition } from "../tools/toolContracts.js";
import {
  handlePluginDisable,
  handlePluginDiscover,
  handlePluginEnable,
  handlePluginInstall,
  handlePluginUninstall,
  handleSkillDisable,
  handleSkillDiscover,
  handleSkillInstall,
  handleSkillInvoke,
  handleSkillUninstall,
  handleSkillUse
} from "./extensionToolHandlers.js";
import { extensionDiscoverSchema, extensionInstallSchema, extensionNameSchema, skillInvokeSchema } from "./extensionToolSchemas.js";

export const extensionToolDefinitions: ToolDefinition[] = [
  { name: "skill.discover", description: "Discover available local skills and their tool/prompt contributions.", risk: "low", parameters: extensionDiscoverSchema, handler: handleSkillDiscover },
  { name: "skill.invoke", description: "Invoke a local skill and return the rendered instructions.", risk: "high", parameters: skillInvokeSchema, handler: handleSkillInvoke },
  { name: "skill.install", description: "Install a local SKILL.md file or skill package directory.", risk: "medium", parameters: extensionInstallSchema, handler: handleSkillInstall },
  { name: "skill.uninstall", description: "Uninstall a local skill by name.", risk: "medium", parameters: extensionNameSchema, handler: handleSkillUninstall },
  { name: "skill.use", description: "Enable a local skill for the current session.", risk: "medium", parameters: extensionNameSchema, handler: handleSkillUse },
  { name: "skill.disable", description: "Disable a previously enabled local skill.", risk: "medium", parameters: extensionNameSchema, handler: handleSkillDisable },
  { name: "plugin.discover", description: "Discover local plugins and their tool/prompt contributions.", risk: "low", parameters: extensionDiscoverSchema, handler: handlePluginDiscover },
  { name: "plugin.install", description: "Install a local plugin directory into .kevin/plugins.", risk: "medium", parameters: extensionInstallSchema, handler: handlePluginInstall },
  { name: "plugin.uninstall", description: "Uninstall an installed plugin by name.", risk: "medium", parameters: extensionNameSchema, handler: handlePluginUninstall },
  { name: "plugin.enable", description: "Enable a local plugin for the current session.", risk: "medium", parameters: extensionNameSchema, handler: handlePluginEnable },
  { name: "plugin.disable", description: "Disable a previously enabled local plugin.", risk: "medium", parameters: extensionNameSchema, handler: handlePluginDisable }
];
