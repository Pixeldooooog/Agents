import { createInterface } from "node:readline";
import { TerminalEventWriter } from "./terminalEventWriter.js";
import { createHostServices } from "../services/hostServices.js";
import { TerminalHostSession } from "./terminalHostSession.js";

const repoRoot = valueAfter("--repo-root") || process.env.KEVIN_REPO_ROOT || process.cwd();
const services = await createHostServices(repoRoot);
const writer = new TerminalEventWriter();
const terminalHostSession = new TerminalHostSession(repoRoot, services, writer);

terminalHostSession.ready();

const lines = createInterface({ input: process.stdin });
for await (const line of lines) {
  if (!line.trim()) continue;
  try {
    const result = await terminalHostSession.handleCommand(JSON.parse(line));
    if (result === "exit") process.exit(0);
  } catch (error) {
    writer.write({ type: "error", message: error instanceof Error ? error.message : String(error) });
  }
}

function valueAfter(flag: string): string | undefined {
  const index = process.argv.indexOf(flag);
  return index >= 0 ? process.argv[index + 1] : undefined;
}
