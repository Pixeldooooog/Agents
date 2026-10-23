import type { TeamRecord } from "../types/collaborationTypes.js";
import type { JsonObject } from "../types/jsonTypes.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";
import { booleanArg, numberArg, stringArg } from "../tools/toolInputs.js";
import { memberPayload, objectList, requireTeam, safeId, scope, teamMessage, teamPayload } from "./collaborationState.js";
import { runDelegatedAgent } from "./collaborationAgentActions.js";

export async function teamCreate(context: ToolExecutionContext, args: JsonObject) {
  if (!context.store) throw new Error("state store is not available");
  const now = Date.now() / 1000;
  const teamId = safeId(stringArg(args.team_id, "default"));
  const existing = await context.store.loadTeam(teamId, scope(context));
  const members = { ...(existing?.members || {}) };
  for (const member of objectList(args.members)) members[safeId(member.agent_id)] = memberPayload(context, member);
  const team: TeamRecord = {
    ...scope(context),
    team_id: teamId,
    name: stringArg(args.name, existing?.name || teamId),
    description: stringArg(args.description, existing?.description || ""),
    members,
    metadata: existing?.metadata || {},
    created_at: existing?.created_at || now,
    updated_at: now
  };
  return { team: teamPayload(await context.store.saveTeam(team)) };
}

export async function teamMembers(context: ToolExecutionContext, args: JsonObject) {
  const team = await requireTeam(context, stringArg(args.team_id, "default"));
  const members = Object.values(team.members);
  return { team: teamPayload(team), members, count: members.length };
}

export async function teamDelete(context: ToolExecutionContext, args: JsonObject = {}) {
  if (!context.store) throw new Error("state store is not available");
  const teamId = safeId(stringArg(args.team_id, "default"));
  const deleted = await context.store.deleteTeam(teamId, scope(context));
  if (!deleted) throw new Error(`team not found: ${teamId}`);
  return {
    success: true,
    deleted: true,
    team: teamPayload(deleted),
    team_name: deleted.name,
    message: `Deleted team ${deleted.name}`
  };
}

export async function teamSend(context: ToolExecutionContext, args: JsonObject) {
  if (!context.store) throw new Error("state store is not available");
  const team = await requireTeam(context, stringArg(args.team_id, "default"));
  const recipients = stringArg(args.to) === "*"
    ? Object.keys(team.members)
    : [safeId(stringArg(args.to))].filter((id) => team.members[id]);
  if (!recipients.length) throw new Error(`team recipient not found: ${stringArg(args.to)}`);
  const sent = [];
  for (const recipient of recipients) {
    const message = teamMessage(
      context,
      team.team_id,
      stringArg(args.from_agent, context.spec?.agent_id || "agent"),
      recipient,
      String(args.message || ""),
      stringArg(args.message_type, "message")
    );
    sent.push(await context.store.addTeamMessage(message));
  }
  return { sent, count: sent.length };
}

export async function teamInbox(context: ToolExecutionContext, args: JsonObject) {
  if (!context.store) throw new Error("state store is not available");
  const agentId = safeId(stringArg(args.agent_id, context.spec?.agent_id || "agent"));
  const messages = await context.store.listTeamMessages({
    ...scope(context),
    team_id: stringArg(args.team_id),
    to_agent: agentId,
    unread_only: args.unread_only !== false,
    limit: numberArg(args.limit, 50)
  });
  if (booleanArg(args.mark_read)) {
    await context.store.markTeamMessagesRead(messages.map((message) => message.message_id));
  }
  return { agent_id: agentId, messages, count: messages.length, total: messages.length };
}

export async function teamRunMember(context: ToolExecutionContext, args: JsonObject) {
  const team = await requireTeam(context, stringArg(args.team_id, "default"));
  const member = team.members[safeId(stringArg(args.agent_id))];
  if (!member) throw new Error(`team member not found: ${stringArg(args.agent_id)}`);
  const result = await runDelegatedAgent(context, {
    prompt: args.prompt,
    description: member.role || member.name,
    agent_id: member.agent_id,
    system_prompt: member.system_prompt,
    enabled_tools: member.enabled_tools
  }, false);
  const delivered = context.store
    ? await context.store.addTeamMessage(teamMessage(
      context,
      team.team_id,
      member.agent_id,
      stringArg(args.reply_to, context.spec?.agent_id || "agent"),
      String(result.content || ""),
      "agent_result",
      { run_id: String(result.run_id), status: String(result.status) }
    ))
    : undefined;
  return { member, result, delivered };
}
