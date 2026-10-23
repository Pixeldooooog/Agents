import { createSignal, For, Show } from "solid-js";
import type { Accessor } from "solid-js";
import { Play, RefreshCw, Square, Plus } from "lucide-solid";
import type { TaskRecord, TaskStepRecord } from "../types/runtimeTypes";

type Props = {
  tasks: Accessor<TaskRecord[]>;
  taskSteps: Accessor<TaskStepRecord[]>;
  selectedTaskId: Accessor<string>;
  refreshTasks: () => Promise<void>;
  openTask: (taskId: string) => Promise<void>;
  createTask: (message: string, title?: string) => Promise<void>;
  runTask: (taskId: string) => Promise<void>;
  cancelTask: (taskId: string) => Promise<void>;
};

export function TasksView(props: Props) {
  const [title, setTitle] = createSignal("");
  const [message, setMessage] = createSignal("");

  const submit = async () => {
    if (!message().trim()) return;
    await props.createTask(message().trim(), title().trim());
    setTitle("");
    setMessage("");
  };

  return (
    <section class="split-view">
      <article class="panel-card">
        <div class="panel-header">
          <div><p class="eyebrow">Queue</p><h2>Tasks</h2></div>
          <button class="icon-button" title="Refresh tasks" onClick={() => void props.refreshTasks()}><RefreshCw size={15} /></button>
        </div>
        <div class="task-create">
          <input value={title()} onInput={(event) => setTitle(event.currentTarget.value)} placeholder="Task title" />
          <textarea value={message()} onInput={(event) => setMessage(event.currentTarget.value)} placeholder="Task input" />
          <button class="plain-button task-create-button" onClick={() => void submit()}><Plus size={14} /><span>Create task</span></button>
        </div>
        <div class="table-head">
          <span>title</span><span>status</span><span>actions</span>
        </div>
        <div class="table-body">
          <Show when={props.tasks().length > 0} fallback={<p class="trace-empty">No tasks</p>}>
            <For each={props.tasks()}>{(task) => (
              <div class="table-row task-row" classList={{ active: props.selectedTaskId() === task.task_id }}>
                <button class="task-link" onClick={() => void props.openTask(task.task_id)}>{task.title || task.task_id}</button>
                <span class={`status-${task.status}`}>{task.status}</span>
                <div class="task-actions">
                  <button class="icon-button" title="Run task" onClick={() => void props.runTask(task.task_id)}><Play size={14} /></button>
                  <button class="icon-button" title="Cancel task" onClick={() => void props.cancelTask(task.task_id)}><Square size={13} /></button>
                </div>
              </div>
            )}</For>
          </Show>
        </div>
      </article>

      <article class="panel-card">
        <div class="panel-header"><div><p class="eyebrow">Execution</p><h2>Steps</h2></div></div>
        <div class="table-body">
          <Show when={props.taskSteps().length > 0} fallback={<p class="trace-empty">Select a task to inspect steps</p>}>
            <For each={props.taskSteps()}>{(step) => (
              <div class="step-card">
                <strong>{step.step_id}</strong>
                <span class={`status-${step.status}`}>{step.status}</span>
                <Show when={step.output}><pre>{step.output}</pre></Show>
                <Show when={step.error}><pre class="step-error">{step.error}</pre></Show>
              </div>
            )}</For>
          </Show>
        </div>
      </article>
    </section>
  );
}
