import type { StateStore } from "../ports/stateStore.js";
import { JsonStatePersistence } from "./jsonStatePersistence.js";
import { jsonCollaborationStoreMethods } from "./jsonCollaborationStore.js";
import { jsonMcpStoreMethods } from "./jsonMcpStore.js";
import { jsonMemoryStoreMethods } from "./jsonMemoryStore.js";
import { jsonPlanningHookStoreMethods } from "./jsonPlanningHookStore.js";
import { jsonRunStoreMethods, type JsonStateAccess } from "./jsonRunStore.js";
import { jsonScheduleStoreMethods } from "./jsonScheduleStore.js";
import { jsonTaskStoreMethods } from "./jsonTaskStore.js";

export { statePath } from "./storeHelpers.js";

export interface JsonStateStore extends StateStore {}

export class JsonStateStore {
  private readonly persistence: JsonStatePersistence;

  constructor(filename: string) {
    this.persistence = new JsonStatePersistence(filename);
    const access = this.stateAccess();
    Object.assign(
      this,
      jsonRunStoreMethods(access),
      jsonTaskStoreMethods(access),
      jsonScheduleStoreMethods(access),
      jsonMemoryStoreMethods(access),
      jsonPlanningHookStoreMethods(access),
      jsonMcpStoreMethods(access),
      jsonCollaborationStoreMethods(access)
    );
  }

  private stateAccess(): JsonStateAccess {
    return {
      read: () => this.persistence.read(),
      mutate: (change) => this.persistence.mutate(change)
    };
  }
}
