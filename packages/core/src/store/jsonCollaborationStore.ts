import type { AgentProfileRecord, TeamMessageRecord, TeamRecord } from "../types/collaborationTypes.js";
import {
  addTeamMessageRecord,
  deleteTeamRecord,
  listAgentProfileRecords,
  listTeamMessageRecords,
  loadTeamRecord,
  markTeamMessageRecordsRead,
  saveAgentProfileRecord,
  saveTeamRecord
} from "./collaborationStateStore.js";
import type { JsonStateAccess } from "./jsonRunStore.js";
import type { AgentProfileFilters, StoreScopeFilter, TeamMessageFilters } from "./storeFilters.js";

export type JsonCollaborationStoreMethods = {
  saveAgentProfile(profile: AgentProfileRecord): Promise<AgentProfileRecord>;
  listAgentProfiles(filters?: AgentProfileFilters): Promise<AgentProfileRecord[]>;
  saveTeam(team: TeamRecord): Promise<TeamRecord>;
  loadTeam(teamId: string, filters?: StoreScopeFilter): Promise<TeamRecord | undefined>;
  deleteTeam(teamId: string, filters?: StoreScopeFilter): Promise<TeamRecord | undefined>;
  addTeamMessage(message: TeamMessageRecord): Promise<TeamMessageRecord>;
  listTeamMessages(filters?: TeamMessageFilters): Promise<TeamMessageRecord[]>;
  markTeamMessagesRead(messageIds: string[]): Promise<number>;
};

export function jsonCollaborationStoreMethods(access: JsonStateAccess): JsonCollaborationStoreMethods {
  return {
    saveAgentProfile: (profile) => saveAgentProfileRecord(access.mutate, profile),
    listAgentProfiles: (filters = {}) => listAgentProfileRecords(access.read, filters),
    saveTeam: (team) => saveTeamRecord(access.mutate, team),
    loadTeam: (teamId, filters = {}) => loadTeamRecord(access.read, teamId, filters),
    deleteTeam: (teamId, filters = {}) => deleteTeamRecord(access.mutate, teamId, filters),
    addTeamMessage: (message) => addTeamMessageRecord(access.mutate, message),
    listTeamMessages: (filters = {}) => listTeamMessageRecords(access.read, filters),
    markTeamMessagesRead: (messageIds) => markTeamMessageRecordsRead(access.mutate, messageIds)
  };
}
