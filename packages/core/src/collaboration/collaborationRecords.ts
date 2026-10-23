import type { AgentProfileRecord, TeamMessageRecord, TeamRecord } from "../types/collaborationTypes.js";
import { publicSpec, specFromPayload } from "../types/agentTypes.js";

export function normalizeAgentProfile(rawProfile: Partial<AgentProfileRecord>): AgentProfileRecord {
  const storedSpec = rawProfile.spec as AgentProfileRecord["spec"] | undefined;
  return {
    agent_id: String(rawProfile.agent_id || storedSpec?.agent_id || "agent"),
    name: String(rawProfile.name || rawProfile.agent_id || storedSpec?.agent_id || "agent"),
    tenant_id: String(rawProfile.tenant_id || storedSpec?.tenant_id || ""),
    user_id: String(rawProfile.user_id || storedSpec?.user_id || ""),
    spec: storedSpec || publicSpec(specFromPayload({ message: "", agent_id: String(rawProfile.agent_id || "agent") })),
    created_at: Number(rawProfile.created_at || timestamp()),
    updated_at: Number(rawProfile.updated_at || timestamp())
  };
}

export function normalizeTeamRecord(rawTeam: Partial<TeamRecord>): TeamRecord {
  return {
    team_id: String(rawTeam.team_id || "default"),
    name: String(rawTeam.name || rawTeam.team_id || "default"),
    description: String(rawTeam.description || ""),
    members: normalizeTeamMembers(rawTeam.members),
    agent_id: String(rawTeam.agent_id || ""),
    tenant_id: String(rawTeam.tenant_id || ""),
    user_id: String(rawTeam.user_id || ""),
    workspace_id: String(rawTeam.workspace_id || ""),
    metadata: coerceStringRecord(rawTeam.metadata),
    created_at: Number(rawTeam.created_at || timestamp()),
    updated_at: Number(rawTeam.updated_at || timestamp())
  };
}

export function normalizeTeamMessage(rawMessage: Partial<TeamMessageRecord>): TeamMessageRecord {
  return {
    message_id: String(rawMessage.message_id || newRecordId("team_msg")),
    team_id: String(rawMessage.team_id || "default"),
    from_agent: String(rawMessage.from_agent || ""),
    to_agent: String(rawMessage.to_agent || ""),
    message_type: String(rawMessage.message_type || "message"),
    message: String(rawMessage.message || ""),
    read: Boolean(rawMessage.read),
    agent_id: String(rawMessage.agent_id || ""),
    tenant_id: String(rawMessage.tenant_id || ""),
    user_id: String(rawMessage.user_id || ""),
    workspace_id: String(rawMessage.workspace_id || ""),
    metadata: coerceStringRecord(rawMessage.metadata),
    created_at: Number(rawMessage.created_at || timestamp()),
    updated_at: Number(rawMessage.updated_at || timestamp())
  };
}

export function teamKey(team: TeamRecord): string {
  return [team.tenant_id, team.user_id, team.agent_id, team.workspace_id, team.team_id].join("\0");
}

function normalizeTeamMembers(rawMembers: unknown): TeamRecord["members"] {
  if (!rawMembers || typeof rawMembers !== "object" || Array.isArray(rawMembers)) return {};
  return Object.fromEntries(Object.entries(rawMembers).map(([agentId, rawMember]) => {
    const member = rawMember && typeof rawMember === "object" && !Array.isArray(rawMember) ? rawMember as Record<string, unknown> : {};
    return [agentId, {
      agent_id: String(member.agent_id || agentId),
      name: String(member.name || member.agent_id || agentId),
      role: String(member.role || ""),
      system_prompt: String(member.system_prompt || ""),
      enabled_tools: Array.isArray(member.enabled_tools) ? member.enabled_tools.map(String) : [],
      status: String(member.status || "idle")
    }];
  }));
}

function coerceStringRecord(rawRecord: unknown): Record<string, string> {
  if (!rawRecord || typeof rawRecord !== "object" || Array.isArray(rawRecord)) return {};
  return Object.fromEntries(Object.entries(rawRecord).map(([key, rawValue]) => [key, String(rawValue)]));
}

function timestamp(): number {
  return Date.now() / 1000;
}

function newRecordId(prefix: string): string {
  return `${prefix}_${crypto.randomUUID().replaceAll("-", "")}`;
}
