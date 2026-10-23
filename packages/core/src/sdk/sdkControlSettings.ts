import type { SdkControlRequestPayload, SdkPermissionModeInput } from "./sdkControlTypes.js";
import type { SdkProtocolRunnerOptions } from "./sdkProtocolRunner.js";
import { normalizeSdkPermissionMode, sdkPermissionProfileForMode } from "./sdkPermissionModes.js";

export function settingsControlResponsePayload(options: SdkProtocolRunnerOptions): Record<string, unknown> {
  const resolvedPermissionMode = normalizeSdkPermissionMode(options.permissionMode ?? options.permission_mode);
  const resolvedPermissionProfile = settingsPermissionProfile(options);
  return {
    effective: compactObject({
      protocol: options.protocol,
      model: options.model,
      baseUrl: options.baseUrl || options.base_url,
      cwd: options.cwd,
      permissionMode: resolvedPermissionMode,
      permissionProfile: resolvedPermissionProfile,
      systemPrompt: options.systemPrompt || options.system_prompt,
      allowedTools: options.allowedTools || options.allowed_tools,
      enabledTools: options.enabledTools || options.enabled_tools,
      deniedTools: options.deniedTools || options.denied_tools,
      approvalRequiredTools: options.approvalRequiredTools || options.approval_required_tools,
      maxToolIterations: options.maxToolIterations ?? options.max_tool_iterations ?? options.maxTurns ?? options.max_turns,
      maxThinkingTokens: options.maxThinkingTokens ?? options.max_thinking_tokens,
      sessionId: options.sessionId || options.session_id,
      tenantId: options.tenantId || options.tenant_id,
      userId: options.userId || options.user_id,
      agentId: options.agentId || options.agent_id,
      workspaceId: options.workspaceId || options.workspace_id,
      skills: options.skills,
      outputFormat: options.outputFormat || options.output_format,
      replayUserMessages: options.replayUserMessages ?? options.replay_user_messages
    }),
    sources: [
      { source: "flagSettings", settings: compactObject(options.flagSettings || {}) },
      { source: "sdkOptions", settings: compactObject(options.metadata || {}) }
    ],
    applied: {
      model: options.model || "",
      protocol: options.protocol || "",
      permissionMode: resolvedPermissionMode || "",
      permissionProfile: resolvedPermissionProfile || ""
    }
  };
}

export function applySdkControlRequestToOptions(
  request: SdkControlRequestPayload,
  options: SdkProtocolRunnerOptions
): Record<string, unknown> | undefined {
  if (request.subtype === "set_model") return applyModel(request.model, options);
  if (request.subtype === "set_permission_mode") return applyPermissionMode(request.mode, options);
  if (request.subtype === "set_max_thinking_tokens") return applyMaxThinkingTokens(request.maxThinkingTokens, options);
  if (request.subtype === "apply_flag_settings") return applyFlagSettings(request.settings || {}, options);
  return undefined;
}

function applyModel(model: string | null | undefined, options: SdkProtocolRunnerOptions): Record<string, unknown> {
  options.model = stringField(model);
  return { model: options.model };
}

function applyPermissionMode(mode: SdkPermissionModeInput, options: SdkProtocolRunnerOptions): Record<string, unknown> {
  const normalizedMode = normalizeSdkPermissionMode(mode) || "default";
  options.permissionMode = normalizedMode;
  options.permissionProfile = sdkPermissionProfileForMode(normalizedMode);
  return { mode: normalizedMode, permissionProfile: options.permissionProfile };
}

function applyMaxThinkingTokens(value: unknown, options: SdkProtocolRunnerOptions): Record<string, unknown> {
  const maxThinkingTokens = nonNegativeInteger(value);
  options.maxThinkingTokens = maxThinkingTokens;
  return {
    maxThinkingTokens: maxThinkingTokens ?? null,
    max_thinking_tokens: maxThinkingTokens ?? null
  };
}

function applyFlagSettings(
  settings: Record<string, unknown>,
  options: SdkProtocolRunnerOptions
): Record<string, unknown> {
  const applied: Record<string, unknown> = {};
  applyStringSetting(settings, "model", options, applied);
  applyStringSetting(settings, "protocol", options, applied);
  applyStringSetting(settings, "baseUrl", options, applied, ["base_url"]);
  applyStringSetting(settings, "cwd", options, applied);
  applyStringSetting(settings, "systemPrompt", options, applied, ["system_prompt"]);
  applyStringListSetting(settings, "allowedTools", options, applied, ["allowed_tools"]);
  applyStringListSetting(settings, "enabledTools", options, applied, ["enabled_tools"]);
  applyStringListSetting(settings, "deniedTools", options, applied, ["denied_tools"]);
  applyStringListSetting(settings, "approvalRequiredTools", options, applied, ["approval_required_tools"]);
  applyStringListSetting(settings, "skills", options, applied);
  const maxToolIterations = maxToolIterationsSetting(settings);
  if (maxToolIterations !== undefined) {
    options.maxToolIterations = maxToolIterations;
    applied.maxToolIterations = maxToolIterations;
  }
  const maxThinkingTokensSetting = settingEntry(settings, "maxThinkingTokens", ["max_thinking_tokens"]);
  if (maxThinkingTokensSetting.found) {
    const maxThinkingTokens = nonNegativeInteger(maxThinkingTokensSetting.value);
    options.maxThinkingTokens = maxThinkingTokens;
    applied.maxThinkingTokens = maxThinkingTokens ?? null;
    applied.max_thinking_tokens = maxThinkingTokens ?? null;
  }
  const permissionProfileSetting = settingEntry(settings, "permissionProfile", ["permission_profile"]);
  if (permissionProfileSetting.found) {
    options.permissionProfile = stringField(permissionProfileSetting.value);
    applied.permissionProfile = options.permissionProfile;
  }
  const permissionModeSetting = settingEntry(settings, "permissionMode", ["permission_mode"]);
  if (permissionModeSetting.found) {
    const mode = normalizeSdkPermissionMode(permissionModeSetting.value);
    if (mode) {
      options.permissionMode = mode;
      options.permissionProfile = sdkPermissionProfileForMode(mode);
      applied.permissionMode = mode;
      applied.permissionProfile = options.permissionProfile;
    }
  }
  const outputFormatSetting = settingEntry(settings, "outputFormat", ["output_format"]);
  if (outputFormatSetting.found) {
    const outputFormat = objectSetting(outputFormatSetting.value);
    options.outputFormat = outputFormat;
    applied.outputFormat = outputFormat;
  }
  const replayUserMessagesSetting = settingEntry(settings, "replayUserMessages", ["replay_user_messages"]);
  if (replayUserMessagesSetting.found) {
    const replayUserMessages = booleanSetting(replayUserMessagesSetting.value);
    options.replayUserMessages = replayUserMessages;
    applied.replayUserMessages = replayUserMessages ?? null;
  }
  const flagSettings = { ...(options.flagSettings || {}), ...settings };
  options.flagSettings = flagSettings;
  options.metadata = { ...(options.metadata || {}), flagSettings };
  return {
    applied,
    settings: settingsControlResponsePayload(options)
  };
}

function applyStringSetting(
  source: Record<string, unknown>,
  key: "model" | "protocol" | "baseUrl" | "cwd" | "systemPrompt",
  options: SdkProtocolRunnerOptions,
  applied: Record<string, unknown>,
  aliases: string[] = []
): void {
  const setting = settingEntry(source, key, aliases);
  if (!setting.found) return;
  const value = stringField(setting.value);
  options[key] = value;
  applied[key] = value;
}

function applyStringListSetting(
  source: Record<string, unknown>,
  key: "allowedTools" | "enabledTools" | "deniedTools" | "approvalRequiredTools" | "skills",
  options: SdkProtocolRunnerOptions,
  applied: Record<string, unknown>,
  aliases: string[] = []
): void {
  const setting = settingEntry(source, key, aliases);
  if (!setting.found) return;
  const value = stringList(setting.value);
  options[key] = value;
  applied[key] = value;
}

function settingEntry(
  source: Record<string, unknown>,
  key: string,
  aliases: string[] = []
): { found: boolean; value: unknown } {
  for (const candidate of [key, ...aliases]) {
    if (Object.prototype.hasOwnProperty.call(source, candidate)) {
      return { found: true, value: source[candidate] };
    }
  }
  return { found: false, value: undefined };
}

function maxToolIterationsSetting(settings: Record<string, unknown>): number | undefined {
  for (const key of ["maxToolIterations", "max_tool_iterations", "maxTurns", "max_turns"]) {
    if (!Object.prototype.hasOwnProperty.call(settings, key)) continue;
    const maxToolIterations = nonNegativeInteger(settings[key]);
    if (maxToolIterations !== undefined) return maxToolIterations;
  }
  return undefined;
}

function settingsPermissionProfile(options: SdkProtocolRunnerOptions): string {
  const explicitProfile = stringField(options.permissionProfile ?? options.permission_profile);
  if (explicitProfile) return explicitProfile;
  return sdkPermissionProfileForMode(options.permissionMode ?? options.permission_mode);
}

function compactObject(value: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(Object.entries(value).filter(([, entry]) => entry !== undefined && entry !== "" && entry !== null));
}

function stringField(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  return [];
}

function objectSetting(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? { ...value as Record<string, unknown> } : {};
}

function booleanSetting(value: unknown): boolean | undefined {
  if (typeof value === "boolean") return value;
  if (typeof value !== "string") return undefined;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  if (["0", "false", "no", "off"].includes(normalized)) return false;
  return undefined;
}

function nonNegativeInteger(value: unknown): number | undefined {
  if (value === undefined || value === null || value === "") return undefined;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : undefined;
}
