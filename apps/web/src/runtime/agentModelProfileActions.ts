import type { Setter } from "solid-js";
import type { ModelProfile } from "../types/runtimeTypes";
import type { createApiClient } from "./apiClient";

type ApiClient = ReturnType<typeof createApiClient>;

type AgentModelProfileActionsOptions = {
  api: () => ApiClient;
  modelProfiles: () => ModelProfile[];
  setModelProfiles: Setter<ModelProfile[]>;
  setActiveProfile: Setter<string>;
  setProtocol: Setter<string>;
  setModel: Setter<string>;
  setModelBaseUrl: Setter<string>;
};

export function createAgentModelProfileActions(options: AgentModelProfileActionsOptions) {
  const refreshModelProfiles = async () => {
    const data = await options.api().modelProfiles();
    options.setModelProfiles(data.profiles || []);
    options.setActiveProfile(data.active_profile || "");
  };

  const applyModelProfile = (name: string) => {
    const targetProfile = options.modelProfiles().find((profile) => profile.name === name);
    if (!targetProfile) return;
    options.setActiveProfile(targetProfile.name);
    options.setProtocol(targetProfile.protocol);
    options.setModel(targetProfile.model);
    options.setModelBaseUrl(targetProfile.base_url);
  };

  return { refreshModelProfiles, applyModelProfile };
}
