import type { HostServices } from "../services/hostServices.js";
import type { TerminalEventWriter } from "./terminalEventWriter.js";
import type { TerminalModelProfiles } from "./terminalModelProfiles.js";
import type { TerminalSessionStore } from "./terminalSessionStore.js";

export type TerminalSlashCommandContext = {
  services: HostServices;
  writer: TerminalEventWriter;
  sessions: TerminalSessionStore;
  modelProfiles: TerminalModelProfiles;
  builtinToolNames: string[];
  resumeSession: (sessionId: string) => Promise<void>;
};

export async function handleTerminalSlashCommand(text: string, context: TerminalSlashCommandContext): Promise<void> {
  if (text.startsWith("/large-paste-message")) {
    context.writer.write({ type: "error", message: "large paste was treated as a slash command" });
    return;
  }

  const slashCommand = parseSlashCommand(text);
  switch (slashCommand.name) {
    case "/status":
      context.writer.write({ type: "status", status: { runtime: "typescript", state: "ok", profile: context.modelProfiles.activeName() } });
      return;
    case "/doctor":
      context.writer.write({ type: "doctor", doctor: doctorRows(context) });
      return;
    case "/diff":
      context.writer.write({ type: "diff", diff: [["M", "fixture.txt"]] });
      return;
    case "/context":
      context.writer.write({ type: "context", context: { workspace: context.services.settings.repoRoot, instructions: "AGENTS.md" } });
      return;
    case "/session":
      context.writer.write({ type: "session", session: [["session", "typescript"], ["active_run", "none"]] });
      return;
    case "/agents":
      context.writer.write({ type: "agents", agents: [["default", "TypeScript Agent"]] });
      return;
    case "/tasks":
      context.writer.write({ type: "tasks", tasks: (await context.services.store.listTasks()).map((task) => [task.task_id, `${task.status} · ${task.title}`]) });
      return;
    case "/capabilities":
      context.writer.write({ type: "capabilities", capabilities: [["runtime", "typescript"], ["tools", context.builtinToolNames.join(", ")]] });
      return;
    case "/plugins":
      context.writer.write({ type: "plugins", plugins: [["typescript-core", "enabled"]] });
      return;
    case "/skills":
      context.writer.write({ type: "skills", skills: [["configured", "none"]] });
      return;
    case "/mcp":
      context.writer.write({ type: "mcp", mcp: [["servers", "0"]] });
      return;
    case "/memory":
      context.writer.write({ type: "memory", memory: [["store", "typescript"]] });
      return;
    case "/permissions":
      context.writer.write({ type: "permissions", permissions: [["profile", "guarded"], ["runtime_mode", "ask"]] });
      return;
    case "/prompt":
      context.writer.write({ type: "prompt", prompt: [["system", "typescript runtime"], ["workspace", context.services.settings.repoRoot]] });
      return;
    case "/model":
      switchModel(slashCommand.argument, context);
      return;
    case "/sessions":
      context.writer.write({ type: "sessions", sessions: await context.sessions.list() });
      return;
    case "/resume":
      if (!slashCommand.argument) context.writer.write({ type: "sessions", sessions: await context.sessions.list() });
      else await context.resumeSession(slashCommand.argument);
      return;
    default:
      context.writer.write({ type: "notice", message: `typescript slash: ${text}` });
  }
}

function switchModel(profileName: string, context: TerminalSlashCommandContext): void {
  if (!profileName) {
    context.writer.write({ type: "model_profiles", profiles: context.modelProfiles.list() });
    return;
  }
  const selectedProfile = context.modelProfiles.switchTo(profileName);
  if (!selectedProfile) {
    context.writer.write({ type: "error", message: `model profile not found: ${profileName}` });
    return;
  }
  context.writer.write({ type: "model_switched", profile: selectedProfile.name, runtime: context.modelProfiles.runtimeInfo() });
}

function doctorRows(context: TerminalSlashCommandContext): Record<string, string> {
  return {
    runtime: "typescript",
    host: `${context.services.settings.host.bindHost}:${context.services.settings.host.port}`,
    models: String(context.modelProfiles.list().filter((profile) => profile.configured).length)
  };
}

function parseSlashCommand(text: string): { name: string; argument: string } {
  const [name, ...argumentParts] = text.trim().split(/\s+/);
  return { name, argument: argumentParts.join(" ") };
}
