export const agentRunSchema = {
  type: "object",
  properties: {
    prompt: { type: "string" },
    description: { type: "string" },
    agent_id: { type: "string" },
    system_prompt: { type: "string" },
    enabled_tools: { type: "array", items: { type: "string" } },
    isolation: { type: "string", enum: ["worktree", "remote"] },
    cwd: { type: "string" }
  },
  required: ["prompt"]
};

export const teamCreateSchema = {
  type: "object",
  properties: {
    team_id: { type: "string" },
    name: { type: "string" },
    description: { type: "string" },
    members: { type: "array", items: { type: "object" } }
  }
};

export const sendSchema = {
  type: "object",
  properties: {
    to: { type: "string" },
    message: {},
    team_id: { type: "string" },
    from_agent: { type: "string" },
    message_type: { type: "string" },
    summary: { type: "string" },
    team_name: { type: "string" }
  },
  required: ["to", "message"]
};

export const agentProfilesSchema = { type: "object", properties: { query: { type: "string" }, limit: { type: "integer", minimum: 1, maximum: 100 } } };
export const agentSaveProfileSchema = { type: "object", properties: {
  agent_id: { type: "string" }, name: { type: "string" }, system_prompt: { type: "string" },
  enabled_tools: { type: "array", items: { type: "string" } }, permission_profile: { type: "string" }
} };
export const teamIdentitySchema = { type: "object", properties: { team_id: { type: "string" } } };
export const teamInboxSchema = { type: "object", properties: {
  team_id: { type: "string" }, agent_id: { type: "string" }, unread_only: { type: "boolean" },
  mark_read: { type: "boolean" }, limit: { type: "integer", minimum: 1, maximum: 1000 }
} };
export const teamRunMemberSchema = { type: "object", properties: {
  team_id: { type: "string" }, agent_id: { type: "string", minLength: 1 }, prompt: { type: "string", minLength: 1 }, reply_to: { type: "string" }
}, required: ["agent_id", "prompt"] };
