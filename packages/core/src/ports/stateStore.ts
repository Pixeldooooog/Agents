import type { RunStore } from "./runStore.js";
import type { TaskStore } from "./taskStore.js";
import type { ScheduleStore } from "./scheduleStore.js";
import type { MemoryStore } from "./memoryStore.js";
import type { PlanningHookStore } from "./planningHookStore.js";
import type { McpStore } from "./mcpStore.js";
import type { CollaborationStore } from "./collaborationStore.js";

/** Existing runtime storage port; durable transactions are a separate B2 contract. */
export interface StateStore extends RunStore, TaskStore, ScheduleStore, MemoryStore, PlanningHookStore, McpStore, CollaborationStore {}
