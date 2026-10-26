import type { RuntimeOptions } from "../runtime/runtimeOptions.js";
import type { AgentSpec } from "../types/agentTypes.js";
import type { HookEvent, HookRecord } from "../types/hookTypes.js";
import { runtimeEvent, type Message, type RuntimeEvent } from "../types/runtimeTypes.js";
import { hookScopeFromSpec } from "./hookScopes.js";

const ACTIONS: Record<HookEvent, readonly string[]> = {
  before_request: ["record", "append_system", "append_user"],
  after_response: ["record"], pre_tool_use: ["record", "deny_tool"], post_tool_use: ["record"],
  worktree_create: ["record"], worktree_remove: ["record"]
};

export function validateExecutableHook(hook: Pick<HookRecord, "event" | "action" | "content" | "metadata">): void {
  if (!ACTIONS[hook.event]?.includes(hook.action)) throw new Error(`unsupported hook action ${hook.action} for ${hook.event}`);
  if (Buffer.byteLength(hook.content) > 4096) throw new Error("hook content exceeds 4 KiB");
  const matcher = hook.metadata.tool;
  if (matcher && !/^(?:\*|[a-zA-Z0-9_.-]+\*?)$/.test(matcher)) throw new Error("hook matcher must be an exact tool name or a trailing wildcard");
}

export async function dispatchRuntimeHooks(options: RuntimeOptions, spec: AgentSpec, event: HookEvent, toolName?: string): Promise<{
  events: RuntimeEvent[]; messages: Message[]; denied: boolean;
}> {
  const result = { events: [] as RuntimeEvent[], messages: [] as Message[], denied: false };
  if (!options.store) return result;
  const control = event === "before_request" || event === "pre_tool_use";
  try {
    const hooks = await readHooks(options, spec, event);
    // Store list APIs are capped at 100; never silently omit a control hook beyond the cap.
    if (hooks.length >= 100) throw new Error("runtime hook limit reached (maximum 99 per event)");
    let contentBytes = 0;
    for (const hook of hooks.sort((a, b) => a.created_at - b.created_at || a.hook_id.localeCompare(b.hook_id))) {
      options.signal?.throwIfAborted();
      // Empty request scope must not select another tenant's records.
      if (hook.tenant_id !== spec.tenant_id || (hook.user_id && hook.user_id !== spec.user_id) || (hook.agent_id && hook.agent_id !== spec.agent_id) || (hook.workspace_id && hook.workspace_id !== spec.workspace_id)) continue;
      if (!matchesTool(hook.metadata.tool, toolName)) continue;
      validateExecutableHook(hook);
      contentBytes += Buffer.byteLength(hook.content);
      if (contentBytes > 64 * 1024) throw new Error("hook guidance exceeds 64 KiB per event");
      if (hook.action === "deny_tool") result.denied = true;
      if (hook.action === "append_system" || hook.action === "append_user") result.messages.push({ role: hook.action === "append_system" ? "system" : "user", content: hook.content });
      result.events.push(runtimeEvent("hook_executed", { hook_id: hook.hook_id, event, action: hook.action, tool: toolName, denied: hook.action === "deny_tool" }));
    }
  } catch (error) {
    if (control) options.signal?.throwIfAborted();
    if (control) throw new Error(`control hook failed: ${error instanceof Error ? error.message : String(error)}`);
    result.events.push(runtimeEvent("hook_error", { event, message: error instanceof Error ? error.message : String(error) }));
  }
  return result;
}

function matchesTool(pattern: string | undefined, name?: string): boolean {
  if (!pattern || pattern === "*") return true;
  if (!name) return false;
  return pattern.endsWith("*") ? name.startsWith(pattern.slice(0, -1)) : name === pattern;
}

async function readHooks(options: RuntimeOptions, spec: AgentSpec, event: HookEvent): Promise<HookRecord[]> {
  const deadline = new AbortController();
  const signal = options.signal ? AbortSignal.any([options.signal, deadline.signal]) : deadline.signal;
  signal.throwIfAborted();
  const timer = setTimeout(() => deadline.abort(new Error("hook store timed out")), 5000);
  let onAbort = () => {};
  try {
    return await Promise.race([
      options.store!.listHooks({ ...hookScopeFromSpec(spec), event, enabled: true, limit: 100 }),
      new Promise<never>((_, reject) => {
        onAbort = () => reject(signal.reason);
        signal.addEventListener("abort", onAbort, { once: true });
        if (signal.aborted) onAbort();
      })
    ]);
  } finally { clearTimeout(timer); signal.removeEventListener("abort", onAbort); }
}
