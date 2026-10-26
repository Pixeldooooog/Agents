import type { AgentProfileRecord, TeamMessageRecord, TeamRecord } from "../types/collaborationTypes.js";
import type { AgentProfileFilters, StoreScopeFilter, TeamMessageFilters } from "../store/storeFilters.js";

export type CollaborationStore = {
  saveAgentProfile(profile: AgentProfileRecord): Promise<AgentProfileRecord>;
  listAgentProfiles(filters?: AgentProfileFilters): Promise<AgentProfileRecord[]>;
  saveTeam(team: TeamRecord): Promise<TeamRecord>;
  loadTeam(teamId: string, filters?: StoreScopeFilter): Promise<TeamRecord | undefined>;
  deleteTeam(teamId: string, filters?: StoreScopeFilter): Promise<TeamRecord | undefined>;
  addTeamMessage(message: TeamMessageRecord): Promise<TeamMessageRecord>;
  listTeamMessages(filters?: TeamMessageFilters): Promise<TeamMessageRecord[]>;
  markTeamMessagesRead(messageIds: string[]): Promise<number>;
};
