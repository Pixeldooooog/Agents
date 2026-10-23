import { discoverCommands, publicCommand } from "../commands/commandDiscovery.js";
import { buildModelProfiles, defaultEnabledTools, profileDefaults } from "../models/modelProfiles.js";
import { canonicalToolName, listBuiltinTools } from "../tools/toolRegistry.js";
import { sdkCommandPayload } from "./sdkCommandRecords.js";
import type { SdkControlRequestMessage } from "./sdkControlTypes.js";
import {
  mcpMessageControlResponsePayload,
  mcpReconnectControlResponsePayload,
  mcpSetServersControlResponsePayload,
  mcpStatusControlResponsePayload,
  mcpToggleControlResponsePayload
} from "./sdkMcpControlHandlers.js";
import {
  applySdkControlRequestToOptions,
  settingsControlResponsePayload
} from "./sdkControlSettings.js";
import { contextUsageControlResponsePayload } from "./sdkContextUsageControlHandlers.js";
import {
  elicitationControlResponsePayload,
  hookCallbackControlResponsePayload
} from "./sdkInteractionControlHandlers.js";
import {
  rewindFilesControlResponsePayload,
  seedReadStateControlResponsePayload
} from "./sdkFileControlHandlers.js";
import { stopTaskControlResponsePayload } from "./sdkTaskControlHandlers.js";
import {
  cancelAsyncMessageControlResponsePayload,
  interruptControlResponsePayload
} from "./sdkTurnControlHandlers.js";
import { reloadPluginsControlResponsePayload } from "./sdkPluginControlHandlers.js";
import {
  sdkOptionApprovalRequiredTools,
  sdkOptionDeniedTools,
  sdkOptionEnabledTools,
  sdkOptionPermissionProfile
} from "./sdkProtocolOptionAccess.js";
import type { SdkControlRequestHandlerContext, SdkProtocolRunnerOptions } from "./sdkProtocolRunner.js";

export async function defaultSdkControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const request = message.request;
  if (request.subtype === "initialize") return initializeControlResponsePayload(message, context);
  if (request.subtype === "can_use_tool") return permissionControlResponsePayload(request.toolName, context.options);
  if (request.subtype === "get_settings") return settingsControlResponsePayload(context.options);
  if (request.subtype === "mcp_status") return mcpStatusControlResponsePayload(context);
  if (request.subtype === "mcp_message") return mcpMessageControlResponsePayload(message, context);
  if (request.subtype === "mcp_set_servers") return mcpSetServersControlResponsePayload(message, context);
  if (request.subtype === "mcp_reconnect") return mcpReconnectControlResponsePayload(message, context);
  if (request.subtype === "mcp_toggle") return mcpToggleControlResponsePayload(message, context);
  if (request.subtype === "hook_callback") return hookCallbackControlResponsePayload(message, context);
  if (request.subtype === "elicitation") return elicitationControlResponsePayload(message, context);
  if (request.subtype === "get_context_usage") return contextUsageControlResponsePayload(context);
  if (request.subtype === "stop_task") return stopTaskControlResponsePayload(message, context);
  if (request.subtype === "interrupt") return interruptControlResponsePayload(context);
  if (request.subtype === "cancel_async_message") return cancelAsyncMessageControlResponsePayload(message, context);
  if (request.subtype === "seed_read_state") return seedReadStateControlResponsePayload(message, context);
  if (request.subtype === "rewind_files") return rewindFilesControlResponsePayload(message, context);
  if (request.subtype === "reload_plugins") return reloadPluginsControlResponsePayload(context);
  if (request.subtype === "set_model" || request.subtype === "set_permission_mode" ||
    request.subtype === "set_max_thinking_tokens" || request.subtype === "apply_flag_settings") {
    return applySdkControlRequestToOptions(request, context.options) || {};
  }
  return {};
}

async function initializeControlResponsePayload(
  message: SdkControlRequestMessage,
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const settings = context.client.settings;
  const defaults = profileDefaults(settings);
  const model = context.options.model || defaults.model || "";
  const outputStyle = String(context.options.metadata?.outputStyle || context.options.metadata?.output_style || "default");
  const availableOutputStyles = ["default"];
  const fastModeState = context.options.metadata?.fastModeState || context.options.metadata?.fast_mode_state;
  return {
    commands: (await discoverCommands(settings.repoRoot)).map((command) => sdkCommandPayload(publicCommand(command))),
    agents: agentInfosFromInitializeRequest(message),
    outputStyle,
    output_style: outputStyle,
    availableOutputStyles,
    available_output_styles: availableOutputStyles,
    models: modelInfos(context),
    account: accountInfo(context.options),
    tools: listBuiltinTools(),
    enabledTools: sdkOptionEnabledTools(context.options) || defaultEnabledTools(settings),
    mcp: await mcpStatusControlResponsePayload(context),
    fastModeState,
    fast_mode_state: fastModeState,
    model
  };
}

function permissionControlResponsePayload(toolName: string, options: SdkProtocolRunnerOptions): Record<string, unknown> {
  const canonicalName = canonicalToolName(toolName);
  const permissionProfile = sdkOptionPermissionProfile(options);
  const deniedTools = sdkOptionDeniedTools(options);
  const approvalRequiredTools = sdkOptionApprovalRequiredTools(options);
  const denied = permissionProfile === "deny" || deniedTools.includes(canonicalName);
  const approvalAllowedByProfile = permissionProfile !== "auto" && permissionProfile !== "deny";
  const requiresApproval = !denied && approvalAllowedByProfile && (
    permissionProfile === "ask" || approvalRequiredTools.includes(canonicalName)
  );
  return {
    behavior: denied ? "deny" : requiresApproval ? "ask" : "allow",
    allowed: !denied,
    requiresApproval,
    requires_approval: requiresApproval,
    reason: denied ? "tool is denied by SDK options" : requiresApproval ? "tool requires approval" : "tool allowed",
    metadata: { toolName: canonicalName, requestedToolName: toolName }
  };
}

function modelInfos(context: SdkControlRequestHandlerContext): Array<Record<string, unknown>> {
  const profiles = buildModelProfiles(context.client.settings);
  if (!profiles.length && context.options.model) {
    return [{ value: context.options.model, displayName: context.options.model, description: "SDK model", configured: false }];
  }
  return profiles.map((profile) => ({
    value: profile.model || profile.name,
    displayName: profile.name,
    description: profile.endpoint,
    protocol: profile.protocol,
    endpoint: profile.endpoint,
    configured: profile.configured
  }));
}

function agentInfosFromInitializeRequest(message: SdkControlRequestMessage): Array<Record<string, string>> {
  const request = message.request;
  if (request.subtype !== "initialize" || !request.agents) return [];
  return Object.entries(request.agents).map(([name, rawDefinition]) => {
    const definition = objectValue(rawDefinition);
    return compactStringObject({
      name,
      description: String(definition.description || definition.prompt || ""),
      model: String(definition.model || "")
    });
  });
}

function accountInfo(options: SdkProtocolRunnerOptions): Record<string, string> {
  const source = String(options.metadata?.apiKeySource || options.metadata?.api_key_source || "project");
  return { apiKeySource: ["user", "project", "org", "temporary", "oauth"].includes(source) ? source : "project" };
}

function compactStringObject(value: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(value).filter(([, entry]) => entry !== ""));
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
