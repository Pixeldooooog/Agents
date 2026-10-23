import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolDefinition, ToolExecutionContext } from "../tools/toolContracts.js";

type ConfigSetting = {
  valueType: "string" | "boolean";
  defaultValue: string | boolean;
  options?: string[];
};

const supportedSettings: Record<string, ConfigSetting> = {
  theme: { valueType: "string", defaultValue: "dark", options: ["auto", "dark", "light", "light-daltonized", "dark-daltonized", "light-ansi", "dark-ansi"] },
  editorMode: { valueType: "string", defaultValue: "normal", options: ["normal", "vim"] },
  verbose: { valueType: "boolean", defaultValue: false },
  preferredNotifChannel: { valueType: "string", defaultValue: "auto", options: ["auto", "iterm2", "iterm2_with_bell", "terminal_bell", "kitty", "ghostty", "notifications_disabled"] },
  autoCompactEnabled: { valueType: "boolean", defaultValue: true },
  autoMemoryEnabled: { valueType: "boolean", defaultValue: false },
  autoDreamEnabled: { valueType: "boolean", defaultValue: false },
  fileCheckpointingEnabled: { valueType: "boolean", defaultValue: true },
  showTurnDuration: { valueType: "boolean", defaultValue: true },
  terminalProgressBarEnabled: { valueType: "boolean", defaultValue: true },
  todoFeatureEnabled: { valueType: "boolean", defaultValue: true },
  model: { valueType: "string", defaultValue: "default" },
  alwaysThinkingEnabled: { valueType: "boolean", defaultValue: false },
  "permissions.defaultMode": { valueType: "string", defaultValue: "default", options: ["default", "plan", "acceptEdits", "dontAsk", "auto"] },
  language: { valueType: "string", defaultValue: "" },
  teammateMode: { valueType: "string", defaultValue: "auto", options: ["auto", "tmux", "in-process"] },
  classifierPermissionsEnabled: { valueType: "boolean", defaultValue: false },
  voiceEnabled: { valueType: "boolean", defaultValue: false },
  remoteControlAtStartup: { valueType: "boolean", defaultValue: false },
  taskCompleteNotifEnabled: { valueType: "boolean", defaultValue: false },
  inputNeededNotifEnabled: { valueType: "boolean", defaultValue: false },
  agentPushNotifEnabled: { valueType: "boolean", defaultValue: false }
};

export const configToolDefinitions: ToolDefinition[] = [
  {
    name: "config.manage",
    description: "Get or set configuration settings.",
    risk: "medium",
    parameters: {
      type: "object",
      properties: {
        setting: { type: "string", description: "The setting key, for example theme, model, or permissions.defaultMode." },
        value: { type: ["string", "boolean", "number"], description: "The new value. Omit this field to get the current value." }
      },
      required: ["setting"],
      additionalProperties: false
    },
    handler: configManage
  }
];

async function configManage(context: ToolExecutionContext, args: JsonObject): Promise<Record<string, unknown>> {
  const setting = requiredSetting(args.setting);
  const config = supportedSettings[setting];
  if (!config) throw new Error(`Unknown setting: "${setting}"`);
  if (!Object.prototype.hasOwnProperty.call(args, "value")) {
    return { success: true, operation: "get", setting, value: currentValue(context, setting, config) };
  }
  const nextValue = coerceValue(setting, config, args.value);
  const previousValue = currentValue(context, setting, config);
  applyConfigValue(context, setting, nextValue);
  return { success: true, operation: "set", setting, previousValue, newValue: nextValue };
}

function currentValue(context: ToolExecutionContext, setting: string, config: ConfigSetting): string | boolean {
  const override = context.spec?.metadata[`config.${setting}`];
  if (override !== undefined) return decodeConfigValue(override);
  if (setting === "model") return context.spec?.model || config.defaultValue;
  if (setting === "permissions.defaultMode") return permissionModeForProfile(context.spec?.permission_profile || "");
  return config.defaultValue;
}

function applyConfigValue(context: ToolExecutionContext, setting: string, value: string | boolean): void {
  if (!context.spec) throw new Error("agent spec is not available");
  if (setting === "model") {
    context.spec.model = String(value);
    delete context.spec.metadata["config.model"];
    return;
  }
  if (setting === "permissions.defaultMode") {
    context.spec.permission_profile = permissionProfileForConfig(String(value));
    context.spec.metadata[`config.${setting}`] = JSON.stringify(value);
    return;
  }
  context.spec.metadata[`config.${setting}`] = JSON.stringify(value);
}

function coerceValue(setting: string, config: ConfigSetting, value: unknown): string | boolean {
  if (config.valueType === "boolean") {
    const booleanValue = typeof value === "string" ? parseBoolean(value) : value;
    if (typeof booleanValue !== "boolean") throw new Error(`${setting} requires true or false.`);
    return booleanValue;
  }
  const stringValue = String(value ?? "");
  if (config.options && !config.options.includes(stringValue)) {
    throw new Error(`Invalid value "${stringValue}". Options: ${config.options.join(", ")}`);
  }
  return stringValue;
}

function permissionModeForProfile(profile: string): string {
  if (["default", "plan", "acceptEdits", "dontAsk", "auto"].includes(profile)) return profile;
  if (profile === "ask") return "plan";
  return "default";
}

function permissionProfileForConfig(value: string): string {
  const mapping: Record<string, string> = { default: "auto", auto: "auto", plan: "ask", acceptEdits: "auto", dontAsk: "auto" };
  if (!mapping[value]) throw new Error(`Invalid value "${value}". Options: default, plan, acceptEdits, dontAsk, auto`);
  return mapping[value];
}

function decodeConfigValue(value: string): string | boolean {
  try {
    const parsed = JSON.parse(value);
    return typeof parsed === "boolean" || typeof parsed === "string" ? parsed : String(parsed);
  } catch {
    return value;
  }
}

function parseBoolean(value: string): boolean | string {
  const normalized = value.trim().toLowerCase();
  if (normalized === "true") return true;
  if (normalized === "false") return false;
  return value;
}

function requiredSetting(value: unknown): string {
  const setting = String(value || "").trim();
  if (!setting) throw new Error("setting is required");
  return setting;
}
