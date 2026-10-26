import { createSignal, For, Show } from "solid-js";
import type { Accessor } from "solid-js";
import { Play, RefreshCw, Square, Plus } from "lucide-solid";
import type { TaskRecord, TaskStepRecord } from "../types/runtimeTypes";
import { copy, statusLabel } from "../copy";

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
          <div><p class="eyebrow">{copy.tasks.eyebrow}</p><h2>{copy.tasks.title}</h2></div>
          <button class="icon-button" title={copy.tasks.refresh} aria-label={copy.tasks.refresh} onClick={() => void props.refreshTasks()}><RefreshCw size={15} /></button>
        </div>
        <div class="task-create">
          <input value={title()} onInput={(event) => setTitle(event.currentTarget.value)} placeholder={copy.tasks.titlePlaceholder} />
          <textarea value={message()} onInput={(event) => setMessage(event.currentTarget.value)} placeholder={copy.tasks.inputPlaceholder} />
          <button class="plain-button task-create-button" onClick={() => void submit()}><Plus size={14} /><span>{copy.tasks.create}</span></button>
        </div>
        <div class="table-head">
          <span>{copy.tasks.columnTitle}</span><span>{copy.tasks.columnStatus}</span><span>{copy.tasks.columnActions}</span>
        </div>
        <div class="table-body">
          <Show when={props.tasks().length > 0} fallback={<p class="trace-empty">{copy.tasks.empty}</p>}>
            <For each={props.tasks()}>{(task) => (
              <div class="table-row task-row" classList={{ active: props.selectedTaskId() === task.task_id }}>
                <button class="task-link" onClick={() => void props.openTask(task.task_id)}>{task.title || task.task_id}</button>
                <span class={`status-${task.status}`}>{statusLabel(task.status)}</span>
                <div class="task-actions">
                  <button class="icon-button" title={copy.tasks.run} aria-label={copy.tasks.run} onClick={() => void props.runTask(task.task_id)}><Play size={14} /></button>
                  <button class="icon-button" title={copy.tasks.cancel} aria-label={copy.tasks.cancel} onClick={() => void props.cancelTask(task.task_id)}><Square size={13} /></button>
                </div>
              </div>
            )}</For>
          </Show>
        </div>
      </article>

      <article class="panel-card">
        <div class="panel-header"><div><p class="eyebrow">{copy.tasks.stepsEyebrow}</p><h2>{copy.tasks.stepsTitle}</h2></div></div>
        <div class="table-body">
          <Show when={props.taskSteps().length > 0} fallback={<p class="trace-empty">{copy.tasks.stepsEmpty}</p>}>
            <For each={props.taskSteps()}>{(step) => (
              <div class="step-card">
                <strong>{step.step_id}</strong>
                <span class={`status-${step.status}`}>{statusLabel(step.status)}</span>
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
