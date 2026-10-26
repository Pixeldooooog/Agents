import { defineTool, type RegisteredTool } from "../tools/toolContracts.js";
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

export const extensionToolDefinitions: RegisteredTool[] = [
  defineTool({ name: "skill.discover", description: "Discover local skill metadata; declared tools do not grant permissions.", risk: "low", parameters: extensionDiscoverSchema, requires: [], handler: handleSkillDiscover }),
  defineTool({ name: "skill.invoke", description: "Invoke a local skill and return the rendered instructions.", risk: "high", parameters: skillInvokeSchema, requires: [], handler: handleSkillInvoke }),
  defineTool({ name: "skill.install", description: "Install a local SKILL.md file or skill package directory.", risk: "medium", parameters: extensionInstallSchema, requires: [], handler: handleSkillInstall }),
  defineTool({ name: "skill.uninstall", description: "Uninstall a local skill by name.", risk: "medium", parameters: extensionNameSchema, requires: [], handler: handleSkillUninstall }),
  defineTool({ name: "skill.use", description: "Enable a local skill for the current session without changing tool permissions.", risk: "medium", parameters: extensionNameSchema, requires: [], handler: handleSkillUse }),
  defineTool({ name: "skill.disable", description: "Disable a previously enabled local skill.", risk: "medium", parameters: extensionNameSchema, requires: [], handler: handleSkillDisable }),
  defineTool({ name: "plugin.discover", description: "Discover local plugins and their tool/prompt contributions.", risk: "low", parameters: extensionDiscoverSchema, requires: [], handler: handlePluginDiscover }),
  defineTool({ name: "plugin.install", description: "Install a local plugin directory into .kevin/plugins.", risk: "medium", parameters: extensionInstallSchema, requires: [], handler: handlePluginInstall }),
  defineTool({ name: "plugin.uninstall", description: "Uninstall an installed plugin by name.", risk: "medium", parameters: extensionNameSchema, requires: [], handler: handlePluginUninstall }),
  defineTool({ name: "plugin.enable", description: "Enable a local plugin for the current session.", risk: "medium", parameters: extensionNameSchema, requires: [], handler: handlePluginEnable }),
  defineTool({ name: "plugin.disable", description: "Disable a previously enabled local plugin.", risk: "medium", parameters: extensionNameSchema, requires: [], handler: handlePluginDisable })
];
