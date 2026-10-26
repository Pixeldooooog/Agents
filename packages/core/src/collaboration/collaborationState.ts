import type { AgentSpec } from "../types/agentTypes.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { TeamMemberRecord, TeamMessageRecord, TeamRecord } from "../types/collaborationTypes.js";
import { specFromPayload } from "../types/agentTypes.js";
import type { ToolContext } from "../tools/toolContracts.js";

export type CollaborationToolContext = ToolContext<never, "store" | "agentRunner">;
import { stringArg } from "../tools/toolInputs.js";

export function childAgentSpec(context: CollaborationToolContext, args: JsonObject): AgentSpec {
  const base = currentSpec(context);
  return {
    ...base,
    agent_id: safeId(stringArg(args.agent_id, `agent_${crypto.randomUUID().slice(0, 8)}`)),
    system_prompt: stringArg(args.system_prompt, base.system_prompt),
    enabled_tools: stringList(args.enabled_tools, base.enabled_tools)
  };
}

export function currentSpec(context: CollaborationToolContext): AgentSpec {
  return context.spec || specFromPayload({ message: "" });
}

export async function requireTeam(context: CollaborationToolContext, teamId: string): Promise<TeamRecord> {
  if (!context.store) throw new Error("state store is not available");
  const team = await context.store.loadTeam(safeId(teamId || "default"), scope(context));
  if (!team) throw new Error(`team not found: ${teamId || "default"}`);
  return team;
}

export function memberPayload(context: CollaborationToolContext, raw: Record<string, unknown>): TeamMemberRecord {
  const agentId = safeId(raw.agent_id);
  if (!agentId) throw new Error("member agent_id is required");
  return {
    agent_id: agentId,
    name: stringArg(raw.name, agentId),
    role: stringArg(raw.role),
    system_prompt: stringArg(raw.system_prompt),
    enabled_tools: stringList(raw.enabled_tools, context.spec?.enabled_tools || []),
    status: "idle"
  };
}

export function teamMessage(context: CollaborationToolContext, teamId: string, fromAgent: string, toAgent: string, message: string, messageType: string, metadata: Record<string, string> = {}): TeamMessageRecord {
  const now = Date.now() / 1000;
  return {
    ...scope(context),
    message_id: `team_msg_${crypto.randomUUID().replaceAll("-", "")}`,
    team_id: teamId,
    from_agent: safeId(fromAgent),
    to_agent: safeId(toAgent),
    message_type: messageType,
    message,
    read: false,
    metadata,
    created_at: now,
    updated_at: now
  };
}

export function teamPayload(team: TeamRecord) {
  return {
    team_id: team.team_id,
    name: team.name,
    description: team.description,
    member_count: Object.keys(team.members).length,
    created_at: team.created_at,
    updated_at: team.updated_at
  };
}

export function scope(context: CollaborationToolContext) {
  return {
    tenant_id: context.spec?.tenant_id || "",
    user_id: context.spec?.user_id || "",
    agent_id: context.spec?.agent_id || "",
    workspace_id: context.spec?.workspace_id || ""
  };
}

export function safeId(value: unknown): string {
  return String(value || "").trim().replace(/[^A-Za-z0-9_.-]+/g, "-").replace(/^[.-]+|[.-]+$/g, "");
}

export function stringList(value: unknown, fallback: string[] = []): string[] {
  return Array.isArray(value) ? value.map(String).filter(Boolean) : fallback;
}

export function objectList(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.filter((item) => item && typeof item === "object" && !Array.isArray(item)) as Record<string, unknown>[] : [];
}

export function requiredText(value: unknown, name: string): string {
  const text = stringArg(value);
  if (!text) throw new Error(`${name} is required`);
  return text;
}
