import { AgentRunService, JsonStateStore, TaskService, loadSettings, statePath } from "@agents/core";

export type HostServices = Awaited<ReturnType<typeof createHostServices>>;

export async function createHostServices(repoRoot = process.cwd()) {
  const settings = await loadSettings(repoRoot);
  const store = new JsonStateStore(statePath(settings.repoRoot, settings.agent.statePath));
  const tasks = new TaskService(settings, store);
  const runs = new AgentRunService({ settings, store, taskRunner: tasks });
  return {
    settings,
    store,
    tasks,
    runs
  };
}
