import type { AgentProfileRecord, TeamMessageRecord, TeamRecord } from "../types/collaborationTypes.js";
import {
  normalizeAgentProfile,
  normalizeTeamMessage,
  normalizeTeamRecord,
  teamKey
} from "../collaboration/collaborationRecords.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";
import type { AgentProfileFilters, StoreScopeFilter, TeamMessageFilters } from "./storeFilters.js";
import { clampLimit, matchesScope, timestamp } from "./storeHelpers.js";

export function saveAgentProfileRecord(mutate: MutateState, profile: AgentProfileRecord): Promise<AgentProfileRecord> {
  return mutate((state) => {
    const saved = normalizeAgentProfile({ ...profile, updated_at: timestamp() });
    const index = state.agentProfiles.findIndex((item) => item.tenant_id === saved.tenant_id && item.user_id === saved.user_id && item.agent_id === saved.agent_id);
    if (index >= 0) state.agentProfiles[index] = saved;
    else state.agentProfiles.unshift(saved);
    return saved;
  });
}

export async function listAgentProfileRecords(read: ReadState, filters: AgentProfileFilters = {}): Promise<AgentProfileRecord[]> {
  return (await read()).agentProfiles
    .map(normalizeAgentProfile)
    .filter((profile) => (!filters.tenant_id || profile.tenant_id === filters.tenant_id) && (!filters.user_id || profile.user_id === filters.user_id))
    .sort((a, b) => b.updated_at - a.updated_at || a.agent_id.localeCompare(b.agent_id));
}

export function saveTeamRecord(mutate: MutateState, team: TeamRecord): Promise<TeamRecord> {
  return mutate((state) => {
    const saved = normalizeTeamRecord({ ...team, updated_at: timestamp() });
    const index = state.teams.findIndex((item) => teamKey(item) === teamKey(saved));
    if (index >= 0) state.teams[index] = saved;
    else state.teams.unshift(saved);
    return saved;
  });
}

export async function loadTeamRecord(read: ReadState, teamId: string, filters: StoreScopeFilter = {}): Promise<TeamRecord | undefined> {
  return (await read()).teams.map(normalizeTeamRecord).find((team) => team.team_id === teamId && matchesScope(team, filters));
}

export function deleteTeamRecord(mutate: MutateState, teamId: string, filters: StoreScopeFilter = {}): Promise<TeamRecord | undefined> {
  return mutate((state) => {
    const index = state.teams.findIndex((team) => team.team_id === teamId && matchesScope(team, filters));
    if (index < 0) return undefined;
    const [deleted] = state.teams.splice(index, 1);
    state.teamMessages = state.teamMessages.filter((message) => message.team_id !== teamId || !matchesScope(message, filters));
    return normalizeTeamRecord(deleted);
  });
}

export function addTeamMessageRecord(mutate: MutateState, message: TeamMessageRecord): Promise<TeamMessageRecord> {
  return mutate((state) => {
    const saved = normalizeTeamMessage({ ...message, updated_at: timestamp() });
    state.teamMessages.push(saved);
    return saved;
  });
}

export async function listTeamMessageRecords(read: ReadState, filters: TeamMessageFilters = {}): Promise<TeamMessageRecord[]> {
  const limit = clampLimit(filters.limit, 50, 100);
  return (await read()).teamMessages
    .map(normalizeTeamMessage)
    .filter((message) => matchesScope(message, filters)
      && (!filters.team_id || message.team_id === filters.team_id)
      && (!filters.to_agent || message.to_agent === filters.to_agent)
      && (!filters.unread_only || !message.read))
    .sort((a, b) => a.created_at - b.created_at || a.message_id.localeCompare(b.message_id))
    .slice(-limit);
}

export function markTeamMessageRecordsRead(mutate: MutateState, messageIds: string[]): Promise<number> {
  return mutate((state) => {
    const ids = new Set(messageIds);
    let count = 0;
    for (const message of state.teamMessages) {
      if (!ids.has(message.message_id) || message.read) continue;
      message.read = true;
      message.updated_at = timestamp();
      count += 1;
    }
    return count;
  });
}
