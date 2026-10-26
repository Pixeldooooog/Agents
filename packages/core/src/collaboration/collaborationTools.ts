import type { ToolDefinition } from "../tools/toolContracts.js";
import { agentProfiles, agentRunTool, agentSaveProfile } from "./collaborationAgentActions.js";
import {
  teamCreate,
  teamDelete,
  teamInbox,
  teamMembers,
  teamRunMember,
  teamSend
} from "./collaborationTeamActions.js";
import { agentRunSchema, sendSchema, teamCreateSchema, agentProfilesSchema, agentSaveProfileSchema, teamIdentitySchema, teamInboxSchema, teamRunMemberSchema } from "./collaborationToolSchemas.js";

export const collaborationToolDefinitions: ToolDefinition[] = [
  {
    name: "agent.profiles", parameters: agentProfilesSchema,
    description: "List saved agent profiles.",
    risk: "low",
    handler: agentProfiles
  },
  {
    name: "agent.save_profile", parameters: agentSaveProfileSchema,
    description: "Save the current or provided agent profile.",
    risk: "medium",
    handler: agentSaveProfile
  },
  {
    name: "agent.run",
    description: "Delegate work to a child agent.",
    risk: "high",
    parameters: agentRunSchema,
    handler: agentRunTool
  },
  {
    name: "team.create",
    description: "Create or update a multi-agent team.",
    risk: "low",
    parameters: teamCreateSchema,
    handler: teamCreate
  },
  { name: "team.delete", parameters: teamIdentitySchema, description: "Delete a team.", risk: "medium", handler: teamDelete },
  { name: "team.members", parameters: teamIdentitySchema, description: "List team members.", risk: "low", handler: teamMembers },
  {
    name: "team.send",
    description: "Send a message to a team member.",
    risk: "low",
    parameters: sendSchema,
    handler: teamSend
  },
  { name: "team.inbox", parameters: teamInboxSchema, description: "Read a team member inbox.", risk: "low", handler: teamInbox },
  {
    name: "team.run_member", parameters: teamRunMemberSchema,
    description: "Run a team member agent and deliver the result.",
    risk: "high",
    handler: teamRunMember
  }
];
