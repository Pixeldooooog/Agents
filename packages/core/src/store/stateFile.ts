import { normalizeAgentProfile, normalizeTeamMessage, normalizeTeamRecord } from "../collaboration/collaborationRecords.js";
import { normalizeHookRecord } from "../hooks/hookRecords.js";
import { normalizeMemoryRecord } from "../memory/memoryRecords.js";
import { normalizeMcpServerRecord } from "../mcp/mcpStoredRecords.js";
import { normalizePlanningState } from "../planning/planningState.js";
import { normalizeScheduleRecord } from "../schedules/scheduleRecords.js";
import type { AgentProfileRecord, TeamMessageRecord, TeamRecord } from "../types/collaborationTypes.js";
import type { HookRecord } from "../types/hookTypes.js";
import type { McpServerRecord } from "../types/mcpTypes.js";
import type { MemoryRecord } from "../types/memoryTypes.js";
import type { PlanningStateRecord } from "../types/planningTypes.js";
import type { RunRecord } from "../types/runtimeTypes.js";
import type { ScheduleRecord } from "../types/scheduleTypes.js";
import type { TaskRecord, TaskStepRecord } from "../types/taskTypes.js";

export type StateFile = {
  runs: RunRecord[];
  tasks: TaskRecord[];
  steps: TaskStepRecord[];
  schedules: ScheduleRecord[];
  memories: MemoryRecord[];
  planning: PlanningStateRecord[];
  hooks: HookRecord[];
  mcpServers: McpServerRecord[];
  agentProfiles: AgentProfileRecord[];
  teams: TeamRecord[];
  teamMessages: TeamMessageRecord[];
};

export function emptyState(): StateFile {
  return {
    runs: [],
    tasks: [],
    steps: [],
    schedules: [],
    memories: [],
    planning: [],
    hooks: [],
    mcpServers: [],
    agentProfiles: [],
    teams: [],
    teamMessages: []
  };
}

export function normalizeState(rawState: Partial<StateFile>): StateFile {
  return {
    ...emptyState(),
    runs: Array.isArray(rawState.runs) ? rawState.runs : [],
    tasks: Array.isArray(rawState.tasks) ? rawState.tasks : [],
    steps: Array.isArray(rawState.steps) ? rawState.steps : [],
    schedules: Array.isArray(rawState.schedules) ? rawState.schedules.map(normalizeScheduleRecord) : [],
    memories: Array.isArray(rawState.memories) ? rawState.memories.map(normalizeMemoryRecord) : [],
    planning: Array.isArray(rawState.planning) ? rawState.planning.map(normalizePlanningState) : [],
    hooks: Array.isArray(rawState.hooks) ? rawState.hooks.map(normalizeHookRecord) : [],
    mcpServers: Array.isArray(rawState.mcpServers) ? rawState.mcpServers.map(normalizeMcpServerRecord) : [],
    agentProfiles: Array.isArray(rawState.agentProfiles) ? rawState.agentProfiles.map(normalizeAgentProfile) : [],
    teams: Array.isArray(rawState.teams) ? rawState.teams.map(normalizeTeamRecord) : [],
    teamMessages: Array.isArray(rawState.teamMessages) ? rawState.teamMessages.map(normalizeTeamMessage) : []
  };
}
