import type { AgentProfileRecord } from "../types/collaborationTypes.js";
import type { AgentSpec } from "../types/agentTypes.js";
import { publicSpec } from "../types/agentTypes.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { CollaborationToolContext } from "./collaborationState.js";
import { numberArg, stringArg } from "../tools/toolInputs.js";
import { childAgentSpec, currentSpec, requiredText, scope, stringList } from "./collaborationState.js";

export async function agentProfiles(context: CollaborationToolContext, args: JsonObject) {
  const profiles = context.store ? await context.store.listAgentProfiles(scope(context)) : [];
  const query = stringArg(args.query).toLowerCase();
  const matches = query ? profiles.filter((profile) => profileHaystack(profile).includes(query)) : profiles;
  const limit = Math.max(1, Math.min(100, numberArg(args.limit, 50)));
  return { profiles: matches.slice(0, limit), count: Math.min(matches.length, limit), total: profiles.length };
}

export async function agentSaveProfile(context: CollaborationToolContext, args: JsonObject) {
  if (!context.store) throw new Error("state store is not available");
  const base = currentSpec(context);
  const spec: AgentSpec = {
    ...base,
    agent_id: stringArg(args.agent_id, base.agent_id || "agent"),
    system_prompt: stringArg(args.system_prompt, base.system_prompt),
    enabled_tools: stringList(args.enabled_tools, base.enabled_tools),
    permission_profile: stringArg(args.permission_profile, base.permission_profile)
  };
  const now = Date.now() / 1000;
  const profile: AgentProfileRecord = {
    agent_id: spec.agent_id,
    name: stringArg(args.name, spec.agent_id),
    tenant_id: spec.tenant_id,
    user_id: spec.user_id,
    spec: publicSpec(spec),
    created_at: now,
    updated_at: now
  };
  return { profile: await context.store.saveAgentProfile(profile) };
}

export async function agentRunTool(context: CollaborationToolContext, args: JsonObject) {
  return runDelegatedAgent(context, args, false);
}

export async function runDelegatedAgent(context: CollaborationToolContext, args: JsonObject, runInBackground: boolean) {
  const prompt = requiredText(args.prompt, "prompt");
  const childSpec = childAgentSpec(context, args);
  const runId = `subagent_${crypto.randomUUID().replaceAll("-", "")}`;
  const description = stringArg(args.description);
  if (context.agentRunner && !runInBackground) {
    const result = await context.agentRunner.run({ spec: childSpec, prompt, runId, description });
    return {
      agent_id: childSpec.agent_id,
      run_id: runId,
      description,
      status: result.status,
      content: result.content,
      messages: result.messages?.length || 0,
      tool_results: result.tool_results?.length || 0
    };
  }
  const task = context.store
    ? await context.store.createTask(
      childSpec,
      prompt,
      stringArg(args.description, "Agent task"),
      { source: "agent.run" }
    )
    : undefined;
  return {
    agent_id: childSpec.agent_id,
    run_id: runId,
    description,
    status: runInBackground ? "async_launched" : "created",
    content: "",
    messages: 0,
    tool_results: 0,
    runner_available: Boolean(context.agentRunner),
    task
  };
}

function profileHaystack(profile: AgentProfileRecord): string {
  return `${profile.agent_id} ${profile.name} ${JSON.stringify(profile.spec)}`.toLowerCase();
}
