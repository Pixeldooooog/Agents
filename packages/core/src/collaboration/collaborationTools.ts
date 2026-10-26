import { defineTool, type RegisteredTool } from "../tools/toolContracts.js";
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

export const collaborationToolDefinitions: RegisteredTool[] = [
  defineTool({
    name: "agent.profiles", parameters: agentProfilesSchema,
    description: "List saved agent profiles.",
    risk: "low",
    requires: [],
    uses: ["store"],
    handler: agentProfiles
  }),
  defineTool({
    name: "agent.save_profile", parameters: agentSaveProfileSchema,
    description: "Save the current or provided agent profile.",
    risk: "medium",
    requires: [],
    uses: ["store"],
    handler: agentSaveProfile
  }),
  defineTool({
    name: "agent.run",
    description: "Delegate work to a child agent.",
    risk: "high",
    parameters: agentRunSchema,
    requires: [],
    uses: ["store", "agentRunner"],
    handler: agentRunTool
  }),
  defineTool({
    name: "team.create",
    description: "Create or update a multi-agent team.",
    risk: "low",
    parameters: teamCreateSchema,
    requires: [],
    uses: ["store"],
    handler: teamCreate
  }),
  defineTool({ name: "team.delete", parameters: teamIdentitySchema, description: "Delete a team.", risk: "medium", requires: [], uses: ["store"], handler: teamDelete }),
  defineTool({ name: "team.members", parameters: teamIdentitySchema, description: "List team members.", risk: "low", requires: [], uses: ["store"], handler: teamMembers }),
  defineTool({
    name: "team.send",
    description: "Send a message to a team member.",
    risk: "low",
    parameters: sendSchema,
    requires: [],
    uses: ["store"],
    handler: teamSend
  }),
  defineTool({ name: "team.inbox", parameters: teamInboxSchema, description: "Read a team member inbox.", risk: "low", requires: [], uses: ["store"], handler: teamInbox }),
  defineTool({
    name: "team.run_member", parameters: teamRunMemberSchema,
    description: "Run a team member agent and deliver the result.",
    risk: "high",
    requires: [],
    uses: ["store", "agentRunner"],
    handler: teamRunMember
  })
];
