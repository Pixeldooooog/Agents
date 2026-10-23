import { publicCommand } from "../commands/commandDiscovery.js";

export function sdkCommandPayload(command: ReturnType<typeof publicCommand>): Record<string, unknown> {
  return {
    ...command,
    name: command.name.replace(/^\//, ""),
    aliases: command.aliases.map((alias) => alias.replace(/^\//, ""))
  };
}
