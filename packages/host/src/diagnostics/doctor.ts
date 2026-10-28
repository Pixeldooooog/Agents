import { buildModelProfiles, builtinToolNames, loadSettings } from "@pixeldooooog/otto-core";

const settings = await loadSettings(valueAfter("--repo-root") || process.cwd());
const profiles = buildModelProfiles(settings);
const configured = profiles.filter((profile) => profile.configured).map((profile) => profile.name).join(", ") || "none";

console.log(JSON.stringify({
  runtime: "typescript",
  host: `${settings.host.bindHost}:${settings.host.port}`,
  models: configured,
  tools: builtinToolNames.length,
  state: settings.agent.statePath
}, null, 2));

function valueAfter(flag: string): string | undefined {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : undefined;
}
