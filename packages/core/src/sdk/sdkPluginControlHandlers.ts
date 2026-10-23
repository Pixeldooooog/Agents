import { discoverCommands, publicCommand } from "../commands/commandDiscovery.js";
import { discoverPlugins, discoverSkills, publicExtensionPayload } from "../extensions/extensionManifests.js";
import type { ToolExecutionContext } from "../tools/toolContracts.js";
import type { ExtensionManifest } from "../extensions/extensionManifestTypes.js";
import { sdkCommandPayload } from "./sdkCommandRecords.js";
import { mcpStatusControlResponsePayload } from "./sdkMcpControlHandlers.js";
import type { SdkControlRequestHandlerContext } from "./sdkProtocolRunner.js";

export async function reloadPluginsControlResponsePayload(
  context: SdkControlRequestHandlerContext
): Promise<Record<string, unknown>> {
  const extensionContext = extensionToolContext(context);
  const [commands, skills, plugins, mcp] = await Promise.all([
    discoverCommands(context.client.settings.repoRoot),
    discoverSkills(extensionContext),
    discoverPlugins(extensionContext),
    mcpStatusControlResponsePayload(context)
  ]);
  const manifests = [...skills, ...plugins];
  const invalidManifests = manifests.filter((manifest) => manifest.invalid);
  return {
    commands: commands.map((command) => sdkCommandPayload(publicCommand(command))),
    skills: skills.map((skill) => publicExtensionPayload(extensionContext, skill)),
    agents: agentPayloadsFromManifests(extensionContext, manifests),
    plugins: plugins.map((plugin) => publicExtensionPayload(extensionContext, plugin)),
    mcpServers: Array.isArray(mcp.servers) ? mcp.servers : [],
    mcp,
    errorCount: invalidManifests.length,
    error_count: invalidManifests.length,
    errors: invalidManifests.map((manifest) => extensionErrorPayload(extensionContext, manifest))
  };
}

function extensionToolContext(context: SdkControlRequestHandlerContext): ToolExecutionContext {
  return {
    repoRoot: context.client.settings.repoRoot,
    settings: context.client.settings
  };
}

function agentPayloadsFromManifests(
  context: ToolExecutionContext,
  manifests: ExtensionManifest[]
): Array<Record<string, unknown>> {
  return manifests
    .filter((manifest) => manifest.agent && !manifest.invalid)
    .map((manifest) => ({
      name: manifest.agent,
      source: manifest.kind,
      extension: manifest.name,
      description: manifest.description,
      model: manifest.model,
      path: publicExtensionPayload(context, manifest).path
    }));
}

function extensionErrorPayload(
  context: ToolExecutionContext,
  manifest: ExtensionManifest
): Record<string, unknown> {
  const payload = publicExtensionPayload(context, manifest);
  return {
    kind: manifest.kind,
    name: manifest.name,
    path: payload.path,
    manifestPath: payload.manifest_path,
    error: manifest.error || "invalid extension manifest"
  };
}
