import type { RunRecord } from "../types/runtimeTypes.js";
import type { SdkSystemInitMessage } from "./sdkMessages.js";
import { normalizeSdkPermissionModeOrDefault } from "./sdkPermissionModes.js";

const sdkVersion = "0.1.0";

export function sdkSystemInitMessageFromRun(run: RunRecord, sessionId: string): SdkSystemInitMessage {
  const metadata = { ...(run.spec.metadata || {}), ...(run.metadata || {}) };
  const tools = metadataStringList(metadata, "sdk_init_tools_json", "sdk_init_tools");
  return {
    type: "system",
    subtype: "init",
    runId: run.run_id,
    sessionId,
    agents: metadataStringList(metadata, "agents", "sdk_agents"),
    apiKeySource: apiKeySource(metadataValue(metadata, "apiKeySource", "api_key_source")),
    betas: metadataStringList(metadata, "betas", "sdk_betas"),
    claudeCodeVersion: textField(metadata, "claude_code_version", "sdk_version") || sdkVersion,
    cwd: runCwd(run),
    tools: tools.length ? tools : [...(run.spec.enabled_tools || [])],
    mcpServers: metadataRecordList(metadata, "mcpServers", "mcp_servers", "sdk_mcp_servers"),
    model: textField(metadata, "sdk_init_model") || run.spec.model || "",
    permissionMode: normalizeSdkPermissionModeOrDefault(
      metadataValue(metadata, "permissionMode", "permission_mode") || run.spec.permission_profile
    ),
    slashCommands: metadataStringList(metadata, "slash_commands", "slashCommands", "sdk_slash_commands"),
    outputStyle: textField(metadata, "output_style", "outputStyle") || "default",
    skills: metadataStringList(metadata, "skills", "sdk_skills", "enabled_skills"),
    plugins: metadataRecordList(metadata, "plugins", "sdk_plugins"),
    fastModeState: fastModeState(metadataValue(metadata, "fast_mode_state", "fastModeState")),
    uuid: textField(metadata, "uuid", "message_id", "messageId") || crypto.randomUUID()
  };
}

function runCwd(run: RunRecord): string {
  return String(run.metadata.sdk_cwd || run.metadata.cwd || "");
}

function metadataValue(metadata: Record<string, string>, ...keys: string[]): unknown {
  for (const key of keys) {
    if (metadata[key] !== undefined) return metadata[key];
  }
  return undefined;
}

function textField(metadata: Record<string, string>, ...keys: string[]): string {
  const value = metadataValue(metadata, ...keys);
  return typeof value === "string" ? value.trim() : "";
}

function metadataStringList(metadata: Record<string, string>, ...keys: string[]): string[] {
  for (const key of keys) {
    const parsed = stringList(metadata[key]);
    if (parsed.length) return parsed;
  }
  return [];
}

function stringList(value: unknown): string[] {
  if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
  if (typeof value !== "string" || !value.trim()) return [];
  const parsed = parseJson(value);
  if (Array.isArray(parsed)) return parsed.map((item) => String(item).trim()).filter(Boolean);
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

function metadataRecordList(metadata: Record<string, string>, ...keys: string[]): Array<Record<string, string>> {
  for (const key of keys) {
    const records = recordList(metadata[key]);
    if (records.length) return records;
  }
  return [];
}

function recordList(value: unknown): Array<Record<string, string>> {
  const parsed = typeof value === "string" ? parseJson(value) : value;
  if (!Array.isArray(parsed)) return [];
  return parsed.flatMap((item) => {
    if (typeof item === "string" && item.trim()) return [{ name: item.trim(), path: "" }];
    if (!item || typeof item !== "object" || Array.isArray(item)) return [];
    return [stringRecord(item as Record<string, unknown>)];
  }).filter((item) => Object.keys(item).length > 0);
}

function stringRecord(record: Record<string, unknown>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(record)
      .map(([key, value]) => [key, String(value ?? "")])
      .filter(([, value]) => value !== "")
  );
}

function parseJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
}

function apiKeySource(value: unknown): SdkSystemInitMessage["apiKeySource"] {
  return value === "user" || value === "project" || value === "org" || value === "temporary" || value === "oauth"
    ? value
    : "project";
}

function fastModeState(value: unknown): SdkSystemInitMessage["fastModeState"] {
  return value === "off" || value === "cooldown" || value === "on" ? value : null;
}
