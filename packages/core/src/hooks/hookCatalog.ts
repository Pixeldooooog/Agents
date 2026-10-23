import type { HookAction, HookEvent } from "../types/hookTypes.js";

export const hookEvents: HookEvent[] = ["before_request", "after_response", "pre_tool_use", "post_tool_use", "worktree_create", "worktree_remove"];
export const hookActions: HookAction[] = ["append_system", "append_user", "record", "deny_tool", "run_command"];

export function normalizeHookEvent(value: unknown): HookEvent {
  const normalized = String(value || "").trim().replace(/-/g, "_").toLowerCase();
  const aliases: Record<string, HookEvent> = {
    beforerequest: "before_request",
    before_request: "before_request",
    afterresponse: "after_response",
    after_response: "after_response",
    pretooluse: "pre_tool_use",
    pre_tool_use: "pre_tool_use",
    pretool: "pre_tool_use",
    posttooluse: "post_tool_use",
    post_tool_use: "post_tool_use",
    posttool: "post_tool_use",
    worktreecreate: "worktree_create",
    worktree_create: "worktree_create",
    worktree: "worktree_create",
    worktreeremove: "worktree_remove",
    worktree_remove: "worktree_remove"
  };
  const event = aliases[normalized] || normalized;
  if (hookEvents.includes(event as HookEvent)) return event as HookEvent;
  throw new Error(`unknown hook event: ${value}`);
}

export function normalizeHookAction(value: unknown): HookAction {
  const normalized = String(value || "").trim().replace(/-/g, "_").toLowerCase();
  const action = ({ command: "run_command", runcommand: "run_command" } as Record<string, string>)[normalized] || normalized;
  if (hookActions.includes(action as HookAction)) return action as HookAction;
  throw new Error(`unknown hook action: ${value}`);
}
