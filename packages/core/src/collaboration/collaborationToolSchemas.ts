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
