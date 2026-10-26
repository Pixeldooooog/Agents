import { Match, Switch, createSignal, createMemo, onMount } from "solid-js";
import { ChatThread } from "../components/ChatThread";
import { OperationStage } from "../components/OperationStage";
import { RunsView } from "../components/RunsView";
import { SettingsView } from "../components/SettingsView";
import { TasksView } from "../components/TasksView";
import { TopBar } from "../components/TopBar";
import { createAgentSession } from "../runtime/agentSession";

import type { KevinState } from "../components/kevin/KevinAvatar";

export function App() {
  const session = createAgentSession();
  const [view, setView] = createSignal("chat");

  const agentState = createMemo<KevinState>(() => {
    if (session.pendingApprovals().length) return "approval";
    if (!session.busy()) return "ready";
    const latest = session.operations()[session.operations().length - 1];
    return latest && ["opening", "running"].includes(latest.phase) ? "working" : "thinking";
  });

  onMount(() => {
    void session.bootstrap();
  });

  return (
    <div class="studio-shell">
      <TopBar
        view={view}
        setView={setView}
        health={session.health}
        checkHealth={session.checkHealth}
      />
      <main class="conversation-stage">
        <Switch>
          <Match when={view() === "chat"}>
            <div class="operation-layout">
              <ChatThread
                agentState={agentState}
                messages={session.messages}
                busy={session.busy}
                protocol={session.protocol}
                model={session.model}
                permissionMode={session.permissionMode}
                latency={session.latency}
                toolCount={() => session.toolList().length}
                showDetails={session.showDetails}
                pendingApprovals={session.pendingApprovals}
                input={session.input}
                setInput={session.setInput}
                canSend={session.canSend}
                send={session.send}
                decideApproval={session.decideApproval}
                clear={session.clear}
              />
              <OperationStage operations={session.operations} busy={session.busy} runId={session.runId} />
            </div>
          </Match>
          <Match when={view() === "runs"}>
            <RunsView
              runs={session.runs}
              runId={session.runId}
              setRunId={session.setRunId}
              activity={session.activity}
              baseUrl={session.baseUrl}
              token={session.token}
              refreshRuns={session.refreshRuns}
            />
          </Match>
          <Match when={view() === "tasks"}>
            <TasksView
              tasks={session.tasks}
              taskSteps={session.taskSteps}
              selectedTaskId={session.selectedTaskId}
              refreshTasks={session.refreshTasks}
              openTask={session.openTask}
              createTask={session.createTask}
              runTask={session.runTask}
              cancelTask={session.cancelTask}
            />
          </Match>
          <Match when={view() === "settings"}>
            <SettingsView
              baseUrl={session.baseUrl}
              setBaseUrl={session.setBaseUrl}
              token={session.token}
              setToken={session.setToken}
              protocol={session.protocol}
              setProtocol={session.setProtocol}
              model={session.model}
              setModel={session.setModel}
              modelBaseUrl={session.modelBaseUrl}
              setModelBaseUrl={session.setModelBaseUrl}
              apiKey={session.apiKey}
              setApiKey={session.setApiKey}
              enabledTools={session.enabledTools}
              setEnabledTools={session.setEnabledTools}
              permissionMode={session.permissionMode}
              setPermissionMode={session.setPermissionMode}
              systemPrompt={session.systemPrompt}
              setSystemPrompt={session.setSystemPrompt}
              tenantId={session.tenantId}
              setTenantId={session.setTenantId}
              userId={session.userId}
              setUserId={session.setUserId}
              agentId={session.agentId}
              setAgentId={session.setAgentId}
              workspaceId={session.workspaceId}
              setWorkspaceId={session.setWorkspaceId}
              modelProfiles={session.modelProfiles}
              activeProfile={session.activeProfile}
              refreshModelProfiles={session.refreshModelProfiles}
              applyModelProfile={session.applyModelProfile}
              streaming={session.streaming}
              setStreaming={session.setStreaming}
              showDetails={session.showDetails}
              setShowDetails={session.setShowDetails}
            />
          </Match>
        </Switch>
      </main>
    </div>
  );
}
