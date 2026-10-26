import type { ModelProfile } from "@kevin/core";

export type TerminalRuntimeInfo = {
  protocol: string;
  model: string;
  model_profile: string;
  endpoint: string;
};

export class TerminalModelProfiles {
  private selectedProfileName: string;

  constructor(private readonly profiles: ModelProfile[]) {
    this.selectedProfileName = profiles.find((profile) => profile.configured)?.name || profiles[0]?.name || "default";
  }

  activeName(): string {
    return this.selectedProfileName;
  }

  list() {
    return this.profiles.map((profile) => ({ ...profile, active: profile.name === this.selectedProfileName }));
  }

  runtimeInfo(): TerminalRuntimeInfo {
    return runtimeInfoFor(this.activeProfile(), this.selectedProfileName);
  }

  switchTo(profileName: string): ModelProfile | undefined {
    const targetProfile = this.profiles.find((profile) => profile.name === profileName) || this.profiles[0];
    if (!targetProfile) return undefined;
    this.selectedProfileName = targetProfile.name;
    return targetProfile;
  }

  private activeProfile(): ModelProfile | undefined {
    return this.profiles.find((profile) => profile.name === this.selectedProfileName) || this.profiles[0];
  }
}

export function runtimeInfoFor(profile: ModelProfile | undefined, fallbackProfileName: string): TerminalRuntimeInfo {
  return {
    protocol: profile?.protocol || "typescript",
    model: profile?.model || "unconfigured",
    model_profile: profile?.name || fallbackProfileName,
    endpoint: profile?.endpoint || ""
  };
}
