import type { McpProvider, ToolExecutionContext } from "../tools/toolContracts.js";

type ProviderState = { controller: AbortController; closing?: Promise<void> };
const states = new WeakMap<McpProvider, ProviderState>();

export class McpCallInterruptedError extends Error {
  constructor(readonly code: "cancelled" | "revoked" | "timeout", cause?: unknown) {
    super(code === "timeout" ? "MCP call timed out" : `MCP call ${code}`, { cause });
    this.name = "McpCallInterruptedError";
  }
}

function stateFor(provider: McpProvider): ProviderState {
  let state = states.get(provider);
  if (!state) {
    state = { controller: new AbortController() };
    states.set(provider, state);
  }
  return state;
}

export function isMcpProviderActive(provider: McpProvider): boolean {
  return !states.get(provider)?.controller.signal.aborted;
}

export function mcpTimeoutMilliseconds(context: ToolExecutionContext): number {
  const seconds = context.settings?.mcp.clientTimeout ?? 30;
  if (!Number.isFinite(seconds) || seconds <= 0 || seconds > 2147483) throw new Error("invalid MCP client timeout");
  return Math.ceil(seconds * 1000);
}

/** Cancellation stops waiting even if an injected provider ignores its signal. */
export async function callMcpProvider<T>(
  context: ToolExecutionContext,
  provider: McpProvider,
  call: (signal: AbortSignal) => Promise<T>
): Promise<T> {
  const signals = [stateFor(provider).controller.signal];
  if (context.signal) signals.push(context.signal);
  return boundedCall(call, mcpTimeoutMilliseconds(context), signals);
}

export async function closeMcpProviders(providers: McpProvider[], timeoutMs = 30_000): Promise<void> {
  const unique = [...new Set(providers)];
  // Revoke every provider before waiting for any close operation.
  for (const provider of unique) stateFor(provider).controller.abort(new McpCallInterruptedError("revoked"));
  const results = await Promise.allSettled(unique.map(provider => {
    const state = stateFor(provider);
    state.closing ??= boundedCall(async () => { await provider.close?.(); }, timeoutMs, []);
    return state.closing;
  }));
  const failures = results.flatMap(result => result.status === "rejected" ? [result.reason] : []);
  if (failures.length) throw new AggregateError(failures, "failed to close MCP providers");
}

async function boundedCall<T>(call: (signal: AbortSignal) => Promise<T>, timeoutMs: number, signals: AbortSignal[]): Promise<T> {
  const deadline = new AbortController();
  const signal = AbortSignal.any([...signals, deadline.signal]);
  const interrupted = () => signal.reason instanceof McpCallInterruptedError
    ? signal.reason
    : new McpCallInterruptedError(deadline.signal.aborted ? "timeout" : "cancelled", signal.reason);
  if (signal.aborted) throw interrupted();
  const timer = setTimeout(() => deadline.abort(new Error("MCP request timed out")), timeoutMs);
  let onAbort: () => void = () => {};
  try {
    const cancellation = new Promise<never>((_, reject) => {
      onAbort = () => reject(interrupted());
      signal.addEventListener("abort", onAbort, { once: true });
    });
    const result = await Promise.race([Promise.resolve().then(() => {
      if (signal.aborted) throw interrupted();
      return call(signal);
    }), cancellation]);
    if (signal.aborted) throw interrupted();
    return result;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener("abort", onAbort);
  }
}
