import { RefreshCw } from "lucide-solid";
import { For, Show } from "solid-js";
import type { Accessor, Setter } from "solid-js";
import type { ModelProfile, PermissionMode } from "../types/runtimeTypes";
import { copy } from "../copy";

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
  return (
    <section class="settings-grid">
      <div class="settings-column">
        <article class="panel-card">
          <div class="panel-header"><div><p class="eyebrow">{copy.settings.connectionEyebrow}</p><h2>{copy.settings.connectionTitle}</h2></div></div>
          <label><span>{copy.settings.hostUrl}</span><input value={props.baseUrl()} onInput={(event) => props.setBaseUrl(event.currentTarget.value)} /></label>
          <label><span>{copy.settings.accessToken}</span><input type="password" value={props.token()} onInput={(event) => props.setToken(event.currentTarget.value)} /></label>
        </article>

        <article class="panel-card">
          <div class="panel-header"><div><p class="eyebrow">{copy.settings.scopeEyebrow}</p><h2>{copy.settings.scopeTitle}</h2></div></div>
          <label><span>{copy.settings.tenantId}</span><input value={props.tenantId()} onInput={(event) => props.setTenantId(event.currentTarget.value)} /></label>
          <label><span>{copy.settings.userId}</span><input value={props.userId()} onInput={(event) => props.setUserId(event.currentTarget.value)} /></label>
          <label><span>{copy.settings.agentId}</span><input value={props.agentId()} onInput={(event) => props.setAgentId(event.currentTarget.value)} /></label>
          <label><span>{copy.settings.workspaceId}</span><input value={props.workspaceId()} onInput={(event) => props.setWorkspaceId(event.currentTarget.value)} /></label>
        </article>
      </div>

      <div class="settings-column settings-column-wide">
        <article class="panel-card">
          <div class="panel-header">
            <div><p class="eyebrow">{copy.settings.modelEyebrow}</p><h2>{copy.settings.modelTitle}</h2></div>
            <button class="icon-button" title={copy.settings.refreshProfiles} aria-label={copy.settings.refreshProfiles} onClick={() => void props.refreshModelProfiles()}><RefreshCw size={15} /></button>
          </div>
          <label><span>{copy.settings.activeProfile}</span>
            <select value={props.activeProfile()} onInput={(event) => props.applyModelProfile(event.currentTarget.value)}>
              <option value="">{copy.settings.manualProfile}</option>
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
          <label><span>{copy.settings.protocol}</span><input value={props.protocol()} onInput={(event) => props.setProtocol(event.currentTarget.value)} /></label>
          <label><span>{copy.settings.model}</span><input value={props.model()} onInput={(event) => props.setModel(event.currentTarget.value)} /></label>
          <label><span>{copy.settings.baseUrl}</span><input value={props.modelBaseUrl()} onInput={(event) => props.setModelBaseUrl(event.currentTarget.value)} /></label>
          <label><span>{copy.settings.apiKey}</span><input type="password" value={props.apiKey()} onInput={(event) => props.setApiKey(event.currentTarget.value)} /></label>
        </article>

        <article class="panel-card">
          <div class="panel-header"><div><p class="eyebrow">{copy.settings.behaviorEyebrow}</p><h2>{copy.settings.behaviorTitle}</h2></div></div>
          <label><span>{copy.settings.enabledTools}</span><input placeholder={copy.settings.enabledToolsPlaceholder} value={props.enabledTools()} onInput={(event) => props.setEnabledTools(event.currentTarget.value)} /></label>
          <label><span>{copy.settings.permissionMode}</span>
            <select value={props.permissionMode()} onInput={(event) => props.setPermissionMode(event.currentTarget.value as PermissionMode)}>
              <option value="ask">{copy.settings.permissionModes.ask}</option><option value="auto">{copy.settings.permissionModes.auto}</option><option value="deny">{copy.settings.permissionModes.deny}</option>
            </select>
          </label>
          <label><span>{copy.settings.systemPrompt}</span><textarea value={props.systemPrompt()} onInput={(event) => props.setSystemPrompt(event.currentTarget.value)} /></label>
        </article>

        <article class="panel-card">
          <div class="panel-header"><div><p class="eyebrow">{copy.settings.developerEyebrow}</p><h2>{copy.settings.developerTitle}</h2></div></div>
          <label class="toggle-row">
            <input type="checkbox" checked={props.streaming()} onChange={(event) => props.setStreaming(event.currentTarget.checked)} />
            <span><strong>{copy.settings.streaming}</strong><small>{copy.settings.streamingHint}</small></span>
          </label>
          <label class="toggle-row">
            <input type="checkbox" checked={props.showDetails()} onChange={(event) => props.setShowDetails(event.currentTarget.checked)} />
            <span><strong>{copy.settings.showDetails}</strong><small>{copy.settings.showDetailsHint}</small></span>
          </label>
          <a class="plain-button settings-link" href="?design">{copy.settings.designStudio}</a>
        </article>
      </div>
    </section>
  );
}
