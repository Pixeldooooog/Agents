import {
  normalizeHookRecord
} from "../hooks/hookRecords.js";
import { hookMatchesScope, type HookScopeFilter } from "../hooks/hookScopes.js";
import type { HookRecord } from "../types/hookTypes.js";
import type { MutateState, ReadState } from "./stateStoreAccess.js";
import { clampLimit, timestamp } from "./storeHelpers.js";

export function saveHookRecord(mutate: MutateState, hook: HookRecord): Promise<HookRecord> {
  return mutate((state) => {
    const saved = normalizeHookRecord({ ...hook, updated_at: timestamp() });
    const index = state.hooks.findIndex((item) => item.hook_id === saved.hook_id);
    if (index >= 0) state.hooks[index] = saved;
    else state.hooks.unshift(saved);
    return saved;
  });
}

export async function listHookRecords(read: ReadState, filters: HookScopeFilter = {}): Promise<HookRecord[]> {
  const limit = clampLimit(filters.limit, 50, 100);
  return (await read()).hooks
    .map(normalizeHookRecord)
    .filter((hook) => hookMatchesScope(hook, filters))
    .sort((a, b) => b.updated_at - a.updated_at || a.hook_id.localeCompare(b.hook_id))
    .slice(0, limit);
}

export function deleteHookRecord(mutate: MutateState, hookId: string): Promise<boolean> {
  return mutate((state) => {
    const before = state.hooks.length;
    state.hooks = state.hooks.filter((item) => item.hook_id !== hookId);
    return state.hooks.length !== before;
  });
}
