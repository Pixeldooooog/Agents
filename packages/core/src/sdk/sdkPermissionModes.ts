export type SdkPermissionMode = "default" | "acceptEdits" | "bypassPermissions" | "plan" | "dontAsk";

export type SdkPermissionModeAlias =
  | "accept-edits"
  | "accept_edits"
  | "acceptedits"
  | "bypass"
  | "bypass-permissions"
  | "bypass_permissions"
  | "bypasspermissions"
  | "deny"
  | "dont-ask"
  | "dont_ask"
  | "dontask";

export type SdkPermissionModeInput = SdkPermissionMode | SdkPermissionModeAlias;

const sdkPermissionModes = ["default", "acceptEdits", "bypassPermissions", "plan", "dontAsk"] as const;

export function normalizeSdkPermissionMode(value: unknown): SdkPermissionMode | undefined {
  if (isSdkPermissionMode(value)) return value;
  const normalized = String(value || "").trim().toLowerCase().replaceAll("_", "-");
  if (normalized === "accept-edits" || normalized === "acceptedits") return "acceptEdits";
  if (normalized === "bypass" || normalized === "bypass-permissions" || normalized === "bypasspermissions") {
    return "bypassPermissions";
  }
  if (normalized === "deny" || normalized === "dont-ask" || normalized === "dontask") return "dontAsk";
  if (normalized === "plan") return "plan";
  return undefined;
}

export function normalizeSdkPermissionModeOrDefault(value: unknown): SdkPermissionMode {
  return normalizeSdkPermissionMode(value) || "default";
}

export function sdkPermissionProfileForMode(value: unknown): string {
  const mode = normalizeSdkPermissionMode(value);
  if (mode === "bypassPermissions") return "auto";
  if (mode === "dontAsk") return "deny";
  if (mode === "default" || mode === "acceptEdits" || mode === "plan") return "ask";
  return "";
}

export function isSdkPermissionMode(value: unknown): value is SdkPermissionMode {
  return sdkPermissionModes.includes(value as SdkPermissionMode);
}
