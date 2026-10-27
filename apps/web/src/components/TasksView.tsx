import { createEffect, createMemo, createSignal, For, Show, onMount } from "solid-js";
import type { Accessor } from "solid-js";
import { Play, RefreshCw, Square, Plus, X, ArrowUpRight } from "lucide-solid";
import type { TaskRecord, TaskStepRecord } from "../types/runtimeTypes";
import { statusLabel } from "../copy";
import { TaskDetail } from "./TaskDetail";
import { FailureNotice } from "./FailureNotice";

type Props = {
  tasks: Accessor<TaskRecord[]>;
  taskSteps: Accessor<TaskStepRecord[]>;
  selectedTaskId: Accessor<string>;
  refreshTasks: () => Promise<void>;
  openTask: (taskId: string) => Promise<void>;
  createTask: (message: string, title?: string) => Promise<void>;
  runTask: (taskId: string) => Promise<void>;
  cancelTask: (taskId: string) => Promise<void>;
  openChat: () => void;
  hasApproval: (runId: string) => boolean;
};

type TaskFilter = "all" | "pending" | "completed";
const isFinished = (task: TaskRecord) =>
  ["completed", "cancelled", "failed"].includes(task.status);

export function TasksView(props: Props) {
  let draftInput: HTMLTextAreaElement | undefined;
  const [draft, setDraft] = createSignal("");
  const [creating, setCreating] = createSignal(false);
  createEffect(() => {
    if (creating()) draftInput?.focus();
  });
  const [filter, setFilter] = createSignal<TaskFilter>("all");
  const [pending, setPending] = createSignal(new Set<string>());
  const [failure, setFailure] = createSignal("");
  const [opening, setOpening] = createSignal("");
  const selected = createMemo(() =>
    props.tasks().find((task) => task.task_id === props.selectedTaskId()),
  );
  const visible = createMemo(() =>
    props
      .tasks()
      .filter(
        (task) =>
          filter() === "all" ||
          (filter() === "completed" ? isFinished(task) : !isFinished(task)),
      ),
  );
  const filters: { id: TaskFilter; label: string }[] = [
    { id: "all", label: "全部" },
    { id: "pending", label: "待推进" },
    { id: "completed", label: "已结束" },
  ];
  const perform = async (key: string, action: () => Promise<void>) => {
    if (pending().has(key)) return false;
    setPending((current) => new Set([...current, key]));
    setFailure("");
    try {
      await action();
      return true;
    } catch (error) {
      setFailure(error instanceof Error ? error.message : String(error));
      return false;
    } finally {
      setPending((current) => {
        const next = new Set(current);
        next.delete(key);
        return next;
      });
    }
  };
  const submit = async () => {
    if (!draft().trim()) return;
    if (await perform("create", () => props.createTask(draft().trim()))) {
      setDraft("");
      setCreating(false);
      setFilter("all");
    }
  };
  const open = async (id: string) => {
    setOpening(id);
    await perform(`open:${id}`, () => props.openTask(id));
    if (opening() === id) setOpening("");
  };
  onMount(() => {
    void perform("refresh", props.refreshTasks);
  });
  return (
    <section class="tasks-page">
      <header class="page-intro page-intro-actions">
        <div>
          <p class="eyebrow">一件一件，认真做好</p>
          <h1>留给 Kevin 的事。</h1>
          <p>先记下来，准备好后再开始。进度与结果，都留在这里。</p>
        </div>
        <button class="notebook-primary" onClick={() => setCreating(true)}>
          <Plus size={16} />
          记一件事
        </button>
      </header>
      <Show when={failure()}>
        <FailureNotice detail={failure()} />
      </Show>
      <Show when={creating()}>
        <form
          class="task-draft"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          <header>
            <h2>这次，想完成什么？</h2>
            <button
              type="button"
              class="icon-button"
              aria-label="收起新任务"
              onClick={() => setCreating(false)}
            >
              <X size={16} />
            </button>
          </header>
          <label>
            <span>任务目标</span>
            <textarea
              ref={draftInput}
              value={draft()}
              onInput={(event) => setDraft(event.currentTarget.value)}
              placeholder="写下目标，也可以加上背景、限制和你期待的结果。"
            />
          </label>
          <footer>
            <span>先创建，不会立即执行。标题会从目标中生成。</span>
            <button
              class="notebook-primary"
              disabled={!draft().trim() || pending().has("create")}
            >
              {pending().has("create") ? "正在记下…" : "创建任务"}
              <ArrowUpRight size={15} />
            </button>
          </footer>
        </form>
      </Show>
      <div
        class="task-workspace"
        classList={{ "task-workspace-empty": !props.tasks().length }}
      >
        <div class="task-list-pane">
          <div class="task-list-toolbar">
            <div class="notebook-filters" aria-label="筛选任务">
              <For each={filters}>
                {(item) => (
                  <button
                    aria-pressed={filter() === item.id}
                    onClick={() => setFilter(item.id)}
                  >
                    {item.label}
                  </button>
                )}
              </For>
            </div>
            <button
              class="icon-button"
              disabled={pending().has("refresh")}
              aria-label="刷新任务"
              title="刷新任务"
              onClick={() => void perform("refresh", props.refreshTasks)}
            >
              <RefreshCw size={15} />
            </button>
          </div>
          <Show
            when={visible().length}
            fallback={
              <div class="task-list-empty">
                <span aria-hidden="true">＋</span>
                <h2>
                  {props.tasks().length
                    ? "这一页暂时是空的"
                    : "先留下一件小事。"}
                </h2>
                <p>
                  {props.tasks().length
                    ? "换一个筛选，看看其他任务。"
                    : "不用一次想好所有步骤。告诉 Kevin 目标，就可以开始。"}
                </p>
                <Show when={!props.tasks().length}>
                  <button
                    class="plain-button"
                    onClick={() => setCreating(true)}
                  >
                    记下第一件事
                  </button>
                </Show>
              </div>
            }
          >
            <ul class="task-notes">
              <For each={visible()}>
                {(task, index) => (
                  <li
                    classList={{
                      selected: props.selectedTaskId() === task.task_id,
                    }}
                  >
                    <button
                      class="task-note-main"
                      aria-pressed={props.selectedTaskId() === task.task_id}
                      onClick={() => void open(task.task_id)}
                    >
                      <span class="task-note-number">
                        {String(index() + 1).padStart(2, "0")}
                      </span>
                      <span>
                        <strong>{task.title || "未命名任务"}</strong>
                        <Show when={task.input !== task.title}>
                          <small>{task.input}</small>
                        </Show>
                      </span>
                      <span aria-hidden="true">↗</span>
                    </button>
                    <div class="task-note-footer">
                      <span class={`task-status status-${task.status}`}>
                        {pending().has(`run:${task.task_id}`)
                          ? "执行中"
                          : statusLabel(task.status)}
                      </span>
                      <span class="task-note-actions">
                        <Show
                          when={
                            task.status === "running" ||
                            pending().has(`run:${task.task_id}`)
                          }
                          fallback={
                            <Show when={task.status !== "waiting_approval"}>
                              <button
                                aria-label={`开始：${task.title}`}
                                onClick={() =>
                                  void perform(`run:${task.task_id}`, () =>
                                    props.runTask(task.task_id),
                                  )
                                }
                              >
                                <Play size={13} />
                                {isFinished(task) ? "再做一次" : "开始"}
                              </button>
                            </Show>
                          }
                        >
                          <button
                            disabled={pending().has(`cancel:${task.task_id}`)}
                            onClick={() =>
                              void perform(`cancel:${task.task_id}`, () =>
                                props.cancelTask(task.task_id),
                              )
                            }
                          >
                            <Square size={12} />
                            停止
                          </button>
                        </Show>
                      </span>
                    </div>
                  </li>
                )}
              </For>
            </ul>
          </Show>
        </div>
        <Show when={props.tasks().length}>
          <TaskDetail
            task={selected()}
            steps={props.taskSteps()}
            loading={!!opening()}
            canReviewApproval={props.hasApproval(
              props.taskSteps()[props.taskSteps().length - 1]?.run_id || "",
            )}
            openChat={props.openChat}
          />
        </Show>
      </div>
    </section>
  );
}
