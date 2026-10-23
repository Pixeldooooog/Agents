export type CommandRecord = {
  name: string;
  description: string;
  argumentHint: string;
  aliases: string[];
  source: "workspace";
  category: string;
  path: string;
  absolutePath: string;
};

export type CommandFrontmatter = {
  metadata: Record<string, string>;
  content: string;
};

export type PublicCommandRecord = Omit<CommandRecord, "absolutePath">;
