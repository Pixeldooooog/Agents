import { RefreshCw } from "lucide-solid";
import { For, Show } from "solid-js";
import type { Accessor, Setter } from "solid-js";
import type { ModelProfile, PermissionMode } from "../types/runtimeTypes";

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
};

export function SettingsView(props: Props) {
  return (
    <section class="settings-grid">
      <div class="settings-column">
        <article class="panel-card">
          <div class="panel-header"><div><p class="eyebrow">Connection</p><h2>Host</h2></div></div>
          <label><span>Host URL</span><input value={props.baseUrl()} onInput={(event) => props.setBaseUrl(event.currentTarget.value)} /></label>
          <label><span>Access Token</span><input type="password" value={props.token()} onInput={(event) => props.setToken(event.currentTarget.value)} /></label>
        </article>

        <article class="panel-card">
          <div class="panel-header"><div><p class="eyebrow">Scope</p><h2>Workspace</h2></div></div>
          <label><span>tenant_id</span><input value={props.tenantId()} onInput={(event) => props.setTenantId(event.currentTarget.value)} /></label>
          <label><span>user_id</span><input value={props.userId()} onInput={(event) => props.setUserId(event.currentTarget.value)} /></label>
          <label><span>agent_id</span><input value={props.agentId()} onInput={(event) => props.setAgentId(event.currentTarget.value)} /></label>
          <label><span>workspace_id</span><input value={props.workspaceId()} onInput={(event) => props.setWorkspaceId(event.currentTarget.value)} /></label>
        </article>
      </div>

      <div class="settings-column settings-column-wide">
        <article class="panel-card">
          <div class="panel-header">
            <div><p class="eyebrow">Model</p><h2>Profiles</h2></div>
            <button class="icon-button" title="Refresh profiles" onClick={() => void props.refreshModelProfiles()}><RefreshCw size={15} /></button>
          </div>
          <label><span>Active profile</span>
            <select value={props.activeProfile()} onInput={(event) => props.applyModelProfile(event.currentTarget.value)}>
              <option value="">manual</option>
              <For each={props.modelProfiles()}>{(profile) => <option value={profile.name}>{profile.name}</option>}</For>
            </select>
          </label>
          <Show when={props.modelProfiles().length > 0}>
            <div class="profile-grid">
              <For each={props.modelProfiles()}>{(profile) => (
                <button class="profile-item" classList={{ active: props.activeProfile() === profile.name }} onClick={() => props.applyModelProfile(profile.name)}>
                  <strong>{profile.name}</strong>
                  <span>{profile.protocol} · {profile.model}</span>
                  <span>{profile.endpoint}</span>
                </button>
              )}</For>
            </div>
          </Show>
          <label><span>Protocol</span><input value={props.protocol()} onInput={(event) => props.setProtocol(event.currentTarget.value)} /></label>
          <label><span>Model</span><input value={props.model()} onInput={(event) => props.setModel(event.currentTarget.value)} /></label>
          <label><span>Base URL</span><input value={props.modelBaseUrl()} onInput={(event) => props.setModelBaseUrl(event.currentTarget.value)} /></label>
          <label><span>API Key</span><input type="password" value={props.apiKey()} onInput={(event) => props.setApiKey(event.currentTarget.value)} /></label>
        </article>

        <article class="panel-card">
          <div class="panel-header"><div><p class="eyebrow">Behavior</p><h2>Agent</h2></div></div>
          <label><span>Enabled Tools</span><input placeholder="empty uses runtime defaults" value={props.enabledTools()} onInput={(event) => props.setEnabledTools(event.currentTarget.value)} /></label>
          <label><span>Permission Mode</span>
            <select value={props.permissionMode()} onInput={(event) => props.setPermissionMode(event.currentTarget.value as PermissionMode)}>
              <option value="ask">ask</option><option value="auto">auto</option><option value="deny">deny</option>
            </select>
          </label>
          <label><span>System Prompt</span><textarea value={props.systemPrompt()} onInput={(event) => props.setSystemPrompt(event.currentTarget.value)} /></label>
        </article>
      </div>
    </section>
  );
}
