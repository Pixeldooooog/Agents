import { JsonStatePersistence } from "./jsonStatePersistence.js";
import { jsonCollaborationStoreMethods, type JsonCollaborationStoreMethods } from "./jsonCollaborationStore.js";
import { jsonMcpStoreMethods, type JsonMcpStoreMethods } from "./jsonMcpStore.js";
import { jsonMemoryStoreMethods, type JsonMemoryStoreMethods } from "./jsonMemoryStore.js";
import { jsonPlanningHookStoreMethods, type JsonPlanningHookStoreMethods } from "./jsonPlanningHookStore.js";
import { jsonRunStoreMethods, type JsonRunStoreMethods, type JsonStateAccess } from "./jsonRunStore.js";
import { jsonScheduleStoreMethods, type JsonScheduleStoreMethods } from "./jsonScheduleStore.js";
import { jsonTaskStoreMethods, type JsonTaskStoreMethods } from "./jsonTaskStore.js";

export { statePath } from "./storeHelpers.js";

export interface JsonStateStore extends
  JsonRunStoreMethods,
  JsonTaskStoreMethods,
  JsonScheduleStoreMethods,
  JsonMemoryStoreMethods,
  JsonPlanningHookStoreMethods,
  JsonMcpStoreMethods,
  JsonCollaborationStoreMethods {}

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
