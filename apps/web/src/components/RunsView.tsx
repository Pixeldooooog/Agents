import { RefreshCw, Search } from "lucide-solid";
import type { Accessor } from "solid-js";
import { For, Show, createMemo, createSignal, onMount } from "solid-js";
import type { RuntimeRun } from "../types/runtimeTypes";
import { RunInspector } from "./RunInspector";
import { FailureNotice } from "./FailureNotice";
import { presentRun, runDate } from "../runtime/runPresentation";
import { statusLabel } from "../copy";

type Props = { runs: Accessor<RuntimeRun[]>; refreshRuns: () => Promise<void> };

export function RunsView(props: Props) {
  let journalPanel: HTMLElement | undefined;
  const [selectedId, setSelectedId] = createSignal("");
  const [search, setSearch] = createSignal("");
  const [refreshing, setRefreshing] = createSignal(false);
  const [failure, setFailure] = createSignal("");
  const records = createMemo(() =>
    props.runs().map((run) => ({ run, summary: presentRun(run).summary })),
  );
  const filtered = createMemo(() => {
    const query = search().trim().toLowerCase();
    return records().filter(
      ({ run, summary }) =>
        !query ||
        `${run.run_id} ${summary} ${statusLabel(run.status)}`
          .toLowerCase()
          .includes(query),
    );
  });
  const selected = createMemo(() =>
    props.runs().find((run) => run.run_id === selectedId()),
  );
  const selectRun = (runId: string) => {
    setSelectedId(runId);
    if (window.matchMedia("(max-width: 960px)").matches)
      queueMicrotask(() => {
        journalPanel?.focus({ preventScroll: true });
        journalPanel?.scrollIntoView({ block: "start" });
      });
  };
  const refresh = async () => {
    if (refreshing()) return;
    setRefreshing(true);
    setFailure("");
    try {
      await props.refreshRuns();
    } catch (error) {
      setFailure(error instanceof Error ? error.message : String(error));
    } finally {
      setRefreshing(false);
    }
  };
  onMount(() => {
    void refresh();
  });
  return (
    <section class="runs-page">
      <header class="page-intro page-intro-actions">
        <div>
          <p class="eyebrow">每一次认真，都有记录</p>
          <h1>一起做过的事。</h1>
          <p>
            回看结果，也看清过程。这里展示最近加载的 {props.runs().length}{" "}
            条运行。
          </p>
        </div>
        <button
          class="plain-button"
          disabled={refreshing()}
          onClick={() => void refresh()}
        >
          <RefreshCw size={15} />
          {refreshing() ? "正在更新…" : "刷新记录"}
        </button>
      </header>
      <Show when={failure()}>
        <FailureNotice detail={failure()} />
      </Show>
      <div class="run-archive">
        <div class="run-index">
          <label class="run-search">
            <Search size={16} />
            <input
              type="search"
              aria-label="搜索已加载的运行"
              placeholder="搜索结果摘要、状态或编号"
              value={search()}
              onInput={(event) => setSearch(event.currentTarget.value)}
            />
          </label>
          <Show
            when={filtered().length}
            fallback={
              <div class="archive-empty">
                <h2>{search() ? "没有找到这条记录" : "故事才刚开始。"}</h2>
                <p>
                  {search()
                    ? "试试其他关键词，或刷新最近的记录。"
                    : "和 Kevin 完成一次对话后，再来这里回看。"}
                </p>
              </div>
            }
          >
            <ol class="run-index-list">
              <For each={filtered()}>
                {({ run, summary }) => (
                  <li>
                    <button
                      aria-pressed={selectedId() === run.run_id}
                      onClick={() => selectRun(run.run_id)}
                    >
                      <span class="run-index-meta">
                        <time>{runDate(run.created_at)}</time>
                        <span class={`status-${run.status}`}>
                          {statusLabel(run.status)}
                        </span>
                      </span>
                      <strong>{summary}</strong>
                      <span class="run-index-id">
                        #{run.run_id.replace(/^run_/, "").slice(0, 8)}
                        <span aria-hidden="true">↗</span>
                      </span>
                    </button>
                  </li>
                )}
              </For>
            </ol>
          </Show>
        </div>
        <RunInspector
          run={selected()}
          ref={(element) => {
            journalPanel = element;
          }}
        />
      </div>
    </section>
  );
}
