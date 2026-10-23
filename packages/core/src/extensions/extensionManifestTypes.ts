export type ExtensionKind = "skill" | "plugin";
export type ExtensionManifestFormat = "skill-md" | "plugin-json";

export type ExtensionManifest = {
  kind: ExtensionKind;
  format: ExtensionManifestFormat;
  name: string;
  version: string;
  description: string;
  when_to_use: string;
  tools: string[];
  allowed_tools: string[];
  disallowed_tools: string[];
  prompt_fragments: string[];
  instructions: string[];
  paths: string[];
  context: string;
  model: string;
  effort: string;
  agent: string;
  user_invocable: boolean;
  disable_model_invocation: boolean;
  metadata: Record<string, unknown>;
  rootPath: string;
  manifestPath: string;
  invalid?: boolean;
  error?: string;
};
