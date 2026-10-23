import type { SdkElicitationRequest, SdkElicitationResponse } from "./sdkControlTypes.js";

export function sdkElicitationRequestFromMcpParams(
  serverName: string,
  params: unknown
): SdkElicitationRequest {
  const mode = String(mcpParamField(params, "mode") || "form");
  const requestedSchema = mcpParamField(params, "requested_schema", "requestedSchema");
  return {
    subtype: "elicitation",
    mcpServerName: serverName || "",
    message: String(mcpParamField(params, "message") || ""),
    mode: mode === "url" ? "url" : "form",
    url: optionalString(mcpParamField(params, "url")),
    elicitationId: optionalString(mcpParamField(params, "elicitation_id", "elicitationId")),
    requestedSchema: isRecord(requestedSchema) ? { ...requestedSchema } : undefined
  };
}

export function normalizeSdkElicitationResponse(
  response: SdkElicitationResponse | undefined
): Record<string, unknown> {
  if (response === undefined) return { action: "cancel" };
  if (!isRecord(response)) throw new Error("elicitation handler must return an object");
  const action = String(response.action || "cancel");
  if (!["accept", "decline", "cancel"].includes(action)) {
    throw new Error("elicitation action must be accept, decline, or cancel");
  }
  const payload: Record<string, unknown> = { action };
  if (response.content !== undefined) {
    if (!isRecord(response.content)) throw new Error("elicitation content must be an object");
    payload.content = { ...response.content };
  }
  return payload;
}

function mcpParamField(params: unknown, ...names: string[]): unknown {
  const direct = fieldFromObject(params, names);
  if (direct !== undefined) return direct;
  return fieldFromObject(modelDump(params), names);
}

function fieldFromObject(value: unknown, names: string[]): unknown {
  if (!isRecord(value)) return undefined;
  for (const name of names) {
    if (name in value) return value[name];
  }
  return undefined;
}

function modelDump(value: unknown): unknown {
  if (!isRecord(value)) return undefined;
  const dump = value.model_dump || value.modelDump;
  if (typeof dump !== "function") return undefined;
  try {
    return dump.call(value, { by_alias: true });
  } catch {
    return dump.call(value);
  }
}

function optionalString(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined;
  const text = String(value);
  return text ? text : undefined;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}
