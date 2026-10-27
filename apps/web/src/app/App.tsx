import {
  Match,
  Show,
  Switch,
  createSignal,
  createMemo,
  createEffect,
  onMount,
} from "solid-js";
import { ChatThread } from "../components/ChatThread";
import { WorkProgress } from "../components/WorkProgress";
import { RunsView } from "../components/RunsView";
import { SettingsView } from "../components/SettingsView";
import { TasksView } from "../components/TasksView";
import { AppSidebar } from "../components/AppSidebar";
import { PanelLeft, PanelRight, WifiOff } from "lucide-solid";
import { createAgentSession } from "../runtime/agentSession";

import type { KevinState } from "../components/kevin/KevinAvatar";

export function App() {
  const session = createAgentSession();
  let contentPanel: HTMLDivElement | undefined;
  const [view, setView] = createSignal("chat");
  const [compactSidebar, setCompactSidebar] = createSignal(false);
  const [showWork, setShowWork] = createSignal(false);

  const agentState = createMemo<KevinState>(() => {
    if (session.pendingApprovals().length) return "approval";
    if (!session.busy()) return "ready";
    const latest = session.operations()[session.operations().length - 1];
    return latest && ["opening", "running"].includes(latest.phase)
      ? "working"
      : "thinking";
  });

  createEffect(() => {
    view();
    contentPanel?.scrollTo(0, 0);
  });

  onMount(() => {
    void session.bootstrap();
  });

  return (
    <div class="kevin-app" classList={{ "compact-sidebar": compactSidebar() }}>
      <AppSidebar
        view={view}
        setView={setView}
        busy={() => session.busy() || session.pendingApprovals().length > 0}
        newConversation={() => {
          session.clear();
          setView("chat");
        }}
      />
      <main class="app-main">
        <header class="app-toolbar">
          <div class="app-toolbar-location">
            <button
              class="icon-button"
              aria-label="切换侧栏"
              aria-expanded={!compactSidebar()}
              onClick={() => setCompactSidebar(!compactSidebar())}
            >
              <PanelLeft size={16} />
            </button>
            <span>
              {
                {
                  chat: "我的工作空间",
                  tasks: "任务",
                  runs: "运行记录",
                  settings: "设置",
                }[view()]
              }
            </span>
          </div>
          <Show when={view() === "chat"}>
            <button
              class="plain-button"
              aria-expanded={showWork()}
              aria-controls="work-panel"
              onClick={() => setShowWork(!showWork())}
            >
              <PanelRight size={16} />
              工作过程{" "}
              <span
                classList={{ "work-live-dot": session.busy() }}
                aria-hidden="true"
              ></span>
            </button>
          </Show>
        </header>
        <Show
          when={
            session.health() === "offline" || session.health() === "degraded"
          }
        >
          <div class="connection-notice" role="status">
            <WifiOff size={15} />
            <span>连接暂时不可用，请检查服务和设置。</span>
            <button class="plain-button" onClick={session.checkHealth}>
              重试
            </button>
          </div>
        </Show>
        <div class="app-content" ref={contentPanel}>
          <Switch>
            <Match when={view() === "chat"}>
              <div
                class="app-conversation"
                classList={{ "with-work": showWork() }}
              >
                <ChatThread
                  agentState={agentState}
                  activity={session.activity}
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
                  cancel={session.cancel}
                  decideApproval={session.decideApproval}
                  openSettings={() => setView("settings")}
                />
                <Show when={showWork()}>
                  <div id="work-panel" class="app-work-panel">
                    <WorkProgress
                      operations={session.operations}
                      busy={session.busy}
                      close={() => setShowWork(false)}
                    />
                  </div>
                </Show>
              </div>
            </Match>
            <Match when={view() === "runs"}>
              <RunsView runs={session.runs} refreshRuns={session.refreshRuns} />
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
                hasApproval={(runId) =>
                  session
                    .pendingApprovals()
                    .some((request) => request.runId === runId)
                }
                openChat={() => setView("chat")}
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
        </div>
      </main>
    </div>
  );
}
