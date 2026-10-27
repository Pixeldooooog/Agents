import { RefreshCw, SlidersHorizontal, ShieldCheck, Radio } from "lucide-solid";
import { For, Show, createSignal } from "solid-js";
import type { Accessor, Setter } from "solid-js";
import type { ModelProfile, PermissionMode } from "../types/runtimeTypes";
import { copy } from "../copy";
import { FailureNotice } from "./FailureNotice";

type Props = {
  baseUrl: Accessor<string>;
  setBaseUrl: Setter<string>;
  token: Accessor<string>;
  setToken: Setter<string>;
  protocol: Accessor<string>;
  setProtocol: Setter<string>;
  model: Accessor<string>;
  setModel: Setter<string>;
  modelBaseUrl: Accessor<string>;
  setModelBaseUrl: Setter<string>;
  apiKey: Accessor<string>;
  setApiKey: Setter<string>;
  enabledTools: Accessor<string>;
  setEnabledTools: Setter<string>;
  permissionMode: Accessor<PermissionMode>;
  setPermissionMode: Setter<PermissionMode>;
  systemPrompt: Accessor<string>;
  setSystemPrompt: Setter<string>;
  tenantId: Accessor<string>;
  setTenantId: Setter<string>;
  userId: Accessor<string>;
  setUserId: Setter<string>;
  agentId: Accessor<string>;
  setAgentId: Setter<string>;
  workspaceId: Accessor<string>;
  setWorkspaceId: Setter<string>;
  modelProfiles: Accessor<ModelProfile[]>;
  activeProfile: Accessor<string>;
  refreshModelProfiles: () => Promise<void>;
  applyModelProfile: (name: string) => void;
  streaming: Accessor<boolean>;
  setStreaming: Setter<boolean>;
  showDetails: Accessor<boolean>;
  setShowDetails: Setter<boolean>;
};

export function SettingsView(props: Props) {
  const [refreshing, setRefreshing] = createSignal(false);
  const [failure, setFailure] = createSignal("");
  const refresh = async () => {
    if (refreshing()) return;
    setRefreshing(true);
    setFailure("");
    try {
      await props.refreshModelProfiles();
    } catch (error) {
      setFailure(error instanceof Error ? error.message : String(error));
    } finally {
      setRefreshing(false);
    }
  };
  const permissions: { value: PermissionMode; title: string; hint: string }[] =
    [
      {
        value: "ask",
        title: "先问过我",
        hint: "需要授权的操作，确认后再继续。",
      },
      {
        value: "deny",
        title: "收紧权限",
        hint: "拒绝需要授权的操作；低风险工具仍按策略处理。",
      },
      {
        value: "auto",
        title: "自动授权",
        hint: "在允许的范围内自动执行，仍受工具策略限制。",
      },
    ];
  return (
    <section class="preferences-page">
      <header class="page-intro">
        <p class="eyebrow">让 Kevin 更合你的习惯</p>
        <h1>你的搭档，你的方式。</h1>
        <p>这里的修改用于当前页面后续请求，刷新页面后恢复默认配置。</p>
      </header>
      <Show when={failure()}>
        <FailureNotice detail={failure()} />
      </Show>
      <article class="preference-section">
        <header class="preference-heading">
          <span class="section-symbol">
            <Radio size={19} />
          </span>
          <div>
            <h2>用哪个模型思考</h2>
            <p>选一个已有配置，或者填入你自己的模型。</p>
          </div>
          <button
            class="icon-button"
            disabled={refreshing()}
            aria-label="刷新模型配置"
            title="刷新模型配置"
            onClick={() => void refresh()}
          >
            <RefreshCw size={16} />
          </button>
        </header>
        <div class="preference-fields">
          <label>
            <span>当前配置</span>
            <select
              value={props.activeProfile()}
              onChange={(event) =>
                props.applyModelProfile(event.currentTarget.value)
              }
            >
              <option value="">手动填写 / 服务默认</option>
              <For each={props.modelProfiles()}>
                {(profile) => (
                  <option
                    value={profile.name}
                    disabled={profile.protocol === "gemini"}
                  >
                    {profile.name} · {profile.model}
                    {profile.protocol === "gemini"
                      ? "（暂不支持智能体工具调用）"
                      : ""}
                  </option>
                )}
              </For>
            </select>
          </label>
          <label>
            <span>模型名称</span>
            <input
              placeholder="留空使用服务默认模型"
              value={props.model()}
              onInput={(event) => {
                props.applyModelProfile("");
                props.setModel(event.currentTarget.value);
              }}
            />
          </label>
        </div>
        <details class="preference-disclosure">
          <summary>
            模型连接详情<span>协议、接口地址与密钥</span>
          </summary>
          <div class="preference-fields">
            <label>
              <span>协议</span>
              <select
                value={props.protocol()}
                onChange={(event) => {
                  props.applyModelProfile("");
                  props.setProtocol(event.currentTarget.value);
                }}
              >
                <option value="openai-chat">Chat Completions</option>
                <option value="claude-messages">Messages</option>
                <option value="openai-responses">Responses</option>
                <option value="gemini" disabled>
                  Gemini（暂不支持工具与流式）
                </option>
              </select>
            </label>
            <label>
              <span>接口地址</span>
              <input
                placeholder="留空使用服务默认地址"
                value={props.modelBaseUrl()}
                onInput={(event) => {
                  props.applyModelProfile("");
                  props.setModelBaseUrl(event.currentTarget.value);
                }}
              />
            </label>
            <label class="field-full">
              <span>API 密钥</span>
              <input
                type="password"
                autocomplete="off"
                placeholder="留空使用服务端配置"
                value={props.apiKey()}
                onInput={(event) => props.setApiKey(event.currentTarget.value)}
              />
            </label>
          </div>
        </details>
      </article>
      <article class="preference-section">
        <header class="preference-heading">
          <span class="section-symbol">
            <ShieldCheck size={19} />
          </span>
          <div>
            <h2>怎样把事情交给我</h2>
            <p>你决定需要多少确认；操作过程始终可以查看。</p>
          </div>
        </header>
        <fieldset class="permission-choices">
          <legend class="visually-hidden">权限模式</legend>
          <For each={permissions}>
            {(item) => (
              <label
                class="permission-choice"
                classList={{ selected: props.permissionMode() === item.value }}
              >
                <input
                  type="radio"
                  name="permission-mode"
                  value={item.value}
                  checked={props.permissionMode() === item.value}
                  onChange={() => props.setPermissionMode(item.value)}
                />
                <span>
                  <strong>{item.title}</strong>
                  <small>{item.hint}</small>
                </span>
              </label>
            )}
          </For>
        </fieldset>
        <label class="preference-prompt">
          <span>给 Kevin 的工作偏好</span>
          <textarea
            value={props.systemPrompt()}
            onInput={(event) =>
              props.setSystemPrompt(event.currentTarget.value)
            }
          />
          <small>作为系统提示发送。适合写语言、表达方式和工作习惯。</small>
        </label>
      </article>
      <article class="preference-section">
        <header class="preference-heading">
          <span class="section-symbol">
            <SlidersHorizontal size={19} />
          </span>
          <div>
            <h2>阅读与反馈</h2>
            <p>让每一次对话更顺手。</p>
          </div>
        </header>
        <label class="preference-toggle">
          <span>
            <strong>边生成，边阅读</strong>
            <small>逐步显示模型回复。</small>
          </span>
          <input
            type="checkbox"
            checked={props.streaming()}
            onChange={(event) =>
              props.setStreaming(event.currentTarget.checked)
            }
          />
        </label>
        <label class="preference-toggle">
          <span>
            <strong>显示运行参数</strong>
            <small>在输入区显示协议、用时和工具信息。</small>
          </span>
          <input
            type="checkbox"
            checked={props.showDetails()}
            onChange={(event) =>
              props.setShowDetails(event.currentTarget.checked)
            }
          />
        </label>
      </article>
      <details class="preference-section preference-advanced">
        <summary>
          <strong>高级配置</strong>
          <span>本地服务、工具与工作区标识</span>
        </summary>
        <p class="preference-note">
          连接到不同服务或工作区时使用。一般无需修改。
        </p>
        <div class="preference-fields">
          <label>
            <span>{copy.settings.hostUrl}</span>
            <input
              value={props.baseUrl()}
              onInput={(event) => props.setBaseUrl(event.currentTarget.value)}
            />
          </label>
          <label>
            <span>{copy.settings.accessToken}</span>
            <input
              type="password"
              autocomplete="off"
              value={props.token()}
              onInput={(event) => props.setToken(event.currentTarget.value)}
            />
          </label>
          <label class="field-full">
            <span>{copy.settings.enabledTools}</span>
            <input
              placeholder={copy.settings.enabledToolsPlaceholder}
              value={props.enabledTools()}
              onInput={(event) =>
                props.setEnabledTools(event.currentTarget.value)
              }
            />
          </label>
          <label>
            <span>{copy.settings.tenantId}</span>
            <input
              value={props.tenantId()}
              onInput={(event) => props.setTenantId(event.currentTarget.value)}
            />
          </label>
          <label>
            <span>{copy.settings.userId}</span>
            <input
              value={props.userId()}
              onInput={(event) => props.setUserId(event.currentTarget.value)}
            />
          </label>
          <label>
            <span>{copy.settings.agentId}</span>
            <input
              value={props.agentId()}
              onInput={(event) => props.setAgentId(event.currentTarget.value)}
            />
          </label>
          <label>
            <span>{copy.settings.workspaceId}</span>
            <input
              value={props.workspaceId()}
              onInput={(event) =>
                props.setWorkspaceId(event.currentTarget.value)
              }
            />
          </label>
        </div>
        <a class="settings-design-link" href="?design">
          查看 Kevin 的设计组件 ↗
        </a>
      </details>
      <p class="preferences-footnote">少一点设置，多一点一起做事的时间。</p>
    </section>
  );
}
